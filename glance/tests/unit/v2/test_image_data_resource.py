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

import http.client as http
import io
from unittest import mock
import uuid

from cursive import exception as cursive_exception
import glance_store
from glance_store._drivers import filesystem
from oslo_config import cfg
import webob

import glance.api.policy
import glance.api.v2.image_data
from glance.common import exception
from glance.common import wsgi
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF
CONF.import_opt('public_endpoint', 'glance.api.versions')


class Raise(object):

    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *args, **kwargs):
        raise self.exc


class FakeImage(object):

    def __init__(self, image_id=None, data=None, checksum=None, size=0,
                 virtual_size=0, locations=None, container_format='bear',
                 disk_format='rawr', status=None, owner=None):
        self.image_id = image_id
        self.data = data
        self.checksum = checksum
        self.size = size
        self.virtual_size = virtual_size
        self.locations = locations
        self.container_format = container_format
        self.disk_format = disk_format
        self.owner = owner
        self._status = status
        self.extra_properties = {}

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if isinstance(self._status, BaseException):
            raise self._status
        else:
            self._status = value

    def get_data(self, offset=0, chunk_size=None):
        if chunk_size:
            return self.data[offset:offset + chunk_size]
        return self.data[offset:]

    def set_data(self, data, size=None, backend=None, set_active=True):
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

    def __init__(self, db=None, store=None, notifier=None,
                 policy=None, repo=None):
        self.db = db
        self.store = store
        self.notifier = notifier
        self.policy = policy
        self.repo = repo

    def get_repo(self, context):
        return self.repo


