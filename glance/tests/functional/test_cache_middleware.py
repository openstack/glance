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

import hashlib
import os
import shutil
import sys
import time

import httplib2
from oslo_serialization import jsonutils
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.tests import functional
from glance.tests.functional.store_utils import get_http_uri
from glance.tests.functional.store_utils import setup_http
from glance.tests.utils import execute
from glance.tests.utils import minimal_headers
from glance.tests.utils import skip_if_disabled
from glance.tests.utils import xattr_writes_supported

FIVE_KB = 5 * units.Ki


class BaseCacheMiddlewareTest(object):

    @skip_if_disabled
    def test_cache_middleware_transparent_v1(self):
        """
        We test that putting the cache middleware into the
        application pipeline gives us transparent image caching
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        image_id = data['image']['id']

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)

        # You might wonder why the heck this is here... well, it's here
        # because it took me forever to figure out that the disk write
        # cache in Linux was causing random failures of the os.path.exists
        # assert directly below this. Basically, since the cache is writing
        # the image file to disk in a different process, the write buffers
        # don't flush the cache file during an os.rename() properly, resulting
        # in a false negative on the file existence check below. This little
        # loop pauses the execution of this process for no more than 1.5
        # seconds. If after that time the cached image file still doesn't
        # appear on disk, something really is wrong, and the assert should
        # trigger...
        i = 0
        while not os.path.exists(image_cached_path) and i < 30:
            time.sleep(0.05)
            i = i + 1

        self.assertTrue(os.path.exists(image_cached_path))

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_middleware_transparent_v2(self):
        """Ensure the v2 API image transfer calls trigger caching"""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify success
        path = "http://%s:%d/v2/images" % ("0.0.0.0", self.api_port)
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
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("0.0.0.0", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = "*" * FIVE_KB
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(204, response.status)

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v2/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(204, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_remote_image(self):
        """
        We test that caching is no longer broken for remote images
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        setup_http(self)

        # Add a remote image and verify a 201 Created is returned
        remote_uri = get_http_uri(self, '2')
        headers = {'X-Image-Meta-Name': 'Image2',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Location': remote_uri}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(FIVE_KB, data['image']['size'])

        image_id = data['image']['id']
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)

        # Grab the image
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Grab the image again to ensure it can be served out from
        # cache with the correct size
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual(FIVE_KB, int(response['content-length']))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_middleware_trans_v1_without_download_image_policy(self):
        """
        Ensure the image v1 API image transfer applied 'download_image'
        policy enforcement.
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        image_id = data['image']['id']

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        rules = {"context_is_admin": "role:admin", "default": "",
                 "download_image": "!"}
        self.set_policy_rules(rules)

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(403, response.status)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

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
        path = "http://%s:%d/v2/images" % ("0.0.0.0", self.api_port)
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
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['id']

        path = "http://%s:%d/v2/images/%s/file" % ("0.0.0.0", self.api_port,
                                                   image_id)
        headers = {'content-type': 'application/octet-stream'}
        image_data = "*" * FIVE_KB
        response, content = http.request(path, 'PUT',
                                         headers=headers,
                                         body=image_data)
        self.assertEqual(204, response.status)

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
        self.assertEqual(403, response.status)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v2/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(204, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_middleware_trans_with_deactivated_image(self):
        """
        Ensure the image v1/v2 API image transfer forbids downloading
        deactivated images.
        Image deactivation is not available in v1. So, we'll deactivate the
        image using v2 but test image transfer with both v1 and v2.
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # Add an image and verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        image_id = data['image']['id']

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertTrue(os.path.exists(image_cached_path))

        # Deactivate the image using v2
        path = "http://%s:%d/v2/images/%s/actions/deactivate"
        path = path % ("127.0.0.1", self.api_port, image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'POST')
        self.assertEqual(204, response.status)

        # Download the image with v1. Ensure it is forbidden
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(403, response.status)

        # Download the image with v2. Ensure it is forbidden
        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(403, response.status)

        # Reactivate the image using v2
        path = "http://%s:%d/v2/images/%s/actions/reactivate"
        path = path % ("127.0.0.1", self.api_port, image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'POST')
        self.assertEqual(204, response.status)

        # Download the image with v1. Ensure it is allowed
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Download the image with v2. Ensure it is allowed
        path = "http://%s:%d/v2/images/%s/file" % ("127.0.0.1", self.api_port,
                                                   image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Now, we delete the image from the server and verify that
        # the image cache no longer contains the deleted image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()


class BaseCacheManageMiddlewareTest(object):

    """Base test class for testing cache management middleware"""

    def verify_no_images(self):
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertIn('images', data)
        self.assertEqual(0, len(data['images']))

    def add_image(self, name):
        """
        Adds an image and returns the newly-added image
        identifier
        """
        image_data = "*" * FIVE_KB
        headers = minimal_headers('%s' % name)

        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual(name, data['image']['name'])
        self.assertTrue(data['image']['is_public'])
        return data['image']['id']

    def verify_no_cached_images(self):
        """
        Verify no images in the image cache
        """
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)
        self.assertEqual([], data['cached_images'])

    @skip_if_disabled
    def test_user_not_authorized(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())
        self.verify_no_images()

        image_id1 = self.add_image("Image1")
        image_id2 = self.add_image("Image2")

        # Verify image does not yet show up in cache (we haven't "hit"
        # it yet using a GET /images/1 ...
        self.verify_no_cached_images()

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id1)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image now in cache
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertEqual(image_id1, cached_images[0]['image_id'])

        # Set policy to disallow access to cache management
        rules = {"manage_image_cache": '!'}
        self.set_policy_rules(rules)

        # Verify an unprivileged user cannot see cached images
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(403, response.status)

        # Verify an unprivileged user cannot delete images from the cache
        path = "http://%s:%d/v1/cached_images/%s" % ("127.0.0.1",
                                                     self.api_port, image_id1)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(403, response.status)

        # Verify an unprivileged user cannot delete all cached images
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(403, response.status)

        # Verify an unprivileged user cannot queue an image
        path = "http://%s:%d/v1/queued_images/%s" % ("127.0.0.1",
                                                     self.api_port, image_id2)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(403, response.status)

        self.stop_servers()

    @skip_if_disabled
    def test_cache_manage_get_cached_images(self):
        """
        Tests that cached images are queryable
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        self.verify_no_images()

        image_id = self.add_image("Image1")

        # Verify image does not yet show up in cache (we haven't "hit"
        # it yet using a GET /images/1 ...
        self.verify_no_cached_images()

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image now in cache
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        # Verify the last_modified/last_accessed values are valid floats
        for cached_image in data['cached_images']:
            for time_key in ('last_modified', 'last_accessed'):
                time_val = cached_image[time_key]
                try:
                    float(time_val)
                except ValueError:
                    self.fail('%s time %s for cached image %s not a valid '
                              'float' % (time_key, time_val,
                                         cached_image['image_id']))

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertEqual(image_id, cached_images[0]['image_id'])
        self.assertEqual(0, cached_images[0]['hits'])

        # Hit the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        # Verify image hits increased in output of manage GET
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertEqual(image_id, cached_images[0]['image_id'])
        self.assertEqual(1, cached_images[0]['hits'])

        self.stop_servers()

    @skip_if_disabled
    def test_cache_manage_delete_cached_images(self):
        """
        Tests that cached images may be deleted
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        self.verify_no_images()

        ids = {}

        # Add a bunch of images...
        for x in range(4):
            ids[x] = self.add_image("Image%s" % str(x))

        # Verify no images in cached_images because no image has been hit
        # yet using a GET /images/<IMAGE_ID> ...
        self.verify_no_cached_images()

        # Grab the images, essentially caching them...
        for x in range(4):
            path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                                  ids[x])
            http = httplib2.Http()
            response, content = http.request(path, 'GET')
            self.assertEqual(200, response.status,
                             "Failed to find image %s" % ids[x])

        # Verify images now in cache
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(4, len(cached_images))

        for x in range(4, 0):  # Cached images returned last modified order
            self.assertEqual(ids[x], cached_images[x]['image_id'])
            self.assertEqual(0, cached_images[x]['hits'])

        # Delete third image of the cached images and verify no longer in cache
        path = "http://%s:%d/v1/cached_images/%s" % ("127.0.0.1",
                                                     self.api_port, ids[2])
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(3, len(cached_images))
        self.assertNotIn(ids[2], [x['image_id'] for x in cached_images])

        # Delete all cached images and verify nothing in cache
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(0, len(cached_images))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_manage_delete_queued_images(self):
        """
        Tests that all queued images may be deleted at once
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        self.verify_no_images()

        ids = {}
        NUM_IMAGES = 4

        # Add and then queue some images
        for x in range(NUM_IMAGES):
            ids[x] = self.add_image("Image%s" % str(x))
            path = "http://%s:%d/v1/queued_images/%s" % ("127.0.0.1",
                                                         self.api_port, ids[x])
            http = httplib2.Http()
            response, content = http.request(path, 'PUT')
            self.assertEqual(200, response.status)

        # Delete all queued images
        path = "http://%s:%d/v1/queued_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        num_deleted = data['num_deleted']
        self.assertEqual(NUM_IMAGES, num_deleted)

        # Verify a second delete now returns num_deleted=0
        path = "http://%s:%d/v1/queued_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        num_deleted = data['num_deleted']
        self.assertEqual(0, num_deleted)

        self.stop_servers()

    @skip_if_disabled
    def test_queue_and_prefetch(self):
        """
        Tests that images may be queued and prefetched
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        cache_config_filepath = os.path.join(self.test_dir, 'etc',
                                             'glance-cache.conf')
        cache_file_options = {
            'image_cache_dir': self.api_server.image_cache_dir,
            'image_cache_driver': self.image_cache_driver,
            'registry_port': self.registry_server.bind_port,
            'log_file': os.path.join(self.test_dir, 'cache.log'),
            'metadata_encryption_key': "012345678901234567890123456789ab",
            'filesystem_store_datadir': self.test_dir
        }
        with open(cache_config_filepath, 'w') as cache_file:
            cache_file.write("""[DEFAULT]
debug = True
verbose = True
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
registry_host = 127.0.0.1
registry_port = %(registry_port)s
metadata_encryption_key = %(metadata_encryption_key)s
log_file = %(log_file)s

[glance_store]
filesystem_store_datadir=%(filesystem_store_datadir)s
""" % cache_file_options)

        self.verify_no_images()

        ids = {}

        # Add a bunch of images...
        for x in range(4):
            ids[x] = self.add_image("Image%s" % str(x))

        # Queue the first image, verify no images still in cache after queueing
        # then run the prefetcher and verify that the image is then in the
        # cache
        path = "http://%s:%d/v1/queued_images/%s" % ("127.0.0.1",
                                                     self.api_port, ids[0])
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(200, response.status)

        self.verify_no_cached_images()

        cmd = ("%s -m glance.cmd.cache_prefetcher --config-file %s" %
               (sys.executable, cache_config_filepath))

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip(), out)

        # Verify first image now in cache
        path = "http://%s:%d/v1/cached_images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        data = jsonutils.loads(content)
        self.assertIn('cached_images', data)

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertIn(ids[0], [r['image_id']
                      for r in data['cached_images']])

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
            return

        if not getattr(self, 'inited', False):
            try:
                import xattr  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.image_cache_driver = "xattr"

        super(TestImageCacheXattr, self).setUp()

        self.api_server.deployment_flavor = "caching"

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            return

    def tearDown(self):
        super(TestImageCacheXattr, self).tearDown()
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)


class TestImageCacheManageXattr(functional.FunctionalTest,
                                BaseCacheManageMiddlewareTest):

    """
    Functional tests that exercise the image cache management
    with the Xattr cache driver
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
                import xattr  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.image_cache_driver = "xattr"

        super(TestImageCacheManageXattr, self).setUp()

        self.api_server.deployment_flavor = "cachemanagement"

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            return

    def tearDown(self):
        super(TestImageCacheManageXattr, self).tearDown()
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


class TestImageCacheManageSqlite(functional.FunctionalTest,
                                 BaseCacheManageMiddlewareTest):

    """
    Functional tests that exercise the image cache management using the
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
        self.image_cache_driver = "sqlite"

        super(TestImageCacheManageSqlite, self).setUp()

        self.api_server.deployment_flavor = "cachemanagement"

    def tearDown(self):
        super(TestImageCacheManageSqlite, self).tearDown()
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)
