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

import datetime
import httplib
import os
import shutil
import StringIO
import sys
import gzip

import stubout
import webob

from glance.common import exception
from glance.parallax import controllers as parallax_controllers
from glance.teller import controllers as teller_controllers
import glance.teller.backends
import glance.teller.backends.swift
import glance.parallax.db.sqlalchemy.api


FAKE_FILESYSTEM_ROOTDIR = os.path.join('/tmp', 'glance-tests')


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


def clean_out_fake_filesystem_backend():
    """
    Removes any leftover directories used in fake filesystem
    backend
    """
    if os.path.exists(FAKE_FILESYSTEM_ROOTDIR):
        shutil.rmtree(FAKE_FILESYSTEM_ROOTDIR, ignore_errors=True)


def stub_out_filesystem_backend(stubs):
    """
    Stubs out the Filesystem Teller service to return fake
    data from files.

    We establish a few fake images in a directory under /tmp/glance-tests
    and ensure that this directory contains the following files:

        /acct/2.gz.0 <-- zipped tarfile containing "chunk0"
        /acct/2.gz.1 <-- zipped tarfile containing "chunk42"

    The stubbed service yields the data in the above files.

    :param stubs: Set of stubout stubs

    """

    class FakeFilesystemBackend(object):

        CHUNKSIZE = 100

        @classmethod
        def get(cls, parsed_uri, expected_size, opener=None):
            filepath = os.path.join('/',
                                    parsed_uri.netloc,
                                    parsed_uri.path.strip(os.path.sep))
            f = gzip.open(filepath, 'rb')
            data = f.read()
            f.close()
            return data

    # Establish a clean faked filesystem with dummy images
    if os.path.exists(FAKE_FILESYSTEM_ROOTDIR):
        shutil.rmtree(FAKE_FILESYSTEM_ROOTDIR, ignore_errors=True)
    os.mkdir(FAKE_FILESYSTEM_ROOTDIR)
    os.mkdir(os.path.join(FAKE_FILESYSTEM_ROOTDIR, 'acct'))

    f = gzip.open(os.path.join(FAKE_FILESYSTEM_ROOTDIR, 'acct', '2.gz.0'),
                  "wb")
    f.write("chunk0")
    f.close()

    f = gzip.open(os.path.join(FAKE_FILESYSTEM_ROOTDIR, 'acct', '2.gz.1'),
                  "wb")
    f.write("chunk42")
    f.close()

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
            (user, key, authurl, container, obj) = \
                SwiftBackend._parse_swift_tokens(parsed_uri)

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


def stub_out_parallax_and_teller_server(stubs):
    """
    Mocks calls to 127.0.0.1 on 9191 and 9292 for testing so
    that a real Teller server does not need to be up and
    running
    """

    class FakeParallaxConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            return True

        def close(self):
            return True

        def request(self, method, url, body=None):
            self.req = webob.Request.blank("/" + url.lstrip("/"))
            self.req.method = method
            if body:
                self.req.body = body

        def getresponse(self):
            res = self.req.get_response(parallax_controllers.API())

            # httplib.Response has a read() method...fake it out
            def fake_reader():
                return res.body

            setattr(res, 'read', fake_reader)
            return res

    class FakeTellerConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            return True

        def close(self):
            return True

        def request(self, method, url, body=None):
            self.req = webob.Request.blank("/" + url.lstrip("/"))
            self.req.method = method
            if body:
                self.req.body = body

        def getresponse(self):
            res = self.req.get_response(teller_controllers.API())

            # httplib.Response has a read() method...fake it out
            def fake_reader():
                return res.body

            setattr(res, 'read', fake_reader)
            return res

    def fake_get_connection_type(client):
        """
        Returns the proper connection type
        """
        DEFAULT_PARALLAX_PORT = 9191
        DEFAULT_TELLER_PORT = 9292

        if (client.port == DEFAULT_TELLER_PORT and
            client.netloc == '127.0.0.1'):
            return FakeTellerConnection
        elif (client.port == DEFAULT_PARALLAX_PORT and
              client.netloc == '127.0.0.1'):
            return FakeParallaxConnection
        else:
            try:
                connection_type = {'http': httplib.HTTPConnection,
                                   'https': httplib.HTTPSConnection}\
                                   [client.protocol]
                return connection_type
            except KeyError:
                raise UnsupportedProtocolError("Unsupported protocol %s. Unable "
                                               " to connect to server."
                                               % self.protocol)

    stubs.Set(glance.client.BaseClient, 'get_connection_type',
              fake_get_connection_type)


