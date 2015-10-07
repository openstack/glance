# Copyright 2012 OpenStack Foundation.
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
import uuid

import glance_store
import mock
import six
import webob

import glance.api.policy
import glance.api.v2.image_data
from glance.common import exception
from glance.common import wsgi
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class Raise(object):
    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *args, **kwargs):
        raise self.exc


class FakeImage(object):
    def __init__(self, image_id=None, data=None, checksum=None, size=0,
                 virtual_size=0, locations=None, container_format='bear',
                 disk_format='rawr', status=None):
        self.image_id = image_id
        self.data = data
        self.checksum = checksum
        self.size = size
        self.virtual_size = virtual_size
        self.locations = locations
        self.container_format = container_format
        self.disk_format = disk_format
        self._status = status

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if isinstance(self._status, BaseException):
            raise self._status
        else:
            self._status = value

    def get_data(self, *args, **kwargs):
        return self.data

    def set_data(self, data, size=None):
        self.data = ''.join(data)
        self.size = size
        self.status = 'modified-by-fake'


class FakeImageRepo(object):
    def __init__(self, result=None):
        self.result = result

    def get(self, image_id):
        if isinstance(self.result, BaseException):
            raise self.result
        else:
            return self.result

    def save(self, image, from_state=None):
        self.saved_image = image


class FakeGateway(object):
    def __init__(self, repo):
        self.repo = repo

    def get_repo(self, context):
        return self.repo


