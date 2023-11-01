# Copyright 2024 Red Hat, Inc.
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


import datetime
import errno
import io
import os
import time
from unittest import mock

from oslo_utils import fileutils

from glance.image_cache.drivers import centralized_db
from glance.tests import functional


DATA = b'IMAGEDATA'


class TestCentralizedDb(functional.SynchronousAPIBase):
    # ToDo(abhishekk): Once system scope is enabled and RBAC is fully
    # supported, enable these tests for RBAC as well
    def setUp(self):
        super(TestCentralizedDb, self).setUp()

    def start_server(self, enable_cache=True, set_worker_url=True):
        if set_worker_url:
            self.config(worker_self_reference_url='http://workerx')
            self.config(image_cache_driver='centralized_db')

        super(TestCentralizedDb, self).start_server(enable_cache=enable_cache)

    def load_data(self):
        output = {}
        # Create 1 queued image as well for testing
        path = "/v2/images"
        data = {
            'name': 'queued-image',
            'container_format': 'bare',
            'disk_format': 'raw'
        }
        response = self.api_post(path, json=data)
        self.assertEqual(201, response.status_code)
        image_id = response.json['id']
        output['queued'] = image_id

        for visibility in ['public', 'private']:
            data = {
                'name': '%s-image' % visibility,
                'visibility': visibility,
                'container_format': 'bare',
                'disk_format': 'raw'
            }
            response = self.api_post(path, json=data)
            self.assertEqual(201, response.status_code)
            image_id = response.json['id']
            # Upload some data to image
            response = self.api_put(
                '/v2/images/%s/file' % image_id,
                headers={'Content-Type': 'application/octet-stream'},
                data=DATA)
            self.assertEqual(204, response.status_code)
            output[visibility] = image_id

        return output

    def wait_for_caching(self, image_id, max_sec=10, delay_sec=0.2,
                         start_delay_sec=None):
        start_time = time.time()
        done_time = start_time + max_sec
        if start_delay_sec:
            time.sleep(start_delay_sec)
        while time.time() <= done_time:
            output = self.list_cache()['cached_images']
            output = [image['image_id'] for image in output]
            if output and image_id in output:
                return
            time.sleep(delay_sec)

        msg = "Image {0} failed to cached within {1} sec"
        raise Exception(msg.format(image_id, max_sec))

    def list_cache(self, expected_code=200):
        path = '/v2/cache'
        response = self.api_get(path)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            return response.json

    def test_centralized_db_worker_url_not_set(self):
        try:
            self.config(image_cache_driver='centralized_db')
            self.start_server(enable_cache=True, set_worker_url=False)
        except RuntimeError as e:
            expected_message = "'worker_self_reference_url' needs to be set " \
                               "if `centralized_db` is defined as cache " \
                               "driver for image_cache_driver config option."
            self.assertIn(expected_message, e.args)

    def test_centralized_db_verify_worker_node_is_set(self):
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.assertEqual(
            'http://workerx', self.driver.db_api.node_reference_get_by_url(
                self.driver.context, 'http://workerx').node_reference_url)

    def test_get_cache_size(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify initially cache size is 0
        self.assertEqual(0, self.driver.get_cache_size())

        # Cache one image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])

        # Verify cache size is equal to len(DATA) i.e. 9
        self.assertEqual(len(DATA), self.driver.get_cache_size())

    def test_get_hit_count(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify that hit count is currently 0 as no image is cached
        self.assertEqual(0, self.driver.get_hit_count(images['public']))

        # Cache one image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))

        # Verify that hit count is still 0 as image is cached, but
        # not downloaded yet from cache
        self.assertEqual(0, self.driver.get_hit_count(images['public']))

        # Download the image
        path = '/v2/images/%s/file' % images['public']
        response = self.api_get(path)
        self.assertEqual('IMAGEDATA', response.text)
        # Verify that hit count is 1 as we hit the cache
        self.assertEqual(1, self.driver.get_hit_count(images['public']))

        # Download the image again
        path = '/v2/images/%s/file' % images['public']
        response = self.api_get(path)
        self.assertEqual('IMAGEDATA', response.text)
        # Verify that hit count is 2 as we hit the cache
        self.assertEqual(2, self.driver.get_hit_count(images['public']))

    def test_get_cached_images(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify that initially there are no cached image(s)
        self.assertEqual(0, len(self.driver.get_cached_images()))

        # Cache one image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))

        # Verify that there is one cached imgae now
        self.assertEqual(1, len(self.driver.get_cached_images()))

        # Verify that passing non-existing node will be
        # returned as 0 cached images
        self.config(worker_self_reference_url="http://fake-worker")
        self.assertEqual(0, len(self.driver.get_cached_images()))

    def test_is_cacheable(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify that is_cacheable will return true as image is not cached yet
        self.assertTrue(self.driver.is_cacheable(images['public']))

        # Now cache the image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))

        # Verify that now above image is not cachable
        self.assertFalse(self.driver.is_cacheable(images['public']))

    def test_is_being_cached(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify that is_being_cached will return False as
        # image is not cached yet
        self.assertFalse(self.driver.is_being_cached(images['public']))

    def test_is_queued(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify that is_queued will return False as
        # image is not queued for caching yet
        self.assertFalse(self.driver.is_queued(images['public']))

        # Now queue image for caching
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.assertTrue(self.driver.is_queued(images['public']))

    def test_delete_cached_image(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify deleting non-existing image from cache will not fail
        self.driver.delete_cached_image('fake-image-id')

        # Now cache the image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))
        self.assertEqual(1, len(self.driver.get_cached_images()))

        # Delete the image from cache
        self.driver.delete_cached_image(images['public'])

        # Verify image is deleted from cache
        self.assertFalse(self.driver.is_cached(images['public']))
        self.assertEqual(0, len(self.driver.get_cached_images()))

    def test_delete_all_cached_images(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify no image is cached yet
        self.assertEqual(0, len(self.driver.get_cached_images()))

        # Verify delete call should not fail even if no images are cached
        self.driver.delete_all_cached_images()

        # Now cache the image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))
        self.assertEqual(1, len(self.driver.get_cached_images()))

        # Now cache another image
        path = '/v2/cache/%s' % images['private']
        self.api_put(path)
        self.wait_for_caching(images['private'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['private']))
        self.assertEqual(2, len(self.driver.get_cached_images()))

        # Delete all the images form cache
        self.driver.delete_all_cached_images()

        # Verify images are deleted from cache
        self.assertEqual(0, len(self.driver.get_cached_images()))

    def test_delete_queued_image(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify deleting non-existing image from queued dir will not fail
        self.driver.delete_queued_image('fake-image-id')

        # Now queue imgae for caching
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        # verify image is queued
        self.assertTrue(self.driver.is_queued(images['public']))
        self.assertEqual(1, len(self.driver.get_queued_images()))

        # Delete the image from queued dir
        self.driver.delete_queued_image(images['public'])

        # Verify image is deleted from cache
        self.assertFalse(self.driver.is_queued(images['public']))
        self.assertEqual(0, len(self.driver.get_queued_images()))

    def test_delete_all_queued_images(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()
        # Verify no image is cached yet
        self.assertEqual(0, len(self.driver.get_queued_images()))

        # Verify delete call should not fail even if no images are queued
        self.driver.delete_all_queued_images()

        # Now queue the image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        # verify image is queued
        self.assertTrue(self.driver.is_queued(images['public']))
        self.assertEqual(1, len(self.driver.get_queued_images()))

        # Now queue another image
        path = '/v2/cache/%s' % images['private']
        self.api_put(path)
        # verify image is queued
        self.assertTrue(self.driver.is_queued(images['private']))
        self.assertEqual(2, len(self.driver.get_queued_images()))

        # Delete all the images form queued dir
        self.driver.delete_all_queued_images()

        # Verify images are deleted from cache
        self.assertEqual(0, len(self.driver.get_queued_images()))

    def test_clean(self):
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()
        cache_dir = os.path.join(self.test_dir, 'cache')
        incomplete_file_path = os.path.join(cache_dir, 'incomplete', '1')
        incomplete_file = open(incomplete_file_path, 'wb')
        incomplete_file.write(DATA)
        incomplete_file.close()

        self.assertTrue(os.path.exists(incomplete_file_path))

        self.delay_inaccurate_clock()
        self.driver.clean(stall_time=0)

        self.assertFalse(os.path.exists(incomplete_file_path))

    def _test_clean_stall_time(
            self, stall_time=None, days=2, stall_failed=False):
        """
        Test the clean method removes the stalled images as expected
        """
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()

        cache_dir = os.path.join(self.test_dir, 'cache')
        incomplete_file_path_1 = os.path.join(cache_dir,
                                              'incomplete', '1')
        incomplete_file_path_2 = os.path.join(cache_dir,
                                              'incomplete', '2')

        for f in (incomplete_file_path_1, incomplete_file_path_2):
            incomplete_file = open(f, 'wb')
            incomplete_file.write(DATA)
            incomplete_file.close()

        mtime = os.path.getmtime(incomplete_file_path_1)
        pastday = (datetime.datetime.fromtimestamp(mtime) -
                   datetime.timedelta(days=days))
        atime = int(time.mktime(pastday.timetuple()))
        mtime = atime
        os.utime(incomplete_file_path_1, (atime, mtime))

        self.assertTrue(os.path.exists(incomplete_file_path_1))
        self.assertTrue(os.path.exists(incomplete_file_path_2))

        # If stall_time is None then it will wait for default time
        # of `image_cache_stall_time` which is 24 hours
        if stall_failed:
            with mock.patch.object(
                    fileutils, 'delete_if_exists') as mock_delete:
                mock_delete.side_effect = OSError(errno.ENOENT, '')
                self.driver.clean(stall_time=stall_time)
                self.assertTrue(os.path.exists(incomplete_file_path_1))
        else:
            self.driver.clean(stall_time=stall_time)
            self.assertFalse(os.path.exists(incomplete_file_path_1))

        self.assertTrue(os.path.exists(incomplete_file_path_2))

    def test_clean_stalled_none_stall_time(self):
        self._test_clean_stall_time()

    def test_clean_stalled_nonzero_stall_time(self):
        """Test the clean method removes expected images."""
        self._test_clean_stall_time(stall_time=3600, days=1)

    def test_clean_stalled_fails(self):
        """Test the clean method fails to delete file, ignores the failure"""
        self._test_clean_stall_time(stall_time=3600, days=1,
                                    stall_failed=True)

    def test_least_recently_accessed(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        self.driver = centralized_db.Driver()
        self.driver.configure()

        # Verify no image is cached yet
        self.assertEqual(0, len(self.driver.get_cached_images()))

        # Verify delete call should not fail even if no images are cached
        self.driver.delete_all_cached_images()

        # Now cache the image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))
        self.assertEqual(1, len(self.driver.get_cached_images()))

        # Now cache another image
        path = '/v2/cache/%s' % images['private']
        self.api_put(path)
        self.wait_for_caching(images['private'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['private']))
        self.assertEqual(2, len(self.driver.get_cached_images()))

        # Verify that 1st image will be returned
        image_id, size = self.driver.get_least_recently_accessed()
        self.assertEqual(images['public'], image_id)
        self.assertEqual(len(DATA), size)

    def test_open_for_write_good(self):
        """
        Test to see if open_for_write works in normal case
        """
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()

        # test a good case
        image_id = '1'
        self.assertFalse(self.driver.is_cached(image_id))
        with self.driver.open_for_write(image_id) as cache_file:
            cache_file.write(b'a')
        self.assertTrue(self.driver.is_cached(image_id),
                        "Image %s was NOT cached!" % image_id)

        # make sure it has tidied up
        cache_dir = os.path.join(self.test_dir, 'cache')
        incomplete_file_path = os.path.join(cache_dir,
                                            'incomplete', image_id)
        cache_file_path = os.path.join(cache_dir, image_id)
        invalid_file_path = os.path.join(cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertFalse(os.path.exists(invalid_file_path))
        self.assertTrue(os.path.exists(cache_file_path))

    def test_open_for_write_with_exception(self):
        """
        Test to see if open_for_write works in a failure case for each driver
        This case is where an exception is raised while the file is being
        written. The image is partially filled in cache and filling won't
        resume so verify the image is moved to invalid/ directory
        """
        # test a case where an exception is raised while the file is open

        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()

        image_id = '1'
        self.assertFalse(self.driver.is_cached(image_id))
        try:
            with self.driver.open_for_write(image_id):
                raise IOError
        except Exception as e:
            self.assertIsInstance(e, IOError)
        self.assertFalse(self.driver.is_cached(image_id),
                         "Image %s was cached!" % image_id)
        # make sure it has tidied up
        cache_dir = os.path.join(self.test_dir, 'cache')
        incomplete_file_path = os.path.join(cache_dir,
                                            'incomplete', image_id)
        invalid_file_path = os.path.join(cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertTrue(os.path.exists(invalid_file_path))

    def test_open_for_read_good(self):
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()
        images = self.load_data()

        self.assertFalse(self.driver.is_cached(images['public']))
        # Cache one image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))
        # verify cache hit count for above image is 0
        self.assertEqual(0, self.driver.get_hit_count(images['public']))
        # Open image for read
        buff = io.BytesIO()
        with self.driver.open_for_read(images['public']) as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.assertEqual(DATA, buff.getvalue())
        # verify now cache hit count for above image is 1
        self.assertEqual(1, self.driver.get_hit_count(images['public']))

    def test_open_for_read_with_exception(self):
        self.start_server(enable_cache=True)
        self.driver = centralized_db.Driver()
        self.driver.configure()
        images = self.load_data()

        self.assertFalse(self.driver.is_cached(images['public']))
        # Cache one image
        path = '/v2/cache/%s' % images['public']
        self.api_put(path)
        self.wait_for_caching(images['public'])
        # verify image is cached
        self.assertTrue(self.driver.is_cached(images['public']))
        # verify cache hit count for above image is 0
        self.assertEqual(0, self.driver.get_hit_count(images['public']))
        # Open image for read
        buff = io.BytesIO()
        try:
            with self.driver.open_for_read(images['public']):
                raise IOError
        except Exception as e:
            self.assertIsInstance(e, IOError)

        self.assertEqual(b'', buff.getvalue())
        # verify now cache hit count for above image is 1 even exception is
        # raised
        self.assertEqual(1, self.driver.get_hit_count(images['public']))
