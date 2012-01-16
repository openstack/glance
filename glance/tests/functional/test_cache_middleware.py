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
Tests a Glance API server which uses the caching middleware that
uses the default SQLite cache driver. We use the filesystem store,
but that is really not relevant, as the image cache is transparent
to the backend store.
"""

import hashlib
import json
import os
import shutil
import thread
import time

import BaseHTTPServer
import httplib2

from glance.tests import functional
from glance.tests.utils import (skip_if_disabled,
                                execute,
                                xattr_writes_supported)


FIVE_KB = 5 * 1024


class RemoteImageHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(s):
        """
        Respond to an image GET request with fake image content.
        """
        if 'images' in s.path:
            s.send_response(200)
            s.send_header('Content-Type', 'application/octet-stream')
            s.send_header('Content-Length', FIVE_KB)
            s.end_headers()
            image_data = '*' * FIVE_KB
            s.wfile.write(image_data)
            self.wfile.close()
            return
        else:
            self.send_error(404, 'File Not Found: %s' % self.path)
            return


class BaseCacheMiddlewareTest(object):

    @skip_if_disabled
    def test_cache_middleware_transparent(self):
        """
        We test that putting the cache middleware into the
        application pipeline gives us transparent image caching
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

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

        image_id = data['image']['id']

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

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
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        self.assertFalse(os.path.exists(image_cached_path))

        self.stop_servers()

    @skip_if_disabled
    def test_cache_remote_image(self):
        """
        We test that caching is no longer broken for remote images
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # set up "remote" image server
        server_class = BaseHTTPServer.HTTPServer
        remote_server = server_class(('127.0.0.1', 0), RemoteImageHandler)
        remote_ip, remote_port = remote_server.server_address

        def serve_requests(httpd):
            httpd.serve_forever()

        thread.start_new_thread(serve_requests, (remote_server,))

        # Add a remote image and verify a 200 OK is returned
        remote_uri = 'http://%s:%d/images/2' % (remote_ip, remote_port)
        headers = {'X-Image-Meta-Name': 'Image2',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Location': remote_uri}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['size'], 0)

        image_id = data['image']['id']

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        # Grab the image again to ensure it can be served out from
        # cache with the correct size
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(int(response['content-length']), FIVE_KB)

        remote_server.shutdown()

        self.stop_servers()


class BaseCacheManageMiddlewareTest(object):

    """Base test class for testing cache management middleware"""

    def verify_no_images(self):
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertTrue('images' in data)
        self.assertEqual(0, len(data['images']))

    def add_image(self, name):
        """
        Adds an image and returns the newly-added image
        identifier
        """
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': '%s' % name,
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
        self.assertEqual(data['image']['name'], name)
        self.assertEqual(data['image']['is_public'], True)
        return data['image']['id']

    def verify_no_cached_images(self):
        """
        Verify no images in the image cache
        """
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)
        self.assertEqual(data['cached_images'], [])

    @skip_if_disabled
    def test_cache_manage_get_cached_images(self):
        """
        Tests that cached images are queryable
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        self.verify_no_images()

        image_id = self.add_image("Image1")

        # Verify image does not yet show up in cache (we haven't "hit"
        # it yet using a GET /images/1 ...
        self.verify_no_cached_images()

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        # Verify image now in cache
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertEqual(image_id, cached_images[0]['image_id'])
        self.assertEqual(0, cached_images[0]['hits'])

        # Hit the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        # Verify image hits increased in output of manage GET
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

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

        api_port = self.api_port
        registry_port = self.registry_port

        self.verify_no_images()

        ids = {}

        # Add a bunch of images...
        for x in xrange(0, 4):
            ids[x] = self.add_image("Image%s" % str(x))

        # Verify no images in cached_images because no image has been hit
        # yet using a GET /images/<IMAGE_ID> ...
        self.verify_no_cached_images()

        # Grab the images, essentially caching them...
        for x in xrange(0, 4):
            path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                                  ids[x])
            http = httplib2.Http()
            response, content = http.request(path, 'GET')
            self.assertEqual(response.status, 200,
                             "Failed to find image %s" % ids[x])

        # Verify images now in cache
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

        cached_images = data['cached_images']
        self.assertEqual(4, len(cached_images))

        for x in xrange(4, 0):  # Cached images returned last modified order
            self.assertEqual(ids[x], cached_images[x]['image_id'])
            self.assertEqual(0, cached_images[x]['hits'])

        # Delete third image of the cached images and verify no longer in cache
        path = "http://%s:%d/v1/cached_images/%s" % ("0.0.0.0", self.api_port,
                                                     ids[2])
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

        cached_images = data['cached_images']
        self.assertEqual(3, len(cached_images))
        self.assertTrue(ids[2] not in [x['image_id'] for x in cached_images])

        # Delete all cached images and verify nothing in cache
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

        cached_images = data['cached_images']
        self.assertEqual(0, len(cached_images))

        self.stop_servers()

    @skip_if_disabled
    def test_queue_and_prefetch(self):
        """
        Tests that images may be queued and prefetched
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        cache_config_filepath = os.path.join(self.test_dir, 'etc',
                                             'glance-cache.conf')
        cache_file_options = {
            'image_cache_dir': self.api_server.image_cache_dir,
            'image_cache_driver': self.image_cache_driver,
            'registry_port': self.api_server.registry_port,
            'log_file': os.path.join(self.test_dir, 'cache.log'),
            'metadata_encryption_key': "012345678901234567890123456789ab"
        }
        with open(cache_config_filepath, 'w') as cache_file:
            cache_file.write("""[DEFAULT]