class TestImagesController(base.StoreClearingUnitTest):

    def setUp(self):
        super(TestImagesController, self).setUp()

        self.config(debug=True)
        self.image_repo = FakeImageRepo()
        db = unit_test_utils.FakeDB()
        policy = unit_test_utils.FakePolicyEnforcer()
        notifier = unit_test_utils.FakeNotifier()
        store = unit_test_utils.FakeStoreAPI()
        self.controller = glance.api.v2.image_data.ImageDataController()
        self.controller.gateway = FakeGateway(db, store, notifier, policy,
                                              self.image_repo)
        # FIXME(abhishekk): Everything is fake in this test, so mocked the
        # image mutable_check, Later we need to fix these tests to use
        # some realistic data
        patcher = mock.patch('glance.api.v2.policy.check_is_image_mutable')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_download(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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

        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd')
        self.image_repo.result = image
        image.locations = ImageLocations()
        image = self.controller.download(request, unit_test_utils.UUID1)
        self.assertEqual('abcd', image.image_id)

    def test_upload(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd', owner='tenant1')
        self.image_repo.result = image
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        self.assertEqual('YYYY', image.data)
        self.assertEqual(4, image.size)

    def test_upload_not_allowed_by_policy(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(self.controller.policy, 'enforce') as mock_enf:
            mock_enf.side_effect = webob.exc.HTTPForbidden()
            exc = self.assertRaises(webob.exc.HTTPNotFound,
                                    self.controller.upload, request,
                                    unit_test_utils.UUID1, 'YYYY', 4)
            self.assertTrue(mock_enf.called)
        # Make sure we did not leak details of the original Forbidden
        # error into the NotFound returned to the client.
        self.assertEqual('The resource could not be found.', str(exc))

        # Now reject the upload_image call, but allow get_image to ensure that
        # we properly see a Forbidden result.
        with mock.patch.object(self.controller.policy, 'enforce') as mock_enf:
            mock_enf.side_effect = [webob.exc.HTTPForbidden(),
                                    lambda *a: None]
            exc = self.assertRaises(webob.exc.HTTPForbidden,
                                    self.controller.upload, request,
                                    unit_test_utils.UUID1, 'YYYY', 4)
            self.assertTrue(mock_enf.called)

    def test_upload_status(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd')
        self.image_repo.result = image
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', None)
        self.assertEqual('YYYY', image.data)
        self.assertIsNone(image.size)

    @mock.patch.object(glance.api.policy.Enforcer, 'enforce')
    def test_upload_image_forbidden(self, mock_enforce):
        request = unit_test_utils.get_fake_request()
        image = FakeImage('abcd', owner='tenant1')
        self.image_repo.result = image
        mock_enforce.side_effect = [exception.Forbidden, lambda *a: None]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.upload,
                          request, unit_test_utils.UUID2, 'YYYY', 4)
        expected_call = [
            mock.call(mock.ANY, 'upload_image', mock.ANY),
            mock.call(mock.ANY, 'get_image', mock.ANY)
        ]
        mock_enforce.assert_has_calls(expected_call)

    def test_upload_invalid(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd')
        image.delete = mocked_delete
        self.image_repo.result = image
        self.image_repo.save = mocked_save
        self.assertRaises(webob.exc.HTTPUnauthorized, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)
        self.assertEqual(3, mocked_save.call_count)
        mocked_delete.assert_called_once_with()

    @mock.patch('glance.common.trust_auth.TokenRefresher')
    def test_upload_with_token_refresh(self, mock_refresher):
        mock_refresher.return_value = mock.MagicMock()
        mocked_save = mock.Mock()
        mocked_save.side_effect = [lambda *a: None,
                                   exception.NotAuthenticated(),
                                   lambda *a: None]
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        request.environ['keystone.token_info'] = {
            'token': {
                'roles': [{'name': 'member'}]
            }
        }
        image = FakeImage('abcd', owner='tenant1')
        self.image_repo.result = image
        self.image_repo.save = mocked_save
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        self.assertEqual('YYYY', image.data)
        self.assertEqual(4, image.size)
        self.assertEqual(3, mocked_save.call_count)

    def test_upload_non_existent_image_during_save_initiates_deletion(self):
        def fake_save_not_found(self, from_state=None):
            raise exception.ImageNotFound()

        def fake_save_conflict(self, from_state=None):
            raise exception.Conflict()

        for fun in [fake_save_not_found, fake_save_conflict]:
            request = unit_test_utils.get_fake_request(
                roles=['admin', 'member'])
            image = FakeImage('abcd', locations=['http://example.com/image'])
            self.image_repo.result = image
            self.image_repo.save = fun
            image.delete = mock.Mock()
            self.assertRaises(webob.exc.HTTPGone, self.controller.upload,
                              request, str(uuid.uuid4()), 'ABC', 3)
            self.assertTrue(image.delete.called)

    def test_upload_non_existent_image_raises_image_not_found_exception(self):
        def fake_save(self, from_state=None):
            raise exception.ImageNotFound()

        def fake_delete():
            raise exception.ImageNotFound()

        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd', locations=['http://example.com/image'])
        self.image_repo.result = image
        self.image_repo.save = fake_save
        image.delete = fake_delete
        self.assertRaises(webob.exc.HTTPGone, self.controller.upload,
                          request, str(uuid.uuid4()), 'ABC', 3)

    def test_upload_non_existent_image_raises_store_not_found_exception(self):
        def fake_save(self, from_state=None):
            raise glance_store.NotFound()

        def fake_delete():
            raise exception.ImageNotFound()

        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage()
        exc = exception.InvalidImageStatusTransition(cur_status='active',
                                                     new_status='queued')
        image.set_data = Raise(exc)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPConflict, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)

    def test_upload_storage_full(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage()
        image.set_data = Raise(glance_store.StorageFull)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'YYYYYYY', 7)

    def test_upload_signature_verification_fails(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage()
        image.set_data = Raise(cursive_exception.SignatureVerificationError)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.upload,
                          request, unit_test_utils.UUID1, 'YYYY', 4)
        self.assertEqual('queued', self.image_repo.saved_image.status)

    def test_image_size_limit_exceeded(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(
            user=unit_test_utils.USER2, roles=['admin', 'member'])
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
        request = unit_test_utils.get_fake_request(
            user=unit_test_utils.USER3, roles=['admin', 'member'])
        image = FakeImage()
        image.set_data = Raise(glance_store.StorageWriteDenied)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'YY', 2)

    def test_upload_storage_store_disabled(self):
        """Test that uploading an image file raises StoreDisabled exception"""
        request = unit_test_utils.get_fake_request(
            user=unit_test_utils.USER3, roles=['admin', 'member'])
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
        self.assertLessEqual(prepare_updated_at, output['meta']['updated_at'])
        self.assertEqual(prepare_log, output_log[0])

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
        self.assertEqual(upload_log, output_log[1])

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
        self.assertEqual(activate_log, output_log[2])

    def test_restore_image_when_upload_failed(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('fake')
        image.set_data = Raise(glance_store.StorageWriteDenied)
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.controller.upload,
                          request, unit_test_utils.UUID2, 'ZZZ', 3)
        self.assertEqual('queued', self.image_repo.saved_image.status)

    @mock.patch.object(filesystem.Store, 'add')
    def test_restore_image_when_staging_failed(self, mock_store_add):
        mock_store_add.side_effect = glance_store.StorageWriteDenied()
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image_id = str(uuid.uuid4())
        image = FakeImage('fake')
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.controller.stage,
                          request, image_id, 'YYYYYYY', 7)
        self.assertEqual('queued', self.image_repo.saved_image.status)

    def test_stage(self):
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(filesystem.Store, 'add') as mock_add:
            mock_add.return_value = ('foo://bar', 4, 'ident', {})
            self.controller.stage(request, image_id, 'YYYY', 4)
        self.assertEqual('uploading', image.status)
        self.assertEqual(4, image.size)

    def test_image_already_on_staging(self):
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(filesystem.Store, 'add') as mock_store_add:
            mock_store_add.return_value = ('foo://bar', 4, 'ident', {})
            self.controller.stage(request, image_id, 'YYYY', 4)
            self.assertEqual('uploading', image.status)
            mock_store_add.side_effect = glance_store.Duplicate()
            self.assertEqual(4, image.size)
            self.assertRaises(webob.exc.HTTPConflict, self.controller.stage,
                              request, image_id, 'YYYY', 4)

    @mock.patch.object(glance_store.driver.Store, 'configure')
    def test_image_stage_raises_bad_store_uri(self, mock_store_configure):
        mock_store_configure.side_effect = AttributeError()
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        self.assertRaises(exception.BadStoreUri, self.controller.stage,
                          request, image_id, 'YYYY', 4)

    @mock.patch.object(filesystem.Store, 'add')
    def test_image_stage_raises_storage_full(self, mock_store_add):
        mock_store_add.side_effect = glance_store.StorageFull()
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(self.controller, "_unstage"):
            self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                              self.controller.stage,
                              request, image_id, 'YYYYYYY', 7)

    @mock.patch.object(filesystem.Store, 'add')
    def test_image_stage_raises_storage_quota_full(self, mock_store_add):
        mock_store_add.side_effect = exception.StorageQuotaFull("message")
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(self.controller, "_unstage"):
            self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                              self.controller.stage,
                              request, image_id, 'YYYYYYY', 7)

    @mock.patch.object(filesystem.Store, 'add')
    def test_image_stage_raises_storage_write_denied(self, mock_store_add):
        mock_store_add.side_effect = glance_store.StorageWriteDenied()
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(self.controller, "_unstage"):
            self.assertRaises(webob.exc.HTTPServiceUnavailable,
                              self.controller.stage,
                              request, image_id, 'YYYYYYY', 7)

    def test_image_stage_raises_internal_error(self):
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.ServerError()
        self.assertRaises(exception.ServerError,
                          self.controller.stage,
                          request, image_id, 'YYYYYYY', 7)

    def test_image_stage_non_existent_image(self):
        request = unit_test_utils.get_fake_request()
        self.image_repo.result = exception.NotFound()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.stage,
                          request, str(uuid.uuid4()), 'ABC', 3)

    @mock.patch.object(filesystem.Store, 'add')
    def test_image_stage_raises_image_size_exceeded(self, mock_store_add):
        mock_store_add.side_effect = exception.ImageSizeLimitExceeded()
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(self.controller, "_unstage"):
            self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                              self.controller.stage,
                              request, image_id, 'YYYYYYY', 7)

    @mock.patch.object(filesystem.Store, 'add')
    def test_image_stage_invalid_image_transition(self, mock_store_add):
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(filesystem.Store, 'add') as mock_add:
            mock_add.return_value = ('foo://bar', 4, 'ident', {})
            self.controller.stage(request, image_id, 'YYYY', 4)
        self.assertEqual('uploading', image.status)
        self.assertEqual(4, image.size)
        # try staging again
        mock_store_add.side_effect = exception.InvalidImageStatusTransition(
            cur_status='uploading', new_status='uploading')
        self.assertRaises(webob.exc.HTTPConflict, self.controller.stage,
                          request, image_id, 'YYYY', 4)

    def _test_image_stage_records_host(self, expected_url):
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        with mock.patch.object(filesystem.Store, 'add') as mock_add:
            mock_add.return_value = ('foo://bar', 4, 'ident', {})
            self.controller.stage(request, image_id, 'YYYY', 4)
        if expected_url is None:
            self.assertNotIn('os_glance_stage_host', image.extra_properties)
        else:
            self.assertEqual(expected_url,
                             image.extra_properties['os_glance_stage_host'])

    def test_image_stage_records_host_unset(self):
        # Make sure we do not set a null staging host, if we are not configured
        # to support worker-to-worker communication.
        self._test_image_stage_records_host(None)

    def test_image_stage_records_host_public_endpoint(self):
        # Make sure we fall back to public_endpoint
        self.config(public_endpoint='http://lb.example.com')
        self._test_image_stage_records_host('http://lb.example.com')

    def test_image_stage_records_host_self_url(self):
        # Make sure worker_self_reference_url takes precedence
        self.config(worker_self_reference_url='http://worker1.example.com')
        self._test_image_stage_records_host('http://worker1.example.com')

    def test_image_stage_fail_does_not_set_host(self):
        # Make sure that if the store.add() fails, we do not claim to have the
        # image staged.
        self.config(public_endpoint='http://worker1.example.com')
        image_id = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage(image_id=image_id)
        self.image_repo.result = image
        exc_cls = glance_store.exceptions.StorageFull
        with mock.patch.object(filesystem.Store, 'add', side_effect=exc_cls):
            self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                              self.controller.stage,
                              request, image_id, 'YYYY', 4)
        self.assertNotIn('os_glance_stage_host', image.extra_properties)


class TestImageDataDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageDataDeserializer, self).setUp()
        self.deserializer = glance.api.v2.image_data.RequestDeserializer()

    def test_upload(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        request.body = b'YYY'
        request.headers['Content-Length'] = 3
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(b'YYY', data.read())
        expected = {'size': 3}
        self.assertEqual(expected, output)

    def test_upload_chunked(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        # If we use body_file, webob assumes we want to do a chunked upload,
        # ignoring the Content-Length header
        request.body_file = io.StringIO('YYY')
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual('YYY', data.read())
        expected = {'size': None}
        self.assertEqual(expected, output)

    def test_upload_chunked_with_content_length(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        request.body_file = io.BytesIO(b'YYY')
        # The deserializer shouldn't care if the Content-Length is
        # set when the user is attempting to send chunked data.
        request.headers['Content-Length'] = 3
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(b'YYY', data.read())
        expected = {'size': 3}
        self.assertEqual(expected, output)

    def test_upload_with_incorrect_content_length(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-stream'
        # The deserializer shouldn't care if the Content-Length and
        # actual request body length differ. That job is left up
        # to the controller
        request.body = b'YYY'
        request.headers['Content-Length'] = 4
        output = self.deserializer.upload(request)
        data = output.pop('data')
        self.assertEqual(b'YYY', data.read())
        expected = {'size': 4}
        self.assertEqual(expected, output)

    def test_upload_wrong_content_type(self):
        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/json'
        request.body = b'YYYYY'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                          self.deserializer.upload, request)

        request = unit_test_utils.get_fake_request()
        request.headers['Content-Type'] = 'application/octet-st'
        request.body = b'YYYYY'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                          self.deserializer.upload, request)

    def test_stage(self):
        req = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['Content-Length'] = 4
        req.body_file = io.BytesIO(b'YYYY')
        output = self.deserializer.stage(req)
        data = output.pop('data')
        self.assertEqual(b'YYYY', data.read())

    def test_stage_without_glance_direct(self):
        self.config(enabled_import_methods=['web-download'])
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.deserializer.stage,
                          req)

    def test_stage_raises_invalid_content_type(self):
        # TODO(abhishekk): change this when import methods are
        # listed in the config file
        req = unit_test_utils.get_fake_request()
        req.headers['Content-Type'] = 'application/json'
        self.assertRaises(webob.exc.HTTPUnsupportedMediaType,
                          self.deserializer.stage,
                          req)


class TestImageDataSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageDataSerializer, self).setUp()
        self.serializer = glance.api.v2.image_data.ResponseSerializer()

    def test_download(self):
        request = wsgi.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
        self.serializer.download(response, image)
        self.assertEqual(b'ZZZ', response.body)
        self.assertEqual('3', response.headers['Content-Length'])
        self.assertNotIn('Content-MD5', response.headers)
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])

    def test_range_requests_for_image_downloads(self):
        """
        Test partial download 'Range' requests for images (random image access)
        """
        def download_successful_Range(d_range):
            request = wsgi.Request.blank('/')
            request.environ = {}
            request.headers['Range'] = d_range
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=[b'X', b'Y', b'Z'])
            self.serializer.download(response, image)
            self.assertEqual(206, response.status_code)
            self.assertEqual('2', response.headers['Content-Length'])
            self.assertEqual('bytes 1-2/3', response.headers['Content-Range'])
            self.assertEqual(b'YZ', response.body)

        download_successful_Range('bytes=1-2')
        download_successful_Range('bytes=1-')
        download_successful_Range('bytes=1-3')
        download_successful_Range('bytes=-2')
        download_successful_Range('bytes=1-100')

        def full_image_download_w_range(d_range):
            request = wsgi.Request.blank('/')
            request.environ = {}
            request.headers['Range'] = d_range
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=[b'X', b'Y', b'Z'])
            self.serializer.download(response, image)
            self.assertEqual(206, response.status_code)
            self.assertEqual('3', response.headers['Content-Length'])
            self.assertEqual('bytes 0-2/3', response.headers['Content-Range'])
            self.assertEqual(b'XYZ', response.body)

        full_image_download_w_range('bytes=0-')
        full_image_download_w_range('bytes=0-2')
        full_image_download_w_range('bytes=0-3')
        full_image_download_w_range('bytes=-3')
        full_image_download_w_range('bytes=-4')
        full_image_download_w_range('bytes=0-100')
        full_image_download_w_range('bytes=-100')

        def download_failures_Range(d_range):
            request = wsgi.Request.blank('/')
            request.environ = {}
            request.headers['Range'] = d_range
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
            self.assertRaises(webob.exc.HTTPRequestRangeNotSatisfiable,
                              self.serializer.download,
                              response, image)
            return

        download_failures_Range('bytes=4-1')
        download_failures_Range('bytes=4-')
        download_failures_Range('bytes=3-')
        download_failures_Range('bytes=1')
        download_failures_Range('bytes=100')
        download_failures_Range('bytes=100-')
        download_failures_Range('bytes=')

    def test_multi_range_requests_raises_bad_request_error(self):
        request = wsgi.Request.blank('/')
        request.environ = {}
        request.headers['Range'] = 'bytes=0-0,-1'
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.serializer.download,
                          response, image)

    def test_download_failure_with_valid_range(self):
        with mock.patch.object(glance.domain.proxy.Image,
                               'get_data') as mock_get_data:
            mock_get_data.side_effect = glance_store.NotFound(image="image")
        request = wsgi.Request.blank('/')
        request.environ = {}
        request.headers['Range'] = 'bytes=1-2'
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
        image.get_data = mock_get_data
        self.assertRaises(webob.exc.HTTPNoContent,
                          self.serializer.download,
                          response, image)

    def test_content_range_requests_for_image_downloads(self):
        """
        Even though Content-Range is incorrect on requests, we support it
        for backward compatibility with clients written for pre-Pike
        Glance.
        The following test is for 'Content-Range' requests, which we have
        to ensure that we prevent regression.
        """
        def download_successful_ContentRange(d_range):
            request = wsgi.Request.blank('/')
            request.environ = {}
            request.headers['Content-Range'] = d_range
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=[b'X', b'Y', b'Z'])
            self.serializer.download(response, image)
            self.assertEqual(206, response.status_code)
            self.assertEqual('2', response.headers['Content-Length'])
            self.assertEqual('bytes 1-2/3', response.headers['Content-Range'])
            self.assertEqual(b'YZ', response.body)

        download_successful_ContentRange('bytes 1-2/3')
        download_successful_ContentRange('bytes 1-2/*')

        def download_failures_ContentRange(d_range):
            request = wsgi.Request.blank('/')
            request.environ = {}
            request.headers['Content-Range'] = d_range
            response = webob.Response()
            response.request = request
            image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
            self.assertRaises(webob.exc.HTTPRequestRangeNotSatisfiable,
                              self.serializer.download,
                              response, image)
            return

        download_failures_ContentRange('bytes -3/3')
        download_failures_ContentRange('bytes 1-/3')
        download_failures_ContentRange('bytes 1-3/3')
        download_failures_ContentRange('bytes 1-4/3')
        download_failures_ContentRange('bytes 1-4/*')
        download_failures_ContentRange('bytes 4-1/3')
        download_failures_ContentRange('bytes 4-1/*')
        download_failures_ContentRange('bytes 4-8/*')
        download_failures_ContentRange('bytes 4-8/10')
        download_failures_ContentRange('bytes 4-8/3')

    def test_download_failure_with_valid_content_range(self):
        with mock.patch.object(glance.domain.proxy.Image,
                               'get_data') as mock_get_data:
            mock_get_data.side_effect = glance_store.NotFound(image="image")
        request = wsgi.Request.blank('/')
        request.environ = {}
        request.headers['Content-Range'] = 'bytes %s-%s/3' % (1, 2)
        response = webob.Response()
        response.request = request
        image = FakeImage(size=3, data=[b'Z', b'Z', b'Z'])
        image.get_data = mock_get_data
        self.assertRaises(webob.exc.HTTPNoContent,
                          self.serializer.download,
                          response, image)

    def test_download_with_checksum(self):
        request = wsgi.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        checksum = '0745064918b49693cca64d6b6a13d28a'
        image = FakeImage(size=3, checksum=checksum, data=[b'Z', b'Z', b'Z'])
        self.serializer.download(response, image)
        self.assertEqual(b'ZZZ', response.body)
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

        self.mock_object(glance.domain.proxy.Image,
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
        with mock.patch.object(glance.domain.proxy.Image,
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
        with mock.patch.object(glance.domain.proxy.Image,
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
        with mock.patch.object(glance.domain.proxy.Image,
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
        with mock.patch.object(glance.domain.proxy.Image,
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
        self.assertEqual(http.NO_CONTENT, response.status_int)
        self.assertEqual('0', response.headers['Content-Length'])

    def test_stage(self):
        request = webob.Request.blank('/')
        request.environ = {}
        response = webob.Response()
        response.request = request
        self.serializer.stage(response, {})
        self.assertEqual(http.NO_CONTENT, response.status_int)
        self.assertEqual('0', response.headers['Content-Length'])


class TestMultiBackendImagesController(base.MultiStoreClearingUnitTest):

    def setUp(self):
        super(TestMultiBackendImagesController, self).setUp()

        self.config(debug=True)
        self.image_repo = FakeImageRepo()
        db = unit_test_utils.FakeDB()
        policy = unit_test_utils.FakePolicyEnforcer()
        notifier = unit_test_utils.FakeNotifier()
        store = unit_test_utils.FakeStoreAPI()
        self.controller = glance.api.v2.image_data.ImageDataController()
        self.controller.gateway = FakeGateway(db, store, notifier, policy,
                                              self.image_repo)
        # FIXME(abhishekk): Everything is fake in this test, so mocked the
        # image muntable_check, Later we need to fix these tests to use
        # some realistic data
        patcher = mock.patch('glance.api.v2.policy.check_is_image_mutable')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_upload(self):
        request = unit_test_utils.get_fake_request(roles=['admin', 'member'])
        image = FakeImage('abcd')
        self.image_repo.result = image
        self.controller.upload(request, unit_test_utils.UUID2, 'YYYY', 4)
        self.assertEqual('YYYY', image.data)
        self.assertEqual(4, image.size)

    def test_upload_invalid_backend_in_request_header(self):
        request = unit_test_utils.get_fake_request()
        request.headers['x-image-meta-store'] = 'dummy'
        image = FakeImage('abcd')
        self.image_repo.result = image
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.upload,
                          request, unit_test_utils.UUID2, 'YYYY', 4)
