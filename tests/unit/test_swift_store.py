# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this swift except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests the Swift backend store"""

import StringIO
import hashlib
import httplib
import sys
import unittest
import urlparse

import stubout

# NOTE(sirp): Avoid swift unit-tests if module is not present
try:
    import swift.common.client
    SWIFT_INSTALLED = True
except ImportError:
    SWIFT_INSTALLED = False

from glance.common import exception
from glance.store import BackendException
from glance.store.swift import SwiftBackend, format_swift_location

FIVE_KB = (5 * 1024)
SWIFT_OPTIONS = {'verbose': True,
                 'debug': True,
                 'swift_store_user': 'user',
                 'swift_store_key': 'key',
                 'swift_store_auth_address': 'localhost:8080',
                 'swift_store_container': 'glance'}


# We stub out as little as possible to ensure that the code paths
# between glance.store.swift and swift.common.client are tested
# thoroughly
def stub_out_swift_common_client(stubs):

    fixture_containers = ['glance']
    fixture_headers = {'glance/2':
                {'content-length': FIVE_KB,
                 'etag': 'c2e5db72bd7fd153f53ede5da5a06de3'}}
    fixture_objects = {'glance/2':
                       StringIO.StringIO("*" * FIVE_KB)}

    def fake_head_container(url, token, container, **kwargs):
        if container not in fixture_containers:
            msg = "No container %s found" % container
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.NOT_FOUND)

    def fake_put_container(url, token, container, **kwargs):
        fixture_containers.append(container)

    def fake_put_object(url, token, container, name, contents, **kwargs):
        # PUT returns the ETag header for the newly-added object
        fixture_key = "%s/%s" % (container, name)
        if not fixture_key in fixture_headers.keys():
            if hasattr(contents, 'read'):
                fixture_object = StringIO.StringIO()
                chunk = contents.read(SwiftBackend.CHUNKSIZE)
                while chunk:
                    fixture_object.write(chunk)
                    chunk = contents.read(SwiftBackend.CHUNKSIZE)
            else:
                fixture_object = StringIO.StringIO(contents)
            fixture_objects[fixture_key] = fixture_object
            fixture_headers[fixture_key] = {
                'content-length': fixture_object.len,
                'etag': hashlib.md5(fixture_object.read()).hexdigest()}
            return fixture_headers[fixture_key]['etag']
        else:
            msg = ("Object PUT failed - Object with key %s already exists"
                   % fixture_key)
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.CONFLICT)

    def fake_get_object(url, token, container, name, **kwargs):
        # GET returns the tuple (list of headers, file object)
        try:
            fixture_key = "%s/%s" % (container, name)
            return fixture_headers[fixture_key], fixture_objects[fixture_key]
        except KeyError:
            msg = "Object GET failed"
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.NOT_FOUND)

    def fake_head_object(url, token, container, name, **kwargs):
        # HEAD returns the list of headers for an object
        try:
            fixture_key = "%s/%s" % (container, name)
            return fixture_headers[fixture_key]
        except KeyError:
            msg = "Object HEAD failed - Object does not exist"
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.NOT_FOUND)

    def fake_delete_object(url, token, container, name, **kwargs):
        # DELETE returns nothing
        fixture_key = "%s/%s" % (container, name)
        if fixture_key not in fixture_headers.keys():
            msg = "Object DELETE failed - Object does not exist"
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.NOT_FOUND)
        else:
            del fixture_headers[fixture_key]
            del fixture_objects[fixture_key]

    def fake_http_connection(*args, **kwargs):
        return None

    def fake_get_auth(*args, **kwargs):
        return None, None

    stubs.Set(swift.common.client,
              'head_container', fake_head_container)
    stubs.Set(swift.common.client,
              'put_container', fake_put_container)
    stubs.Set(swift.common.client,
              'put_object', fake_put_object)
    stubs.Set(swift.common.client,
              'delete_object', fake_delete_object)
    stubs.Set(swift.common.client,
              'head_object', fake_head_object)
    stubs.Set(swift.common.client,
              'get_object', fake_get_object)
    stubs.Set(swift.common.client,
              'get_auth', fake_get_auth)
    stubs.Set(swift.common.client,
              'http_connection', fake_http_connection)

