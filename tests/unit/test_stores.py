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

from glance.store import BackendException, get_from_backend
from glance.store import http
from tests import stubs


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
        http.Store.CHUNKSIZE = 2

    def test_http_get(self):
        url = "http://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        fetcher = get_from_backend(url)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, expected_returns)

    def test_https_get(self):
        url = "https://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        fetcher = get_from_backend(url)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, expected_returns)
