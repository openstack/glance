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
import swift.common.client

from glance.common import exception
from glance.store import BackendException
import glance.store.swift
from glance.store.location import get_location_from_uri

Store = glance.store.swift.Store
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
        # Large object manifest...
        fixture_key = "%s/%s" % (container, name)
        if kwargs.get('headers'):
            etag = kwargs['headers']['ETag']
            fixture_headers[fixture_key] = {'manifest': True,
                                            'etag': etag}
            return etag
        if not fixture_key in fixture_headers.keys():
            if hasattr(contents, 'read'):
                fixture_object = StringIO.StringIO()
                chunk = contents.read(Store.CHUNKSIZE)
                checksum = hashlib.md5()
                while chunk:
                    fixture_object.write(chunk)
                    checksum.update(chunk)
                    chunk = contents.read(Store.CHUNKSIZE)
                etag = checksum.hexdigest()
            else:
                fixture_object = StringIO.StringIO(contents)
                etag = hashlib.md5(fixture_object.getvalue()).hexdigest()
            read_len = fixture_object.len
            fixture_objects[fixture_key] = fixture_object
            fixture_headers[fixture_key] = {
                'content-length': read_len,
                'etag': etag}
            return etag
        else:
            msg = ("Object PUT failed - Object with key %s already exists"
                   % fixture_key)
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.CONFLICT)

    def fake_get_object(url, token, container, name, **kwargs):
        # GET returns the tuple (list of headers, file object)
        fixture_key = "%s/%s" % (container, name)
        if not fixture_key in fixture_headers:
            msg = "Object GET failed"
            raise swift.common.client.ClientException(msg,
                        http_status=httplib.NOT_FOUND)

        fixture = fixture_headers[fixture_key]
        if 'manifest' in fixture:
            # Large object manifest... we return a file containing
            # all objects with prefix of this fixture key
            chunk_keys = sorted([k for k in fixture_headers.keys()
                                 if k.startswith(fixture_key) and
                                 k != fixture_key])
            result = StringIO.StringIO()
            for key in chunk_keys:
                result.write(fixture_objects[key].getvalue())
            return fixture_headers[fixture_key], result

        else:
            return fixture_headers[fixture_key], fixture_objects[fixture_key]

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

    def fake_get_auth(url, *args, **kwargs):
        if 'http' in url and '://' not in url:
            raise ValueError('Invalid url %s' % url)
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


def format_swift_location(user, key, authurl, container, obj):
    """
    Helper method that returns a Swift store URI given
    the component pieces.
    """
    scheme = 'swift+https'
    if authurl.startswith('http://'):
        scheme = 'swift+http'
        authurl = authurl[7:]
    if authurl.startswith('https://'):
        authurl = authurl[8:]
    return "%s://%s:%s@%s/%s/%s" % (scheme, user, key, authurl,
                                    container, obj)


