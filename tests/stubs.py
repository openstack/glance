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
import StringIO
import sys

import stubout
import webob

from glance.common import exception
from glance.parallax import controllers as parallax_controllers
import glance.teller.backends.swift
import glance.parallax.db.sqlalchemy.api


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


def stub_out_parallax_server(stubs):
    """
    Mocks httplib calls to 127.0.0.1:9292 for testing so
    that a real Parallax server does not need to be up and
    running
    """

    def fake_http_connection_constructor(address, port):
        """
        Returns either a faked connection or a real
        one depending on if the connection is to a parallax
        server or not...
        """
        return FakeParallaxConnection()


    class FakeParallaxConnection(object):

        def __init__(self):
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

    stubs.Set(httplib, 'HTTPConnection',
              fake_http_connection_constructor)


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
                'files': [],
                'metadata': []},
            {'id': 2,
                'name': 'fake image #2',
                'status': 'available',
                'image_type': 'kernel',
                'is_public': True,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'files': [],
                'metadata': []}]

        VALID_STATUSES = ('available', 'disabled', 'pending')

        def __init__(self):
            self.images = FakeDatastore.FIXTURES
            self.next_id = 3

        def image_create(self, _context, values):
            values['id'] = self.next_id

            if 'status' not in values.keys():
                values['status'] = 'available'
            else:
                if not values['status'] in self.VALID_STATUSES:
                    raise exception.Invalid("Invalid status '%s' for image" %
                                            values['status'])

            values['deleted'] = False
            values['files'] = values.get('files', [])
            values['metadata'] = values.get('metadata', [])
            values['created_at'] = datetime.datetime.utcnow() 
            values['updated_at'] = datetime.datetime.utcnow()
            values['deleted_at'] = None
            
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
