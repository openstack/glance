# Copyright 2025 Red Hat, Inc.
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

import http.client as http
import time
from unittest import mock

from oslo_config import cfg
import oslo_policy.policy

from glance.api import policy
from glance.tests import functional
from glance.tests.functional.v2 import test_images


CONF = cfg.CONF

TENANT1 = test_images.TENANT1


class TestDownloadFromStore(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestDownloadFromStore, self).setUp()
        self.api_methods = test_images.ImageAPIHelper(
            self.api_get, self.api_post, self.api_put, self.api_delete)
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self, enable_cache=False):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestDownloadFromStore, self).start_server(
                enable_cache=enable_cache)

    def list_cache(self, expected_code=200):
        """List cached images using cache API"""
        path = '/v2/cache'
        # Cache API requires admin role
        admin_headers = self._headers({'X-Roles': 'admin'})
        response = self.api_get(path, headers=admin_headers)
        self.assertEqual(expected_code, response.status_code)
        if response.status_code == 200:
            return response.json

    def wait_for_caching(self, image_id, max_sec=10, delay_sec=0.2,
                         start_delay_sec=None):
        """Wait for an image to be cached"""
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

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_download_with_stores(self):
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2', 'store3']
        image_data = b'TEST_IMAGE_DATA_12345'
        image_id = self.api_methods.create_and_verify_image(
            name='test-image', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        path = '/v2/images/%s/file?prefer=store1' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_stores_fallback(self):
        """Test that download falls back to other stores when not found
        in specified stores
        """
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2', 'store3']
        image_data = b'TEST_IMAGE_DATA_12345'
        image_id = self.api_methods.create_and_verify_image(
            name='test-image', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Request store2 but image is in store1 - should fallback to store1
        path = '/v2/images/%s/file?prefer=store2' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_invalid_store(self):
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2', 'store3']
        image_data = b'TEST_IMAGE_DATA_12345'
        image_id = self.api_methods.create_and_verify_image(
            name='test-image', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        path = '/v2/images/%s/file?prefer=invalid_store' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        self.api_methods.delete_image(image_id)

    def test_download_without_stores_parameter(self):
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2', 'store3']
        image_data = b'TEST_IMAGE_DATA_12345'
        image_id = self.api_methods.create_and_verify_image(
            name='test-image', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_multiple_stores(self):
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2', 'store3']
        image_data = b'TEST_IMAGE_DATA_12345'
        image_id = self.api_methods.create_and_verify_image(
            name='test-image', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store2'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        path = '/v2/images/%s/file?prefer=store1,store2' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_stores_uses_cache_when_cached(self):
        """Test cached images are served from cache even with store params"""
        self.start_server(enable_cache=True)
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2']
        image_data = b'TEST_IMAGE_DATA_CACHE'
        image_id = self.api_methods.create_and_verify_image(
            name='test-cache', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # First download - should cache the image
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        # Wait for async caching to complete and verify using cache API
        self.wait_for_caching(image_id)
        # Explicitly verify image is in cache
        cache_data = self.list_cache()
        cached_image_ids = [img['image_id'] for img in
                            cache_data.get('cached_images', [])]
        self.assertIn(image_id, cached_image_ids,
                      "Image should be present in cache after download")

        # Second download with invalid store parameter - should still use cache
        # (cache takes precedence for performance). If it went through API,
        # it would return 400 for invalid store, but since it's cached, it
        # succeeds.
        path = '/v2/images/%s/file?prefer=invalid_store' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_stores_policy_enforcement(self):
        """Test that download_from_store policy is enforced"""
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2']
        image_data = b'TEST_IMAGE_DATA_POLICY'
        image_id = self.api_methods.create_and_verify_image(
            name='test-policy', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Download with stores parameter - should succeed with default policy
        path = '/v2/images/%s/file?prefer=store1' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)

    def test_download_with_stores_policy_restricted(self):
        """Test that restricted policy prevents store selection"""
        # Set policy to admin only for download_from_store, but keep defaults
        # for other policies so the test can work
        policy_rules = {
            'download_from_store': 'role:admin',
            'get_images': '',
            'get_image': '',
            'download_image': '',
            'add_image': '',
            'upload_image': '',
            'delete_image': '',
        }
        self.set_policy_rules(policy_rules)
        self.start_server()
        self.api_methods.verify_empty_image_list()

        available_stores = ['store1', 'store2']
        image_data = b'TEST_IMAGE_DATA_POLICY_RESTRICTED'
        image_id = self.api_methods.create_and_verify_image(
            name='test-policy-restricted', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        headers = self._headers({
            'content-type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store1'
        })
        path = '/v2/images/%s/file' % image_id
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Download without stores parameter - should succeed (normal download)
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        # Download with stores parameter as non-admin - should fail
        path = '/v2/images/%s/file?prefer=store1' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Download with stores parameter as admin - should succeed
        admin_headers = self._headers({'X-Roles': 'admin'})
        path = '/v2/images/%s/file?prefer=store1' % image_id
        response = self.api_get(path, headers=admin_headers)
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(image_data, response.body)

        self.api_methods.delete_image(image_id)
