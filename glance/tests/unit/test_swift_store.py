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
import tempfile
import unittest

import stubout
import swift.common.client

from glance.common import exception
from glance.common import utils
from glance.store import BackendException
import glance.store.swift
from glance.store.location import get_location_from_uri
from glance.tests import utils as test_utils


FAKE_UUID = utils.generate_uuid

Store = glance.store.swift.Store
FIVE_KB = (5 * 1024)
FIVE_GB = (5 * 1024 * 1024 * 1024)
MAX_SWIFT_OBJECT_SIZE = FIVE_GB
SWIFT_PUT_OBJECT_CALLS = 0
SWIFT_CONF = {'verbose': True,
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
    fixture_headers = {'glance/%s' % FAKE_UUID:
                {'content-length': FIVE_KB,
                 'etag': 'c2e5db72bd7fd153f53ede5da5a06de3'}}
    fixture_objects = {'glance/%s' % FAKE_UUID:
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
        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS += 1
        fixture_key = "%s/%s" % (container, name)
        if not fixture_key in fixture_headers.keys():
            if kwargs.get('headers'):
                etag = kwargs['headers']['ETag']
                fixture_headers[fixture_key] = {'manifest': True,
                                                'etag': etag}
                return etag
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
            if read_len > MAX_SWIFT_OBJECT_SIZE:
                msg = ('Image size:%d exceeds Swift max:%d' %
                        (read_len, MAX_SWIFT_OBJECT_SIZE))
                raise swift.common.client.ClientException(
                        msg, http_status=httplib.REQUEST_ENTITY_TOO_LARGE)
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


class TestStore(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stub_out_swift_common_client(self.stubs)
        self.store = Store(test_utils.TestConfigOpts(SWIFT_CONF))

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        uri = "swift://user:key@auth_address/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        (image_swift, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 5120)

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
                                    "glance/%s" % FAKE_UUID)
        (image_swift, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 5120)

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
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = utils.generate_uuid()
        expected_location = 'swift+https://user:key@localhost:8080' + \
                            '/glance/%s' % expected_image_id
        image_swift = StringIO.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        location, size, checksum = self.store.add(expected_image_id,
                                                  image_swift,
                                                  expected_swift_size)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)
        # Expecting a single object to be created on Swift i.e. no chunking.
        self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 1)

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
        variations = {
            'http://localhost:80': 'swift+http://user:key@localhost:80'
                                   '/glance/%s',
            'http://localhost': 'swift+http://user:key@localhost/glance/%s',
            'http://localhost/v1': 'swift+http://user:key@localhost'
                                   '/v1/glance/%s',
            'http://localhost/v1/': 'swift+http://user:key@localhost'
                                    '/v1/glance/%s',
            'https://localhost': 'swift+https://user:key@localhost/glance/%s',
            'https://localhost:8080': 'swift+https://user:key@localhost:8080'
                                      '/glance/%s',
            'https://localhost/v1': 'swift+https://user:key@localhost'
                                    '/v1/glance/%s',
            'https://localhost/v1/': 'swift+https://user:key@localhost'
                                     '/v1/glance/%s',
            'localhost': 'swift+https://user:key@localhost/glance/%s',
            'localhost:8080/v1': 'swift+https://user:key@localhost:8080'
                                 '/v1/glance/%s',
        }

        for variation, expected_location in variations.items():
            image_id = utils.generate_uuid()
            expected_location = expected_location % image_id
            expected_swift_size = FIVE_KB
            expected_swift_contents = "*" * expected_swift_size
            expected_checksum = \
                    hashlib.md5(expected_swift_contents).hexdigest()
            new_conf = SWIFT_CONF.copy()
            new_conf['swift_store_auth_address'] = variation

            image_swift = StringIO.StringIO(expected_swift_contents)

            global SWIFT_PUT_OBJECT_CALLS
            SWIFT_PUT_OBJECT_CALLS = 0

            self.store = Store(test_utils.TestConfigOpts(new_conf))
            location, size, checksum = self.store.add(image_id, image_swift,
                                                      expected_swift_size)

            self.assertEquals(expected_location, location)
            self.assertEquals(expected_swift_size, size)
            self.assertEquals(expected_checksum, checksum)
            self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 1)

            loc = get_location_from_uri(expected_location)
            (new_image_swift, new_image_size) = self.store.get(loc)
            new_image_contents = new_image_swift.getvalue()
            new_image_swift_size = new_image_swift.len

            self.assertEquals(expected_swift_contents, new_image_contents)
            self.assertEquals(expected_swift_size, new_image_swift_size)

    def test_add_no_container_no_create(self):
        """
        Tests that adding an image with a non-existing container
        raises an appropriate exception
        """
        conf = SWIFT_CONF.copy()
        conf['swift_store_create_container_on_put'] = 'False'
        conf['swift_store_container'] = 'noexist'
        image_swift = StringIO.StringIO("nevergonnamakeit")
        self.store = Store(test_utils.TestConfigOpts(conf))

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        # We check the exception text to ensure the container
        # missing text is found in it, otherwise, we would have
        # simply used self.assertRaises here
        exception_caught = False
        try:
            self.store.add(utils.generate_uuid(), image_swift, 0)
        except BackendException, e:
            exception_caught = True
            self.assertTrue("container noexist does not exist "
                            "in Swift" in str(e))
        self.assertTrue(exception_caught)
        self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 0)

    def test_add_no_container_and_create(self):
        """
        Tests that adding an image with a non-existing container
        creates the container automatically if flag is set
        """
        conf = SWIFT_CONF.copy()
        conf['swift_store_create_container_on_put'] = 'True'
        conf['swift_store_container'] = 'noexist'
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = utils.generate_uuid()
        expected_location = 'swift+https://user:key@localhost:8080' + \
                            '/noexist/%s' % expected_image_id
        image_swift = StringIO.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        self.store = Store(test_utils.TestConfigOpts(conf))
        location, size, checksum = self.store.add(expected_image_id,
                                                  image_swift,
                                                  expected_swift_size)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)
        self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 1)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = new_image_swift.getvalue()
        new_image_swift_size = new_image_swift.len

        self.assertEquals(expected_swift_contents, new_image_contents)
        self.assertEquals(expected_swift_size, new_image_swift_size)

    def test_add_large_object(self):
        """
        Tests that adding a very large image. We simulate the large
        object by setting store.large_object_size to a small number
        and then verify that there have been a number of calls to
        put_object()...
        """
        conf = SWIFT_CONF.copy()
        conf['swift_store_container'] = 'glance'
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = utils.generate_uuid()
        expected_location = 'swift+https://user:key@localhost:8080' + \
                            '/glance/%s' % expected_image_id
        image_swift = StringIO.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        self.store = Store(test_utils.TestConfigOpts(conf))
        orig_max_size = self.store.large_object_size
        orig_temp_size = self.store.large_object_chunk_size
        try:
            self.store.large_object_size = 1024
            self.store.large_object_chunk_size = 1024
            location, size, checksum = self.store.add(expected_image_id,
                                                      image_swift,
                                                      expected_swift_size)
        finally:
            self.store.large_object_chunk_size = orig_temp_size
            self.store.large_object_size = orig_max_size

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)
        # Expecting 6 objects to be created on Swift -- 5 chunks and 1
        # manifest.
        self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 6)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = new_image_swift.getvalue()
        new_image_swift_size = new_image_swift.len

        self.assertEquals(expected_swift_contents, new_image_contents)
        self.assertEquals(expected_swift_size, new_image_swift_size)

    def test_add_large_object_zero_size(self):
        """
        Tests that adding an image to Swift which has both an unknown size and
        exceeds Swift's maximum limit of 5GB is correctly uploaded.

        We avoid the overhead of creating a 5GB object for this test by
        temporarily setting MAX_SWIFT_OBJECT_SIZE to 1KB, and then adding
        an object of 5KB.

        Bug lp:891738
        """
        conf = SWIFT_CONF.copy()
        conf['swift_store_container'] = 'glance'

        # Set up a 'large' image of 5KB
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = utils.generate_uuid()
        expected_location = 'swift+https://user:key@localhost:8080' + \
                            '/glance/%s' % expected_image_id
        image_swift = StringIO.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        # Temporarily set Swift MAX_SWIFT_OBJECT_SIZE to 1KB and add our image,
        # explicitly setting the image_length to 0
        self.store = Store(test_utils.TestConfigOpts(conf))
        orig_max_size = self.store.large_object_size
        orig_temp_size = self.store.large_object_chunk_size
        global MAX_SWIFT_OBJECT_SIZE
        orig_max_swift_object_size = MAX_SWIFT_OBJECT_SIZE
        try:
            MAX_SWIFT_OBJECT_SIZE = 1024
            self.store.large_object_size = 1024
            self.store.large_object_chunk_size = 1024
            location, size, checksum = self.store.add(expected_image_id,
                                                      image_swift, 0)
        finally:
            self.store.large_object_chunk_size = orig_temp_size
            self.store.large_object_size = orig_max_size
            MAX_SWIFT_OBJECT_SIZE = orig_max_swift_object_size

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_swift_size, size)
        self.assertEquals(expected_checksum, checksum)
        # Expecting 7 calls to put_object -- 5 chunks, a zero chunk which is
        # then deleted, and the manifest.  Note the difference with above
        # where the image_size is specified in advance (there's no zero chunk
        # in that case).
        self.assertEquals(SWIFT_PUT_OBJECT_CALLS, 7)

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
                          FAKE_UUID, image_swift, 0)

    def _option_required(self, key):
        conf = SWIFT_CONF.copy()
        del conf[key]

        try:
            self.store = Store(test_utils.TestConfigOpts(conf))
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
        uri = "swift://user:key@authurl/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        self.store.delete(loc)

        self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a swift that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("swift://user:key@authurl/glance/noexist")
        self.assertRaises(exception.NotFound, self.store.delete, loc)


class TestChunkReader(unittest.TestCase):

    def test_read_all_data(self):
        """
        Replicate what goes on in the Swift driver with the
        repeated creation of the ChunkReader object
        """
        CHUNKSIZE = 100
        checksum = hashlib.md5()
        data_file = tempfile.NamedTemporaryFile()
        data_file.write('*' * 1024)
        data_file.flush()
        infile = open(data_file.name, 'rb')
        bytes_read = 0
        while True:
            cr = glance.store.swift.ChunkReader(infile, checksum, CHUNKSIZE)
            chunk = cr.read(CHUNKSIZE)
            bytes_read += len(chunk)
            if len(chunk) == 0:
                break
        self.assertEqual(1024, bytes_read)
        data_file.close()
