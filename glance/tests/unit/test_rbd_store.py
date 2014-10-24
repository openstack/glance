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

import mock
import six

from glance.common import exception
from glance.common import utils
from glance.openstack.common import units
from glance.store.location import Location
import glance.store.rbd as rbd_store
from glance.store.rbd import StoreLocation
from glance.tests.unit import base
from glance.tests.unit.fake_rados import mock_rados
from glance.tests.unit.fake_rados import mock_rbd


class TestStore(base.StoreClearingUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestStore, self).setUp()
        self.stubs.Set(rbd_store, 'rados', mock_rados)
        self.stubs.Set(rbd_store, 'rbd', mock_rbd)
        self.store = rbd_store.Store()
        self.store.chunk_size = 2
        self.called_commands_actual = []
        self.called_commands_expected = []
        self.store_specs = {'pool': 'fake_pool',
                            'image': 'fake_image',
                            'snapshot': 'fake_snapshot'}
        self.location = StoreLocation(self.store_specs)
        # Provide enough data to get more than one chunk iteration.
        self.data_len = 3 * units.Ki
        self.data_iter = six.StringIO('*' * self.data_len)

    def test_add_w_image_size_zero(self):
        """Assert that correct size is returned even though 0 was provided."""
        self.store.chunk_size = units.Ki
        with mock.patch.object(rbd_store.rbd.Image, 'resize') as resize:
            with mock.patch.object(rbd_store.rbd.Image, 'write') as write:
                ret = self.store.add('fake_image_id', self.data_iter, 0)

        resize.assert_called()
        write.assert_called()
        self.assertEqual(ret[1], self.data_len)

    def test_add_w_rbd_image_exception(self):
        def _fake_create_image(*args, **kwargs):
            self.called_commands_actual.append('create')
            return self.location

        def _fake_delete_image(*args, **kwargs):
            self.called_commands_actual.append('delete')

        def _fake_enter(*args, **kwargs):
            raise exception.NotFound("")

        self.stubs.Set(self.store, '_create_image', _fake_create_image)
        self.stubs.Set(self.store, '_delete_image', _fake_delete_image)
        self.stubs.Set(mock_rbd.Image, '__enter__', _fake_enter)

        self.assertRaises(exception.NotFound, self.store.add,
                          'fake_image_id', self.data_iter, self.data_len)

        self.called_commands_expected = ['create', 'delete']

    def test_add_duplicate_image(self):
        def _fake_create_image(*args, **kwargs):
            self.called_commands_actual.append('create')
            raise mock_rbd.ImageExists()

        self.stubs.Set(self.store, '_create_image', _fake_create_image)
        self.assertRaises(exception.Duplicate, self.store.add,
                          'fake_image_id', self.data_iter, self.data_len)
        self.called_commands_expected = ['create']

    def test_delete(self):
        def _fake_remove(*args, **kwargs):
            self.called_commands_actual.append('remove')

        self.stubs.Set(mock_rbd.RBD, 'remove', _fake_remove)
        self.store.delete(Location('test_rbd_store', StoreLocation,
                                   self.location.get_uri()))
        self.called_commands_expected = ['remove']

    def test__delete_image(self):
        def _fake_remove(*args, **kwargs):
            self.called_commands_actual.append('remove')

        self.stubs.Set(mock_rbd.RBD, 'remove', _fake_remove)
        self.store._delete_image('fake_pool', self.location)
        self.called_commands_expected = ['remove']

    def test__delete_image_w_snap(self):
        def _fake_unprotect_snap(*args, **kwargs):
            self.called_commands_actual.append('unprotect_snap')

        def _fake_remove_snap(*args, **kwargs):
            self.called_commands_actual.append('remove_snap')

        def _fake_remove(*args, **kwargs):
            self.called_commands_actual.append('remove')

        self.stubs.Set(mock_rbd.RBD, 'remove', _fake_remove)
        self.stubs.Set(mock_rbd.Image, 'unprotect_snap', _fake_unprotect_snap)
        self.stubs.Set(mock_rbd.Image, 'remove_snap', _fake_remove_snap)
        self.store._delete_image('fake_pool', self.location,
                                 snapshot_name='snap')

        self.called_commands_expected = ['unprotect_snap', 'remove_snap',
                                         'remove']

    def test__delete_image_w_snap_exc_image_not_found(self):
        def _fake_unprotect_snap(*args, **kwargs):
            self.called_commands_actual.append('unprotect_snap')
            raise mock_rbd.ImageNotFound()

        self.stubs.Set(mock_rbd.Image, 'unprotect_snap', _fake_unprotect_snap)
        self.assertRaises(exception.NotFound, self.store._delete_image,
                          'fake_pool', self.location, snapshot_name='snap')

        self.called_commands_expected = ['unprotect_snap']

    def test__delete_image_exc_image_not_found(self):
        def _fake_remove(*args, **kwargs):
            self.called_commands_actual.append('remove')
            raise mock_rbd.ImageNotFound()

        self.stubs.Set(mock_rbd.RBD, 'remove', _fake_remove)
        self.assertRaises(exception.NotFound, self.store._delete_image,
                          'fake_pool', self.location, snapshot_name='snap')

        self.called_commands_expected = ['remove']

    def test_image_size_exceeded_exception(self):
        def _fake_write(*args, **kwargs):
            if 'write' not in self.called_commands_actual:
                self.called_commands_actual.append('write')
            raise exception.ImageSizeLimitExceeded

        def _fake_delete_image(*args, **kwargs):
            self.called_commands_actual.append('delete')

        self.stubs.Set(mock_rbd.Image, 'write', _fake_write)
        self.stubs.Set(self.store, '_delete_image', _fake_delete_image)
        data = utils.LimitingReader(self.data_iter, self.data_len)
        self.assertRaises(exception.ImageSizeLimitExceeded,
                          self.store.add, 'fake_image_id',
                          data, self.data_len + 1)

        self.called_commands_expected = ['write', 'delete']

    def tearDown(self):
        self.assertEqual(self.called_commands_actual,
                         self.called_commands_expected)
        super(TestStore, self).tearDown()
