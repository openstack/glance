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

"""Tests the Swift backend store"""

import hashlib
import httplib
import mock
import tempfile
import uuid

from oslo.config import cfg
import six
import six.moves.urllib.parse as urlparse
import stubout
import swiftclient

import glance.common.auth
from glance.common import exception
from glance.openstack.common import units

from glance.store import BackendException
from glance.store.location import get_location_from_uri
from glance.store.swift import swift_retry_iter
from glance.tests.unit import base

CONF = cfg.CONF

FAKE_UUID = lambda: str(uuid.uuid4())

Store = glance.store.swift.Store
FIVE_KB = 5 * units.Ki
FIVE_GB = 5 * units.Gi
MAX_SWIFT_OBJECT_SIZE = FIVE_GB
SWIFT_PUT_OBJECT_CALLS = 0
SWIFT_CONF = {'verbose': True,
              'debug': True,
              'known_stores': ['glance.store.swift.Store'],
              'default_store': 'swift',
              'swift_store_user': 'user',
              'swift_store_key': 'key',
              'swift_store_auth_address': 'localhost:8080',
              'swift_store_container': 'glance',
              'swift_store_retry_get_count': 1}


# We stub out as little as possible to ensure that the code paths
# between glance.store.swift and swiftclient are tested
# thoroughly
def stub_out_swiftclient(stubs, swift_store_auth_version):
    fixture_containers = ['glance']
    fixture_container_headers = {}
    fixture_headers = {
        'glance/%s' % FAKE_UUID: {
            'content-length': FIVE_KB,
            'etag': 'c2e5db72bd7fd153f53ede5da5a06de3'
        }
    }
    fixture_objects = {'glance/%s' % FAKE_UUID:
                       six.StringIO("*" * FIVE_KB)}

    def fake_head_container(url, token, container, **kwargs):
        if container not in fixture_containers:
            msg = "No container %s found" % container
            raise swiftclient.ClientException(msg,
                                              http_status=httplib.NOT_FOUND)
        return fixture_container_headers

    def fake_put_container(url, token, container, **kwargs):
        fixture_containers.append(container)

    def fake_post_container(url, token, container, headers, http_conn=None):
        for key, value in headers.iteritems():
            fixture_container_headers[key] = value

    def fake_put_object(url, token, container, name, contents, **kwargs):
        # PUT returns the ETag header for the newly-added object
        # Large object manifest...
        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS += 1
        CHUNKSIZE = 64 * units.Ki
        fixture_key = "%s/%s" % (container, name)
        if fixture_key not in fixture_headers:
            if kwargs.get('headers'):
                etag = kwargs['headers']['ETag']
                fixture_headers[fixture_key] = {'manifest': True,
                                                'etag': etag}
                return etag
            if hasattr(contents, 'read'):
                fixture_object = six.StringIO()
                chunk = contents.read(CHUNKSIZE)
                checksum = hashlib.md5()
                while chunk:
                    fixture_object.write(chunk)
                    checksum.update(chunk)
                    chunk = contents.read(CHUNKSIZE)
                etag = checksum.hexdigest()
            else:
                fixture_object = six.StringIO(contents)
                etag = hashlib.md5(fixture_object.getvalue()).hexdigest()
            read_len = fixture_object.len
            if read_len > MAX_SWIFT_OBJECT_SIZE:
                msg = ('Image size:%d exceeds Swift max:%d' %
                       (read_len, MAX_SWIFT_OBJECT_SIZE))
                raise swiftclient.ClientException(
                    msg, http_status=httplib.REQUEST_ENTITY_TOO_LARGE)
            fixture_objects[fixture_key] = fixture_object
            fixture_headers[fixture_key] = {
                'content-length': read_len,
                'etag': etag}
            return etag
        else:
            msg = ("Object PUT failed - Object with key %s already exists"
                   % fixture_key)
            raise swiftclient.ClientException(msg,
                                              http_status=httplib.CONFLICT)

    def fake_get_object(url, token, container, name, **kwargs):
        # GET returns the tuple (list of headers, file object)
        fixture_key = "%s/%s" % (container, name)
        if fixture_key not in fixture_headers:
            msg = "Object GET failed"
            raise swiftclient.ClientException(msg,
                                              http_status=httplib.NOT_FOUND)

        byte_range = None
        headers = kwargs.get('headers', dict())
        if headers is not None:
            headers = dict((k.lower(), v) for k, v in headers.iteritems())
            if 'range' in headers:
                byte_range = headers.get('range')

        fixture = fixture_headers[fixture_key]
        if 'manifest' in fixture:
            # Large object manifest... we return a file containing
            # all objects with prefix of this fixture key
            chunk_keys = sorted([k for k in fixture_headers.keys()
                                 if k.startswith(fixture_key) and
                                 k != fixture_key])
            result = six.StringIO()
            for key in chunk_keys:
                result.write(fixture_objects[key].getvalue())
        else:
            result = fixture_objects[fixture_key]

        if byte_range is not None:
            start = int(byte_range.split('=')[1].strip('-'))
            result = six.StringIO(result.getvalue()[start:])
            fixture_headers[fixture_key]['content-length'] = len(
                result.getvalue())

        return fixture_headers[fixture_key], result

    def fake_head_object(url, token, container, name, **kwargs):
        # HEAD returns the list of headers for an object
        try:
            fixture_key = "%s/%s" % (container, name)
            return fixture_headers[fixture_key]
        except KeyError:
            msg = "Object HEAD failed - Object does not exist"
            raise swiftclient.ClientException(msg,
                                              http_status=httplib.NOT_FOUND)

    def fake_delete_object(url, token, container, name, **kwargs):
        # DELETE returns nothing
        fixture_key = "%s/%s" % (container, name)
        if fixture_key not in fixture_headers:
            msg = "Object DELETE failed - Object does not exist"
            raise swiftclient.ClientException(msg,
                                              http_status=httplib.NOT_FOUND)
        else:
            del fixture_headers[fixture_key]
            del fixture_objects[fixture_key]

    def fake_http_connection(*args, **kwargs):
        return None

    def fake_get_auth(url, user, key, snet, auth_version, **kwargs):
        if url is None:
            return None, None
        if 'http' in url and '://' not in url:
            raise ValueError('Invalid url %s' % url)
        # Check the auth version against the configured value
        if swift_store_auth_version != auth_version:
            msg = 'AUTHENTICATION failed (version mismatch)'
            raise swiftclient.ClientException(msg)
        return None, None

    stubs.Set(swiftclient.client,
              'head_container', fake_head_container)
    stubs.Set(swiftclient.client,
              'put_container', fake_put_container)
    stubs.Set(swiftclient.client,
              'post_container', fake_post_container)
    stubs.Set(swiftclient.client,
              'put_object', fake_put_object)
    stubs.Set(swiftclient.client,
              'delete_object', fake_delete_object)
    stubs.Set(swiftclient.client,
              'head_object', fake_head_object)
    stubs.Set(swiftclient.client,
              'get_object', fake_get_object)
    stubs.Set(swiftclient.client,
              'get_auth', fake_get_auth)
    stubs.Set(swiftclient.client,
              'http_connection', fake_http_connection)


