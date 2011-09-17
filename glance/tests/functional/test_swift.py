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
Tests a Glance API server which uses an Swift backend by default

This test requires that a real Swift account is available. It looks
in a file GLANCE_TEST_SWIFT_CONF environ variable for the credentials to
use.

Note that this test clears the entire container from the Swift account
for use by the test case, so make sure you supply credentials for
test accounts only.

If a connection cannot be established, all the test cases are
skipped.
"""

import ConfigParser
import hashlib
import httplib
import httplib2
import json
import os
import tempfile
import unittest

import glance.store.swift  # Needed to register driver for location
from glance.store.location import get_location_from_uri
from glance.tests.functional import test_api
from glance.tests.utils import execute, skip_if_disabled

FIVE_MB = 5 * 1024 * 1024


class TestSwift(test_api.TestApi):

    """Functional tests for the Swift backend"""

    # Test machines can set the GLANCE_TEST_SWIFT_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_SWIFT_CONF')

    def setUp(self):
        """
        Test a connection to an Swift store using the credentials
        found in the environs or /tests/functional/test_swift.conf, if found.
        If the connection fails, mark all tests to skip.
        """
        self.inited = False
        self.disabled = True

        if self.inited:
            return

        if not self.CONFIG_FILE_PATH:
            self.disabled_message = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.inited = True
            return

        if os.path.exists(TestSwift.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestSwift.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.__dict__[key] = value
            except ConfigParser.ParsingError, e:
                self.disabled_message = ("Failed to read test_swift.conf "
                                         "file. Got error: %s" % e)
                self.inited = True
                return

        from swift.common import client as swift_client

        try:
            swift_host = self.swift_store_auth_address
            if not swift_host.startswith('http'):
                swift_host = 'https://' + swift_host
            user = self.swift_store_user
            key = self.swift_store_key
            container_name = self.swift_store_container
        except AttributeError, e:
            self.disabled_message = ("Failed to find required configuration "
                                     "options for Swift store. "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.swift_conn = swift_conn = swift_client.Connection(
            authurl=swift_host, user=user, key=key, snet=False, retries=1)

        try:
            _resp_headers, containers = swift_conn.get_account()
        except Exception, e:
            self.disabled_message = ("Failed to get_account from Swift "
                                     "Got error: %s" % e)
            self.inited = True
            return

        try:
            for container in containers:
                if container == container_name:
                    swift_conn.delete_container(container)
        except swift_client.ClientException, e:
            self.disabled_message = ("Failed to delete container from Swift "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.swift_conn = swift_conn

        try:
            swift_conn.put_container(container_name)
        except swift_client.ClientException, e:
            self.disabled_message = ("Failed to create container. "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.disabled = False
        self.inited = True
        self.default_store = 'swift'

        super(TestSwift, self).setUp()

    def tearDown(self):
        if not self.disabled:
            self.clear_container()
        super(TestSwift, self).tearDown()

    def clear_container(self):
        from swift.common import client as swift_client
        try:
            self.swift_conn.delete_container(self.swift_store_container)
        except swift_client.ClientException, e:
            if e.http_status == httplib.CONFLICT:
                pass
            else:
                raise
        self.swift_conn.put_container(self.swift_store_container)

    @skip_if_disabled
    def test_large_objects(self):
        """
        We test the large object manifest code path in the Swift driver.
        In the case where an image file is bigger than the config variable
        swift_store_large_object_size, then we chunk the image into
        Swift, and add a manifest put_object at the end.

        We test that the delete of the large object cleans up all the
        chunks in Swift, in addition to the manifest file (LP Bug# 833285)
        """
        self.cleanup()

        self.swift_store_large_object_size = 2  # In MB
        self.swift_store_large_object_chunk_size = 1  # In MB
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_MB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201, content)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_MB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # HEAD /images/1
        # Verify image found now
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # GET /images/1
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image_headers = {
            'x-image-meta-id': '1',
            'x-image-meta-name': 'Image1',
            'x-image-meta-is_public': 'True',
            'x-image-meta-status': 'active',
            'x-image-meta-disk_format': '',
            'x-image-meta-container_format': '',
            'x-image-meta-size': str(FIVE_MB)
        }

        expected_std_headers = {
            'content-length': str(FIVE_MB),
            'content-type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key, expected_value,
                               response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               response[expected_key]))

        self.assertEqual(content, "*" * FIVE_MB)
        self.assertEqual(hashlib.md5(content).hexdigest(),
                         hashlib.md5("*" * FIVE_MB).hexdigest())

        # We test that the delete of the large object cleans up all the
        # chunks in Swift, in addition to the manifest file (LP Bug# 833285)

        # Grab the actual Swift location and query the object manifest for
        # the chunks/segments. We will check that the segments don't exist
        # after we delete the object through Glance...
        path = "http://%s:%d/images/1" % ("0.0.0.0", self.registry_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        image_loc = get_location_from_uri(data['image']['location'])
        swift_loc = image_loc.store_location

        from swift.common import client as swift_client
        swift_conn = swift_client.Connection(
            authurl=swift_loc.swift_auth_url,
            user=swift_loc.user, key=swift_loc.key)

        # Verify the object manifest exists
        headers = swift_conn.head_object(swift_loc.container, swift_loc.obj)
        manifest = headers.get('x-object-manifest')
        self.assertTrue(manifest is not None, "Manifest could not be found!")

        # Grab the segment identifiers
        obj_container, obj_prefix = manifest.split('/', 1)
        segments = [segment['name'] for segment in
                    swift_conn.get_container(obj_container,
                                             prefix=obj_prefix)[1]]

        # Verify the segments exist
        for segment in segments:
            headers = swift_conn.head_object(obj_container, segment)
            self.assertTrue(headers.get('content-length') is not None,
                            headers)

        # DELETE /images/1
        # Verify image and all chunks are gone...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # Verify the segments no longer exist
        for segment in segments:
            self.assertRaises(swift_client.ClientException,
                              swift_conn.head_object,
                              obj_container, segment)

        self.stop_servers()

    @skip_if_disabled
    def test_add_large_object_manifest_uneven_size(self):
        """
        Test when large object manifest in scenario where
        image size % chunk size != 0
        """
        self.cleanup()

        self.swift_store_large_object_size = 3  # In MB
        self.swift_store_large_object_chunk_size = 2  # In MB
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_MB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201, content)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_MB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 4. HEAD /images/1
        # Verify image found now
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 5. GET /images/1
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image_headers = {
            'x-image-meta-id': '1',
            'x-image-meta-name': 'Image1',
            'x-image-meta-is_public': 'True',
            'x-image-meta-status': 'active',
            'x-image-meta-disk_format': '',
            'x-image-meta-container_format': '',
            'x-image-meta-size': str(FIVE_MB)
        }

        expected_std_headers = {
            'content-length': str(FIVE_MB),
            'content-type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key, expected_value,
                               response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               response[expected_key]))

        self.assertEqual(content, "*" * FIVE_MB)
        self.assertEqual(hashlib.md5(content).hexdigest(),
                         hashlib.md5("*" * FIVE_MB).hexdigest())

        self.stop_servers()
