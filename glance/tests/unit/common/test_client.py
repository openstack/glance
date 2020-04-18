# Copyright 2013 Red Hat, Inc.
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

from unittest import mock

from six.moves import http_client
import testtools

from glance.common import auth
from glance.common import client
from glance.tests import utils


class TestClient(testtools.TestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.endpoint = 'example.com'
        self.client = client.BaseClient(self.endpoint, port=9191,
                                        auth_token=u'abc123')

    def tearDown(self):
        super(TestClient, self).tearDown()

    def test_make_auth_plugin(self):
        creds = {'strategy': 'keystone'}
        insecure = False

        with mock.patch.object(auth, 'get_plugin_from_strategy'):
            self.client.make_auth_plugin(creds, insecure)

    @mock.patch.object(http_client.HTTPConnection, "getresponse")
    @mock.patch.object(http_client.HTTPConnection, "request")
    def test_http_encoding_headers(self, _mock_req, _mock_resp):
        # Lets fake the response
        # returned by http_client
        fake = utils.FakeHTTPResponse(data=b"Ok")
        _mock_resp.return_value = fake

        headers = {"test": u'ni\xf1o'}
        resp = self.client.do_request('GET', '/v1/images/detail',
                                      headers=headers)
        self.assertEqual(fake, resp)

    @mock.patch.object(http_client.HTTPConnection, "getresponse")
    @mock.patch.object(http_client.HTTPConnection, "request")
    def test_http_encoding_params(self, _mock_req, _mock_resp):
        # Lets fake the response
        # returned by http_client
        fake = utils.FakeHTTPResponse(data=b"Ok")
        _mock_resp.return_value = fake

        params = {"test": u'ni\xf1o'}
        resp = self.client.do_request('GET', '/v1/images/detail',
                                      params=params)
        self.assertEqual(fake, resp)
