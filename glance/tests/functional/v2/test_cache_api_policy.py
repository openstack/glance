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

from unittest import mock

import oslo_policy.policy

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
