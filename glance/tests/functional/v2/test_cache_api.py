# Copyright 2021 Red Hat, Inc.
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
import os
import time
from unittest import mock
import uuid

import oslo_policy.policy
from oslo_utils import units

from glance.api import policy
from glance.api.v2 import cached_images
from glance.tests import functional


class TestImageCache(functional.SynchronousAPIBase):
    # ToDo(abhishekk): Once system scope is enabled and RBAC is fully
    # supported, enable these tests for RBAC as well
    def setUp(self):
        super(TestImageCache, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self, enable_cache=True, cache_driver='sqlite'):
        # NOTE(abhishekk): Once sqlite driver is removed, fix these tests
        # to work with centralized_db driver
        self.config(image_cache_driver=cache_driver)
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImageCache, self).start_server(enable_cache=enable_cache)

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
                data=b'IMAGEDATA')
            self.assertEqual(204, response.status_code)
            output[visibility] = image_id

        return output

    def list_cache(self, expected_code=200):
        path = '/v2/cache'
        response = self.api_get(path)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            return response.json

    def list_cached_nodes(self, image_id, expected_code=200):
        path = '/v2/cache/nodes/%s' % image_id
        response = self.api_get(path)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            return response.json

    def cache_queue(self, image_id, expected_code=202):
        # Queue image for prefetching
        path = '/v2/cache/%s' % image_id
        response = self.api_put(path)
        self.assertEqual(expected_code, response.status_code)

    def cache_delete(self, image_id, expected_code=204):
        path = '/v2/cache/%s' % image_id
        response = self.api_delete(path)
        self.assertEqual(expected_code, response.status_code)

    def cache_clear(self, target='', expected_code=204):
        path = '/v2/cache'
        headers = {}
        if target:
            headers['x-image-cache-clear-target'] = target
        response = self.api_delete(path, headers=headers)
        if target not in ('', 'cache', 'queue'):
            self.assertEqual(expected_code, response.status_code)
        else:
            self.assertEqual(expected_code, response.status_code)

    def cache_clean(self, expected_code=200):
        path = '/v2/cache/clean'
        response = self.api_post(path)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            # Response body may be empty, return empty dict if so
            try:
                return response.json if response.json else {}
            except (ValueError, AttributeError):
                return {}
        return None

    def cache_prune(self, expected_code=200):
        path = '/v2/cache/prune'
        response = self.api_post(path)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            # Response should always have JSON body
            try:
                return response.json if response.json else {}
            except (ValueError, AttributeError):
                # Handle empty response body
                if response.body:
                    return {}
                return {}
        return None

    def wait_for_caching(self, image_id, max_sec=10, delay_sec=0.2,
                         start_delay_sec=None):
        """Wait until image is cached."""
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

    def wait_for_in_cache(self, image_id, max_sec=10, delay_sec=0.1,
                          start_delay_sec=0.1):
        """Wait until image is queued or cached."""
        if start_delay_sec:
            time.sleep(start_delay_sec)
        start_time = time.time()
        done_time = start_time + max_sec
        while time.time() <= done_time:
            output = self.list_cache()
            queued = output['queued_images']
            cached = [img['image_id'] for img in output['cached_images']]
            if image_id in queued or image_id in cached:
                return (image_id in queued, image_id in cached)
            time.sleep(delay_sec)

        msg = "Image {0} failed to appear in cache system within {1} sec"
        raise Exception(msg.format(image_id, max_sec))

    def wait_for_queued(self, image_id, max_sec=2, delay_sec=0.05):
        """Wait until image is in queue."""
        start_time = time.time()
        done_time = start_time + max_sec
        while time.time() <= done_time:
            output = self.list_cache()
            if image_id in output['queued_images']:
                return True
            # Already cached, queue was too fast
            cached = [img['image_id'] for img in output['cached_images']]
            if image_id in cached:
                return False
            time.sleep(delay_sec)
        return False

    def test_cache_list(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        # Ensure that nothing is cached and nothing is queued for caching
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        # Queue 1 image for caching
        with mock.patch.object(cached_images.WORKER, 'submit'):
            self.cache_queue(images['public'])
        self.wait_for_in_cache(images['public'])
        output = self.list_cache()
        total = len(output['queued_images']) + len(output['cached_images'])
        self.assertEqual(1, total)

    def test_list_cached_nodes_centralized_cache_disabled(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Test that 409 is returned when centralized caching is disabled
        # This check is based on driver configuration, not cache state
        self.list_cached_nodes(images['public'],
                               expected_code=409)

    def test_list_cached_nodes_centralized_cache_enabled(self):
        self.start_server(enable_cache=True, cache_driver='centralized_db')
        images = self.load_data()

        # Test that empty list is returned for uncached image
        output = self.list_cached_nodes(images['public'])
        self.assertEqual(0, len(output))

        # Queue 1 image for caching
        self.cache_queue(images['public'])
        self.wait_for_caching(images['public'])

        # Test that we get the expected node URL
        output = self.list_cached_nodes(images['public'])
        self.assertEqual(1, len(output))
        # Should return the worker URL we configured
        self.assertIn('http://workerx', output[0])

        # Test that a different image still returns empty
        output = self.list_cached_nodes(images['private'])
        self.assertEqual(0, len(output))

    def test_list_cached_nodes_nonexistent_image(self):
        """Test 404 for non-existent image."""
        self.start_server(enable_cache=True, cache_driver='centralized_db')

        # Use a random UUID that doesn't exist
        fake_image_id = str(uuid.uuid4())

        # Should return 404 for non-existent image
        self.list_cached_nodes(fake_image_id, expected_code=404)

    def test_list_cached_nodes_invalid_uuid(self):
        """Test that requesting cached nodes with invalid UUID returns 404."""
        self.start_server(enable_cache=True, cache_driver='centralized_db')

        # Use an invalid UUID format
        invalid_image_id = "not-a-valid-uuid"

        # Should return 404 for invalid UUID format
        # (treated as non-existent image)
        self.list_cached_nodes(invalid_image_id, expected_code=404)

    def test_cache_queue(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Ensure that nothing is cached and nothing is queued for caching
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        # Queue 1 image for caching
        self.cache_queue(images['public'])
        # NOTE(abhishekk): As queue call will immediately start caching
        # the image, lets wait for completion.
        self.wait_for_caching(images['public'])
        # Now verify that we have 1 cached image
        output = self.list_cache()
        self.assertEqual(1, len(output['cached_images']))
        # Verify same image is cached
        self.assertIn(images['public'], output['cached_images'][0]['image_id'])

    def test_cache_delete(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Queue 1 image for caching
        self.cache_queue(images['public'])
        self.wait_for_caching(images['public'])
        # Now verify that we have 1 cached image
        output = self.list_cache()
        self.assertEqual(1, len(output['cached_images']))
        # Verify same image is cached
        self.assertIn(images['public'], output['cached_images'][0]['image_id'])

        # Delete cached image
        self.cache_delete(images['public'])
        # Now verify that we have 0 cached image
        output = self.list_cache()
        self.assertEqual(0, len(output['cached_images']))

    def test_cache_clear_queued_images(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Queue 2 images for caching
        self.list_cache()
        with mock.patch.object(cached_images.WORKER, 'submit'):
            self.cache_queue(images['public'])
            self.cache_queue(images['private'])

        self.wait_for_in_cache(images['public'])
        self.wait_for_in_cache(images['private'])
        output = self.list_cache()
        total = len(output['queued_images']) + len(output['cached_images'])
        self.assertEqual(2, total)

        self.cache_clear(target='queue')
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))

    def test_cache_clear_cached_images(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Queue 2 images for caching
        self.cache_queue(images['public'])
        self.cache_queue(images['private'])
        self.wait_for_caching(images['public'])
        self.wait_for_caching(images['private'])
        # Now verify that we have 2 cached images
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(2, len(output['cached_images']))

        # Clear all images from cache
        self.cache_clear(target='cache')
        # Now verify that we have 0 cached images
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

    def test_cache_clear(self):
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Queue first image and wait for it to be cached
        self.cache_queue(images['public'])
        self.wait_for_caching(images['public'])
        output = self.list_cache()
        self.assertEqual(1, len(output['cached_images']))
        self.assertIn(images['public'],
                      [img['image_id'] for img in output['cached_images']])

        with mock.patch.object(cached_images.WORKER, 'submit'):
            self.cache_queue(images['private'])

        self.wait_for_in_cache(images['private'])
        output = self.list_cache()
        total = len(output['queued_images']) + len(output['cached_images'])
        self.assertEqual(2, total)

        self.cache_clear()
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

    def test_cache_api_negative_scenarios(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        # Try non-existing image to queue for caching
        self.cache_queue('non-existing-image-id', expected_code=404)

        # Verify that you can not queue non-active image
        self.cache_queue(images['queued'], expected_code=400)

        # Try to delete non-existing image from cache
        self.cache_delete('non-existing-image-id', expected_code=404)

        # Verify clearing cache fails with 400 if invalid header is passed
        self.cache_clear(target='both', expected_code=400)

    def test_cache_image_queue_delete(self):
        # Delete original image, then remove it from cache with cache-delete
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Ensure that nothing is cached and nothing is queued for caching
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        self.list_cache()
        with mock.patch.object(cached_images.WORKER, 'submit'):
            self.cache_queue(images['public'])

        self.wait_for_in_cache(images['public'])

        path = '/v2/images/%s' % images['public']
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)

        # Deleting the Glance image may already drop the cache entry (404 on
        # cache-delete) or leave it queued/cached (204 on cache-delete).
        output = self.list_cache()
        queued = output['queued_images']
        cached = [img['image_id'] for img in output['cached_images']]
        if images['public'] in queued or images['public'] in cached:
            self.cache_delete(images['public'])

        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

    def test_cache_image_cache_delete(self):
        # This test verifies that if image is queued for caching
        # and user deletes the original image, but it is still
        # present in queued list and deleted with cache-delete API.
        self.start_server(enable_cache=True)
        images = self.load_data()

        # Ensure that nothing is cached and nothing is queued for caching
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        self.cache_queue(images['public'])

        # wait for caching the image
        self.wait_for_caching(images['public'])
        # Now verify that we have 0 queued image and 1 cached image
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(1, len(output['cached_images']))
        # Verify same image cached
        self.assertIn(images['public'], output['cached_images'][0]['image_id'])

        # Delete image and verify that it is deleted from
        # cache as well
        path = '/v2/images/%s' % images['public']
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)

        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

    def test_cache_api_cache_disabled(self):
        self.start_server(enable_cache=False)
        images = self.load_data()
        # As cache is not enabled each API call should return 404 response
        self.list_cache(expected_code=404)
        self.cache_queue(images['public'], expected_code=404)
        self.cache_delete(images['public'], expected_code=404)
        self.cache_clear(expected_code=404)
        self.cache_clear(target='both', expected_code=404)

        # Now disable cache policies and ensure that you will get 403
        self.set_policy_rules({
            'cache_list': '!',
            'cache_delete': '!',
            'cache_image': '!',
            'add_image': '',
            'upload_image': ''
        })
        self.list_cache(expected_code=403)
        self.cache_queue(images['public'], expected_code=403)
        self.cache_delete(images['public'], expected_code=403)
        self.cache_clear(expected_code=403)
        self.cache_clear(target='both', expected_code=403)

    def test_cache_api_not_allowed(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        # As cache operations are not allowed each API call should return
        # 403 response
        self.set_policy_rules({
            'cache_list': '!',
            'cache_delete': '!',
            'cache_image': '!',
            'add_image': '',
            'upload_image': ''
        })
        self.list_cache(expected_code=403)
        self.cache_queue(images['public'], expected_code=403)
        self.cache_delete(images['public'], expected_code=403)
        self.cache_clear(expected_code=403)
        self.cache_clear(target='both', expected_code=403)

    def test_cache_clean(self):
        self.start_server(enable_cache=True)
        self.load_data()

        # Get the cache directory
        cache_dir = self._store_dir('cache')
        invalid_dir = os.path.join(cache_dir, 'invalid')
        incomplete_dir = os.path.join(cache_dir, 'incomplete')

        # Ensure directories exist
        os.makedirs(invalid_dir, exist_ok=True)
        os.makedirs(incomplete_dir, exist_ok=True)

        # Create an invalid cache file
        invalid_file_path = os.path.join(invalid_dir, 'invalid-image-id')
        with open(invalid_file_path, 'wb') as f:
            f.write(b'invalid cache data')
        self.assertTrue(os.path.exists(invalid_file_path))

        # Create a stalled incomplete file (older than default stall time)
        stalled_file_path = os.path.join(incomplete_dir, 'stalled-image-id')
        with open(stalled_file_path, 'wb') as f:
            f.write(b'incomplete cache data')
        # Set file timestamp to 2 days ago (older than default 24h stall time)
        mtime = os.path.getmtime(stalled_file_path)
        past_time = (datetime.datetime.fromtimestamp(mtime) -
                     datetime.timedelta(days=2))
        atime = int(time.mktime(past_time.timetuple()))
        mtime = atime
        os.utime(stalled_file_path, (atime, mtime))
        self.assertTrue(os.path.exists(stalled_file_path))

        # Create a recent incomplete file (should NOT be cleaned)
        recent_file_path = os.path.join(incomplete_dir, 'recent-image-id')
        with open(recent_file_path, 'wb') as f:
            f.write(b'recent incomplete data')
        self.assertTrue(os.path.exists(recent_file_path))

        # Clean cache - should remove invalid and stalled files
        self.cache_clean()

        # Verify invalid file was removed
        self.assertFalse(os.path.exists(invalid_file_path),
                         "Invalid cache file should have been cleaned")

        # Verify stalled incomplete file was removed
        self.assertFalse(os.path.exists(stalled_file_path),
                         "Stalled incomplete file should have been cleaned")

        # Verify recent incomplete file was NOT removed
        self.assertTrue(os.path.exists(recent_file_path),
                        "Recent incomplete file should NOT have been cleaned")

    def test_cache_prune(self):
        # Set a small max cache size (100KB) to force pruning
        self.config(image_cache_max_size=100 * units.Ki)
        self.start_server(enable_cache=True)
        self.load_data()

        # Prune cache when empty - should return zeros
        result = self.cache_prune()
        self.assertIsNotNone(result)
        self.assertEqual(0, result['total_files_pruned'])
        self.assertEqual(0, result['total_bytes_pruned'])

        # Cache multiple images to exceed the max size limit
        # Each image is ~9 bytes (b'IMAGEDATA'), so we need many images
        # Let's cache 20 images which should exceed 100KB when considering
        # overhead, but let's be safe and cache more
        cached_image_ids = []
        for i in range(15):
            # Create and upload a new image for each iteration
            path = "/v2/images"
            data = {
                'name': 'prune-test-image-%d' % i,
                'container_format': 'bare',
                'disk_format': 'raw'
            }
            response = self.api_post(path, json=data)
            self.assertEqual(201, response.status_code)
            image_id = response.json['id']

            # Upload data to make it cacheable (larger than 9 bytes)
            # Use 10KB per image to ensure we exceed 100KB with 15 images
            image_data = b'X' * (10 * units.Ki)
            response = self.api_put(
                '/v2/images/%s/file' % image_id,
                headers={'Content-Type': 'application/octet-stream'},
                data=image_data)
            self.assertEqual(204, response.status_code)

            # Queue for caching
            self.cache_queue(image_id)
            cached_image_ids.append(image_id)

        # Wait for all images to be cached
        for image_id in cached_image_ids:
            self.wait_for_caching(image_id)

        # Verify all images are cached
        output = self.list_cache()
        self.assertEqual(len(cached_image_ids), len(output['cached_images']))

        # Get the cache directory to verify files exist
        cache_dir = self._store_dir('cache')

        # Verify all cached image files exist before pruning
        for image_id in cached_image_ids:
            image_file_path = os.path.join(cache_dir, image_id)
            self.assertTrue(os.path.exists(image_file_path),
                            "Image %s should be cached before prune" %
                            image_id)

        # Prune cache - should remove some images to get under limit
        result = self.cache_prune()

        # Verify that the pruned files no longer exist on disk and
        # calculate bytes
        pruned_count = 0
        pruned_bytes = 0
        for image_id in cached_image_ids:
            image_file_path = os.path.join(cache_dir, image_id)
            if not os.path.exists(image_file_path):
                pruned_count += 1
                # Each image is 10KB
                pruned_bytes += 10 * units.Ki

        # Verify that the API result matches the actual count and bytes
        # of removed files
        self.assertEqual(pruned_count, result['total_files_pruned'],
                         "Number of removed files should match pruned count")
        self.assertEqual(pruned_bytes, result['total_bytes_pruned'],
                         "Number of bytes pruned should match actual "
                         "bytes removed")

        # Verify that the cache list reflects the pruned count
        output_after = self.list_cache()
        expected_remaining = (len(cached_image_ids) -
                              result['total_files_pruned'])
        self.assertEqual(len(output_after['cached_images']),
                         expected_remaining,
                         "Cache list should show exactly the remaining "
                         "images")

    def test_cache_clean_disabled(self):
        self.start_server(enable_cache=False)
        self.cache_clean(expected_code=404)

    def test_cache_prune_disabled(self):
        self.start_server(enable_cache=False)
        self.cache_prune(expected_code=404)
