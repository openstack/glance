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

from unittest import mock
from unittest.mock import patch
import uuid

import glance_store
from oslo_config import cfg

from glance.common import exception
from glance.db.sqlalchemy import api as db_api
from glance import scrubber
from glance.tests import utils as test_utils

CONF = cfg.CONF


class TestScrubber(test_utils.BaseTestCase):

    def setUp(self):
        super(TestScrubber, self).setUp()
        glance_store.register_opts(CONF)
        self.config(group='glance_store', default_store='file',
                    filesystem_store_datadir=self.test_dir)
        glance_store.create_stores()

    def tearDown(self):
        # These globals impact state outside of this test class, kill them.
        scrubber._file_queue = None
        scrubber._db_queue = None
        super(TestScrubber, self).tearDown()

    def _scrubber_cleanup_with_store_delete_exception(self, ex):
        uri = 'file://some/path/%s' % uuid.uuid4()
        id = 'helloworldid'
        scrub = scrubber.Scrubber(glance_store)
        with patch.object(glance_store,
                          "delete_from_backend") as _mock_delete:
            _mock_delete.side_effect = ex
            scrub._scrub_image(id, [(id, '-', uri)])

    @mock.patch.object(db_api, "image_get")
    def test_store_delete_successful(self, mock_image_get):
        uri = 'file://some/path/%s' % uuid.uuid4()
        id = 'helloworldid'

        scrub = scrubber.Scrubber(glance_store)
        with patch.object(glance_store,
                          "delete_from_backend"):
            scrub._scrub_image(id, [(id, '-', uri)])

    @mock.patch.object(db_api, "image_get")
    def test_store_delete_store_exceptions(self, mock_image_get):
        # While scrubbing image data, all store exceptions, other than
        # NotFound, cause image scrubbing to fail. Essentially, no attempt
        # would be made to update the status of image.

        uri = 'file://some/path/%s' % uuid.uuid4()
        id = 'helloworldid'
        ex = glance_store.GlanceStoreException()

        scrub = scrubber.Scrubber(glance_store)
        with patch.object(glance_store,
                          "delete_from_backend") as _mock_delete:
            _mock_delete.side_effect = ex
            scrub._scrub_image(id, [(id, '-', uri)])

    @mock.patch.object(db_api, "image_get")
    def test_store_delete_notfound_exception(self, mock_image_get):
        # While scrubbing image data, NotFound exception is ignored and image
        # scrubbing succeeds
        uri = 'file://some/path/%s' % uuid.uuid4()
        id = 'helloworldid'
        ex = glance_store.NotFound(message='random')

        scrub = scrubber.Scrubber(glance_store)
        with patch.object(glance_store,
                          "delete_from_backend") as _mock_delete:
            _mock_delete.side_effect = ex
            scrub._scrub_image(id, [(id, '-', uri)])

    def test_scrubber_exits(self):
        # Checks for Scrubber exits when it is not able to fetch jobs from
        # the queue
        scrub_jobs = scrubber.ScrubDBQueue.get_all_locations
        scrub_jobs = mock.MagicMock()
        scrub_jobs.side_effect = exception.NotFound
        scrub = scrubber.Scrubber(glance_store)
        self.assertRaises(exception.FailedToGetScrubberJobs,
                          scrub._get_delete_jobs)

    @mock.patch.object(db_api, "image_restore")
    def test_scrubber_revert_image_status(self, mock_image_restore):
        scrub = scrubber.Scrubber(glance_store)
        scrub.revert_image_status('fake_id')

        mock_image_restore.side_effect = exception.ImageNotFound
        self.assertRaises(exception.ImageNotFound,
                          scrub.revert_image_status,
                          'fake_id')

        mock_image_restore.side_effect = exception.Conflict
        self.assertRaises(exception.Conflict,
                          scrub.revert_image_status,
                          'fake_id')


class TestScrubDBQueue(test_utils.BaseTestCase):

    def setUp(self):
        super(TestScrubDBQueue, self).setUp()

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
            def mock_get_images_detailed(ctx, filters, marker=None,
                                         limit=None):
                return pager()
            return mock_get_images_detailed

        with patch.object(db_api, 'image_get_all') as (
                _mock_get_images_detailed):
            _mock_get_images_detailed.side_effect = (
                make_get_images_detailed(image_pager))
            actual = list(scrub_queue._get_all_images())

        self.assertEqual(images, actual)

    def test_get_all_images_paged(self):
        scrub_queue = scrubber.ScrubDBQueue()
        images = self._create_image_list(15)
        image_pager = ImagePager(images, page_size=4)

        def make_get_images_detailed(pager):
            def mock_get_images_detailed(ctx, filters, marker=None,
                                         limit=None):
                return pager()
            return mock_get_images_detailed

        with patch.object(db_api, 'image_get_all') as (
                _mock_get_images_detailed):
            _mock_get_images_detailed.side_effect = (
                make_get_images_detailed(image_pager))
            actual = list(scrub_queue._get_all_images())

        self.assertEqual(images, actual)


class ImagePager(object):
    def __init__(self, images, page_size=0):
        image_count = len(images)
        if page_size == 0 or page_size > image_count:
            page_size = image_count
        self.image_batches = []
        start = 0
        while start < image_count:
            self.image_batches.append(images[start: start + page_size])
            start += page_size
            if (image_count - start) < page_size:
                page_size = image_count - start

    def __call__(self):
        if len(self.image_batches) == 0:
            return []
        else:
            return self.image_batches.pop(0)