class TestImagesController(base.StoreClearingUnitTest):
    def setUp(self):
        super(TestImagesController, self).setUp()

        self.config(verbose=True, debug=True)
        self.image_repo = FakeImageRepo()
        self.gateway = FakeGateway(self.image_repo)
        self.controller = glance.api.v2.image_data.ImageDataController(
            gateway=self.gateway)

    def test_download(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd',
                          locations=[{'url': 'http://example.com/image',
                                      'metadata': {}, 'status': 'active'}])
        self.image_repo.result = image
        image = self.controller.download(request, unit_test_utils.UUID1)
        self.assertEqual('abcd', image.image_id)

    def test_download_deactivated(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd',
                          status='deactivated',
                          locations=[{'url': 'http://example.com/image',
                                      'metadata': {}, 'status': 'active'}])
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.download,
                          request, str(uuid.uuid4()))

    def test_download_no_location(self):
        # NOTE(mclaren): NoContent will be raised by the ResponseSerializer
        # That's tested below.
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = FakeImage('abcd')
        image = self.controller.download(request, unit_test_utils.UUID2)
        self.assertEqual('abcd', image.image_id)

    def test_download_non_existent_image(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.NotFound()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.download,
                          request, str(uuid.uuid4()))

    def test_download_forbidden(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.Forbidden()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.download,
                          request, str(uuid.uuid4()))

    def test_download_ok_when_get_image_location_forbidden(self):
        class ImageLocations(object):
            def __len__(self):
                raise exception.Forbidden()

        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        self.image_repo.result = image
        image.locations = ImageLocations()
        image = self.controller.download(request, unit_test_utils.UUID1)
        self.assertEqual('abcd', image.image_id)

    def test_upload(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        self.image_repo.result = image
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        self.assertEqual('YYYY', image.data)
        self.assertEqual(4, image.size)

    def test_upload_status(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        self.image_repo.result = image
        insurance = {'called': False}

        def read_data():
            insurance['called'] = True
            self.assertEqual('saving', self.image_repo.saved_image.status)
            yield 'YYYY'

        self.controller.upload(request, unit_test_utils.UUID2,
                               read_data(), None)
        self.assertTrue(insurance['called'])
        self.assertEqual('modified-by-fake',
                         self.image_repo.saved_image.status)

    def test_upload_no_size(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        self.image_repo.result = image
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', None)
        self.assertEqual('YYYY', image.data)
        self.assertIsNone(image.size)

    def test_upload_invalid(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        image.status = ValueError()
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)

    def test_upload_with_expired_token(self):
        def side_effect(image, from_state=None):
            if from_state == 'saving':
                raise exception.NotAuthenticated()

        mocked_save = mock.Mock(side_effect=side_effect)
        mocked_delete = mock.Mock()
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd')
        image.delete = mocked_delete
        self.image_repo.result = image
        self.image_repo.save = mocked_save
        self.assertRaises(webob.exc.HTTPUnauthorized, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)
        self.assertEqual(3, mocked_save.call_count)
        mocked_delete.assert_called_once_with()

    def test_upload_non_existent_image_during_save_initiates_deletion(self):
        def fake_save_not_found(self):
            raise exception.ImageNotFound()

        def fake_save_conflict(self):
            raise exception.Conflict()

        for fun in [fake_save_not_found, fake_save_conflict]:
            request = unit_test_utils.get_fake_request()
            image = FakeImage('abcd', locations=['http://example.com/image'])
            self.image_repo.result = image
            self.image_repo.save = fun
            image.delete = mock.Mock()
            self.assertRaises(webob.exc.HTTPGone, self.controller.upload,
                              request, str(uuid.uuid4()), 'ABC', 3)
            self.assertTrue(image.delete.called)

    def test_upload_non_existent_image_raises_not_found_exception(self):
        def fake_save(self):
            raise exception.ImageNotFound()

        def fake_delete():
            raise exception.ImageNotFound()

        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd', locations=['http://example.com/image'])
        self.image_repo.result = image
        self.image_repo.save = fake_save
        image.delete = fake_delete
        self.assertRaises(webob.exc.HTTPGone, self.controller.upload,
                          request, str(uuid.uuid4()), 'ABC', 3)

    def test_upload_non_existent_image_before_save(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.NotFound()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.upload,
                          request, str(uuid.uuid4()), 'ABC', 3)

    def test_upload_data_exists(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage()
        exc = exception.InvalidImageStatusTransition(cur_status='active',
                                                     new_status='queued')
        image.set_data = Raise(exc)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPConflict, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)

    def test_upload_storage_full(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage()
        image.set_data = Raise(glance_store.StorageFull)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'YYYYYYY', 7)

    def test_upload_signature_verification_fails(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage()
        image.set_data = Raise(exception.SignatureVerificationError)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)
        self.assertEqual('killed', self.image_repo.saved_image.status)

    def test_image_size_limit_exceeded(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage()
        image.set_data = Raise(exception.ImageSizeLimitExceeded)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYYYYY', 7)

    def test_upload_storage_quota_full(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.StorageQuotaFull("message")
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYYYYY', 7)

    def test_upload_storage_forbidden(self):
        request = unit_test_utils.get_fake_request(user=unit_test_utils.USER2)
        image = FakeImage()
        image.set_data = Raise(exception.Forbidden)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.upload,
                          request, unit_test_utils.UUID2, 'YY', 2)

    def test_upload_storage_internal_error(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.ServerError()
        self.assertRaises(exception.ServerError,
                          self.controller.upload,
                          request, unit_test_utils.UUID1, 'ABC', 3)

    def test_upload_storage_write_denied(self):
        request = unit_test_utils.get_fake_request(user=unit_test_utils.USER3)
        image = FakeImage()
        image.set_data = Raise(glance_store.StorageWriteDenied)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'YY', 2)

    def test_upload_storage_store_disabled(self):
        """Test that uploading an image file raises StoreDisabled exception"""
        request = unit_test_utils.get_fake_request(user=unit_test_utils.USER3)
        image = FakeImage()
        image.set_data = Raise(glance_store.StoreAddDisabled)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPGone,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'YY', 2)

    def _test_upload_download_prepare_notification(self):
        request = unit_test_utils.get_fake_request()
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        output = self.controller.download(request, unit_test_utils.UUID2)
        output_log = self.notifier.get_logs()
        prepare_payload = output['meta'].copy()
        prepare_payload['checksum'] = None
        prepare_payload['size'] = None
        prepare_payload['virtual_size'] = None
        prepare_payload['location'] = None
        prepare_payload['status'] = 'queued'
        del prepare_payload['updated_at']
        prepare_log = {
            'notification_type': "INFO",
            'event_type': "image.prepare",
            'payload': prepare_payload,
        }
        self.assertEqual(3, len(output_log))
        prepare_updated_at = output_log[0]['payload']['updated_at']
        del output_log[0]['payload']['updated_at']
        self.assertTrue(prepare_updated_at <= output['meta']['updated_at'])
        self.assertEqual(output_log[0], prepare_log)

    def _test_upload_download_upload_notification(self):
        request = unit_test_utils.get_fake_request()
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        output = self.controller.download(request, unit_test_utils.UUID2)
        output_log = self.notifier.get_logs()
        upload_payload = output['meta'].copy()
        upload_log = {
            'notification_type': "INFO",
            'event_type': "image.upload",
            'payload': upload_payload,
        }
        self.assertEqual(3, len(output_log))
        self.assertEqual(output_log[1], upload_log)

    def _test_upload_download_activate_notification(self):
        request = unit_test_utils.get_fake_request()
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        output = self.controller.download(request, unit_test_utils.UUID2)
        output_log = self.notifier.get_logs()
        activate_payload = output['meta'].copy()
        activate_log = {
            'notification_type': "INFO",
            'event_type': "image.activate",
            'payload': activate_payload,
        }
        self.assertEqual(3, len(output_log))
        self.assertEqual(output_log[2], activate_log)

    def test_restore_image_when_upload_failed(self):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('fake')
        image.set_data = Raise(glance_store.StorageWriteDenied)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'ZZZ', 3)
        self.assertEqual('queued', self.image_repo.saved_image.status)


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
        self.assertEqual('YYY', data.read())
        expected = {'size': 3}
        self.assertEqual(expected, output)

    def test_upload_chunked(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        # If we use body_file, webob assumes we want to do a chunked upload,
        # ignoring the Content-Length header
        request.body_file = six.StringIO('YYY')
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual('YYY', data.read())
        expected = {'size': None}
        self.assertEqual(expected, output)

    def test_upload_chunked_with_content_length(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        request.body_file = six.StringIO('YYY')
        # The deserializer shouldn't care if the Content-Length is
        # set when the user is attempting to send chunked data.
        request.headers['Content-Length'] = 3
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual('YYY', data.read())
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
        self.assertEqual('YYY', data.read())
        expected = {'size': 4}
        self.assertEqual(expected, output)

    def test_upload_wrong_content_type(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/json'
        request.body = 'YYYYY'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                          self.deserializer.upload, request)

        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-st'
        request.body = 'YYYYY'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                          self.deserializer.upload, request)


class TestImageDataSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageDataSerializer, self).setUp()
        self.serializer = glance.api.v2.image_data.ResponseSerializer()

    def test_download(self):
        request = wsgi.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=iter('ZZZ'))
        self.serializer.download(response, image)
        self.assertEqual('ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertNotIn('Content-MD5', response.headers)
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])

    def test_download_with_checksum(self):
        request = wsgi.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        checksum = '0745064918b49693cca64d6b6a13d28a'
        image = FakeImage(size=3, checksum=checksum, data=iter('ZZZ'))
        self.serializer.download(response, image)
        self.assertEqual('ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertEqual(checksum, response.headers['Content-MD5'])
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])

    def test_download_forbidden(self):
        """Make sure the serializer can return 403 forbidden error instead of
        500 internal server error.
        """
        def get_data(*args, **kwargs):
            raise exception.Forbidden()

        self.stubs.Set(glance.api.policy.ImageProxy,
                       'get_data',
                       get_data)
        request = wsgi.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=iter('ZZZ'))
        image.get_data = get_data
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.serializer.download,
                          response, image)

    def test_download_no_content(self):
        """Test image download returns HTTPNoContent

        Make sure that serializer returns 204 no content error in case of
        image data is not available at specified location.
        """
        with mock.patch.object(glance.api.policy.ImageProxy,
                               'get_data') as mock_get_data:
            mock_get_data.side_effect = glance_store.NotFound(image="image")

            request = wsgi.Request.blank('/')
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=iter('ZZZ'))
            image.get_data = mock_get_data
            self.assertRaises(webob.exc.HTTPNoContent,
                              self.serializer.download,
                              response, image)

    def test_download_service_unavailable(self):
        """Test image download returns HTTPServiceUnavailable."""
        with mock.patch.object(glance.api.policy.ImageProxy,
                               'get_data') as mock_get_data:
            mock_get_data.side_effect = glance_store.RemoteServiceUnavailable()

            request = wsgi.Request.blank('/')
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=iter('ZZZ'))
            image.get_data = mock_get_data
            self.assertRaises(webob.exc.HTTPServiceUnavailable,
                              self.serializer.download,
                              response, image)

    def test_download_store_get_not_support(self):
        """Test image download returns HTTPBadRequest.

        Make sure that serializer returns 400 bad request error in case of
        getting images from this store is not supported at specified location.
        """
        with mock.patch.object(glance.api.policy.ImageProxy,
                               'get_data') as mock_get_data:
            mock_get_data.side_effect = glance_store.StoreGetNotSupported()

            request = wsgi.Request.blank('/')
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=iter('ZZZ'))
            image.get_data = mock_get_data
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.serializer.download,
                              response, image)

    def test_download_store_random_get_not_support(self):
        """Test image download returns HTTPBadRequest.

        Make sure that serializer returns 400 bad request error in case of
        getting randomly images from this store is not supported at
        specified location.
        """
        with mock.patch.object(glance.api.policy.ImageProxy,
                               'get_data') as m_get_data:
            err = glance_store.StoreRandomGetNotSupported(offset=0,
                                                          chunk_size=0)
            m_get_data.side_effect = err

            request = wsgi.Request.blank('/')
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=iter('ZZZ'))
            image.get_data = m_get_data
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.serializer.download,
                              response, image)

    def test_upload(self):
        request = webob.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        self.serializer.upload(response, {})
        self.assertEqual(204, response.status_int)
        self.assertEqual('0', response.headers['Content-Length'])
