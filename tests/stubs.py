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

"""Stubouts, mocks and fixtures for the test suite"""

import datetime
import httplib
import os
import shutil
import StringIO
import sys

import stubout
import webob

from glance.common import exception
from glance.registry import server as rserver
from glance.api import v1 as server
import glance.store
import glance.store.filesystem
import glance.store.http
import glance.registry.db.api


FAKE_FILESYSTEM_ROOTDIR = os.path.join('/tmp', 'glance-tests')
VERBOSE = False
DEBUG = False


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


def stub_out_filesystem_backend():
    """
    Stubs out the Filesystem Glance service to return fake
    pped image data from files.

    We establish a few fake images in a directory under //tmp/glance-tests
    and ensure that this directory contains the following files:

        //tmp/glance-tests/2 <-- file containing "chunk00000remainder"

    The stubbed service yields the data in the above files.

    """

    # Establish a clean faked filesystem with dummy images
    if os.path.exists(FAKE_FILESYSTEM_ROOTDIR):
        shutil.rmtree(FAKE_FILESYSTEM_ROOTDIR, ignore_errors=True)
    os.mkdir(FAKE_FILESYSTEM_ROOTDIR)

    f = open(os.path.join(FAKE_FILESYSTEM_ROOTDIR, '2'), "wb")
    f.write("chunk00000remainder")
    f.close()


def stub_out_s3_backend(stubs):
    """ Stubs out the S3 Backend with fake data and calls.

    The stubbed s3 backend provides back an iterator over
    the data ""

    :param stubs: Set of stubout stubs

    """

    class FakeSwiftAuth(object):
        pass

    class FakeS3Connection(object):
        pass

    class FakeS3Backend(object):
        CHUNK_SIZE = 2
        DATA = 'I am a teapot, short and stout\n'

        @classmethod
        def get(cls, parsed_uri, expected_size, conn_class=None):
            S3Backend = glance.store.s3.S3Backend

            # raise BackendException if URI is bad.
            (user, key, authurl, container, obj) = \
                S3Backend._parse_s3_tokens(parsed_uri)

            def chunk_it():
                for i in xrange(0, len(cls.DATA), cls.CHUNK_SIZE):
                    yield cls.DATA[i:i + cls.CHUNK_SIZE]
            return chunk_it()

    fake_s3_backend = FakeS3Backend()
    stubs.Set(glance.store.s3.S3Backend, 'get',
              fake_s3_backend.get)


def stub_out_registry_and_store_server(stubs):
    """
    Mocks calls to 127.0.0.1 on 9191 and 9292 for testing so
    that a real Glance server does not need to be up and
    running
    """

    class FakeRegistryConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            return True

        def close(self):
            return True

        def request(self, method, url, body=None, headers={}):
            self.req = webob.Request.blank("/" + url.lstrip("/"))
            self.req.method = method
            if headers:
                self.req.headers = headers
            if body:
                self.req.body = body

        def getresponse(self):
            sql_connection = os.environ.get('GLANCE_SQL_CONNECTION',
                                            "sqlite://")
            options = {'sql_connection': sql_connection, 'verbose': VERBOSE,
                       'debug': DEBUG}
            res = self.req.get_response(rserver.API(options))

            # httplib.Response has a read() method...fake it out
            def fake_reader():
                return res.body

            setattr(res, 'read', fake_reader)
            return res

    class FakeGlanceConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            return True

        def close(self):
            return True

        def putrequest(self, method, url):
            self.req = webob.Request.blank("/" + url.lstrip("/"))
            self.req.method = method

        def putheader(self, key, value):
            self.req.headers[key] = value

        def endheaders(self):
            pass

        def send(self, data):
            # send() is called during chunked-transfer encoding, and
            # data is of the form %x\r\n%s\r\n. Strip off the %x and
            # only write the actual data in tests.
            self.req.body += data.split("\r\n")[1]

        def request(self, method, url, body=None, headers={}):
            self.req = webob.Request.blank("/" + url.lstrip("/"))
            self.req.method = method
            if headers:
                self.req.headers = headers
            if body:
                self.req.body = body

        def getresponse(self):
            options = {'verbose': VERBOSE,
                       'debug': DEBUG,
                       'registry_host': '0.0.0.0',
                       'registry_port': '9191',
                       'default_store': 'file',
                       'filesystem_store_datadir': FAKE_FILESYSTEM_ROOTDIR}
            res = self.req.get_response(server.API(options))

            # httplib.Response has a read() method...fake it out
            def fake_reader():
                return res.body

            setattr(res, 'read', fake_reader)
            return res

    def fake_get_connection_type(client):
        """
        Returns the proper connection type
        """
        DEFAULT_REGISTRY_PORT = 9191
        DEFAULT_API_PORT = 9292

        if (client.port == DEFAULT_API_PORT and
            client.host == '0.0.0.0'):
            return FakeGlanceConnection
        elif (client.port == DEFAULT_REGISTRY_PORT and
              client.host == '0.0.0.0'):
            return FakeRegistryConnection

    def fake_image_iter(self):
        for i in self.response.app_iter:
            yield i

    stubs.Set(glance.client.BaseClient, 'get_connection_type',
              fake_get_connection_type)
    stubs.Set(glance.client.ImageBodyIterator, '__iter__',
              fake_image_iter)


