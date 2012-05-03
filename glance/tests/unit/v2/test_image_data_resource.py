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

import unittest

import webob

import glance.api.v2.image_data
from glance.common import utils
import glance.tests.unit.utils as test_utils
import glance.tests.utils


class TestImagesController(unittest.TestCase):
    def setUp(self):
        super(TestImagesController, self).setUp()

        conf = glance.tests.utils.TestConfigOpts({
                'verbose': True,
                'debug': True,
                })
        self.controller = glance.api.v2.image_data.ImageDataController(conf,
                db_api=test_utils.FakeDB(),
                store_api=test_utils.FakeStoreAPI())

    def test_download(self):
        request = test_utils.FakeRequest()
        output = self.controller.download(request, test_utils.UUID1)
        expected = {'data': 'XXX', 'size': 3}
        self.assertEqual(expected, output)

    def test_download_no_data(self):
        request = test_utils.FakeRequest()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.download,
                          request, test_utils.UUID2)

    def test_download_non_existant_image(self):
        request = test_utils.FakeRequest()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.download,
                          request, utils.generate_uuid())

    def test_upload_download(self):
        request = test_utils.FakeRequest()
        self.controller.upload(request, test_utils.UUID2, 'YYYY')
        output = self.controller.download(request, test_utils.UUID2)
        expected = {'data': 'YYYY', 'size': 4}
        self.assertEqual(expected, output)

    def test_upload_non_existant_image(self):
        request = test_utils.FakeRequest()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.upload,
                          request, utils.generate_uuid(), 'YYYY')


class TestImageDataDeserializer(unittest.TestCase):
    def setUp(self):
        self.deserializer = glance.api.v2.image_data.RequestDeserializer()

    def test_upload(self):
        request = test_utils.FakeRequest()
        request.body = 'YYY'
        output = self.deserializer.upload(request)
        expected = {'data': 'YYY'}
        self.assertEqual(expected, output)


class TestImageDataSerializer(unittest.TestCase):
    def setUp(self):
        self.serializer = glance.api.v2.image_data.ResponseSerializer()

    def test_download(self):
        response = webob.Response()
        self.serializer.download(response, {'data': 'ZZZ', 'size': 3})
        self.assertEqual('ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])
