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

import os
from unittest import mock

import oslo_policy.policy
from oslo_utils import units

from glance.api import policy
from glance.image_cache import prefetcher
from glance.tests import functional


class TestCacheImagesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestCacheImagesPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestCacheImagesPolicy, self).start_server(enable_cache=True)

    def _create_upload_and_cache(self, cache_image=False,
                                 expected_code=200):
        image_id = self._create_and_upload()
        # Queue image for caching
        path = '/v2/queued_images/%s' % image_id
        response = self.api_put(path)
        self.assertEqual(expected_code, response.status_code)

        if cache_image:
            # NOTE(abhishekk): Here we are not running periodic job which
            # caches queued images as precaching is not part of this
            # patch, so to test all caching operations we are using this
            # way to cache images for us
            cache_prefetcher = prefetcher.Prefetcher()
            cache_prefetcher.run()

        return image_id

    def test_queued_images(self):
        self.start_server()
        # Verify that you can queue image for caching
        self._create_upload_and_cache(expected_code=200)

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!',
            'add_image': '',
            'upload_image': ''
        })
        self._create_upload_and_cache(expected_code=403)

    def test_get_queued_images(self):
        self.start_server()
        # Create image and queue it for caching
        image_id = self._create_upload_and_cache()

        # make sure you are able to get queued images
        path = '/v2/queued_images'
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        output = response.json
        self.assertIn(image_id, output['queued_images'])

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        response = self.api_get(path)
        self.assertEqual(403, response.status_code)

    def test_delete_queued_image(self):
        self.start_server()
        # Create image and queue it for caching
        image_id = self._create_upload_and_cache()
        # Create another image while you can
        second_image_id = self._create_upload_and_cache()

        # make sure you are able to delete queued image
        path = '/v2/queued_images/%s' % image_id
        response = self.api_delete(path)
        self.assertEqual(200, response.status_code)

        # verify image is deleted from queue list
        path = '/v2/queued_images'
        response = self.api_get(path)
        output = response.json
        self.assertNotIn(image_id, output['queued_images'])

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        path = '/v2/queued_images/%s' % second_image_id
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

    def test_delete_queued_images(self):
        self.start_server()
        # Create image and queue it for caching
        self._create_upload_and_cache()
        # Create another image while you can
        self._create_upload_and_cache()

        # make sure you are able to delete queued image
        path = '/v2/queued_images'
        response = self.api_delete(path)
        self.assertEqual(200, response.status_code)

        # verify images are deleted from queue list
        path = '/v2/queued_images'
        response = self.api_get(path)
        output = response.json
        self.assertEqual([], output['queued_images'])

        # Create another image and queue it for caching
        image_id = self._create_upload_and_cache()

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        path = '/v2/queued_images'
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

        # Verify that image is still present in queue list
        self.set_policy_rules({
            'manage_image_cache': '',
        })
        path = '/v2/queued_images'
        response = self.api_get(path)
        output = response.json
        self.assertIn(image_id, output['queued_images'])

    def test_get_cached_images(self):
        self.start_server()
        # Create image and cache it
        image_id = self._create_upload_and_cache(cache_image=True)

        # make sure you are able to get cached images
        path = '/v2/cached_images'
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        output = response.json
        self.assertEqual(image_id, output['cached_images'][0]['image_id'])

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        response = self.api_get(path)
        self.assertEqual(403, response.status_code)

    def test_list_cached_nodes(self):
        self.start_server()
        # Create image and cache it
        image_id = self._create_upload_and_cache(cache_image=True)
        # make sure you are able to get cached images
        path = '/v2/cache/nodes/%s' % image_id
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        # Now disable list_cached_nodes to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'list_cached_nodes': '!'
        })
        response = self.api_get(path)
        self.assertEqual(403, response.status_code)

    def test_list_cached_nodes_default_policy(self):
        """Test default policy for list_cached_nodes endpoint."""
        self.start_server()
        # Set up the default policy for list_cached_nodes
        self.set_policy_rules({
            'list_cached_nodes': 'role:admin',
            'add_image': '',
            'upload_image': '',
            'manage_image_cache': 'role:admin'
        })
        # Create image and cache it
        image_id = self._create_upload_and_cache(cache_image=True)
        path = '/v2/cache/nodes/%s' % image_id

        # Test with default headers (admin role) - should succeed
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)

        # Test with admin role explicitly - should succeed
        headers = {'X-Roles': 'admin'}
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # Test with reader role - should fail (403 Forbidden)
        headers = {'X-Roles': 'reader'}
        response = self.api_get(path, headers=headers)
        self.assertEqual(403, response.status_code)

        # Test with member role - should fail (403 Forbidden)
        headers = {'X-Roles': 'member'}
        response = self.api_get(path, headers=headers)
        self.assertEqual(403, response.status_code)

        # Test with no roles - should fail (403 Forbidden)
        headers = {'X-Roles': ''}
        response = self.api_get(path, headers=headers)
        self.assertEqual(403, response.status_code)

    def test_delete_cached_image(self):
        self.start_server()
        # Create image and cache it
        image_id = self._create_upload_and_cache(cache_image=True)
        # Create another image while you can
        second_image_id = self._create_upload_and_cache(cache_image=True)

        # make sure you are able to delete cached image
        path = '/v2/cached_images/%s' % image_id
        response = self.api_delete(path)
        self.assertEqual(200, response.status_code)

        # verify image is deleted from cached list
        path = '/v2/cached_images'
        response = self.api_get(path)
        output = response.json
        self.assertEqual(1, len(output['cached_images']))

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        path = '/v2/cached_images/%s' % second_image_id
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

    def test_delete_cached_images(self):
        self.start_server()
        # Create image and cache it
        self._create_upload_and_cache(cache_image=True)
        # Create another image while you can
        self._create_upload_and_cache(cache_image=True)

        # make sure you are able to delete cached image
        path = '/v2/cached_images'
        response = self.api_delete(path)
        self.assertEqual(200, response.status_code)

        # verify images are deleted from cached list
        path = '/v2/cached_images'
        response = self.api_get(path)
        output = response.json
        self.assertEqual(0, len(output['cached_images']))

        # Create another image and cache it
        self._create_upload_and_cache(cache_image=True)

        # Now disable manage_image_cache to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'manage_image_cache': '!'
        })
        path = '/v2/cached_images'
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

        # Verify that image is still present in cache
        self.set_policy_rules({
            'manage_image_cache': '',
        })
        path = '/v2/cached_images'
        response = self.api_get(path)
        output = response.json
        self.assertEqual(1, len(output['cached_images']))

    def test_clean_cache(self):
        self.start_server()
        # Create some invalid cache files to clean
        cache_dir = self._store_dir('cache')
        invalid_dir = os.path.join(cache_dir, 'invalid')
        os.makedirs(invalid_dir, exist_ok=True)
        invalid_file = os.path.join(invalid_dir, 'invalid-image-id')
        with open(invalid_file, 'wb') as f:
            f.write(b'invalid cache data')

        # Make sure you are able to clean cache
        path = '/v2/cache/clean'
        response = self.api_post(path)
        self.assertEqual(200, response.status_code)

        # Verify invalid file was cleaned
        self.assertFalse(os.path.exists(invalid_file))

        # Create another invalid file
        invalid_file2 = os.path.join(invalid_dir, 'invalid-image-id-2')
        with open(invalid_file2, 'wb') as f:
            f.write(b'invalid cache data 2')

        # Now disable cache_clean policy to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'cache_clean': '!',
            'cache_list': '',
            'cache_delete': '',
            'cache_image': '',
            'add_image': '',
            'upload_image': ''
        })
        response = self.api_post(path)
        self.assertEqual(403, response.status_code)

        # Verify that invalid file is still present
        self.assertTrue(os.path.exists(invalid_file2))

    def test_prune_cache(self):
        self.start_server()
        # Set a small max cache size to force pruning
        self.config(image_cache_max_size=100 * units.Ki)

        # Create and cache multiple images to exceed the limit
        image_ids = []
        for i in range(5):
            image_id = self._create_upload_and_cache(cache_image=True)
            image_ids.append(image_id)

        # Make sure you are able to prune cache
        path = '/v2/cache/prune'
        response = self.api_post(path)
        self.assertEqual(200, response.status_code)
        output = response.json
        self.assertIn('total_files_pruned', output)
        self.assertIn('total_bytes_pruned', output)
        self.assertIsInstance(output['total_files_pruned'], int)
        self.assertIsInstance(output['total_bytes_pruned'], int)

        # Now disable cache_prune policy to ensure you will get
        # 403 Forbidden error
        self.set_policy_rules({
            'cache_prune': '!',
            'cache_list': '',
            'cache_delete': '',
            'cache_image': '',
            'add_image': '',
            'upload_image': ''
        })
        response = self.api_post(path)
        self.assertEqual(403, response.status_code)
