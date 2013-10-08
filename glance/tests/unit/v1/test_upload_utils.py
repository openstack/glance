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

import mox

import webob.exc

from glance.api.v1 import upload_utils
from glance.common import exception
import glance.registry.client.v1.api as registry
import glance.store
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils


class TestUploadUtils(base.StoreClearingUnitTest):
    def setUp(self):
        super(TestUploadUtils, self).setUp()
        self.config(verbose=True, debug=True)
        self.mox = mox.Mox()

    def tearDown(self):
        super(TestUploadUtils, self).tearDown()
        self.mox.UnsetStubs()

    def test_initiate_delete(self):
        req = unit_test_utils.get_fake_request()
        location = "file://foo/bar"
        id = unit_test_utils.UUID1

        self.mox.StubOutWithMock(glance.store, "safe_delete_from_backend")
        glance.store.safe_delete_from_backend(req.context, location, id)
        self.mox.ReplayAll()

        upload_utils.initiate_deletion(req, location, id)

        self.mox.VerifyAll()

    def test_initiate_delete_with_delayed_delete(self):
        req = unit_test_utils.get_fake_request()
        location = "file://foo/bar"
        id = unit_test_utils.UUID1

        self.mox.StubOutWithMock(glance.store,
                                 "schedule_delayed_delete_from_backend")
        glance.store.schedule_delayed_delete_from_backend(req.context,
                                                          location,
                                                          id)
        self.mox.ReplayAll()

        upload_utils.initiate_deletion(req, location, id, True)

        self.mox.VerifyAll()

    def test_safe_kill(self):
        req = unit_test_utils.get_fake_request()
        id = unit_test_utils.UUID1

        self.mox.StubOutWithMock(registry, "update_image_metadata")
        registry.update_image_metadata(req.context, id, {'status': 'killed'},
                                       'saving')
        self.mox.ReplayAll()

        upload_utils.safe_kill(req, id, 'saving')

        self.mox.VerifyAll()

    def test_safe_kill_with_error(self):
        req = unit_test_utils.get_fake_request()
        id = unit_test_utils.UUID1

        self.mox.StubOutWithMock(registry, "update_image_metadata")
        registry.update_image_metadata(req.context,
                                       id,
                                       {'status': 'killed'},
                                       'saving'
                                       ).AndRaise(Exception())
        self.mox.ReplayAll()

        upload_utils.safe_kill(req, id, 'saving')

        self.mox.VerifyAll()

    def test_upload_data_to_store(self):
        req = unit_test_utils.get_fake_request()

        location = "file://foo/bar"
        size = 10
        checksum = "checksum"

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size}
        image_data = "blah"

        notifier = self.mox.CreateMockAnything()
        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndReturn((location, size, checksum, {}))

        self.mox.StubOutWithMock(registry, 'update_image_metadata')
        update_data = {'checksum': checksum,
                       'size': size}
        registry.update_image_metadata(req.context, image_meta['id'],
                                       update_data, from_state='saving'
                                       ).AndReturn(
                                           image_meta.update(update_data))
        self.mox.ReplayAll()

        actual_meta, actual_loc, loc_meta = upload_utils.upload_data_to_store(
            req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()

        self.assertEqual(actual_loc, location)
        self.assertEqual(actual_meta, image_meta.update(update_data))

    def test_upload_data_to_store_mismatch_size(self):
        req = unit_test_utils.get_fake_request()

        location = "file://foo/bar"
        size = 10
        checksum = "checksum"

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size + 1}  # Need incorrect size for test

        image_data = "blah"

        notifier = self.mox.CreateMockAnything()
        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndReturn((location, size, checksum, {}))

        self.mox.StubOutWithMock(registry, "update_image_metadata")
        update_data = {'checksum': checksum}
        registry.update_image_metadata(
            req.context, image_meta['id'],
            update_data).AndReturn(image_meta.update(update_data))
        notifier.error('image.upload', mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(webob.exc.HTTPBadRequest,
                          upload_utils.upload_data_to_store,
                          req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()

    def test_upload_data_to_store_mismatch_checksum(self):
        req = unit_test_utils.get_fake_request()

        location = "file://foo/bar"
        size = 10
        checksum = "checksum"

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size}
        image_data = "blah"

        notifier = self.mox.CreateMockAnything()
        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndReturn((location,
                                           size,
                                           checksum + "NOT",
                                           {}))

        self.mox.StubOutWithMock(registry, "update_image_metadata")
        update_data = {'checksum': checksum}
        registry.update_image_metadata(
            req.context, image_meta['id'],
            update_data).AndReturn(image_meta.update(update_data))
        notifier.error('image.upload', mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(webob.exc.HTTPBadRequest,
                          upload_utils.upload_data_to_store,
                          req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()

    def _test_upload_data_to_store_exception(self, exc_class, expected_class):
        req = unit_test_utils.get_fake_request()

        size = 10

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size}
        image_data = "blah"

        notifier = self.mox.CreateMockAnything()
        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndRaise(exc_class)

        self.mox.StubOutWithMock(upload_utils, "safe_kill")
        upload_utils.safe_kill(req, image_meta['id'], 'saving')
        self.mox.ReplayAll()

        self.assertRaises(expected_class,
                          upload_utils.upload_data_to_store,
                          req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()

    def _test_upload_data_to_store_exception_with_notify(self,
                                                         exc_class,
                                                         expected_class,
                                                         image_killed=True):
        req = unit_test_utils.get_fake_request()

        size = 10

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size}
        image_data = "blah"

        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndRaise(exc_class)

        if image_killed:
            self.mox.StubOutWithMock(upload_utils, "safe_kill")
            upload_utils.safe_kill(req, image_meta['id'], 'saving')

        notifier = self.mox.CreateMockAnything()
        notifier.error('image.upload', mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(expected_class,
                          upload_utils.upload_data_to_store,
                          req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()

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
            exception.StorageFull,
            webob.exc.HTTPRequestEntityTooLarge)

    def test_upload_data_to_store_storage_write_denied(self):
        self._test_upload_data_to_store_exception_with_notify(
            exception.StorageWriteDenied,
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

        location = "file://foo/bar"
        size = 10
        checksum = "checksum"

        image_meta = {'id': unit_test_utils.UUID1,
                      'size': size}
        image_data = "blah"

        notifier = self.mox.CreateMockAnything()
        store = self.mox.CreateMockAnything()
        store.add(
            image_meta['id'],
            mox.IgnoreArg(),
            image_meta['size']).AndReturn((location, size, checksum, {}))

        self.mox.StubOutWithMock(registry, 'update_image_metadata')
        update_data = {'checksum': checksum,
                       'size': size}
        registry.update_image_metadata(req.context, image_meta['id'],
                                       update_data, from_state='saving'
                                       ).AndRaise(exception.NotFound)
        self.mox.StubOutWithMock(upload_utils, "initiate_deletion")
        upload_utils.initiate_deletion(req, location, image_meta['id'],
                                       mox.IsA(bool))
        self.mox.StubOutWithMock(upload_utils, "safe_kill")
        upload_utils.safe_kill(req, image_meta['id'], 'saving')
        notifier.error('image.upload', mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(webob.exc.HTTPPreconditionFailed,
                          upload_utils.upload_data_to_store,
                          req, image_meta, image_data, store, notifier)

        self.mox.VerifyAll()