debug = True
verbose = True
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
registry_host = 0.0.0.0
registry_port = %(registry_port)s
metadata_encryption_key = %(metadata_encryption_key)s
log_file = %(log_file)s

[app:glance-pruner]
paste.app_factory = glance.common.wsgi:app_factory
glance.app_factory = glance.image_cache.pruner:Pruner

[app:glance-prefetcher]
paste.app_factory = glance.common.wsgi:app_factory
glance.app_factory = glance.image_cache.prefetcher:Prefetcher

[app:glance-cleaner]
paste.app_factory = glance.common.wsgi:app_factory
glance.app_factory = glance.image_cache.cleaner:Cleaner

[app:glance-queue-image]
paste.app_factory = glance.common.wsgi:app_factory
glance.app_factory = glance.image_cache.queue_image:Queuer
""" % cache_file_options)
            cache_file.flush()

        self.verify_no_images()

        ids = {}

        # Add a bunch of images...
        for x in xrange(0, 4):
            ids[x] = self.add_image("Image%s" % str(x))

        # Queue the first image, verify no images still in cache after queueing
        # then run the prefetcher and verify that the image is then in the
        # cache
        path = "http://%s:%d/v1/queued_images/%s" % ("0.0.0.0", self.api_port,
                                                     ids[0])
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(response.status, 200)

        self.verify_no_cached_images()

        cmd = "bin/glance-cache-prefetcher --config-file %s" % \
            cache_config_filepath

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip(), out)

        # Verify first image now in cache
        path = "http://%s:%d/v1/cached_images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        data = json.loads(content)
        self.assertTrue('cached_images' in data)

        cached_images = data['cached_images']
        self.assertEqual(1, len(cached_images))
        self.assertTrue(ids[0] in [r['image_id']
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
                import xattr
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache"
        self.image_cache_driver = "xattr"

        super(TestImageCacheXattr, self).setUp()

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            return

    def tearDown(self):
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
                import xattr
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache cache_manage"
        self.image_cache_driver = "xattr"

        super(TestImageCacheManageXattr, self).setUp()

        if not xattr_writes_supported(self.test_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            return

    def tearDown(self):
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
                import sqlite3
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-sqlite3 not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache"

        super(TestImageCacheSqlite, self).setUp()

    def tearDown(self):
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
                import sqlite3
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-sqlite3 not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache cache_manage"
        self.image_cache_driver = "sqlite"

        super(TestImageCacheManageSqlite, self).setUp()

    def tearDown(self):
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)
