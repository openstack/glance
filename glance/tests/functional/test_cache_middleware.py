# Copyright 2011 OpenStack Foundation
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

"""
Tests a Glance API server which uses the caching middleware that
uses the default SQLite cache driver. We use the filesystem store,
but that is really not relevant, as the image cache is transparent
to the backend store.
"""

import http.client as http_client
import os
from unittest import mock

import oslo_policy.policy
from oslo_serialization import jsonutils
from oslo_utils import units

from glance.api import policy
from glance.tests import functional
from glance.tests.utils import skip_if_disabled
from glance.tests.utils import xattr_writes_supported

FIVE_KB = 5 * units.Ki


class BaseCacheMiddlewareTest(object):

    @skip_if_disabled
    def test_cache_middleware_transparent_v2(self):
        """Ensure the v2 API image transfer calls trigger caching"""
        self.start_server()
        # Add an image and verify success
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response = self.api_post(path, headers=headers, json=image_entity)
        self.assertEqual(http_client.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # upload data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b"*" * FIVE_KB
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)

        # Verify image not in cache
        cache_dir = self._store_dir('cache')
        image_cached_path = os.path.join(cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        response = self.api_get('/v2/images/%s/file' % image_id)
        self.assertEqual(http_client.OK, response.status_code)
        self.assertEqual(image_data, response.text.encode('utf-8'))

        # Verify image now in cache
        self.assertTrue(os.path.exists(image_cached_path))

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        response = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)
        self.assertFalse(os.path.exists(image_cached_path))

    @skip_if_disabled
    def test_partially_downloaded_images_are_not_cached_v2_api(self):
        """
        Verify that we do not cache images that were downloaded partially
        using v2 images API.
        """
        self.start_server()
        # Add an image and verify success
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response = self.api_post(path, headers=headers, json=image_entity)
        self.assertEqual(http_client.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)

        # Verify image not in cache
        cache_dir = self._store_dir('cache')
        image_cached_path = os.path.join(cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # range download request
        range_ = 'bytes=3-5'
        headers = self._headers({'Range': range_})
        # partially download this image and verify status 206
        response = self.api_get('/v2/images/%s/file' % image_id,
                                headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status_code)
        self.assertEqual(b'DEF', response.text.encode('utf-8'))

        # content-range download request
        # NOTE(dharinic): Glance incorrectly supports Content-Range for partial
        # image downloads in requests. This test is included to ensure that
        # we prevent regression.
        content_range = 'bytes 3-5/*'
        headers = self._headers({'Content-Range': content_range})
        response = self.api_get('/v2/images/%s/file' % image_id,
                                headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status_code)
        self.assertEqual(b'DEF', response.text.encode('utf-8'))

        # verify that we do not cache the partial image
        self.assertFalse(os.path.exists(image_cached_path))

    @skip_if_disabled
    def test_partial_download_of_cached_images_v2_api(self):
        """
        Verify that partial download requests for a fully cached image
        succeeds; we do not serve it from cache.
        """
        self.start_server()
        # Add an image and verify success
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response = self.api_post(path, headers=headers, json=image_entity)
        self.assertEqual(http_client.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)

        # Verify that this image is not in cache
        cache_dir = self._store_dir('cache')
        image_cached_path = os.path.join(cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Download the entire image
        response = self.api_get('/v2/images/%s/file' % image_id,
                                headers=headers)
        self.assertEqual(http_client.OK, response.status_code)
        self.assertEqual(b'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                         response.text.encode('utf-8'))

        # Verify that the image is now in cache
        self.assertTrue(os.path.exists(image_cached_path))
        # Modify the data in cache so we can verify the partially downloaded
        # content was not from cache indeed.
        with open(image_cached_path, 'w') as cache_file:
            cache_file.write('0123456789')

        # Partially attempt a download of this image and verify that is not
        # from cache
        # range download request
        range_ = 'bytes=3-5'
        headers = self._headers({'Range': range_,
                                 'content-type': 'application/json'})
        response = self.api_get('/v2/images/%s/file' % image_id,
                                headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status_code)
        self.assertEqual(b'DEF', response.text.encode('utf-8'))
        self.assertNotEqual(b'345', response.text.encode('utf-8'))
        self.assertNotEqual(image_data, response.text.encode('utf-8'))

        # content-range download request
        # NOTE(dharinic): Glance incorrectly supports Content-Range for partial
        # image downloads in requests. This test is included to ensure that
        # we prevent regression.
        content_range = 'bytes 3-5/*'
        headers = self._headers({'Content-Range': content_range,
                                 'content-type': 'application/json'})
        response = self.api_get('/v2/images/%s/file' % image_id,
                                headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status_code)
        self.assertEqual(b'DEF', response.text.encode('utf-8'))
        self.assertNotEqual(b'345', response.text.encode('utf-8'))
        self.assertNotEqual(image_data, response.text.encode('utf-8'))

    @skip_if_disabled
    def test_cache_middleware_trans_v2_without_download_image_policy(self):
        """
        Ensure the image v2 API image transfer applied 'download_image'
        policy enforcement.
        """
        self.start_server()
        # Add an image and verify success
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response = self.api_post(path, headers=headers, json=image_entity)
        self.assertEqual(http_client.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # upload data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b"*" * FIVE_KB
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)

        # Verify image not in cache
        cache_dir = self._store_dir('cache')
        image_cached_path = os.path.join(cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        rules = {"context_is_admin": "role:admin", "default": "",
                 "download_image": "!"}
        self.set_policy_rules(rules)

        # Grab the image
        response = self.api_get('/v2/images/%s/file' % image_id)
        self.assertEqual(http_client.FORBIDDEN, response.status_code)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        response = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(http_client.NO_CONTENT, response.status_code)
        self.assertFalse(os.path.exists(image_cached_path))


class TestImageCacheXattr(functional.SynchronousAPIBase,
                          BaseCacheMiddlewareTest):

    """Functional tests that exercise the image cache using the xattr driver"""

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-xattr installed and xattr support on the
        filesystem)
        """
        if getattr(self, 'disabled', False):
            raise self.skipException('Test disabled.')

        if not getattr(self, 'inited', False):
            try:
                import xattr  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                raise self.skipException(self.disabled_message)

        self.inited = True
        self.disabled = False

        super(TestImageCacheXattr, self).setUp()
        self.config(image_cache_driver="xattr")
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            raise self.skipException(self.disabled_message)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImageCacheXattr, self).start_server()


class TestImageCacheSqlite(functional.SynchronousAPIBase,
                           BaseCacheMiddlewareTest):

    """
    Functional tests that exercise the image cache using the
    SQLite driver
    """

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-xattr installed and xattr support on the
        filesystem)
        """
        if getattr(self, 'disabled', False):
            return

        if not getattr(self, 'inited', False):
            try:
                import sqlite3  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-sqlite3 not installed.")
                return

        self.inited = True
        self.disabled = False

        super(TestImageCacheSqlite, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImageCacheSqlite, self).start_server()
