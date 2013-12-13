# Copyright 2010-2011 OpenStack Foundation
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

from six.moves import xrange
import stubout

from glance.common import exception
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance.registry.client.v1.api import configure_registry_client
from glance.store import delete_from_backend
from glance.store.http import MAX_REDIRECTS
from glance.store.http import Store
from glance.store.location import get_location_from_uri
from glance.store import safe_delete_from_backend
from glance.tests import stubs as test_stubs
from glance.tests.unit import base
from glance.tests import utils


# The response stack is used to return designated responses in order;
# however when it's empty a default 200 OK response is returned from
# FakeHTTPConnection below.
FAKE_RESPONSE_STACK = []


def stub_out_http_backend(stubs):
    """
    Stubs out the httplib.HTTPRequest.getresponse to return
    faked-out data instead of grabbing actual contents of a resource

    The stubbed getresponse() returns an iterator over
    the data "I am a teapot, short and stout\n"

    :param stubs: Set of stubout stubs
    """

    class FakeHTTPConnection(object):

        def __init__(self, *args, **kwargs):
            pass

        def getresponse(self):
            if len(FAKE_RESPONSE_STACK):
                return FAKE_RESPONSE_STACK.pop()
            return utils.FakeHTTPResponse()

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


class TestHttpStore(base.StoreClearingUnitTest):

    def setUp(self):
        global FAKE_RESPONSE_STACK
        FAKE_RESPONSE_STACK = []
        self.config(default_store='http',
                    known_stores=['glance.store.http.Store'])
        super(TestHttpStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        stub_out_http_backend(self.stubs)
        Store.CHUNKSIZE = 2
        self.store = Store()
        configure_registry_client()

    def test_http_get(self):
        uri = "http://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        loc = get_location_from_uri(uri)
        (image_file, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 31)
        chunks = [c for c in image_file]
        self.assertEqual(chunks, expected_returns)

    def test_http_get_redirect(self):
        # Add two layers of redirects to the response stack, which will
        # return the default 200 OK with the expected data after resolving
        # both redirects.
        redirect_headers_1 = {"location": "http://example.com/teapot.img"}
        redirect_resp_1 = utils.FakeHTTPResponse(status=302,
                                                 headers=redirect_headers_1)
        redirect_headers_2 = {"location": "http://example.com/teapot_real.img"}
        redirect_resp_2 = utils.FakeHTTPResponse(status=301,
                                                 headers=redirect_headers_2)
        FAKE_RESPONSE_STACK.append(redirect_resp_1)
        FAKE_RESPONSE_STACK.append(redirect_resp_2)

        uri = "http://netloc/path/to/file.tar.gz"
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        loc = get_location_from_uri(uri)
        (image_file, image_size) = self.store.get(loc)
        self.assertEqual(image_size, 31)

        chunks = [c for c in image_file]
        self.assertEqual(chunks, expected_returns)

    def test_http_get_max_redirects(self):
        # Add more than MAX_REDIRECTS redirects to the response stack
        redirect_headers = {"location": "http://example.com/teapot.img"}
        redirect_resp = utils.FakeHTTPResponse(status=302,
                                               headers=redirect_headers)
        for i in xrange(MAX_REDIRECTS + 2):
            FAKE_RESPONSE_STACK.append(redirect_resp)

        uri = "http://netloc/path/to/file.tar.gz"
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.MaxRedirectsExceeded, self.store.get, loc)

    def test_http_get_redirect_invalid(self):
        redirect_headers = {"location": "http://example.com/teapot.img"}
        redirect_resp = utils.FakeHTTPResponse(status=307,
                                               headers=redirect_headers)
        FAKE_RESPONSE_STACK.append(redirect_resp)

        uri = "http://netloc/path/to/file.tar.gz"
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.BadStoreUri, self.store.get, loc)

    def test_http_get_not_found(self):
        not_found_resp = utils.FakeHTTPResponse(status=404,
                                                data="404 Not Found")
        FAKE_RESPONSE_STACK.append(not_found_resp)

        uri = "http://netloc/path/to/file.tar.gz"
        loc = get_location_from_uri(uri)
        self.assertRaises(exception.NotFound, self.store.get, loc)

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
        ctx = context.RequestContext()
        self.assertRaises(NotImplementedError, self.store.delete, loc)
        self.assertRaises(exception.StoreDeleteNotSupported,
                          delete_from_backend, ctx, uri)

    def test_http_schedule_delete_swallows_error(self):
        uri = "https://netloc/path/to/file.tar.gz"
        ctx = context.RequestContext()
        stub_out_registry_image_update(self.stubs)
        try:
            safe_delete_from_backend(ctx, uri, 'image_id')
        except exception.StoreDeleteNotSupported:
            self.fail('StoreDeleteNotSupported should be swallowed')
