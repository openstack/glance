# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

from StringIO import StringIO

import stubout
import unittest
import urlparse

from glance.store.s3 import S3Backend
from glance.store import Backend, BackendException, get_from_backend
from tests import stubs

Backend.CHUNKSIZE = 2


class TestBackend(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()


class TestHTTPBackend(TestBackend):

    def setUp(self):
        super(TestHTTPBackend, self).setUp()
        stubs.stub_out_http_backend(self.stubs)

    def test_http_get(self):
        url = "http://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        fetcher = get_from_backend(url,
                                   expected_size=8)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, expected_returns)

    def test_https_get(self):
        url = "https://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        fetcher = get_from_backend(url,
                                   expected_size=8)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, expected_returns)


class TestS3Backend(TestBackend):
    def setUp(self):
        super(TestS3Backend, self).setUp()
        stubs.stub_out_s3_backend(self.stubs)

    def test_get(self):
        s3_uri = "s3://user:password@localhost/bucket1/file.tar.gz"

        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        fetcher = get_from_backend(s3_uri,
                                   expected_size=8,
                                   conn_class=S3Backend)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, expected_returns)
