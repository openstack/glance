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

"""Tests the S3 backend store"""

import hashlib
import uuid
import xml.etree.ElementTree

import boto.s3.connection
import mock
import six
import stubout

from glance.common import exception
from glance.openstack.common import units

from glance.store.location import get_location_from_uri
import glance.store.s3
from glance.store.s3 import get_s3_location
from glance.store.s3 import Store
from glance.store import UnsupportedBackend
from glance.tests.unit import base


FAKE_UUID = str(uuid.uuid4())

FIVE_KB = 5 * units.Ki
S3_CONF = {'verbose': True,
           'debug': True,
           'default_store': 's3',
           's3_store_access_key': 'user',
           's3_store_secret_key': 'key',
           's3_store_host': 'localhost:8080',
           's3_store_bucket': 'glance',
           'known_stores': ['glance.store.s3.Store'],
           's3_store_large_object_size': 5,        # over 5MB is large
           's3_store_large_object_chunk_size': 6}  # part size is 6MB

# ensure that mpu api is used and parts are uploaded as expected
mpu_parts_uploaded = 0


# We stub out as little as possible to ensure that the code paths
# between glance.store.s3 and boto.s3.connection are tested
# thoroughly
def stub_out_s3(stubs):

    class FakeKey:
        """
        Acts like a ``boto.s3.key.Key``
        """
        def __init__(self, bucket, name):
            self.bucket = bucket
            self.name = name
            self.data = None
            self.size = 0
            self.etag = None
            self.BufferSize = 1024

        def close(self):
            pass

        def exists(self):
            return self.bucket.exists(self.name)

        def delete(self):
            self.bucket.delete(self.name)

        def compute_md5(self, data):
            chunk = data.read(self.BufferSize)
            checksum = hashlib.md5()
            while chunk:
                checksum.update(chunk)
                chunk = data.read(self.BufferSize)
            checksum_hex = checksum.hexdigest()
            return checksum_hex, None

        def set_contents_from_file(self, fp, replace=False, **kwargs):
            max_read = kwargs.get('size')
            self.data = six.StringIO()
            checksum = hashlib.md5()
            while True:
                if max_read is None or max_read > self.BufferSize:
                    read_size = self.BufferSize
                elif max_read <= 0:
                    break
                else:
                    read_size = max_read
                chunk = fp.read(read_size)
                if not chunk:
                    break
                checksum.update(chunk)
                self.data.write(chunk)
                if max_read is not None:
                    max_read -= len(chunk)
            self.size = self.data.len
            # Reset the buffer to start
            self.data.seek(0)
            self.etag = checksum.hexdigest()
            self.read = self.data.read

        def get_file(self):
            return self.data

    class FakeMPU:
        """
        Acts like a ``boto.s3.multipart.MultiPartUpload``
        """
        def __init__(self, bucket, key_name):
            self.bucket = bucket
            self.id = str(uuid.uuid4())
            self.key_name = key_name
            self.parts = {}  # pnum -> FakeKey
            global mpu_parts_uploaded
            mpu_parts_uploaded = 0

        def upload_part_from_file(self, fp, part_num, **kwargs):
            size = kwargs.get('size')
            part = FakeKey(self.bucket, self.key_name)
            part.set_contents_from_file(fp, size=size)
            self.parts[part_num] = part
            global mpu_parts_uploaded
            mpu_parts_uploaded += 1
            return part

        def verify_xml(self, xml_body):
            """
            Verify xml matches our part info.
            """
            xmlparts = {}
            cmuroot = xml.etree.ElementTree.fromstring(xml_body)
            for cmupart in cmuroot:
                pnum = int(cmupart.findtext('PartNumber'))
                etag = cmupart.findtext('ETag')
                xmlparts[pnum] = etag
            if len(xmlparts) != len(self.parts):
                return False
            for pnum in xmlparts.keys():
                if self.parts[pnum] is None:
                    return False
                if xmlparts[pnum] != self.parts[pnum].etag:
                    return False
            return True

        def complete_key(self):
            """
            Complete the parts into one big FakeKey
            """
            key = FakeKey(self.bucket, self.key_name)
            key.data = six.StringIO()
            checksum = hashlib.md5()
            cnt = 0
            for pnum in sorted(self.parts.keys()):
                cnt += 1
                part = self.parts[pnum]
                chunk = part.data.read(key.BufferSize)
                while chunk:
                    checksum.update(chunk)
                    key.data.write(chunk)
                    chunk = part.data.read(key.BufferSize)
            key.size = key.data.len
            key.data.seek(0)
            key.etag = checksum.hexdigest() + '-%d' % cnt
            key.read = key.data.read
            return key

    class FakeBucket:
        """
        Acts like a ``boto.s3.bucket.Bucket``
        """
        def __init__(self, name, keys=None):
            self.name = name
            self.keys = keys or {}
            self.mpus = {}  # {key_name -> {id -> FakeMPU}}

        def __str__(self):
            return self.name

        def exists(self, key):
            return key in self.keys

        def delete(self, key):
            del self.keys[key]

        def get_key(self, key_name, **kwargs):
            return self.keys.get(key_name)

        def new_key(self, key_name):
            new_key = FakeKey(self, key_name)
            self.keys[key_name] = new_key
            return new_key

        def initiate_multipart_upload(self, key_name, **kwargs):
            mpu = FakeMPU(self, key_name)
            if key_name not in self.mpus:
                self.mpus[key_name] = {}
            self.mpus[key_name][mpu.id] = mpu
            return mpu

        def cancel_multipart_upload(self, key_name, upload_id, **kwargs):
            if key_name in self.mpus:
                if upload_id in self.mpus[key_name]:
                    del self.mpus[key_name][upload_id]
                    if not self.mpus[key_name]:
                        del self.mpus[key_name]

        def complete_multipart_upload(self, key_name, upload_id,
                                      xml_body, **kwargs):
            if key_name in self.mpus:
                if upload_id in self.mpus[key_name]:
                    mpu = self.mpus[key_name][upload_id]
                    if mpu.verify_xml(xml_body):
                        key = mpu.complete_key()
                        self.cancel_multipart_upload(key_name, upload_id)
                        self.keys[key_name] = key
                        cmpu = mock.Mock()
                        cmpu.bucket = self
                        cmpu.bucket_name = self.name
                        cmpu.key_name = key_name
                        cmpu.etag = key.etag
                        return cmpu
            return None  # tho raising an exception might be better

    fixture_buckets = {'glance': FakeBucket('glance')}
    b = fixture_buckets['glance']
    k = b.new_key(FAKE_UUID)
    k.set_contents_from_file(six.StringIO("*" * FIVE_KB))

    def fake_connection_constructor(self, *args, **kwargs):
        host = kwargs.get('host')
        if host.startswith('http://') or host.startswith('https://'):
            raise UnsupportedBackend(host)

    def fake_get_bucket(conn, bucket_id):
        bucket = fixture_buckets.get(bucket_id)
        if not bucket:
            bucket = FakeBucket(bucket_id)
        return bucket

    stubs.Set(boto.s3.connection.S3Connection,
              '__init__', fake_connection_constructor)
    stubs.Set(boto.s3.connection.S3Connection,
              'get_bucket', fake_get_bucket)


