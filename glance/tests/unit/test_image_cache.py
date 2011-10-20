# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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
import random
import shutil
import StringIO
import unittest

from glance import image_cache
from glance.common import exception

FIXTURE_DATA = '*' * 1024


class TestImageCache(unittest.TestCase):
    def setUp(self):
        self.cache_dir = os.path.join("/", "tmp", "test.cache.%d" %
                                      random.randint(0, 1000000))
        self.options = {'image_cache_datadir': self.cache_dir}
        self.cache = image_cache.ImageCache(self.options)

    def tearDown(self):
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)

    def test_auto_properties(self):
        """
        Test that the auto-assigned properties are correct
        """
        self.assertEqual(self.cache.path, self.cache_dir)
        self.assertEqual(self.cache.invalid_path,
                         os.path.join(self.cache_dir,
                                      'invalid'))
        self.assertEqual(self.cache.incomplete_path,
                         os.path.join(self.cache_dir,
                                      'incomplete'))
        self.assertEqual(self.cache.prefetch_path,
                         os.path.join(self.cache_dir,
                                      'prefetch'))
        self.assertEqual(self.cache.prefetching_path,
                         os.path.join(self.cache_dir,
                                      'prefetching'))

    def test_hit(self):
        """
        Verify hit(1) returns 0, then add something to the cache
        and verify hit(1) returns 1.
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        self.assertFalse(self.cache.hit(1))

        with self.cache.open(meta, 'wb') as cache_file:
            cache_file.write(FIXTURE_DATA)

        self.assertTrue(self.cache.hit(1))

    def test_bad_open_mode(self):
        """
        Test than an exception is raised if attempting to open
        the cache file context manager with an invalid mode string
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        bad_modes = ('xb', 'wa', 'rw')
        for mode in bad_modes:
            exc_raised = False
            try:
                with self.cache.open(meta, 'xb') as cache_file:
                    cache_file.write(FIXTURE_DATA)
            except:
                exc_raised = True
            self.assertTrue(exc_raised,
                            'Using mode %s, failed to raise exception.' % mode)

    def test_read(self):
        """
        Verify hit(1) returns 0, then add something to the cache
        and verify after a subsequent read from the cache that
        hit(1) returns 1.
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        self.assertFalse(self.cache.hit(1))

        with self.cache.open(meta, 'wb') as cache_file:
            cache_file.write(FIXTURE_DATA)

        buff = StringIO.StringIO()
        with self.cache.open(meta, 'rb') as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.assertEqual(FIXTURE_DATA, buff.getvalue())

    def test_open_for_read(self):
        """
        Test convenience wrapper for opening a cache file via
        its image identifier.
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        self.assertFalse(self.cache.hit(1))

        with self.cache.open(meta, 'wb') as cache_file:
            cache_file.write(FIXTURE_DATA)

        buff = StringIO.StringIO()
        with self.cache.open_for_read(1) as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.assertEqual(FIXTURE_DATA, buff.getvalue())

    def test_purge(self):
        """
        Test purge method that removes an image from the cache
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        self.assertFalse(self.cache.hit(1))

        with self.cache.open(meta, 'wb') as cache_file:
            cache_file.write(FIXTURE_DATA)

        self.assertTrue(self.cache.hit(1))

        self.cache.purge(1)

        self.assertFalse(self.cache.hit(1))

    def test_clear(self):
        """
        Test purge method that removes an image from the cache
        """
        metas = [
            {'id': 1,
             'name': 'Image1',
             'size': len(FIXTURE_DATA)},
            {'id': 2,
             'name': 'Image2',
             'size': len(FIXTURE_DATA)}]

        for image_id in (1, 2):
            self.assertFalse(self.cache.hit(image_id))

        for meta in metas:
            with self.cache.open(meta, 'wb') as cache_file:
                cache_file.write(FIXTURE_DATA)

        for image_id in (1, 2):
            self.assertTrue(self.cache.hit(image_id))

        self.cache.clear()

        for image_id in (1, 2):
            self.assertFalse(self.cache.hit(image_id))

    def test_prefetch(self):
        """
        Test that queueing for prefetch and prefetching works properly
        """
        meta = {'id': 1,
                'name': 'Image1',
                'size': len(FIXTURE_DATA)}

        self.assertFalse(self.cache.hit(1))

        self.cache.queue_prefetch(meta)

        self.assertFalse(self.cache.hit(1))

        # Test that an exception is raised if we try to queue the
        # same image for prefetching
        self.assertRaises(exception.Invalid, self.cache.queue_prefetch,
                          meta)

        self.cache.delete_queued_prefetch_image(1)

        self.assertFalse(self.cache.hit(1))

        # Test that an exception is raised if we try to queue for
        # prefetching an image that has already been cached

        with self.cache.open(meta, 'wb') as cache_file:
            cache_file.write(FIXTURE_DATA)

        self.assertTrue(self.cache.hit(1))

        self.assertRaises(exception.Invalid, self.cache.queue_prefetch,
                          meta)

        self.cache.purge(1)

        # We can't prefetch an image that has not been queued
        # for prefetching
        self.assertRaises(OSError, self.cache.do_prefetch, 1)

        self.cache.queue_prefetch(meta)

        self.assertTrue(self.cache.is_image_queued_for_prefetch(1))

        self.assertFalse(self.cache.is_currently_prefetching_any_images())
        self.assertFalse(self.cache.is_image_currently_prefetching(1))

        self.assertEqual(str(1), self.cache.pop_prefetch_item())

        self.cache.do_prefetch(1)
        self.assertFalse(self.cache.is_image_queued_for_prefetch(1))
        self.assertTrue(self.cache.is_currently_prefetching_any_images())
        self.assertTrue(self.cache.is_image_currently_prefetching(1))
