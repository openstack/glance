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
import unittest

from cloudfiles import Connection
from cloudfiles.authentication import MockAuthentication as Auth

from swiftfakehttp import CustomHTTPConnection
from glance.teller.backends import Backend, BackendException, get_from_backend


class TestBackends(unittest.TestCase):
    def setUp(self):
        Backend.CHUNKSIZE = 2

    def test_filesystem_get_from_backend(self):
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

    def test_http_get_from_backend(self):
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

    def test_swift_get_from_backend(self):
        class FakeSwift(object):
            def __init__(self, *args, **kwargs): 
                pass
            @classmethod
            def get_connection(self, *args, **kwargs):
                auth = Auth("user", "password")
                conn = Connection(auth=auth)
                conn.connection = CustomHTTPConnection("localhost", 8000)
                return conn

        swift_uri="swift://user:password@localhost/container1/file.tar.gz"
        swift_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s', 
                         'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']

        fetcher = get_from_backend(swift_uri,
                                   expected_size=21,
                                   conn_class=FakeSwift)

        chunks = [c for c in fetcher]

        self.assertEqual(chunks, swift_returns)

    def test_swift_get_from_backend_with_bad_uri(self):
        class FakeSwift(object):
            def __init__(self, *args, **kwargs): 
                pass
            @classmethod
            def get_connection(self, *args, **kwargs):
                auth = Auth("user", "password")
                conn = Connection(auth=auth)
                conn.connection = CustomHTTPConnection("localhost", 8000)
                return conn

        swift_url="swift://localhost/container1/file.tar.gz"

        self.assertRaises(BackendException, get_from_backend, 
                          swift_url, expected_size=21)


if __name__ == "__main__":
    unittest.main()