class SwiftTests(object):

    @property
    def swift_store_user(self):
        return urlparse.quote(CONF.swift_store_user)

    def test_get_size(self):
        """
        Test that we can get the size of an object in the swift store
        """
        uri = "swift://%s:key@auth_address/glance/%s" % (
            self.swift_store_user, FAKE_UUID)
        loc = get_location_from_uri(uri)
        image_size = self.store.get_size(loc)
        self.assertEqual(image_size, 5120)

    def test_get_size_with_multi_tenant_on(self):
        """Test that single tenant uris work with multi tenant on."""
        uri = ("swift://%s:key@auth_address/glance/%s" %
               (self.swift_store_user, FAKE_UUID))
        self.config(swift_store_multi_tenant=True)
        #NOTE(markwash): ensure the image is found
        context = glance.context.RequestContext()
        size = glance.store.get_size_from_backend(context, uri)
        self.assertEqual(size, 5120)

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        uri = "swift://%s:key@auth_address/glance/%s" % (
            self.swift_store_user, FAKE_UUID)
        loc = get_location_from_uri(uri)
        (image_swift, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 5120)

        expected_data = "*" * FIVE_KB
        data = ""

        for chunk in image_swift:
            data += chunk
        self.assertEqual(expected_data, data)

    def test_get_with_retry(self):
        """
        Test a retrieval where Swift does not get the full image in a single
        request.
        """
        uri = "swift://%s:key@auth_address/glance/%s" % (
            self.swift_store_user, FAKE_UUID)
        loc = get_location_from_uri(uri)
        (image_swift, image_size) = self.store.get(loc)
        resp_full = ''.join([chunk for chunk in image_swift.wrapped])
        resp_half = resp_full[:len(resp_full) / 2]
        image_swift.wrapped = swift_retry_iter(resp_half, image_size,
                                               self.store,
                                               loc.store_location)
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
        loc = get_location_from_uri("swift+http://%s:key@auth_address/"
                                    "glance/%s" %
                                    (self.swift_store_user, FAKE_UUID))
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
        loc = get_location_from_uri("swift://%s:key@authurl/glance/noexist" % (
            self.swift_store_user))
        self.assertRaises(exception.NotFound,
                          self.store.get,
                          loc)

    def test_add(self):
        """Test that we can add an image via the swift backend"""
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = str(uuid.uuid4())
        loc = 'swift+https://%s:key@localhost:8080/glance/%s'
        expected_location = loc % (self.swift_store_user,
                                   expected_image_id)
        image_swift = six.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        location, size, checksum, _ = self.store.add(expected_image_id,
                                                     image_swift,
                                                     expected_swift_size)

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_swift_size, size)
        self.assertEqual(expected_checksum, checksum)
        # Expecting a single object to be created on Swift i.e. no chunking.
        self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 1)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = ''.join([chunk for chunk in new_image_swift])
        new_image_swift_size = len(new_image_swift)

        self.assertEqual(expected_swift_contents, new_image_contents)
        self.assertEqual(expected_swift_size, new_image_swift_size)

    def test_add_auth_url_variations(self):
        """
        Test that we can add an image via the swift backend with
        a variety of different auth_address values
        """
        variations = {
            'http://localhost:80': 'swift+http://%s:key@localhost:80'
                                   '/glance/%s',
            'http://localhost': 'swift+http://%s:key@localhost/glance/%s',
            'http://localhost/v1': 'swift+http://%s:key@localhost'
                                   '/v1/glance/%s',
            'http://localhost/v1/': 'swift+http://%s:key@localhost'
                                    '/v1/glance/%s',
            'https://localhost': 'swift+https://%s:key@localhost/glance/%s',
            'https://localhost:8080': 'swift+https://%s:key@localhost:8080'
                                      '/glance/%s',
            'https://localhost/v1': 'swift+https://%s:key@localhost'
                                    '/v1/glance/%s',
            'https://localhost/v1/': 'swift+https://%s:key@localhost'
                                     '/v1/glance/%s',
            'localhost': 'swift+https://%s:key@localhost/glance/%s',
            'localhost:8080/v1': 'swift+https://%s:key@localhost:8080'
                                 '/v1/glance/%s',
        }

        for variation, expected_location in variations.items():
            image_id = str(uuid.uuid4())
            expected_location = expected_location % (
                self.swift_store_user, image_id)
            expected_swift_size = FIVE_KB
            expected_swift_contents = "*" * expected_swift_size
            expected_checksum = \
                hashlib.md5(expected_swift_contents).hexdigest()

            image_swift = six.StringIO(expected_swift_contents)

            global SWIFT_PUT_OBJECT_CALLS
            SWIFT_PUT_OBJECT_CALLS = 0

            self.config(swift_store_auth_address=variation)
            self.store = Store()
            location, size, checksum, _ = self.store.add(image_id, image_swift,
                                                         expected_swift_size)

            self.assertEqual(expected_location, location)
            self.assertEqual(expected_swift_size, size)
            self.assertEqual(expected_checksum, checksum)
            self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 1)

            loc = get_location_from_uri(expected_location)
            (new_image_swift, new_image_size) = self.store.get(loc)
            new_image_contents = ''.join([chunk for chunk in new_image_swift])
            new_image_swift_size = len(new_image_swift)

            self.assertEqual(expected_swift_contents, new_image_contents)
            self.assertEqual(expected_swift_size, new_image_swift_size)

    def test_add_no_container_no_create(self):
        """
        Tests that adding an image with a non-existing container
        raises an appropriate exception
        """
        self.config(swift_store_create_container_on_put=False,
                    swift_store_container='noexist')
        self.store = Store()

        image_swift = six.StringIO("nevergonnamakeit")

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        # We check the exception text to ensure the container
        # missing text is found in it, otherwise, we would have
        # simply used self.assertRaises here
        exception_caught = False
        try:
            self.store.add(str(uuid.uuid4()), image_swift, 0)
        except BackendException as e:
            exception_caught = True
            self.assertTrue("container noexist does not exist "
                            "in Swift" in six.text_type(e))
        self.assertTrue(exception_caught)
        self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 0)

    def test_add_no_container_and_create(self):
        """
        Tests that adding an image with a non-existing container
        creates the container automatically if flag is set
        """
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = str(uuid.uuid4())
        loc = 'swift+https://%s:key@localhost:8080/noexist/%s'
        expected_location = loc % (self.swift_store_user,
                                   expected_image_id)
        image_swift = six.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        self.config(swift_store_create_container_on_put=True,
                    swift_store_container='noexist')
        self.store = Store()
        location, size, checksum, _ = self.store.add(expected_image_id,
                                                     image_swift,
                                                     expected_swift_size)

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_swift_size, size)
        self.assertEqual(expected_checksum, checksum)
        self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 1)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = ''.join([chunk for chunk in new_image_swift])
        new_image_swift_size = len(new_image_swift)

        self.assertEqual(expected_swift_contents, new_image_contents)
        self.assertEqual(expected_swift_size, new_image_swift_size)

    def test_add_large_object(self):
        """
        Tests that adding a very large image. We simulate the large
        object by setting store.large_object_size to a small number
        and then verify that there have been a number of calls to
        put_object()...
        """
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = str(uuid.uuid4())
        loc = 'swift+https://%s:key@localhost:8080/glance/%s'
        expected_location = loc % (self.swift_store_user,
                                   expected_image_id)
        image_swift = six.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        self.config(swift_store_container='glance')
        self.store = Store()
        orig_max_size = self.store.large_object_size
        orig_temp_size = self.store.large_object_chunk_size
        try:
            self.store.large_object_size = 1024
            self.store.large_object_chunk_size = 1024
            location, size, checksum, _ = self.store.add(expected_image_id,
                                                         image_swift,
                                                         expected_swift_size)
        finally:
            self.store.large_object_chunk_size = orig_temp_size
            self.store.large_object_size = orig_max_size

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_swift_size, size)
        self.assertEqual(expected_checksum, checksum)
        # Expecting 6 objects to be created on Swift -- 5 chunks and 1
        # manifest.
        self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 6)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = ''.join([chunk for chunk in new_image_swift])
        new_image_swift_size = len(new_image_contents)

        self.assertEqual(expected_swift_contents, new_image_contents)
        self.assertEqual(expected_swift_size, new_image_swift_size)

    def test_add_large_object_zero_size(self):
        """
        Tests that adding an image to Swift which has both an unknown size and
        exceeds Swift's maximum limit of 5GB is correctly uploaded.

        We avoid the overhead of creating a 5GB object for this test by
        temporarily setting MAX_SWIFT_OBJECT_SIZE to 1KB, and then adding
        an object of 5KB.

        Bug lp:891738
        """
        # Set up a 'large' image of 5KB
        expected_swift_size = FIVE_KB
        expected_swift_contents = "*" * expected_swift_size
        expected_checksum = hashlib.md5(expected_swift_contents).hexdigest()
        expected_image_id = str(uuid.uuid4())
        loc = 'swift+https://%s:key@localhost:8080/glance/%s'
        expected_location = loc % (self.swift_store_user,
                                   expected_image_id)
        image_swift = six.StringIO(expected_swift_contents)

        global SWIFT_PUT_OBJECT_CALLS
        SWIFT_PUT_OBJECT_CALLS = 0

        # Temporarily set Swift MAX_SWIFT_OBJECT_SIZE to 1KB and add our image,
        # explicitly setting the image_length to 0
        self.config(swift_store_container='glance')
        self.store = Store()
        orig_max_size = self.store.large_object_size
        orig_temp_size = self.store.large_object_chunk_size
        global MAX_SWIFT_OBJECT_SIZE
        orig_max_swift_object_size = MAX_SWIFT_OBJECT_SIZE
        try:
            MAX_SWIFT_OBJECT_SIZE = 1024
            self.store.large_object_size = 1024
            self.store.large_object_chunk_size = 1024
            location, size, checksum, _ = self.store.add(expected_image_id,
                                                         image_swift, 0)
        finally:
            self.store.large_object_chunk_size = orig_temp_size
            self.store.large_object_size = orig_max_size
            MAX_SWIFT_OBJECT_SIZE = orig_max_swift_object_size

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_swift_size, size)
        self.assertEqual(expected_checksum, checksum)
        # Expecting 7 calls to put_object -- 5 chunks, a zero chunk which is
        # then deleted, and the manifest.  Note the difference with above
        # where the image_size is specified in advance (there's no zero chunk
        # in that case).
        self.assertEqual(SWIFT_PUT_OBJECT_CALLS, 7)

        loc = get_location_from_uri(expected_location)
        (new_image_swift, new_image_size) = self.store.get(loc)
        new_image_contents = ''.join([chunk for chunk in new_image_swift])
        new_image_swift_size = len(new_image_contents)

        self.assertEqual(expected_swift_contents, new_image_contents)
        self.assertEqual(expected_swift_size, new_image_swift_size)

    def test_add_already_existing(self):
        """
        Tests that adding an image with an existing identifier
        raises an appropriate exception
        """
        image_swift = six.StringIO("nevergonnamakeit")
        self.assertRaises(exception.Duplicate,
                          self.store.add,
                          FAKE_UUID, image_swift, 0)

    def test_add_saves_and_reraises_and_not_uses_wildcard_raise(self):
        image_id = str(uuid.uuid4())
        swift_size = self.store.large_object_size = 1024
        swift_contents = "*" * swift_size
        connection = mock.Mock()

        def fake_delete_chunk(connection,
                              container,
                              chunks):
            try:
                raise Exception()
            except Exception:
                pass

        image_swift = six.StringIO(swift_contents)
        connection.put_object.side_effect = exception.ClientConnectionError
        self.store._delete_stale_chunks = fake_delete_chunk

        self.assertRaises(exception.ClientConnectionError,
                          self.store.add,
                          image_id,
                          image_swift,
                          swift_size,
                          connection)

    def _option_required(self, key):
        conf = self.getConfig()
        conf[key] = None

        try:
            self.config(**conf)
            self.store = Store()
            return self.store.add == self.store.add_disabled
        except Exception:
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
        uri = "swift://%s:key@authurl/glance/%s" % (
            self.swift_store_user, FAKE_UUID)
        loc = get_location_from_uri(uri)
        self.store.delete(loc)

        self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a swift that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("swift://%s:key@authurl/glance/noexist" % (
            self.swift_store_user))
        self.assertRaises(exception.NotFound, self.store.delete, loc)

    def test_read_acl_public(self):
        """
        Test that we can set a public read acl.
        """
        self.config(swift_store_multi_tenant=True)
        context = glance.context.RequestContext()
        store = Store(context)
        uri = "swift+http://storeurl/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        store.set_acls(loc, public=True)
        container_headers = swiftclient.client.head_container('x', 'y',
                                                              'glance')
        self.assertEqual(container_headers['X-Container-Read'],
                         ".r:*,.rlistings")

    def test_read_acl_tenants(self):
        """
        Test that we can set read acl for tenants.
        """
        self.config(swift_store_multi_tenant=True)
        context = glance.context.RequestContext()
        store = Store(context)
        uri = "swift+http://storeurl/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        read_tenants = ['matt', 'mark']
        store.set_acls(loc, read_tenants=read_tenants)
        container_headers = swiftclient.client.head_container('x', 'y',
                                                              'glance')
        self.assertEqual(container_headers['X-Container-Read'],
                         'matt:*,mark:*')

    def test_write_acls(self):
        """
        Test that we can set write acl for tenants.
        """
        self.config(swift_store_multi_tenant=True)
        context = glance.context.RequestContext()
        store = Store(context)
        uri = "swift+http://storeurl/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        read_tenants = ['frank', 'jim']
        store.set_acls(loc, write_tenants=read_tenants)
        container_headers = swiftclient.client.head_container('x', 'y',
                                                              'glance')
        self.assertEqual(container_headers['X-Container-Write'],
                         'frank:*,jim:*')


