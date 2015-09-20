# Copyright 2013 OpenStack Foundation
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

from contextlib import contextmanager

import glance_store
import mock
from mock import patch
import webob.exc

from glance.api.v1 import upload_utils
from glance.common import exception
from glance.common import store_utils
from glance.common import utils
import glance.registry.client.v1.api as registry
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils


class TestUploadUtils(base.StoreClearingUnitTest):
    def setUp(self):
        super(TestUploadUtils, self).setUp()
        self.config(verbose=True, debug=True)

    def tearDown(self):
        super(TestUploadUtils, self).tearDown()

    def test_initiate_delete(self):
        req = unit_test_utils.get_fake_request()
        location = {"url": "file://foo/bar",
                    "metadata": {},
                    "status": "active"}
        id = unit_test_utils.UUID1

        with patch.object(store_utils,
                          "safe_delete_from_backend") as mock_store_utils:
            upload_utils.initiate_deletion(req, location, id)
            mock_store_utils.assert_called_once_with(req.context,
                                                     id,
                                                     location)

    def test_initiate_delete_with_delayed_delete(self):
        self.config(delayed_delete=True)
        req = unit_test_utils.get_fake_request()
        location = {"url": "file://foo/bar",
                    "metadata": {},
                    "status": "active"}
        id = unit_test_utils.UUID1

        with patch.object(store_utils, "schedule_delayed_delete_from_backend",
                          return_value=True) as mock_store_utils:
            upload_utils.initiate_deletion(req, location, id)
            mock_store_utils.assert_called_once_with(req.context,
                                                     id,
                                                     location)

    def test_safe_kill(self):
        req = unit_test_utils.get_fake_request()
        id = unit_test_utils.UUID1

        with patch.object(registry, "update_image_metadata") as mock_registry:
            upload_utils.safe_kill(req, id, 'saving')
            mock_registry.assert_called_once_with(req.context, id,
                                                  {'status': 'killed'},
                                                  from_state='saving')

    def test_safe_kill_with_error(self):
        req = unit_test_utils.get_fake_request()
        id = unit_test_utils.UUID1

        with patch.object(registry, "update_image_metadata",
                          side_effect=Exception()) as mock_registry:
            upload_utils.safe_kill(req, id, 'saving')
            mock_registry.assert_called_once_with(req.context, id,
                                                  {'status': 'killed'},
                                                  from_state='saving')

    @contextmanager
    def _get_store_and_notifier(self, image_size=10, ext_update_data=None,
                                ret_checksum="checksum", exc_class=None):
        location = "file://foo/bar"
        checksum = "checksum"
        size = 10
        update_data = {'checksum': checksum}
        if ext_update_data is not None:
            update_data.update(ext_update_data)
        image_meta = {'id': unit_test_utils.UUID1,
                      'size': image_size}
        image_data = "blah"

        store = mock.MagicMock()
        notifier = mock.MagicMock()

        if exc_class is not None:
            store.add.side_effect = exc_class
        else:
            store.add.return_value = (location, size, ret_checksum, {})
        yield (location, checksum, image_meta, image_data, store, notifier,
               update_data)

        store.add.assert_called_once_with(image_meta['id'], mock.ANY,
                                          image_meta['size'], context=mock.ANY)

    def test_upload_data_to_store(self):
        # 'user_storage_quota' is not set
        def store_add(image_id, data, size, **kwargs):
            # Check if 'data' is instance of 'CooperativeReader' when
            # 'user_storage_quota' is disabled.
            self.assertIsInstance(data, utils.CooperativeReader)
            return location, 10, "checksum", {}

        req = unit_test_utils.get_fake_request()
        with self._get_store_and_notifier(
                ext_update_data={'size': 10},
                exc_class=store_add) as (location, checksum, image_meta,
                                         image_data, store, notifier,
                                         update_data):
            ret = image_meta.update(update_data)
            with patch.object(registry, 'update_image_metadata',
                              return_value=ret) as mock_update_image_metadata:
                actual_meta, location_data = upload_utils.upload_data_to_store(
                    req, image_meta, image_data, store, notifier)

                self.assertEqual(location, location_data['url'])
                self.assertEqual(image_meta.update(update_data), actual_meta)
                mock_update_image_metadata.assert_called_once_with(
                    req.context, image_meta['id'], update_data,
                    from_state='saving')

    def test_upload_data_to_store_user_storage_quota_enabled(self):
        # Enable user_storage_quota
        self.config(user_storage_quota='100B')

        def store_add(image_id, data, size, **kwargs):
            # Check if 'data' is instance of 'LimitingReader' when
            # 'user_storage_quota' is enabled.
            self.assertIsInstance(data, utils.LimitingReader)
            return location, 10, "checksum", {}

        req = unit_test_utils.get_fake_request()
        with self._get_store_and_notifier(
                ext_update_data={'size': 10},
                exc_class=store_add) as (location, checksum, image_meta,
                                         image_data, store, notifier,
                                         update_data):
            ret = image_meta.update(update_data)
            # mock 'check_quota'
            mock_check_quota = patch('glance.api.common.check_quota',
                                     return_value=100)
            mock_check_quota.start()
            self.addCleanup(mock_check_quota.stop)
            with patch.object(registry, 'update_image_metadata',
                              return_value=ret) as mock_update_image_metadata:
                actual_meta, location_data = upload_utils.upload_data_to_store(
                    req, image_meta, image_data, store, notifier)

                self.assertEqual(location, location_data['url'])
                self.assertEqual(image_meta.update(update_data), actual_meta)
                mock_update_image_metadata.assert_called_once_with(
                    req.context, image_meta['id'], update_data,
                    from_state='saving')
                # 'check_quota' is called two times
                check_quota_call_count = (
                    mock_check_quota.target.check_quota.call_count)
                self.assertEqual(2, check_quota_call_count)

    def test_upload_data_to_store_mismatch_size(self):
        req = unit_test_utils.get_fake_request()

        with self._get_store_and_notifier(
            image_size=11) as (location, checksum, image_meta, image_data,
                               store, notifier, update_data):
            ret = image_meta.update(update_data)
            with patch.object(registry, 'update_image_metadata',
                              return_value=ret) as mock_update_image_metadata:
                self.assertRaises(webob.exc.HTTPBadRequest,
                                  upload_utils.upload_data_to_store,
                                  req, image_meta, image_data, store,
                                  notifier)
                mock_update_image_metadata.assert_called_with(
                    req.context, image_meta['id'], {'status': 'killed'},
                    from_state='saving')

    def test_upload_data_to_store_mismatch_checksum(self):
        req = unit_test_utils.get_fake_request()

        with self._get_store_and_notifier(
            ret_checksum='fake') as (location, checksum, image_meta,
                                     image_data, store, notifier, update_data):
            ret = image_meta.update(update_data)
            with patch.object(registry, "update_image_metadata",
                              return_value=ret) as mock_update_image_metadata:
                self.assertRaises(webob.exc.HTTPBadRequest,
                                  upload_utils.upload_data_to_store,
                                  req, image_meta, image_data, store,
                                  notifier)
                mock_update_image_metadata.assert_called_with(
                    req.context, image_meta['id'], {'status': 'killed'},
                    from_state='saving')

    def _test_upload_data_to_store_exception(self, exc_class, expected_class):
        req = unit_test_utils.get_fake_request()

        with self._get_store_and_notifier(
            exc_class=exc_class) as (location, checksum, image_meta,
                                     image_data, store, notifier, update_data):
            with patch.object(upload_utils, 'safe_kill') as mock_safe_kill:
                self.assertRaises(expected_class,
                                  upload_utils.upload_data_to_store,
                                  req, image_meta, image_data, store, notifier)
                mock_safe_kill.assert_called_once_with(
                    req, image_meta['id'], 'saving')

    def _test_upload_data_to_store_exception_with_notify(self,
                                                         exc_class,
                                                         expected_class,
                                                         image_killed=True):
        req = unit_test_utils.get_fake_request()

        with self._get_store_and_notifier(
            exc_class=exc_class) as (location, checksum, image_meta,
                                     image_data, store, notifier, update_data):
            with patch.object(upload_utils, 'safe_kill') as mock_safe_kill:
                self.assertRaises(expected_class,
                                  upload_utils.upload_data_to_store,
                                  req, image_meta, image_data, store,
                                  notifier)
                if image_killed:
                    mock_safe_kill.assert_called_with(req, image_meta['id'],
                                                      'saving')

    def test_upload_data_to_store_raises_store_disabled(self):
        """Test StoreDisabled exception is raised while uploading data"""
        self._test_upload_data_to_store_exception_with_notify(
            glance_store.StoreAddDisabled,
            webob.exc.HTTPGone,
            image_killed=True)

    def test_upload_data_to_store_duplicate(self):
        """See note in glance.api.v1.upload_utils on why we don't want image to
        be deleted in this case.
        """
        self._test_upload_data_to_store_exception_with_notify(
            exception.Duplicate,
            webob.exc.HTTPConflict,
            image_killed=False)

    def test_upload_data_to_store_forbidden(self):
        self._test_upload_data_to_store_exception_with_notify(
            exception.Forbidden,
            webob.exc.HTTPForbidden)

    def test_upload_data_to_store_storage_full(self):
        self._test_upload_data_to_store_exception_with_notify(
            glance_store.StorageFull,
            webob.exc.HTTPRequestEntityTooLarge)

    def test_upload_data_to_store_storage_write_denied(self):
        self._test_upload_data_to_store_exception_with_notify(
            glance_store.StorageWriteDenied,
            webob.exc.HTTPServiceUnavailable)

    def test_upload_data_to_store_size_limit_exceeded(self):
        self._test_upload_data_to_store_exception_with_notify(
            exception.ImageSizeLimitExceeded,
            webob.exc.HTTPRequestEntityTooLarge)

    def test_upload_data_to_store_http_error(self):
        self._test_upload_data_to_store_exception_with_notify(
            webob.exc.HTTPError,
            webob.exc.HTTPError)

    def test_upload_data_to_store_client_disconnect(self):
        self._test_upload_data_to_store_exception(
            ValueError,
            webob.exc.HTTPBadRequest)

    def test_upload_data_to_store_client_disconnect_ioerror(self):
        self._test_upload_data_to_store_exception(
            IOError,
            webob.exc.HTTPBadRequest)

    def test_upload_data_to_store_exception(self):
        self._test_upload_data_to_store_exception_with_notify(
            Exception,
            webob.exc.HTTPInternalServerError)

    def test_upload_data_to_store_not_found_after_upload(self):
        req = unit_test_utils.get_fake_request()

        with self._get_store_and_notifier(
            ext_update_data={'size': 10}) as (location, checksum, image_meta,
                                              image_data, store, notifier,
                                              update_data):
            exc = exception.ImageNotFound
            with patch.object(registry, 'update_image_metadata',
                              side_effect=exc) as mock_update_image_metadata:
                with patch.object(upload_utils,
                                  "initiate_deletion") as mock_initiate_del:
                    with patch.object(upload_utils,
                                      "safe_kill") as mock_safe_kill:
                        self.assertRaises(webob.exc.HTTPPreconditionFailed,
                                          upload_utils.upload_data_to_store,
                                          req, image_meta, image_data, store,
                                          notifier)
                        mock_update_image_metadata.assert_called_once_with(
                            req.context, image_meta['id'], update_data,
                            from_state='saving')
                        mock_initiate_del.assert_called_once_with(
                            req, {'url': location, 'status': 'active',
                                  'metadata': {}}, image_meta['id'])
                        mock_safe_kill.assert_called_once_with(
                            req, image_meta['id'], 'saving')

    @mock.patch.object(registry, 'update_image_metadata',
                       side_effect=exception.NotAuthenticated)
    @mock.patch.object(upload_utils, 'initiate_deletion')
    def test_activate_image_with_expired_token(
            self, mocked_delete, mocked_update):
        """Test token expiration during image upload.

        If users token expired before image was uploaded then if auth error
        was caught from registry during changing image status from 'saving'
        to 'active' then it's required to delete all image data.
        """
        context = mock.Mock()
        req = mock.Mock()
        req.context = context
        with self._get_store_and_notifier() as (location, checksum, image_meta,
                                                image_data, store, notifier,
                                                update_data):
            self.assertRaises(webob.exc.HTTPUnauthorized,
                              upload_utils.upload_data_to_store,
                              req, image_meta, image_data, store, notifier)
            self.assertEqual(2, mocked_update.call_count)
            mocked_delete.assert_called_once_with(
                req,
                {'url': 'file://foo/bar', 'status': 'active', 'metadata': {}},
                'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d')