def format_s3_location(user, key, authurl, bucket, obj):
    """
    Helper method that returns a S3 store URI given
    the component pieces.
    """
    scheme = 's3'
    if authurl.startswith('https://'):
        scheme = 's3+https'
        authurl = authurl[8:]
    elif authurl.startswith('http://'):
        authurl = authurl[7:]
    authurl = authurl.strip('/')
    return "%s://%s:%s@%s/%s/%s" % (scheme, user, key, authurl,
                                    bucket, obj)


class TestStore(base.StoreClearingUnitTest):

    def setUp(self):
        """Establish a clean test environment"""
        self.config(**S3_CONF)
        super(TestStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        stub_out_s3(self.stubs)
        self.store = Store()
        self.addCleanup(self.stubs.UnsetAll)

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/%s" % FAKE_UUID)
        (image_s3, image_size) = self.store.get(loc)

        self.assertEqual(image_size, FIVE_KB)

        expected_data = "*" * FIVE_KB
        data = ""

        for chunk in image_s3:
            data += chunk
        self.assertEqual(expected_data, data)

    def test_get_calling_format_path(self):
        """Test a "normal" retrieval of an image in chunks"""
        self.config(s3_store_bucket_url_format='path')

        def fake_S3Connection_init(*args, **kwargs):
            expected_cls = boto.s3.connection.OrdinaryCallingFormat
            self.assertIsInstance(kwargs.get('calling_format'), expected_cls)

        self.stubs.Set(boto.s3.connection.S3Connection, '__init__',
                       fake_S3Connection_init)

        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/%s" % FAKE_UUID)
        (image_s3, image_size) = self.store.get(loc)

    def test_get_calling_format_default(self):
        """Test a "normal" retrieval of an image in chunks"""

        def fake_S3Connection_init(*args, **kwargs):
            expected_cls = boto.s3.connection.SubdomainCallingFormat
            self.assertIsInstance(kwargs.get('calling_format'), expected_cls)

        self.stubs.Set(boto.s3.connection.S3Connection, '__init__',
                       fake_S3Connection_init)

        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/%s" % FAKE_UUID)
        (image_s3, image_size) = self.store.get(loc)

    def test_get_non_existing(self):
        """
        Test that trying to retrieve a s3 that doesn't exist
        raises an error
        """
        uri = "s3://user:key@auth_address/badbucket/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.NotFound, self.store.get, loc)

        uri = "s3://user:key@auth_address/glance/noexist"
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_add(self):
        """Test that we can add an image via the s3 backend"""
        expected_image_id = str(uuid.uuid4())
        expected_s3_size = FIVE_KB
        expected_s3_contents = "*" * expected_s3_size
        expected_checksum = hashlib.md5(expected_s3_contents).hexdigest()
        expected_location = format_s3_location(
            S3_CONF['s3_store_access_key'],
            S3_CONF['s3_store_secret_key'],
            S3_CONF['s3_store_host'],
            S3_CONF['s3_store_bucket'],
            expected_image_id)
        image_s3 = six.StringIO(expected_s3_contents)

        location, size, checksum, _ = self.store.add(expected_image_id,
                                                     image_s3,
                                                     expected_s3_size)

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_s3_size, size)
        self.assertEqual(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        (new_image_s3, new_image_size) = self.store.get(loc)
        new_image_contents = six.StringIO()
        for chunk in new_image_s3:
            new_image_contents.write(chunk)
        new_image_s3_size = new_image_contents.len

        self.assertEqual(expected_s3_contents, new_image_contents.getvalue())
        self.assertEqual(expected_s3_size, new_image_s3_size)

    def test_add_size_variations(self):
        """
        Test that adding images of various sizes which exercise both S3
        single uploads and the multipart upload apis. We've configured
        the big upload threshold to 5MB and the part size to 6MB.
        """
        variations = [(FIVE_KB, 0),  # simple put   (5KB < 5MB)
                      (5242880, 1),  # 1 part       (5MB <= 5MB < 6MB)
                      (6291456, 1),  # 1 part exact (5MB <= 6MB <= 6MB)
                      (7340032, 2)]  # 2 parts      (6MB < 7MB <= 12MB)
        for (vsize, vcnt) in variations:
            expected_image_id = str(uuid.uuid4())
            expected_s3_size = vsize
            expected_s3_contents = "12345678" * (expected_s3_size / 8)
            expected_chksum = hashlib.md5(expected_s3_contents).hexdigest()
            expected_location = format_s3_location(
                S3_CONF['s3_store_access_key'],
                S3_CONF['s3_store_secret_key'],
                S3_CONF['s3_store_host'],
                S3_CONF['s3_store_bucket'],
                expected_image_id)
            image_s3 = six.StringIO(expected_s3_contents)

            # add image
            location, size, chksum, _ = self.store.add(expected_image_id,
                                                       image_s3,
                                                       expected_s3_size)
            self.assertEqual(expected_location, location)
            self.assertEqual(expected_s3_size, size)
            self.assertEqual(expected_chksum, chksum)
            self.assertEqual(vcnt, mpu_parts_uploaded)

            # get image
            loc = get_location_from_uri(expected_location)
            (new_image_s3, new_image_s3_size) = self.store.get(loc)
            new_image_contents = six.StringIO()
            for chunk in new_image_s3:
                new_image_contents.write(chunk)
            new_image_size = new_image_contents.len
            self.assertEqual(expected_s3_size, new_image_s3_size)
            self.assertEqual(expected_s3_size, new_image_size)
            self.assertEqual(expected_s3_contents,
                             new_image_contents.getvalue())

    def test_add_host_variations(self):
        """
        Test that having http(s):// in the s3serviceurl in config
        options works as expected.
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
        for variation in variations:
            expected_image_id = str(uuid.uuid4())
            expected_s3_size = FIVE_KB
            expected_s3_contents = "*" * expected_s3_size
            expected_checksum = hashlib.md5(expected_s3_contents).hexdigest()
            new_conf = S3_CONF.copy()
            new_conf['s3_store_host'] = variation
            expected_location = format_s3_location(
                new_conf['s3_store_access_key'],
                new_conf['s3_store_secret_key'],
                new_conf['s3_store_host'],
                new_conf['s3_store_bucket'],
                expected_image_id)
            image_s3 = six.StringIO(expected_s3_contents)

            self.config(**new_conf)
            self.store = Store()
            location, size, checksum, _ = self.store.add(expected_image_id,
                                                         image_s3,
                                                         expected_s3_size)

            self.assertEqual(expected_location, location)
            self.assertEqual(expected_s3_size, size)
            self.assertEqual(expected_checksum, checksum)

            loc = get_location_from_uri(expected_location)
            (new_image_s3, new_image_size) = self.store.get(loc)
            new_image_contents = new_image_s3.getvalue()
            new_image_s3_size = len(new_image_s3)

            self.assertEqual(expected_s3_contents, new_image_contents)
            self.assertEqual(expected_s3_size, new_image_s3_size)

    def test_add_already_existing(self):
        """
        Tests that adding an image with an existing identifier
        raises an appropriate exception
        """
        image_s3 = six.StringIO("nevergonnamakeit")
        self.assertRaises(exception.Duplicate,
                          self.store.add,
                          FAKE_UUID, image_s3, 0)

    def _option_required(self, key):
        conf = S3_CONF.copy()
        conf[key] = None

        try:
            self.config(**conf)
            self.store = Store()
            return self.store.add == self.store.add_disabled
        except Exception:
            return False
        return False

    def test_no_access_key(self):
        """
        Tests that options without access key disables the add method
        """
        self.assertTrue(self._option_required('s3_store_access_key'))

    def test_no_secret_key(self):
        """
        Tests that options without secret key disables the add method
        """
        self.assertTrue(self._option_required('s3_store_secret_key'))

    def test_no_host(self):
        """
        Tests that options without host disables the add method
        """
        self.assertTrue(self._option_required('s3_store_host'))

    def test_delete(self):
        """
        Test we can delete an existing image in the s3 store
        """
        uri = "s3://user:key@auth_address/glance/%s" % FAKE_UUID
        loc = get_location_from_uri(uri)
        self.store.delete(loc)

        self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a s3 that doesn't exist
        raises an error
        """
        uri = "s3://user:key@auth_address/glance/noexist"
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.NotFound, self.store.delete, loc)

    def _do_test_get_s3_location(self, host, loc):
        self.assertEqual(get_s3_location(host), loc)
        self.assertEqual(get_s3_location(host + ':80'), loc)
        self.assertEqual(get_s3_location('http://' + host), loc)
        self.assertEqual(get_s3_location('http://' + host + ':80'), loc)
        self.assertEqual(get_s3_location('https://' + host), loc)
        self.assertEqual(get_s3_location('https://' + host + ':80'), loc)

    def test_get_s3_good_location(self):
        """
        Test that the s3 location can be derived from the host
        """
        good_locations = [
            ('s3.amazonaws.com', ''),
            ('s3-eu-west-1.amazonaws.com', 'EU'),
            ('s3-us-west-1.amazonaws.com', 'us-west-1'),
            ('s3-ap-southeast-1.amazonaws.com', 'ap-southeast-1'),
            ('s3-ap-northeast-1.amazonaws.com', 'ap-northeast-1'),
        ]
        for (url, expected) in good_locations:
            self._do_test_get_s3_location(url, expected)

    def test_get_s3_bad_location(self):
        """
        Test that the s3 location cannot be derived from an unexpected host
        """
        bad_locations = [
            ('', ''),
            ('s3.amazon.co.uk', ''),
            ('s3-govcloud.amazonaws.com', ''),
            ('cloudfiles.rackspace.com', ''),
        ]
        for (url, expected) in bad_locations:
            self._do_test_get_s3_location(url, expected)

    def test_calling_format_path(self):
        self.config(s3_store_bucket_url_format='path')
        self.assertIsInstance(glance.store.s3.get_calling_format(),
                              boto.s3.connection.OrdinaryCallingFormat)

    def test_calling_format_subdomain(self):
        self.config(s3_store_bucket_url_format='subdomain')
        self.assertIsInstance(glance.store.s3.get_calling_format(),
                              boto.s3.connection.SubdomainCallingFormat)

    def test_calling_format_default(self):
        self.assertIsInstance(glance.store.s3.get_calling_format(),
                              boto.s3.connection.SubdomainCallingFormat)
