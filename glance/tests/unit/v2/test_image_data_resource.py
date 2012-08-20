# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import StringIO

import webob

import glance.api.v2.image_data
from glance.common import utils
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class TestImagesController(base.StoreClearingUnitTest):
    def setUp(self):
        super(TestImagesController, self).setUp()

        self.config(verbose=True, debug=True)
        self.notifier = unit_test_utils.FakeNotifier()
        self.controller = glance.api.v2.image_data.ImageDataController(
                db_api=unit_test_utils.FakeDB(),
                store_api=unit_test_utils.FakeStoreAPI(),
                policy_enforcer=unit_test_utils.FakePolicyEnforcer(),
                notifier=self.notifier)

    def test_download(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.download(request, unit_test_utils.UUID1)
        self.assertEqual(set(['data', 'meta']), set(output.keys()))
        self.assertEqual(3, output['meta']['size'])
        self.assertEqual('XXX', output['data'])

    def test_download_no_data(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.download,
                          request, unit_test_utils.UUID2)

    def test_download_non_existent_image(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.download,
                          request, utils.generate_uuid())

    def test_upload_download(self):
        request = unit_test_utils.get_fake_request()
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        output = self.controller.download(request, unit_test_utils.UUID2)
        self.assertEqual(set(['data', 'meta']), set(output.keys()))
        self.assertEqual(4, output['meta']['size'])
        self.assertEqual('YYYY', output['data'])
        output_log = self.notifier.get_log()
        expected_log = {'notification_type': "INFO",
                        'event_type': "image.upload",
                        'payload': output['meta'],
        }
        self.assertEqual(output_log, expected_log)

    def test_upload_non_existent_image(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.upload,
                          request, utils.generate_uuid(), 'YYYY', 4)

    def test_upload_data_exists(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPConflict, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)

    def test_upload_storage_full(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                         self.controller.upload,
                         request, unit_test_utils.UUID2, 'YYYYYYY', 7)

    def test_upload_storage_forbidden(self):
        request = unit_test_utils.get_fake_request(user=unit_test_utils.USER2)
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.upload,
                          request, unit_test_utils.UUID2, 'YY', 2)

    def test_upload_storage_write_denied(self):
        request = unit_test_utils.get_fake_request(user=unit_test_utils.USER3)
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                         self.controller.upload,
                         request, unit_test_utils.UUID2, 'YY', 2)

    def test_upload_download_no_size(self):
        request = unit_test_utils.get_fake_request()
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', None)
        output = self.controller.download(request, unit_test_utils.UUID2)
        self.assertEqual(set(['data', 'meta']), set(output.keys()))
        self.assertEqual(4, output['meta']['size'])
        self.assertEqual('YYYY', output['data'])


class TestImageDataControllerPolicies(base.IsolatedUnitTest):

    def setUp(self):
        super(TestImageDataControllerPolicies, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.controller = glance.api.v2.image_data.ImageDataController(
                                                self.db,
                                                policy_enforcer=self.policy)

    def test_download_unauthorized(self):
        rules = {"download_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.download,
                          request, image_id=unit_test_utils.UUID2)


class TestImageDataDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageDataDeserializer, self).setUp()
        self.deserializer = glance.api.v2.image_data.RequestDeserializer()

    def test_upload(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        request.body = 'YYY'
        request.headers['Content-Length'] = 3
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(data.getvalue(), 'YYY')
        expected = {'size': 3}
        self.assertEqual(expected, output)

    def test_upload_chunked(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        # If we use body_file, webob assumes we want to do a chunked upload,
        # ignoring the Content-Length header
        request.body_file = StringIO.StringIO('YYY')
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(data.getvalue(), 'YYY')
        expected = {'size': None}
        self.assertEqual(expected, output)

    def test_upload_chunked_with_content_length(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        request.body_file = StringIO.StringIO('YYY')
        # The deserializer shouldn't care if the Content-Length is
        # set when the user is attempting to send chunked data.
        request.headers['Content-Length'] = 3
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(data.getvalue(), 'YYY')
        expected = {'size': 3}
        self.assertEqual(expected, output)

    def test_upload_with_incorrect_content_length(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        # The deserializer shouldn't care if the Content-Length and
        # actual request body length differ. That job is left up
        # to the controller
        request.body = 'YYY'
        request.headers['Content-Length'] = 4
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(data.getvalue(), 'YYY')
        expected = {'size': 4}
        self.assertEqual(expected, output)

    def test_upload_wrong_content_type(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/json'
        request.body = 'YYYYY'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
            self.deserializer.upload, request)


class TestImageDataSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageDataSerializer, self).setUp()
        self.serializer = glance.api.v2.image_data.ResponseSerializer(
            notifier=unit_test_utils.FakeNotifier())

    def test_download(self):
        request = webob.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        fixture = {
            'data': 'ZZZ',
            'meta': {'size': 3, 'id': 'asdf', 'checksum': None}
        }
        self.serializer.download(response, fixture)
        self.assertEqual('ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertFalse('Content-MD5' in response.headers)
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])

    def test_download_with_checksum(self):
        request = webob.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        checksum = '0745064918b49693cca64d6b6a13d28a'
        fixture = {
            'data': 'ZZZ',
            'meta': {'size': 3, 'id': 'asdf', 'checksum': checksum}
        }
        self.serializer.download(response, fixture)
        self.assertEqual('ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertEqual(checksum, response.headers['Content-MD5'])
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])

    def test_upload(self):
        request = webob.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        self.serializer.upload(response, {})
        self.assertEqual(201, response.status_int)
        self.assertEqual('0', response.headers['Content-Length'])