class TestStore(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stub_out_swift_common_client(self.stubs)
        self.store = Store(SWIFT_OPTIONS)

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        loc = get_location_from_uri("swift://user:key@auth_address/glance/2")
        (image_swift, image_size) = self.store.get(loc)
        self.assertEqual(image_size, None)

        expected_data = "*" * FIVE_KB
        data = ""

        for chunk in image_swift:
            data += chunk
        self.assertEqual(expected_data, data)

    def test_get_with_http_auth(self):
        """
        Test a retrieval from Swift with an HTTP authurl. This is
        specified either via a Location header with swift+http:// or using
        http:// in the swift_store_auth_address config value
        """
        loc = get_location_from_uri("swift+http://user:key@auth_address/"
                                    "glance/2")
        (image_swift, image_size) = self.store.get(loc)
        self.assertEqual(image_size, None)

        expected_data = "*" * FIVE_KB
        data = ""

        for chunk in image_swift:
            data += chunk
        self.assertEqual(expected_data, data)

    def test_get_non_existing(self):
        """
        Test that trying to retrieve a swift that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("swift://user:key@authurl/glance/noexist")
        self.assertRaises(exception.NotFound,
                          self.store.get,
                          loc)

    def test_add(self):
        """Test that we can add an image via the swift backend"""
        expected_image_id = 42
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_location = format_swift_location(
            SWIFT_OPTIONS['swift_store_user'],
            SWIFT_OPTIONS['swift_store_key'],
            SWIFT_OPTIONS['swift_store_auth_address'],
            SWIFT_OPTIONS['swift_store_container'],
            expected_image_id)
        image_swift = StringIO.StringIO(expected_swift_contents)

        location, size, checksum = self.store.add(42, image_swift,
                                                  expected_swift_size)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = new_image_swift.getvalue()
        new_image_swift_size = new_image_swift.len

        self.assertEquals(expected_swift_contents, new_image_contents)
        self.assertEquals(expected_swift_size, new_image_swift_size)

    def test_add_auth_url_variations(self):
        """
        Test that we can add an image via the swift backend with
        a variety of different auth_address values
        """
        variations = ['http://localhost:80',
                      'http://localhost',
                      'http://localhost/v1',
                      'http://localhost/v1/',
                      'https://localhost',
                      'https://localhost:8080',
                      'https://localhost/v1',
                      'https://localhost/v1/',
                      'localhost',
                      'localhost:8080/v1']
        i = 42
        for variation in variations:
            expected_image_id = i
            expected_swift_size = FIVE_KB
            expected_swift_contents = "*" * expected_swift_size
            expected_checksum = \
                    hashlib.md5(expected_swift_contents).hexdigest()
            new_options = SWIFT_OPTIONS.copy()
            new_options['swift_store_auth_address'] = variation
            expected_location = format_swift_location(
                new_options['swift_store_user'],
                new_options['swift_store_key'],
                new_options['swift_store_auth_address'],
                new_options['swift_store_container'],
                expected_image_id)
            image_swift = StringIO.StringIO(expected_swift_contents)

            self.store = Store(new_options)
            location, size, checksum = self.store.add(i, image_swift,
                                                      expected_swift_size)

            self.assertEquals(expected_location, location)
            self.assertEquals(expected_swift_size, size)
            self.assertEquals(expected_checksum, checksum)

            loc = get_location_from_uri(expected_location)
            (new_image_swift, new_image_size) = self.store.get(loc)
            new_image_contents = new_image_swift.getvalue()
            new_image_swift_size = new_image_swift.len

            self.assertEquals(expected_swift_contents, new_image_contents)
            self.assertEquals(expected_swift_size, new_image_swift_size)
            i = i + 1

    def test_add_no_container_no_create(self):
        """
        Tests that adding an image with a non-existing container
        raises an appropriate exception
        """
        options = SWIFT_OPTIONS.copy()
        options['swift_store_create_container_on_put'] = 'False'
        options['swift_store_container'] = 'noexist'
        image_swift = StringIO.StringIO("nevergonnamakeit")
        self.store = Store(options)

        # We check the exception text to ensure the container
        # missing text is found in it, otherwise, we would have
        # simply used self.assertRaises here
        exception_caught = False
        try:
            self.store.add(3, image_swift, 0)
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
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_location = format_swift_location(
            options['swift_store_user'],
            options['swift_store_key'],
            options['swift_store_auth_address'],
            options['swift_store_container'],
            expected_image_id)
        image_swift = StringIO.StringIO(expected_swift_contents)

        self.store = Store(options)
        location, size, checksum = self.store.add(42, image_swift,
                                                  expected_swift_size)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = new_image_swift.getvalue()
        new_image_swift_size = new_image_swift.len

        self.assertEquals(expected_swift_contents, new_image_contents)
        self.assertEquals(expected_swift_size, new_image_swift_size)

    def test_add_large_object(self):
        """
        Tests that adding a very large image. We simulate the large
        object by setting the DEFAULT_LARGE_OBJECT_SIZE to a small number
        and then verify that there have been a number of calls to
        put_object()...
        """
        options = SWIFT_OPTIONS.copy()
        options['swift_store_container'] = 'glance'
        expected_image_id = 42
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_location = format_swift_location(
            options['swift_store_user'],
            options['swift_store_key'],
            options['swift_store_auth_address'],
            options['swift_store_container'],
            expected_image_id)
        image_swift = StringIO.StringIO(expected_swift_contents)

        orig_max_size = glance.store.swift.DEFAULT_LARGE_OBJECT_SIZE
        orig_temp_size = glance.store.swift.DEFAULT_LARGE_OBJECT_CHUNK_SIZE
        try:
            glance.store.swift.DEFAULT_LARGE_OBJECT_SIZE = 1024
            glance.store.swift.DEFAULT_LARGE_OBJECT_CHUNK_SIZE = 1024
            self.store = Store(options)
            location, size, checksum = self.store.add(42, image_swift,
                                                      expected_swift_size)
        finally:
            swift.DEFAULT_LARGE_OBJECT_CHUNK_SIZE = orig_temp_size
            swift.DEFAULT_LARGE_OBJECT_SIZE = orig_max_size

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
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
                          self.store.add,
                          2, image_swift, 0)

    def _option_required(self, key):
        options = SWIFT_OPTIONS.copy()
        del options[key]

        try:
            self.store = Store(options)
            return self.store.add == self.store.add_disabled
        except:
            return False
        return False

    def test_no_user(self):
        """
        Tests that options without user disables the add method
        """
        self.assertTrue(self._option_required('swift_store_user'))

    def test_no_key(self):
        """
        Tests that options without key disables the add method
        """
        self.assertTrue(self._option_required('swift_store_key'))

    def test_no_auth_address(self):
        """
        Tests that options without auth address disables the add method
        """
        self.assertTrue(self._option_required('swift_store_auth_address'))

    def test_delete(self):
        """
        Test we can delete an existing image in the swift store
        """
        loc = get_location_from_uri("swift://user:key@authurl/glance/2")

        self.store.delete(loc)

        self.assertRaises(exception.NotFound,
                          self.store.get,
                          loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a swift that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("swift://user:key@authurl/glance/noexist")
        self.assertRaises(exception.NotFound,
                          self.store.delete,
                          loc)