if SWIFT_INSTALLED:
    class TestSwiftBackend(unittest.TestCase):

        def setUp(self):
            """Establish a clean test environment"""
            self.stubs = stubout.StubOutForTesting()
            stub_out_swift_common_client(self.stubs)

        def tearDown(self):
            """Clear the test environment"""
            self.stubs.UnsetAll()

        def test_get(self):
            """Test a "normal" retrieval of an image in chunks"""
            url_pieces = urlparse.urlparse(
                "swift://user:key@auth_address/glance/2")
            image_swift = SwiftBackend.get(url_pieces)

            expected_data = "*" * FIVE_KB
            data = ""

            for chunk in image_swift:
                data += chunk
            self.assertEqual(expected_data, data)

        def test_get_mismatched_expected_size(self):
            """
            Test retrieval of an image with wrong expected_size param
            raises an exception
            """
            url_pieces = urlparse.urlparse(
                "swift://user:key@auth_address/glance/2")
            self.assertRaises(BackendException,
                              SwiftBackend.get,
                              url_pieces,
                              {'expected_size': 42})

        def test_get_non_existing(self):
            """
            Test that trying to retrieve a swift that doesn't exist
            raises an error
            """
            url_pieces = urlparse.urlparse(
                "swift://user:key@auth_address/noexist")
            self.assertRaises(exception.NotFound,
                              SwiftBackend.get,
                              url_pieces)

        def test_add(self):
            """Test that we can add an image via the swift backend"""
            expected_image_id = 42
            expected_swift_size = 1024 * 5  # 5K
            expected_swift_contents = "*" * expected_swift_size
            expected_location = format_swift_location(
                SWIFT_OPTIONS['swift_store_user'],
                SWIFT_OPTIONS['swift_store_key'],
                SWIFT_OPTIONS['swift_store_auth_address'],
                SWIFT_OPTIONS['swift_store_container'],
                expected_image_id)
            image_swift = StringIO.StringIO(expected_swift_contents)

            location, size = SwiftBackend.add(42, image_swift, SWIFT_OPTIONS)

            self.assertEquals(expected_location, location)
            self.assertEquals(expected_swift_size, size)

            url_pieces = urlparse.urlparse(expected_location)
            new_image_swift = SwiftBackend.get(url_pieces)
            new_image_contents = new_image_swift.getvalue()
            new_image_swift_size = new_image_swift.len

            self.assertEquals(expected_swift_contents, new_image_contents)
            self.assertEquals(expected_swift_size, new_image_swift_size)

        def test_add_no_container_no_create(self):
            """
            Tests that adding an image with a non-existing container
            raises an appropriate exception
            """
            options = SWIFT_OPTIONS.copy()
            options['swift_store_create_container_on_put'] = 'False'
            options['swift_store_container'] = 'noexist'
            image_swift = StringIO.StringIO("nevergonnamakeit")

            # We check the exception text to ensure the container
            # missing text is found in it, otherwise, we would have
            # simply used self.assertRaises here
            exception_caught = False
            try:
                SwiftBackend.add(3, image_swift, options)
            except BackendException, e:
                exception_caught = True
                self.assertTrue("container noexist does not exist "
                                "in Swift" in str(e))
            self.assertTrue(exception_caught)

        def test_add_no_container_and_create(self):
            """
            Tests that adding an image with a non-existing container
            creates the container automatically if flag is set
            """
            options = SWIFT_OPTIONS.copy()
            options['swift_store_create_container_on_put'] = 'True'
            options['swift_store_container'] = 'noexist'
            expected_image_id = 42
            expected_swift_size = 1024 * 5  # 5K
            expected_swift_contents = "*" * expected_swift_size
            expected_location = format_swift_location(
                options['swift_store_user'],
                options['swift_store_key'],
                options['swift_store_auth_address'],
                options['swift_store_container'],
                expected_image_id)
            image_swift = StringIO.StringIO(expected_swift_contents)

            location, size = SwiftBackend.add(42, image_swift, options)

            self.assertEquals(expected_location, location)
            self.assertEquals(expected_swift_size, size)

            url_pieces = urlparse.urlparse(expected_location)
            new_image_swift = SwiftBackend.get(url_pieces)
            new_image_contents = new_image_swift.getvalue()
            new_image_swift_size = new_image_swift.len

            self.assertEquals(expected_swift_contents, new_image_contents)
            self.assertEquals(expected_swift_size, new_image_swift_size)

        def test_add_already_existing(self):
            """
            Tests that adding an image with an existing identifier
            raises an appropriate exception
            """
            image_swift = StringIO.StringIO("nevergonnamakeit")
            self.assertRaises(exception.Duplicate,
                              SwiftBackend.add,
                              2, image_swift, SWIFT_OPTIONS)

        def test_delete(self):
            """
            Test we can delete an existing image in the swift store
            """
            url_pieces = urlparse.urlparse(
                "swift://user:key@auth_address/glance/2")

            SwiftBackend.delete(url_pieces)

            self.assertRaises(exception.NotFound,
                              SwiftBackend.get,
                              url_pieces)

        def test_delete_non_existing(self):
            """
            Test that trying to delete a swift that doesn't exist
            raises an error
            """
            url_pieces = urlparse.urlparse(
                "swift://user:key@auth_address/noexist")
            self.assertRaises(exception.NotFound,
                              SwiftBackend.delete,
                              url_pieces)
