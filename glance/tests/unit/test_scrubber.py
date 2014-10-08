# Copyright 2013 Red Hat, Inc.
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

import os
import shutil
import tempfile
import uuid

import eventlet
import glance_store
import mox
from oslo.config import cfg

from glance.common import exception
from glance import scrubber
from glance.tests import utils as test_utils

CONF = cfg.CONF


class TestScrubber(test_utils.BaseTestCase):

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.config(scrubber_datadir=self.data_dir)
        glance_store.register_opts(CONF)
        glance_store.create_stores()
        self.config(group='glance_store', default_store='file')
        self.mox = mox.Mox()
        super(TestScrubber, self).setUp()

    def tearDown(self):
        self.mox.UnsetStubs()
        shutil.rmtree(self.data_dir)
        # These globals impact state outside of this test class, kill them.
        scrubber._file_queue = None
        scrubber._db_queue = None
        super(TestScrubber, self).tearDown()

    def _scrubber_cleanup_with_store_delete_exception(self, ex):
        uri = 'file://some/path/%s' % uuid.uuid4()
        id = 'helloworldid'
        scrub = scrubber.Scrubber(glance_store)
        scrub.registry = self.mox.CreateMockAnything()
        scrub.registry.get_image(id).AndReturn({'status': 'pending_delete'})
        scrub.registry.update_image(id, {'status': 'deleted'})
        self.mox.StubOutWithMock(glance_store, "delete_from_backend")
        glance_store.delete_from_backend(
            uri,
            mox.IgnoreArg()).AndRaise(ex)
        self.mox.ReplayAll()
        scrub._scrub_image(eventlet.greenpool.GreenPool(1),
                           id, [(id, '-', uri)])
        self.mox.VerifyAll()

        q_path = os.path.join(self.data_dir, id)
        self.assertFalse(os.path.exists(q_path))

    def test_store_delete_unsupported_backend_exception(self):
        ex = glance_store.UnsupportedBackend()
        self._scrubber_cleanup_with_store_delete_exception(ex)

    def test_store_delete_notfound_exception(self):
        ex = exception.NotFound()
        self._scrubber_cleanup_with_store_delete_exception(ex)