def stub_out_parallax_db_image_api(stubs):
    """Stubs out the database set/fetch API calls for Parallax
    so the calls are routed to an in-memory dict. This helps us
    avoid having to manually clear or flush the SQLite database.

    The "datastore" always starts with this set of image fixtures.

    :param stubs: Set of stubout stubs

    """
    class FakeDatastore(object):

        FIXTURES = [
            {'id': 1,
                'name': 'fake image #1',
                'status': 'available',
                'image_type': 'kernel',
                'is_public': False,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'files': [
                    {"location": "swift://user:passwd@acct/container/obj.tar.gz.0",
                     "size": 6},
                    {"location": "swift://user:passwd@acct/container/obj.tar.gz.1",
                     "size": 7}],
                'properties': []},
            {'id': 2,
                'name': 'fake image #2',
                'status': 'available',
                'image_type': 'kernel',
                'is_public': True,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'files': [
                    {"location": "file://tmp/glance-tests/acct/2.gz.0",
                     "size": 6},
                    {"location": "file://tmp/glance-tests/acct/2.gz.1",
                     "size": 7}],
                'properties': []}]

        VALID_STATUSES = ('available', 'disabled', 'pending')

        def __init__(self):
            self.images = FakeDatastore.FIXTURES
            self.next_id = 3

        def image_create(self, _context, values):

            values['id'] = values.get('id', self.next_id)

            if values['id'] in [image['id'] for image in self.images]:
                raise exception.Duplicate("Duplicate image id: %s" %
                                          values['id'])

            if 'status' not in values.keys():
                values['status'] = 'available'
            else:
                if not values['status'] in self.VALID_STATUSES:
                    raise exception.Invalid("Invalid status '%s' for image" %
                                            values['status'])

            values['deleted'] = False
            values['files'] = values.get('files', [])
            values['properties'] = values.get('properties', [])
            values['created_at'] = datetime.datetime.utcnow() 
            values['updated_at'] = datetime.datetime.utcnow()
            values['deleted_at'] = None

            for p in values['properties']:
                p['deleted'] = False
                p['created_at'] = datetime.datetime.utcnow() 
                p['updated_at'] = datetime.datetime.utcnow()
                p['deleted_at'] = None
            
            self.next_id += 1
            self.images.append(values)
            return values

        def image_update(self, _context, image_id, values):
            image = self.image_get(_context, image_id)
            image.update(values)
            return image

        def image_destroy(self, _context, image_id):
            image = self.image_get(_context, image_id)
            self.images.remove(image)

        def image_get(self, _context, image_id):

            images = [i for i in self.images if str(i['id']) == str(image_id)]

            if len(images) != 1 or images[0]['deleted']:
                new_exc = exception.NotFound("No model for id %s %s" %
                                             (image_id, str(self.images)))
                raise new_exc.__class__, new_exc, sys.exc_info()[2]
            else:
                return images[0]

        def image_get_all_public(self, _context, public):
            return [f for f in self.images
                    if f['is_public'] == public]

    fake_datastore = FakeDatastore()
    stubs.Set(glance.parallax.db.sqlalchemy.api, 'image_create',
              fake_datastore.image_create)
    stubs.Set(glance.parallax.db.sqlalchemy.api, 'image_update',
              fake_datastore.image_update)
    stubs.Set(glance.parallax.db.sqlalchemy.api, 'image_destroy',
              fake_datastore.image_destroy)
    stubs.Set(glance.parallax.db.sqlalchemy.api, 'image_get',
              fake_datastore.image_get)
    stubs.Set(glance.parallax.db.sqlalchemy.api, 'image_get_all_public',
              fake_datastore.image_get_all_public)