class TestStoreAuthV1(base.StoreClearingUnitTest, SwiftTests):

    def getConfig(self):
        conf = SWIFT_CONF.copy()
        conf['swift_store_auth_version'] = '1'
        conf['swift_store_user'] = 'user'
        return conf

    def setUp(self):
        """Establish a clean test environment"""
        conf = self.getConfig()
        self.config(**conf)
        super(TestStoreAuthV1, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        stub_out_swiftclient(self.stubs, conf['swift_store_auth_version'])
        self.store = Store()
        self.addCleanup(self.stubs.UnsetAll)


class TestStoreAuthV2(TestStoreAuthV1):

    def getConfig(self):
        conf = super(TestStoreAuthV2, self).getConfig()
        conf['swift_store_user'] = 'tenant:user'
        conf['swift_store_auth_version'] = '2'
        return conf

    def test_v2_with_no_tenant(self):
        conf = self.getConfig()
        conf['swift_store_user'] = 'failme'
        uri = "swift://%s:key@auth_address/glance/%s" % (
            conf['swift_store_user'], FAKE_UUID)
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.BadStoreUri,
                          self.store.get,
                          loc)

    def test_v2_multi_tenant_location(self):
        conf = self.getConfig()
        conf['swift_store_multi_tenant'] = True
        uri = "swift://auth_address/glance/%s" % (FAKE_UUID)
        loc = get_location_from_uri(uri)
        self.assertEqual('swift', loc.store_name)


