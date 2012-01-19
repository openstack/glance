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

import StringIO
import unittest

import stubout

from glance.common import exception, context
from glance.registry.db import api as db_api
from glance.store import (create_stores,
                          delete_from_backend,
                          schedule_delete_from_backend)
from glance.store.http import Store
from glance.store.location import get_location_from_uri
from glance.tests import utils, stubs as test_stubs


def stub_out_http_backend(stubs):
    """
    Stubs out the httplib.HTTPRequest.getresponse to return
    faked-out data instead of grabbing actual contents of a resource

    The stubbed getresponse() returns an iterator over
    the data "I am a teapot, short and stout\n"

    :param stubs: Set of stubout stubs
    """

    class FakeHTTPResponse(object):

        DATA = 'I am a teapot, short and stout\n'
        HEADERS = {'content-length': 31}

        def __init__(self, *args, **kwargs):
            self.data = StringIO.StringIO(self.DATA)
            self.read = self.data.read

        def getheader(self, name, default=None):
            return self.HEADERS.get(name.lower(), default)

    class FakeHTTPConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def getresponse(self):
            return FakeHTTPResponse()

        def request(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

    def fake_get_conn_class(self, *args, **kwargs):
        return FakeHTTPConnection

    stubs.Set(Store, '_get_conn_class', fake_get_conn_class)


def stub_out_registry_image_update(stubs):
    """
    Stubs an image update on the registry.

    :param stubs: Set of stubout stubs
    """
    test_stubs.stub_out_registry_server(stubs)

    def fake_image_update(ctx, image_id, values, purge_props=False):
        return {'properties': {}}

    stubs.Set(db_api, 'image_update', fake_image_update)


class TestHttpStore(unittest.TestCase):

    def setUp(self):
        self.stubs = stubout.StubOutForTesting()
        stub_out_http_backend(self.stubs)
        Store.CHUNKSIZE = 2
        self.store = Store({})

    def test_http_get(self):
        uri = "http://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        loc = get_location_from_uri(uri)
        (image_file, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 31)

        chunks = [c for c in image_file]
        self.assertEqual(chunks, expected_returns)

    def test_https_get(self):
        uri = "https://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        loc = get_location_from_uri(uri)
        (image_file, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 31)

        chunks = [c for c in image_file]
        self.assertEqual(chunks, expected_returns)

    def test_http_delete_raise_error(self):
        uri = "https://netloc/path/to/file.tar.gz"
        loc = get_location_from_uri(uri)
        self.assertRaises(NotImplementedError, self.store.delete, loc)

        create_stores(utils.TestConfigOpts({}))
        self.assertRaises(exception.StoreDeleteNotSupported,
                          delete_from_backend, uri)

    def test_http_schedule_delete_swallows_error(self):
        stub_out_registry_image_update(self.stubs)
        uri = "https://netloc/path/to/file.tar.gz"
        ctx = context.RequestContext()
        conf = utils.TestConfigOpts({})
        create_stores(conf)

        try:
            schedule_delete_from_backend(uri, conf, ctx, 'image_id')
        except exception.StoreDeleteNotSupported:
            self.fail('StoreDeleteNotSupported should be swallowed')
