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

import httplib
import os
import random
import shutil
import unittest

import stubout
import webob

from glance import registry
from glance.api import v1 as server
from glance.api.middleware import cache
from glance.common import context
from glance.tests import stubs

FIXTURE_DATA = '*' * 1024


class TestCacheMiddleware(unittest.TestCase):

    """Test case for the cache middleware"""

    def setUp(self):
        self.cache_dir = os.path.join("/", "tmp", "test.cache.%d" %
                                      random.randint(0, 1000000))
        self.filesystem_store_datadir = os.path.join(self.cache_dir,
                                                     'filestore')
        self.options = {
            'verbose': True,
            'debug': True,
            'image_cache_datadir': self.cache_dir,
            'registry_host': '0.0.0.0',
            'registry_port': 9191,
            'default_store': 'file',
            'filesystem_store_datadir': self.filesystem_store_datadir
        }
        self.cache_filter = cache.CacheFilter(
            server.API(self.options), self.options)
        self.api = context.ContextMiddleware(self.cache_filter, self.options)
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_server(self.stubs)

    def tearDown(self):
        self.stubs.UnsetAll()
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)

    def test_cache_image(self):
        """
        Verify no images cached at start, then request an image,
        and verify the image is in the cache afterwards
        """
        image_cached_path = os.path.join(self.cache_dir, '1')

        self.assertFalse(os.path.exists(image_cached_path))

        req = webob.Request.blank('/images/1')
        res = req.get_response(self.api)
        self.assertEquals(404, res.status_int)

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #1'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = FIXTURE_DATA
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        req = webob.Request.blank('/images/1')
        res = req.get_response(self.api)
        self.assertEquals(200, res.status_int)

        for chunk in res.body:
            pass  # We do this to trigger tee'ing the file

        self.assertTrue(os.path.exists(image_cached_path))
        self.assertEqual(0, self.cache_filter.cache.get_hit_count('1'))

        # Now verify that the next call to GET /images/1
        # yields the image from the cache...

        req = webob.Request.blank('/images/1')
        res = req.get_response(self.api)
        self.assertEquals(200, res.status_int)

        for chunk in res.body:
            pass  # We do this to trigger a hit read

        self.assertTrue(os.path.exists(image_cached_path))
        self.assertEqual(1, self.cache_filter.cache.get_hit_count('1'))