class FakeConnection(object):
    def __init__(self, authurl, user, key, retries=5, preauthurl=None,
                 preauthtoken=None, snet=False, starting_backoff=1,
                 tenant_name=None, os_options={}, auth_version="1",
                 insecure=False, ssl_compression=True):
        self.authurl = authurl
        self.user = user
        self.key = key
        self.preauthurl = preauthurl
        self.preauthtoken = preauthtoken
        self.snet = snet
        self.tenant_name = tenant_name
        self.os_options = os_options
        self.auth_version = auth_version
        self.insecure = insecure


class TestSingleTenantStoreConnections(base.IsolatedUnitTest):
    def setUp(self):
        super(TestSingleTenantStoreConnections, self).setUp()
        self.stubs.Set(swiftclient, 'Connection', FakeConnection)
        self.store = glance.store.swift.SingleTenantStore()
        specs = {'scheme': 'swift',
                 'auth_or_store_url': 'example.com/v2/',
                 'user': 'tenant:user',
                 'key': 'abcdefg',
                 'container': 'cont',
                 'obj': 'object'}
        self.location = glance.store.swift.StoreLocation(specs)

    def test_basic_connection(self):
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.authurl, 'https://example.com/v2/')
        self.assertEqual(connection.auth_version, '2')
        self.assertEqual(connection.user, 'user')
        self.assertEqual(connection.tenant_name, 'tenant')
        self.assertEqual(connection.key, 'abcdefg')
        self.assertFalse(connection.snet)
        self.assertIsNone(connection.preauthurl)
        self.assertIsNone(connection.preauthtoken)
        self.assertFalse(connection.insecure)
        self.assertEqual(connection.os_options,
                         {'service_type': 'object-store',
                          'endpoint_type': 'publicURL'})

    def test_connection_with_no_trailing_slash(self):
        self.location.auth_or_store_url = 'example.com/v2'
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.authurl, 'https://example.com/v2/')

    def test_connection_insecure(self):
        self.config(swift_store_auth_insecure=True)
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertTrue(connection.insecure)

    def test_connection_with_auth_v1(self):
        self.config(swift_store_auth_version='1')
        self.store.configure()
        self.location.user = 'auth_v1_user'
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.auth_version, '1')
        self.assertEqual(connection.user, 'auth_v1_user')
        self.assertIsNone(connection.tenant_name)

    def test_connection_invalid_user(self):
        self.store.configure()
        self.location.user = 'invalid:format:user'
        self.assertRaises(exception.BadStoreUri,
                          self.store.get_connection, self.location)

    def test_connection_missing_user(self):
        self.store.configure()
        self.location.user = None
        self.assertRaises(exception.BadStoreUri,
                          self.store.get_connection, self.location)

    def test_connection_with_region(self):
        self.config(swift_store_region='Sahara')
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.os_options,
                         {'region_name': 'Sahara',
                          'service_type': 'object-store',
                          'endpoint_type': 'publicURL'})

    def test_connection_with_service_type(self):
        self.config(swift_store_service_type='shoe-store')
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.os_options,
                         {'service_type': 'shoe-store',
                          'endpoint_type': 'publicURL'})

    def test_connection_with_endpoint_type(self):
        self.config(swift_store_endpoint_type='internalURL')
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertEqual(connection.os_options,
                         {'service_type': 'object-store',
                          'endpoint_type': 'internalURL'})

    def test_connection_with_snet(self):
        self.config(swift_enable_snet=True)
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertTrue(connection.snet)


