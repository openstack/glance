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
from mock import patch
from mox3 import mox
from oslo_config import cfg
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

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


class TestScrubDBQueue(test_utils.BaseTestCase):

    def setUp(self):
        super(TestScrubDBQueue, self).setUp()

    def tearDown(self):
        super(TestScrubDBQueue, self).tearDown()

    def _create_image_list(self, count):
        images = []
        for x in range(count):
            images.append({'id': x})

        return images

    def test_get_all_images(self):
        scrub_queue = scrubber.ScrubDBQueue()
        images = self._create_image_list(15)
        image_pager = ImagePager(images)

        def make_get_images_detailed(pager):
            def mock_get_images_detailed(filters, marker=None):
                return pager()
            return mock_get_images_detailed

        with patch.object(scrub_queue.registry, 'get_images_detailed') \
                as _mock_get_images_detailed:
            _mock_get_images_detailed.side_effect = \
                make_get_images_detailed(image_pager)
            actual = list(scrub_queue._get_all_images())

        self.assertEqual(images, actual)

    def test_get_all_images_paged(self):
        scrub_queue = scrubber.ScrubDBQueue()
        images = self._create_image_list(15)
        image_pager = ImagePager(images, page_size=4)

        def make_get_images_detailed(pager):
            def mock_get_images_detailed(filters, marker=None):
                return pager()
            return mock_get_images_detailed

        with patch.object(scrub_queue.registry, 'get_images_detailed') \
                as _mock_get_images_detailed:
            _mock_get_images_detailed.side_effect = \
                make_get_images_detailed(image_pager)
            actual = list(scrub_queue._get_all_images())

        self.assertEqual(images, actual)


class ImagePager(object):
    def __init__(self, images, page_size=0):
        image_count = len(images)
        if page_size == 0 or page_size > image_count:
            page_size = image_count
        self.image_batches = []
        start = 0
        l = len(images)
        while start < l:
            self.image_batches.append(images[start: start + page_size])
            start += page_size
            if (l - start) < page_size:
                page_size = l - start

    def __call__(self):
        if len(self.image_batches) == 0:
            return []
        else:
            return self.image_batches.pop(0)
