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

"""
Tests a Glance API server which uses the caching middleware. We
use the filesystem store, but that is really not relevant, as the
image cache is transparent to the backend store.
"""

import hashlib
import json
import os
import unittest

import httplib2

from glance.tests.functional import test_api
from glance.tests.utils import execute, skip_if_disabled


FIVE_KB = 5 * 1024


class TestImageCache(test_api.TestApi):

    """Functional tests that exercise the image cache"""

    @skip_if_disabled
    def test_cache_middleware_transparent(self):
        """
        We test that putting the cache middleware into the
        application pipeline gives us transparent image caching
        """
        self.cleanup()
        self.cache_pipeline = "cache"
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # Verify no image 1
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 404)

        # Add an image and verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_datadir,
                                         '1')
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        # Verify image now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_datadir,
                                         '1')
        self.assertTrue(os.path.exists(image_cached_path))

        self.stop_servers()
