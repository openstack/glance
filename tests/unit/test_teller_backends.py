# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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
import unittest2 as unittest

from tests import stubs
from glance.teller.backends.swift import SwiftBackend
from glance.teller.backends import Backend, BackendException, get_from_backend

Backend.CHUNKSIZE = 2

class TestBackend(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()


class TestFilesystemBackend(TestBackend):

    def test_get(self):
        class FakeFile(object):
            def __enter__(self, *args, **kwargs):
                return StringIO('fakedata')
            def __exit__(self, *args, **kwargs):
                pass

        fetcher = get_from_backend("file:///path/to/file.tar.gz",
                                   expected_size=8,
                                   opener=lambda _: FakeFile())

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, ["fa", "ke", "da", "ta"])


class TestHTTPBackend(TestBackend):

    def setUp(self):
        super(TestHTTPBackend, self).setUp()
        #stubs.stub_out_http_connection()

    def test_get(self):
        class FakeHTTPConnection(object):
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return StringIO('fakedata')
            def close(self):
                pass

        fetcher = get_from_backend("http://netloc/path/to/file.tar.gz",
                                   expected_size=8,
                                   conn_class=FakeHTTPConnection)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, ["fa", "ke", "da", "ta"])


class TestSwiftBackend(TestBackend):

    def setUp(self):
        super(TestSwiftBackend, self).setUp()
        stubs.stub_out_swift(self.stubs)

    def test_get(self):

        swift_uri = "swift://user:password@localhost/container1/file.tar.gz"
        swift_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s', 
                         'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']

        fetcher = get_from_backend(swift_uri,
                                   expected_size=21,
                                   conn_class=SwiftBackend)

        chunks = [c for c in fetcher]

        self.assertEqual(chunks, swift_returns)

    def test_get_bad_uri(self):

        swift_url = "swift://localhost/container1/file.tar.gz"

        self.assertRaises(BackendException, get_from_backend, 
                          swift_url, expected_size=21)
