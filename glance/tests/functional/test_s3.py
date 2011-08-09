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
Tests a Glance API server which uses an S3 backend by default

This test requires that a real S3 account is available. It looks
in a file specified in the GLANCE_TEST_S3_CONF environ variable
for the credentials to use.

Note that this test clears the entire bucket from the S3 account
for use by the test case, so make sure you supply credentials for
test accounts only.

If a connection cannot be established, all the test cases are
skipped.
"""

import ConfigParser
import json
import os
import tempfile
import unittest

from glance.tests.functional import test_api
from glance.tests.utils import execute, skip_if_disabled


class TestS3(test_api.TestApi):

    """Functional tests for the S3 backend"""

    # Test machines can set the GLANCE_TEST_S3_CONF variable
    # to override the location of the config file for S3 testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_S3_CONF')

    def setUp(self):
        """
        Test a connection to an S3 store using the credentials
        found in the environs or /tests/functional/test_s3.conf, if found.
        If the connection fails, mark all tests to skip.
        """
        self.inited = False
        self.disabled = True

        if self.inited:
            return

        if not self.CONFIG_FILE_PATH:
            self.disabled_message = "GLANCE_TEST_S3_CONF environ not set."
            self.inited = True
            return

        if os.path.exists(TestS3.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestS3.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.__dict__[key] = value
            except ConfigParser.ParsingError, e:
                self.disabled_message = ("Failed to read test_s3.conf config "
                                         "file. Got error: %s" % e)
                self.inited = True
                return

        from boto.s3.connection import S3Connection
        from boto.exception import S3ResponseError

        try:
            s3_host = self.s3_store_host
            access_key = self.s3_store_access_key
            secret_key = self.s3_store_secret_key
            bucket_name = self.s3_store_bucket
        except AttributeError, e:
            self.disabled_message = ("Failed to find required configuration "
                                     "options for S3 store. Got error: %s" % e)
            self.inited = True
            return

        s3_conn = S3Connection(access_key, secret_key, host=s3_host)

        self.bucket = None
        try:
            buckets = s3_conn.get_all_buckets()
            for bucket in buckets:
                if bucket.name == bucket_name:
                    self.bucket = bucket
        except S3ResponseError, e:
            self.disabled_message = ("Failed to connect to S3 with "
                                     "credentials, to find bucket. "
                                     "Got error: %s" % e)
            self.inited = True
            return
        except TypeError, e:
            # This hack is necessary because of a bug in boto 1.9b:
            # http://code.google.com/p/boto/issues/detail?id=540
            self.disabled_message = ("Failed to connect to S3 with "
                                     "credentials. Got error: %s" % e)
            self.inited = True
            return

        self.s3_conn = s3_conn

        if not self.bucket:
            try:
                self.bucket = s3_conn.create_bucket(bucket_name)
            except boto.exception.S3ResponseError, e:
                self.disabled_message = ("Failed to create bucket. "
                                         "Got error: %s" % e)
                self.inited = True
                return
        else:
            self.clear_bucket()

        self.disabled = False
        self.inited = True
        self.default_store = 's3'

        super(TestS3, self).setUp()

    def tearDown(self):
        if not self.disabled:
            self.clear_bucket()
        super(TestS3, self).tearDown()

    def clear_bucket(self):
        # It's not possible to simply clear a bucket. You
        # need to loop over all the keys and delete them
        # all first...
        keys = self.bucket.list()
        for key in keys:
            key.delete()