class TestMultiTenantStoreConnections(base.IsolatedUnitTest):
    def setUp(self):
        super(TestMultiTenantStoreConnections, self).setUp()
        self.stubs.Set(swiftclient, 'Connection', FakeConnection)
        self.context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='0123')
        self.store = glance.store.swift.MultiTenantStore(self.context)
        specs = {'scheme': 'swift',
                 'auth_or_store_url': 'example.com',
                 'container': 'cont',
                 'obj': 'object'}
        self.location = glance.store.swift.StoreLocation(specs)

    def test_basic_connection(self):
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertIsNone(connection.authurl)
        self.assertEqual(connection.auth_version, '2')
        self.assertEqual(connection.user, 'user')
        self.assertEqual(connection.tenant_name, 'tenant')
        self.assertIsNone(connection.key)
        self.assertFalse(connection.snet)
        self.assertEqual(connection.preauthurl, 'https://example.com')
        self.assertEqual(connection.preauthtoken, '0123')
        self.assertEqual(connection.os_options, {})

    def test_connection_with_snet(self):
        self.config(swift_enable_snet=True)
        self.store.configure()
        connection = self.store.get_connection(self.location)
        self.assertTrue(connection.snet)


class FakeGetEndpoint(object):
    def __init__(self, response):
        self.response = response

    def __call__(self, service_catalog, service_type=None,
                 endpoint_region=None, endpoint_type=None):
        self.service_type = service_type
        self.endpoint_region = endpoint_region
        self.endpoint_type = endpoint_type
        return self.response


