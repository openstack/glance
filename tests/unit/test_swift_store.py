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

from glance.common import exception
import glance.store.swift

SwiftBackend = glance.store.swift.SwiftBackend

SWIFT_INSTALLED = False

try:
    import swift.common.client
    SWIFT_INSTALLED = True
except ImportError:
    print "Skipping Swift store tests since Swift is not installed."

FIVE_KB = (5 * 1024)
SWIFT_OPTIONS = {'verbose': True,
                 'debug': True,
                 'swift_store_user': 'glance',
                 'swift_store_key': 'key',
                 'swift_store_auth_address': 'localhost:8080',
                 'swift_store_container': 'glance'}


# We stub out as little as possible to ensure that the code paths
# between glance.store.swift and swift.common.client are tested
# thoroughly
def stub_out_swift_common_client(stubs):

    fixture_headers = {'glance/2':
                {'content-length': FIVE_KB,
                 'etag': 'c2e5db72bd7fd153f53ede5da5a06de3'}}
    fixture_objects = {'glance/2':
                       StringIO.StringIO("*" * FIVE_KB)}

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

    def fake_get_connection_class(*args):
        return swift.common.client.Connection

    def fake_http_connection(self):
        return None

    def fake_get_auth(self):
        return None, None

    stubs.Set(swift.common.client,
              'put_object', fake_put_object)
    stubs.Set(swift.common.client,
              'delete_object', fake_delete_object)
    stubs.Set(swift.common.client,
              'head_object', fake_head_object)
    stubs.Set(swift.common.client,
              'get_object', fake_get_object)
    stubs.Set(swift.common.client.Connection,
              'get_auth', fake_get_auth)
    stubs.Set(swift.common.client.Connection,
              'http_connection', fake_http_connection)
    stubs.Set(glance.store.swift,
              'get_connection_class', fake_get_connection_class)


class TestSwiftBackend(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        if SWIFT_INSTALLED:
            stub_out_swift_common_client(self.stubs)

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        if not SWIFT_INSTALLED:
            return
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
        if not SWIFT_INSTALLED:
            return
        url_pieces = urlparse.urlparse(
            "swift://user:key@auth_address/glance/2")
        self.assertRaises(glance.store.BackendException,
                          SwiftBackend.get,
                          url_pieces,
                          {'expected_size': 42})

    def test_get_non_existing(self):
        """
        Test that trying to retrieve a swift that doesn't exist
        raises an error
        """
        if not SWIFT_INSTALLED:
            return
        url_pieces = urlparse.urlparse(
            "swift://user:key@auth_address/noexist")
        self.assertRaises(exception.NotFound,
                          SwiftBackend.get,
                          url_pieces)

    def test_add(self):
        """Test that we can add an image via the swift backend"""
        if not SWIFT_INSTALLED:
            return
        expected_image_id = 42
        expected_swift_size = 1024 * 5  # 5K
        expected_swift_contents = "*" * expected_swift_size
        expected_location = "swift://%s:%s@%s/%s/%s" % (
            SWIFT_OPTIONS['swift_store_user'],
            SWIFT_OPTIONS['swift_store_key'],
            SWIFT_OPTIONS['swift_store_auth_address'],
            SWIFT_OPTIONS['swift_store_container'],
            expected_image_id)
        image_swift = StringIO.StringIO(expected_swift_contents)

        location, size = SwiftBackend.add(42, image_swift, SWIFT_OPTIONS)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)

        url_pieces = urlparse.urlparse(
            "swift://user:key@auth_address/glance/42")
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
        if not SWIFT_INSTALLED:
            return
        image_swift = StringIO.StringIO("nevergonnamakeit")
        self.assertRaises(exception.Duplicate,
                          SwiftBackend.add,
                          2, image_swift, SWIFT_OPTIONS)

    def test_delete(self):
        """
        Test we can delete an existing image in the swift store
        """
        if not SWIFT_INSTALLED:
            return
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
        if not SWIFT_INSTALLED:
            return
        url_pieces = urlparse.urlparse("swift://user:key@auth_address/noexist")
        self.assertRaises(exception.NotFound,
                          SwiftBackend.delete,
                          url_pieces)
