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

import http.client
from unittest import mock

from oslo_log.fixture import logging_error as log_fixture
import testtools

from glance.common import auth
from glance.common import client
from glance.tests.unit import fixtures as glance_fixtures
from glance.tests import utils


class TestClient(testtools.TestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.endpoint = 'example.com'
        self.client = client.BaseClient(self.endpoint, port=9191,
                                        auth_token='abc123')

        # Limit the amount of DeprecationWarning messages in the unit test logs
        self.useFixture(glance_fixtures.WarningsFixture())

        # Make sure logging output is limited but still test debug formatting
        self.useFixture(log_fixture.get_logging_handle_error_fixture())
        self.useFixture(glance_fixtures.StandardLogging())

    def test_make_auth_plugin(self):
        creds = {'strategy': 'keystone'}
        insecure = False

        with mock.patch.object(auth, 'get_plugin_from_strategy'):
            self.client.make_auth_plugin(creds, insecure)

    @mock.patch.object(http.client.HTTPConnection, "getresponse")
    @mock.patch.object(http.client.HTTPConnection, "request")
    def test_http_encoding_headers(self, _mock_req, _mock_resp):
        # Lets fake the response
        # returned by http.client
        fake = utils.FakeHTTPResponse(data=b"Ok")
        _mock_resp.return_value = fake

        headers = {"test": 'ni\xf1o'}
        resp = self.client.do_request('GET', '/v1/images/detail',
                                      headers=headers)
        self.assertEqual(fake, resp)

    @mock.patch.object(http.client.HTTPConnection, "getresponse")
    @mock.patch.object(http.client.HTTPConnection, "request")
    def test_http_encoding_params(self, _mock_req, _mock_resp):
        # Lets fake the response
        # returned by http.client
        fake = utils.FakeHTTPResponse(data=b"Ok")
        _mock_resp.return_value = fake

        params = {"test": 'ni\xf1o'}
        resp = self.client.do_request('GET', '/v1/images/detail',
                                      params=params)
        self.assertEqual(fake, resp)
