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

import contextlib
import StringIO

import stubout

from glance.common import exception
from glance.common import utils
from glance.store.rbd import Store
from glance.store.rbd import StoreLocation
from glance.tests.unit import base
try:
    import rados
    import rbd
except ImportError:
    rbd = None


RBD_CONF = {'verbose': True,
            'debug': True,
            'default_store': 'rbd'}
FAKE_CHUNKSIZE = 1


class TestStore(base.StoreClearingUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        self.config(**RBD_CONF)
        super(TestStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        self.store = Store()
        self.store.chunk_size = FAKE_CHUNKSIZE
        self.addCleanup(self.stubs.UnsetAll)

    def test_cleanup_when_add_image_exception(self):
        if rbd is None:
            msg = 'RBD store can not add images, skip test.'
            self.skipTest(msg)

        called_commands = []

        class FakeConnection(object):
            @contextlib.contextmanager
            def open_ioctx(self, *args, **kwargs):
                yield None

        class FakeImage(object):
            def write(self, *args, **kwargs):
                called_commands.append('write')
                return FAKE_CHUNKSIZE

        @contextlib.contextmanager
        def _fake_rados(*args, **kwargs):
            yield FakeConnection()

        @contextlib.contextmanager
        def _fake_image(*args, **kwargs):
            yield FakeImage()

        def _fake_create_image(*args, **kwargs):
            called_commands.append('create')
            return StoreLocation({'image': 'fake_image',
                                  'snapshot': 'fake_snapshot'})

        def _fake_delete_image(*args, **kwargs):
            called_commands.append('delete')

        self.stubs.Set(rados, 'Rados', _fake_rados)
        self.stubs.Set(rbd, 'Image', _fake_image)
        self.stubs.Set(self.store, '_create_image', _fake_create_image)
        self.stubs.Set(self.store, '_delete_image', _fake_delete_image)

        self.assertRaises(exception.ImageSizeLimitExceeded,
                          self.store.add,
                          'fake_image_id',
                          utils.LimitingReader(StringIO.StringIO('xx'), 1),
                          2)
        self.assertEqual(called_commands, ['create', 'write', 'delete'])
