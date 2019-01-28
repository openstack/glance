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

import os
import shutil
import uuid

import httplib2
from oslo_serialization import jsonutils
from oslo_utils import units
from six.moves import http_client

from glance.tests import functional
from glance.tests.utils import skip_if_disabled
from glance.tests.utils import xattr_writes_supported

FIVE_KB = 5 * units.Ki


class BaseCacheMiddlewareTest(object):

    @skip_if_disabled
    def test_cache_middleware_transparent_v2(self):
        """Ensure the v2 API image transfer calls trigger caching"""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify success
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        headers = {'content-type': 'application/json'}
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response, content = http.request(path, 'POST',
                                         headers=headers,
                                         body=jsonutils.dumps(image_entity))
        self.assertEqual(http_client.CREATED, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = "*" * FIVE_KB
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status)

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(http_client.OK, response.status)

        # Verify image now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertTrue(os.path.exists(image_cached_path))

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v2/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(http_client.NO_CONTENT, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_partially_downloaded_images_are_not_cached_v2_api(self):
        """
        Verify that we do not cache images that were downloaded partially
        using v2 images API.
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify success
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        headers = {'content-type': 'application/json'}
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response, content = http.request(path, 'POST',
                                         headers=headers,
                                         body=jsonutils.dumps(image_entity))
        self.assertEqual(http_client.CREATED, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status)

        # Verify that this image is not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # partially download this image and verify status 206
        http = httplib2.Http()
        # range download request
        range_ = 'bytes=3-5'
        headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': str(uuid.uuid4()),
            'X-Roles': 'member',
            'Range': range_
        }
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status)
        self.assertEqual(b'DEF', content)

        # content-range download request
        # NOTE(dharinic): Glance incorrectly supports Content-Range for partial
        # image downloads in requests. This test is included to ensure that
        # we prevent regression.
        content_range = 'bytes 3-5/*'
        headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': str(uuid.uuid4()),
            'X-Roles': 'member',
            'Content-Range': content_range
        }
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status)
        self.assertEqual(b'DEF', content)

        # verify that we do not cache the partial image
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_partial_download_of_cached_images_v2_api(self):
        """
        Verify that partial download requests for a fully cached image
        succeeds; we do not serve it from cache.
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify success
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        headers = {'content-type': 'application/json'}
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response, content = http.request(path, 'POST',
                                         headers=headers,
                                         body=jsonutils.dumps(image_entity))
        self.assertEqual(http_client.CREATED, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status)

        # Verify that this image is not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Download the entire image
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(http_client.OK, response.status)
        self.assertEqual(b'ABCDEFGHIJKLMNOPQRSTUVWXYZ', content)

        # Verify that the image is now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertTrue(os.path.exists(image_cached_path))
        # Modify the data in cache so we can verify the partially downloaded
        # content was not from cache indeed.
        with open(image_cached_path, 'w') as cache_file:
            cache_file.write('0123456789')

        # Partially attempt a download of this image and verify that is not
        # from cache
        # range download request
        range_ = 'bytes=3-5'
        headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': str(uuid.uuid4()),
            'X-Roles': 'member',
            'Range': range_,
            'content-type': 'application/json'
        }
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status)
        self.assertEqual(b'DEF', content)
        self.assertNotEqual(b'345', content)
        self.assertNotEqual(image_data, content)

        # content-range download request
        # NOTE(dharinic): Glance incorrectly supports Content-Range for partial
        # image downloads in requests. This test is included to ensure that
        # we prevent regression.
        content_range = 'bytes 3-5/*'
        headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': str(uuid.uuid4()),
            'X-Roles': 'member',
            'Content-Range': content_range,
            'content-type': 'application/json'
        }
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(http_client.PARTIAL_CONTENT, response.status)
        self.assertEqual(b'DEF', content)
        self.assertNotEqual(b'345', content)
        self.assertNotEqual(image_data, content)

        self.stop_servers()

    @skip_if_disabled
    def test_cache_middleware_trans_v2_without_download_image_policy(self):
        """
        Ensure the image v2 API image transfer applied 'download_image'
        policy enforcement.
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify success
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        headers = {'content-type': 'application/json'}
        image_entity = {
            'name': 'Image1',
            'visibility': 'public',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        response, content = http.request(path, 'POST',
                                         headers=headers,
                                         body=jsonutils.dumps(image_entity))
        self.assertEqual(http_client.CREATED, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = "*" * FIVE_KB
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(http_client.NO_CONTENT, response.status)

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        rules = {"context_is_admin": "role:admin", "default": "",
                 "download_image": "!"}
        self.set_policy_rules(rules)

        # Grab the image
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(http_client.FORBIDDEN, response.status)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v2/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(http_client.NO_CONTENT, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()


class TestImageCacheXattr(functional.FunctionalTest,
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
        self.image_cache_driver = "xattr"

        super(TestImageCacheXattr, self).setUp()

        self.api_server.deployment_flavor = "caching"

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            raise self.skipException(self.disabled_message)

    def tearDown(self):
        super(TestImageCacheXattr, self).tearDown()
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)


class TestImageCacheSqlite(functional.FunctionalTest,
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

        self.api_server.deployment_flavor = "caching"

    def tearDown(self):
        super(TestImageCacheSqlite, self).tearDown()
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)