def stub_out_registry_db_image_api(stubs):
    """Stubs out the database set/fetch API calls for Registry
    so the calls are routed to an in-memory dict. This helps us
    avoid having to manually clear or flush the SQLite database.

    The "datastore" always starts with this set of image fixtures.

    :param stubs: Set of stubout stubs
    :return: count of items in the "datastore"
    """
    class FakeDatastore(object):

        FIXTURES = [
            {'id': 1,
                'name': 'fake image #1',
                'status': 'active',
                'disk_format': 'ami',
                'container_format': 'ami',
                'is_public': False,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'checksum': None,
                'size': 13,
                'location': "swift://user:passwd@acct/container/obj.tar.0",
             'properties': [{'name': 'type',
                             'value': 'kernel',
                             'deleted': False}]},
            {'id': 2,
                'name': 'fake image #2',
                'status': 'active',
                'disk_format': 'vhd',
                'container_format': 'ovf',
                'is_public': True,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'checksum': None,
                'size': 19,
                'location': "file:///tmp/glance-tests/2",
                'properties': []},
            {'id': 3,
                'name': 'fake iso image',
                'status': 'active',
                'disk_format': 'iso',
                'container_format': 'bare',
                'is_public': False,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'checksum': None,
                'size': 19,
                'location': "file:///tmp/glance-tests/3",
                'properties': {}}]

        def __init__(self):
            self.images = FakeDatastore.FIXTURES
            self.next_id = 4

        def image_create(self, _context, values):

            values['id'] = values.get('id', self.next_id)

            if values['id'] in [image['id'] for image in self.images]:
                raise exception.Duplicate("Duplicate image id: %s" %
                                          values['id'])

            glance.registry.db.api.validate_image(values)

            values['size'] = values.get('size', 0)
            values['checksum'] = values.get('checksum')
            values['deleted'] = False
            values['properties'] = values.get('properties', {})
            values['location'] = values.get('location')
            values['created_at'] = datetime.datetime.utcnow()
            values['updated_at'] = datetime.datetime.utcnow()
            values['deleted_at'] = None

            props = []

            if 'properties' in values.keys():
                for k, v in values['properties'].items():
                    p = {}
                    p['name'] = k
                    p['value'] = v
                    p['deleted'] = False
                    p['created_at'] = datetime.datetime.utcnow()
                    p['updated_at'] = datetime.datetime.utcnow()
                    p['deleted_at'] = None
                    props.append(p)

            values['properties'] = props

            self.next_id += 1
            self.images.append(values)
            return values

        def image_update(self, _context, image_id, values, purge_props=False):

            image = self.image_get(_context, image_id)
            copy_image = image.copy()
            copy_image.update(values)
            glance.registry.db.api.validate_image(copy_image)
            props = []
            orig_properties = image['properties']

            if purge_props == False:
                if 'properties' in values.keys():
                    for k, v in values['properties'].items():
                        p = {}
                        p['name'] = k
                        p['value'] = v
                        p['deleted'] = False
                        p['created_at'] = datetime.datetime.utcnow()
                        p['updated_at'] = datetime.datetime.utcnow()
                        p['deleted_at'] = None
                        props.append(p)

            orig_properties = orig_properties + props
            values['properties'] = orig_properties

            image.update(values)
            return image

        def image_destroy(self, _context, image_id):
            image = self.image_get(_context, image_id)
            self.images.remove(image)

        def image_get(self, _context, image_id):

            images = [i for i in self.images if str(i['id']) == str(image_id)]

            if len(images) != 1 or images[0]['deleted']:
                raise exception.NotFound("No model for id %s %s" %
                                         (image_id, str(self.images)))
            else:
                return images[0]

        def image_get_all_public(self, _context, public=True):
            return [f for f in self.images
                    if f['is_public'] == public]

    fake_datastore = FakeDatastore()
    stubs.Set(glance.registry.db.api, 'image_create',
              fake_datastore.image_create)
    stubs.Set(glance.registry.db.api, 'image_update',
              fake_datastore.image_update)
    stubs.Set(glance.registry.db.api, 'image_destroy',
              fake_datastore.image_destroy)
    stubs.Set(glance.registry.db.api, 'image_get',
              fake_datastore.image_get)
    stubs.Set(glance.registry.db.api, 'image_get_all_public',
              fake_datastore.image_get_all_public)
    return fake_datastore.next_id