class TestCreatingLocations(base.IsolatedUnitTest):
    def test_single_tenant_location(self):
        self.config(swift_store_auth_address='example.com/v2',
                    swift_store_container='container',
                    swift_store_user='tenant:user',
                    swift_store_key='auth_key')
        store = glance.store.swift.SingleTenantStore()
        location = store.create_location('image-id')
        self.assertEqual(location.scheme, 'swift+https')
        self.assertEqual(location.swift_url, 'https://example.com/v2')
        self.assertEqual(location.container, 'container')
        self.assertEqual(location.obj, 'image-id')
        self.assertEqual(location.user, 'tenant:user')
        self.assertEqual(location.key, 'auth_key')

    def test_single_tenant_location_http(self):
        self.config(swift_store_auth_address='http://example.com/v2',
                    swift_store_container='container',
                    swift_store_user='tenant:user',
                    swift_store_key='auth_key')
        store = glance.store.swift.SingleTenantStore()
        location = store.create_location('image-id')
        self.assertEqual(location.scheme, 'swift+http')
        self.assertEqual(location.swift_url, 'http://example.com/v2')

    def test_multi_tenant_location(self):
        self.config(swift_store_container='container')
        fake_get_endpoint = FakeGetEndpoint('https://some_endpoint')
        self.stubs.Set(glance.common.auth, 'get_endpoint', fake_get_endpoint)
        context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='123',
            service_catalog={})
        store = glance.store.swift.MultiTenantStore(context)
        location = store.create_location('image-id')
        self.assertEqual(location.scheme, 'swift+https')
        self.assertEqual(location.swift_url, 'https://some_endpoint')
        self.assertEqual(location.container, 'container_image-id')
        self.assertEqual(location.obj, 'image-id')
        self.assertIsNone(location.user)
        self.assertIsNone(location.key)
        self.assertEqual(fake_get_endpoint.service_type, 'object-store')

    def test_multi_tenant_location_http(self):
        fake_get_endpoint = FakeGetEndpoint('http://some_endpoint')
        self.stubs.Set(glance.common.auth, 'get_endpoint', fake_get_endpoint)
        context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='123',
            service_catalog={})
        store = glance.store.swift.MultiTenantStore(context)
        location = store.create_location('image-id')
        self.assertEqual(location.scheme, 'swift+http')
        self.assertEqual(location.swift_url, 'http://some_endpoint')

    def test_multi_tenant_location_with_region(self):
        self.config(swift_store_region='WestCarolina')
        fake_get_endpoint = FakeGetEndpoint('https://some_endpoint')
        self.stubs.Set(glance.common.auth, 'get_endpoint', fake_get_endpoint)
        context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='123',
            service_catalog={})
        glance.store.swift.MultiTenantStore(context)
        self.assertEqual(fake_get_endpoint.endpoint_region, 'WestCarolina')

    def test_multi_tenant_location_custom_service_type(self):
        self.config(swift_store_service_type='toy-store')
        fake_get_endpoint = FakeGetEndpoint('https://some_endpoint')
        self.stubs.Set(glance.common.auth, 'get_endpoint', fake_get_endpoint)
        context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='123',
            service_catalog={})
        glance.store.swift.MultiTenantStore(context)
        self.assertEqual(fake_get_endpoint.service_type, 'toy-store')

    def test_multi_tenant_location_custom_endpoint_type(self):
        self.config(swift_store_endpoint_type='InternalURL')
        fake_get_endpoint = FakeGetEndpoint('https://some_endpoint')
        self.stubs.Set(glance.common.auth, 'get_endpoint', fake_get_endpoint)
        context = glance.context.RequestContext(
            user='user', tenant='tenant', auth_tok='123',
            service_catalog={})
        glance.store.swift.MultiTenantStore(context)
        self.assertEqual(fake_get_endpoint.endpoint_type, 'InternalURL')


class TestChunkReader(base.StoreClearingUnitTest):

    def test_read_all_data(self):
        """
        Replicate what goes on in the Swift driver with the
        repeated creation of the ChunkReader object
        """
        CHUNKSIZE = 100
        checksum = hashlib.md5()
        data_file = tempfile.NamedTemporaryFile()
        data_file.write('*' * units.Ki)
        data_file.flush()
        infile = open(data_file.name, 'rb')
        bytes_read = 0
        while True:
            cr = glance.store.swift.ChunkReader(infile, checksum, CHUNKSIZE)
            chunk = cr.read(CHUNKSIZE)
            bytes_read += len(chunk)
            if not chunk:
                break
        self.assertEqual(1024, bytes_read)
        data_file.close()
