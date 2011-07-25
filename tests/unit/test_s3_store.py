# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this s3 except in compliance with the License. You may obtain
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

import StringIO
import hashlib
import httplib
import sys
import unittest
import urlparse

import stubout
import boto.s3.connection

from glance.common import exception
from glance.store import BackendException, UnsupportedBackend
from glance.store.location import get_location_from_uri
from glance.store.s3 import S3Backend

FIVE_KB = (5 * 1024)
S3_OPTIONS = {'verbose': True,
              'debug': True,
              's3_store_access_key': 'user',
              's3_store_secret_key': 'key',
              's3_store_host': 'localhost:8080',
              's3_store_bucket': 'glance'}


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
            return checksum.hexdigest(), None

        def set_contents_from_file(self, fp, replace=False, **kwargs):
            self.data = StringIO.StringIO()
            self.data.write(fp.getvalue())
            self.size = self.data.len
            # Reset the buffer to start
            self.data.seek(0)
            self.read = self.data.read

        def get_file(self):
            return self.data

    class FakeBucket:
        """
        Acts like a ``boto.s3.bucket.Bucket``
        """
        def __init__(self, name, keys=None):
            self.name = name
            self.keys = keys or {}

        def __str__(self):
            return self.name

        def exists(self, key):
            return key in self.keys

        def delete(self, key):
            del self.keys[key]

        def get_key(self, key_name, **kwargs):
            key = self.keys.get(key_name)
            if not key:
                return FakeKey(self, key_name)
            return key

        def new_key(self, key_name):
            new_key = FakeKey(self, key_name)
            self.keys[key_name] = new_key
            return new_key

    fixture_buckets = {'glance': FakeBucket('glance')}
    b = fixture_buckets['glance']
    k = b.new_key('2')
    k.set_contents_from_file(StringIO.StringIO("*" * FIVE_KB))

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
    return "%s://%s:%s@%s/%s/%s" % (scheme, user, key, authurl,
                                    bucket, obj)


class TestS3Backend(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stub_out_s3(self.stubs)

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/2")
        image_s3 = S3Backend.get(loc)

        expected_data = "*" * FIVE_KB
        data = ""

        for chunk in image_s3:
            data += chunk
        self.assertEqual(expected_data, data)

    def test_get_mismatched_expected_size(self):
        """
        Test retrieval of an image with wrong expected_size param
        raises an exception
        """
        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/2")
        self.assertRaises(BackendException,
                          S3Backend.get,
                          loc,
                          {'expected_size': 42})

    def test_get_non_existing(self):
        """
        Test that trying to retrieve a s3 that doesn't exist
        raises an error
        """
        loc = get_location_from_uri(
            "s3://user:key@auth_address/badbucket/2")
        self.assertRaises(exception.NotFound,
                          S3Backend.get,
                          loc)

        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/noexist")
        self.assertRaises(exception.NotFound,
                          S3Backend.get,
                          loc)

    def test_add(self):
        """Test that we can add an image via the s3 backend"""
        expected_image_id = 42
        expected_s3_size = FIVE_KB
        expected_s3_contents = "*" * expected_s3_size
        expected_checksum = hashlib.md5(expected_s3_contents).hexdigest()
        expected_location = format_s3_location(
            S3_OPTIONS['s3_store_access_key'],
            S3_OPTIONS['s3_store_secret_key'],
            S3_OPTIONS['s3_store_host'],
            S3_OPTIONS['s3_store_bucket'],
            expected_image_id)
        image_s3 = StringIO.StringIO(expected_s3_contents)

        location, size, checksum = S3Backend.add(42, image_s3, S3_OPTIONS)

        self.assertEquals(expected_location, location)
        self.assertEquals(expected_s3_size, size)
        self.assertEquals(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        new_image_s3 = S3Backend.get(loc)
        new_image_contents = StringIO.StringIO()
        for chunk in new_image_s3:
            new_image_contents.write(chunk)
        new_image_s3_size = new_image_contents.len

        self.assertEquals(expected_s3_contents, new_image_contents.getvalue())
        self.assertEquals(expected_s3_size, new_image_s3_size)

    def test_add_already_existing(self):
        """
        Tests that adding an image with an existing identifier
        raises an appropriate exception
        """
        image_s3 = StringIO.StringIO("nevergonnamakeit")
        self.assertRaises(exception.Duplicate,
                          S3Backend.add,
                          2, image_s3, S3_OPTIONS)

    def _assertOptionRequiredForS3(self, key):
        image_s3 = StringIO.StringIO("nevergonnamakeit")
        options = S3_OPTIONS.copy()
        del options[key]
        self.assertRaises(BackendException, S3Backend.add,
                          2, image_s3, options)

    def test_add_no_user(self):
        """
        Tests that adding options without user raises
        an appropriate exception
        """
        self._assertOptionRequiredForS3('s3_store_access_key')

    def test_no_key(self):
        """
        Tests that adding options without key raises
        an appropriate exception
        """
        self._assertOptionRequiredForS3('s3_store_secret_key')

    def test_add_no_host(self):
        """
        Tests that adding options without host raises
        an appropriate exception
        """
        self._assertOptionRequiredForS3('s3_store_host')

    def test_delete(self):
        """
        Test we can delete an existing image in the s3 store
        """
        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/2")

        S3Backend.delete(loc)

        self.assertRaises(exception.NotFound,
                          S3Backend.get,
                          loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a s3 that doesn't exist
        raises an error
        """
        loc = get_location_from_uri(
            "s3://user:key@auth_address/glance/noexist")
        self.assertRaises(exception.NotFound,
                          S3Backend.delete,
                          loc)
