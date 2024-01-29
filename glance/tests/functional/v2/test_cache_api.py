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
import time
from unittest import mock

import oslo_policy.policy

from glance.api import policy
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

    def start_server(self, enable_cache=True):
        # NOTE(abhishekk): Once sqlite driver is removed, fix these tests
        # to work with centralized_db driver
        self.config(image_cache_driver='sqlite')
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

    def test_cache_list(self):
        self.start_server(enable_cache=True)
        images = self.load_data()
        # Ensure that nothing is cached and nothing is queued for caching
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        # Queue 1 image for caching
        self.cache_queue(images['public'])
        output = self.list_cache()
        self.assertEqual(1, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

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
        self.cache_queue(images['public'])
        self.cache_queue(images['private'])
        # Now verify that we have 2 queued images
        # NOTE(abhishekk): We might fail with race here as queue call
        # will immediately start caching of an image, so we may not find
        # all images in queued state.
        output = self.list_cache()
        self.assertEqual(2, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

        # Clear all images from cache
        self.cache_clear(target='queue')
        # Now verify that we have 0 queued images
        output = self.list_cache()
        self.assertEqual(0, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))

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

        # Queue 2 images for caching
        self.cache_queue(images['public'])
        self.wait_for_caching(images['public'])
        # Now verify that we have 1 cached images
        output = self.list_cache()
        self.assertEqual(1, len(output['cached_images']))

        self.cache_queue(images['private'])
        # Now verify that we have 1 queued and 1 cached images
        output = self.list_cache()
        # NOTE(abhishekk): We might fail with race here as queue call
        # will immediately start caching of an image, so we may not find
        # image in queued state.
        self.assertEqual(1, len(output['queued_images']))
        self.assertEqual(1, len(output['cached_images']))

        # Clear all images from cache
        self.cache_clear()
        # Now verify that we have 0 queued and cached images
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
        # Now verify that we have 1 image queued for caching and 0
        # cached images
        output = self.list_cache()
        self.assertEqual(1, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))
        # Verify same image is queued for caching
        self.assertIn(images['public'], output['queued_images'])

        # Delete image and verify that it is still present
        # in queued list
        path = '/v2/images/%s' % images['public']
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)

        output = self.list_cache()
        self.assertEqual(1, len(output['queued_images']))
        self.assertEqual(0, len(output['cached_images']))
        self.assertIn(images['public'], output['queued_images'])

        # Deleted the image from queued list
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
