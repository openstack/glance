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
import operator
import os
import shutil
import StringIO
import sys

import stubout
import webob

import glance.common.client
from glance.common import context
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
            context_class = 'glance.registry.context.RequestContext'
            options = {'sql_connection': sql_connection, 'verbose': VERBOSE,
                       'debug': DEBUG, 'context_class': context_class}
            api = context.ContextMiddleware(rserver.API(options), options)
            res = self.req.get_response(api)

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
            api = context.ContextMiddleware(server.API(options), options)
            res = self.req.get_response(api)

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

    stubs.Set(glance.common.client.BaseClient, 'get_connection_type',
              fake_get_connection_type)
    stubs.Set(glance.common.client.ImageBodyIterator, '__iter__',
              fake_image_iter)
