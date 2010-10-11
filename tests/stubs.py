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

"""Stubouts, mocks and fixtures for the test suite"""

import httplib
import StringIO

import stubout

import glance.teller.backends.swift

def stub_out_http_backend(stubs):
    """Stubs out the httplib.HTTPRequest.getresponse to return
    faked-out data instead of grabbing actual contents of a resource

    The stubbed getresponse() returns an iterator over 
    the data "I am a teapot, short and stout\n"

    :param stubs: Set of stubout stubs

    """

    class FakeHTTPConnection(object):

        DATA = 'I am a teapot, short and stout\n'

        def getresponse(self):
            return StringIO.StringIO(self.DATA)

        def request(self, *_args, **_kwargs):
            pass

    fake_http_conn = FakeHTTPConnection()
    stubs.Set(httplib.HTTPConnection, 'request',
              fake_http_conn.request)
    stubs.Set(httplib.HTTPSConnection, 'request',
              fake_http_conn.request)
    stubs.Set(httplib.HTTPConnection, 'getresponse',
              fake_http_conn.getresponse)
    stubs.Set(httplib.HTTPSConnection, 'getresponse',
              fake_http_conn.getresponse)


def stub_out_filesystem_backend(stubs):
    """Stubs out the Filesystem Teller service to return fake
    data from files.

    The stubbed service always yields the following fixture::

        //chunk0
        //chunk1

    :param stubs: Set of stubout stubs

    """
    class FakeFilesystemBackend(object):

        @classmethod
        def get(cls, parsed_uri, expected_size, conn_class=None):

            return StringIO.StringIO(parsed_uri.path)

    fake_filesystem_backend = FakeFilesystemBackend()
    stubs.Set(glance.teller.backends.FilesystemBackend, 'get',
              fake_filesystem_backend.get)


def stub_out_swift_backend(stubs):
    """Stubs out the Swift Teller backend with fake data
    and calls.

    The stubbed swift backend provides back an iterator over
    the data "I am a teapot, short and stout\n"

    :param stubs: Set of stubout stubs

    """
    class FakeSwiftAuth(object):
        pass
    class FakeSwiftConnection(object):
        pass

    class FakeSwiftBackend(object):

        CHUNK_SIZE = 2
        DATA = 'I am a teapot, short and stout\n'

        @classmethod
        def get(cls, parsed_uri, expected_size, conn_class=None):
            SwiftBackend = glance.teller.backends.swift.SwiftBackend

            # raise BackendException if URI is bad.
            (user, api_key, authurl, container, file) = \
                SwiftBackend.parse_swift_tokens(parsed_uri)

            def chunk_it():
                for i in xrange(0, len(cls.DATA), cls.CHUNK_SIZE):
                    yield cls.DATA[i:i+cls.CHUNK_SIZE]
            
            return chunk_it()

    fake_swift_backend = FakeSwiftBackend()
    stubs.Set(glance.teller.backends.swift.SwiftBackend, 'get',
              fake_swift_backend.get)


def stub_out_parallax(stubs):
    """Stubs out the Parallax registry with fake data returns.

    The stubbed Parallax always returns the following fixture::

        {'files': [
          {'location': 'file:///chunk0', 'size': 12345},
          {'location': 'file:///chunk1', 'size': 1235}
        ]}

    :param stubs: Set of stubout stubs

    """
    class FakeParallax(object):

        DATA = \
            {'files': [
              {'location': 'file:///chunk0', 'size': 12345},
              {'location': 'file:///chunk1', 'size': 1235}
            ]}

        @classmethod
        def lookup(cls, _parsed_uri):
            return cls.DATA

    fake_parallax_registry = FakeParallax()
    stubs.Set(glance.teller.registries.Parallax, 'lookup',
              fake_parallax_registry.lookup)
