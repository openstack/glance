# Copyright 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

import http.client as http

from oslo_serialization import jsonutils
import webob

from glance.common import auth
from glance.common import exception
from glance.tests import utils


class FakeResponse(object):
    """
    Simple class that masks the inconsistency between
    webob.Response.status_int and httplib.Response.status
    """
    def __init__(self, resp):
        self.resp = resp

    def __getitem__(self, key):
        return self.resp.headers.get(key)

    @property
    def status(self):
        return self.resp.status_int


class V2Token(object):
    def __init__(self):
        self.tok = self.base_token

    @property
    def token(self):
        return self.tok

    @property
    def base_endpoint(self):
        return {
            "adminURL": "http://localhost:9292",
            "internalURL": "http://localhost:9292",
            "publicURL": "http://localhost:9292"
        }

    @property
    def base_token(self):
        return {
            "access": {
                "token": {
                    "expires": "2010-11-23T16:40:53.321584",
                    "id": "5c7f8799-2e54-43e4-851b-31f81871b6c",
                    "tenant": {"id": "1", "name": "tenant-ok"}
                },
                "serviceCatalog": [
                ],
                "user": {
                    "id": "2",
                    "roles": [{
                        "tenantId": "1",
                        "id": "1",
                        "name": "Admin"
                    }],
                    "name": "joeadmin"
                }
            }
        }


class TestKeystoneAuthPlugin(utils.BaseTestCase):
    """Test that the Keystone auth plugin works properly"""

    def setUp(self):
        super(TestKeystoneAuthPlugin, self).setUp()

    def test_required_creds(self):
        """
        Test that plugin created without required
        credential pieces raises an exception
        """
        bad_creds = [
            {},  # missing everything
            {
                'username': 'user1',
                'strategy': 'keystone',
                'password': 'pass'
            },  # missing auth_url
            {
                'password': 'pass',
                'strategy': 'keystone',
                'auth_url': 'http://localhost/v1'
            },  # missing username
            {
                'username': 'user1',
                'strategy': 'keystone',
                'auth_url': 'http://localhost/v1'
            },  # missing password
            {
                'username': 'user1',
                'password': 'pass',
                'auth_url': 'http://localhost/v1'
            },  # missing strategy
            {
                'username': 'user1',
                'password': 'pass',
                'strategy': 'keystone',
                'auth_url': 'http://localhost/v2.0/'
            },  # v2.0: missing tenant
            {
                'username': None,
                'password': 'pass',
                'auth_url': 'http://localhost/v2.0/'
            },  # None parameter
            {
                'username': 'user1',
                'password': 'pass',
                'auth_url': 'http://localhost/v2.0/',
                'tenant': None
            }  # None tenant
        ]
        for creds in bad_creds:
            try:
                plugin = auth.KeystoneStrategy(creds)
                plugin.authenticate()
                self.fail("Failed to raise correct exception when supplying "
                          "bad credentials: %r" % creds)
            except exception.MissingCredentialError:
                continue  # Expected

    def test_invalid_auth_url_v1(self):
        """
        Test that a 400 during authenticate raises exception.AuthBadRequest
        """
        def fake_do_request(*args, **kwargs):
            resp = webob.Response()
            resp.status = http.BAD_REQUEST
            return FakeResponse(resp), ""

        self.mock_object(auth.KeystoneStrategy, '_do_request', fake_do_request)

        bad_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/badauthurl/',
            'password': 'pass',
            'strategy': 'keystone',
        }

        plugin = auth.KeystoneStrategy(bad_creds)
        self.assertRaises(exception.AuthBadRequest, plugin.authenticate)

    def test_invalid_auth_url_v2(self):
        """
        Test that a 400 during authenticate raises exception.AuthBadRequest
        """
        def fake_do_request(*args, **kwargs):
            resp = webob.Response()
            resp.status = http.BAD_REQUEST
            return FakeResponse(resp), ""

        self.mock_object(auth.KeystoneStrategy, '_do_request', fake_do_request)

        bad_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/badauthurl/v2.0/',
            'password': 'pass',
            'tenant': 'tenant1',
            'strategy': 'keystone',
        }

        plugin = auth.KeystoneStrategy(bad_creds)
        self.assertRaises(exception.AuthBadRequest, plugin.authenticate)

    def test_v1_auth(self):
        """Test v1 auth code paths"""
        def fake_do_request(cls, url, method, headers=None, body=None):
            if url.find("2.0") != -1:
                self.fail("Invalid v1.0 token path (%s)" % url)
            headers = headers or {}

            resp = webob.Response()

            if (headers.get('X-Auth-User') != 'user1' or
                    headers.get('X-Auth-Key') != 'pass'):
                resp.status = http.UNAUTHORIZED
            else:
                resp.status = http.OK

            return FakeResponse(resp), ""

        self.mock_object(auth.KeystoneStrategy, '_do_request', fake_do_request)

        unauthorized_creds = [
            {
                'username': 'wronguser',
                'auth_url': 'http://localhost/badauthurl/',
                'strategy': 'keystone',
                'password': 'pass'
            },  # wrong username
            {
                'username': 'user1',
                'auth_url': 'http://localhost/badauthurl/',
                'strategy': 'keystone',
                'password': 'badpass'
            },  # bad password...
        ]

        for creds in unauthorized_creds:
            try:
                plugin = auth.KeystoneStrategy(creds)
                plugin.authenticate()
                self.fail("Failed to raise NotAuthenticated when supplying "
                          "bad credentials: %r" % creds)
            except exception.NotAuthenticated:
                continue  # Expected

        no_strategy_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/redirect/',
            'password': 'pass'
        }

        try:
            plugin = auth.KeystoneStrategy(no_strategy_creds)
            plugin.authenticate()
            self.fail("Failed to raise MissingCredentialError when "
                      "supplying no strategy: %r" % no_strategy_creds)
        except exception.MissingCredentialError:
            pass  # Expected

        good_creds = [
            {
                'username': 'user1',
                'auth_url': 'http://localhost/redirect/',
                'password': 'pass',
                'strategy': 'keystone'
            }
        ]

        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertIsNone(plugin.authenticate())

    def test_v2_auth(self):
        """Test v2 auth code paths"""
        mock_token = None

        def fake_do_request(cls, url, method, headers=None, body=None):
            if (not url.rstrip('/').endswith('v2.0/tokens') or
                    url.count("2.0") != 1):
                self.fail("Invalid v2.0 token path (%s)" % url)

            creds = jsonutils.loads(body)['auth']
            username = creds['passwordCredentials']['username']
            password = creds['passwordCredentials']['password']
            tenant = creds['tenantName']
            resp = webob.Response()

            if (username != 'user1' or password != 'pass' or
                    tenant != 'tenant-ok'):
                resp.status = http.UNAUTHORIZED
            else:
                resp.status = http.OK
                body = mock_token.token

            return FakeResponse(resp), jsonutils.dumps(body)

        mock_token = V2Token()
        self.mock_object(auth.KeystoneStrategy, '_do_request', fake_do_request)

        unauthorized_creds = [
            {
                'username': 'wronguser',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
            },  # wrong username
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'badpass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
            },  # bad password...
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'carterhayes',
                'strategy': 'keystone',
            },  # bad tenant...
        ]

        for creds in unauthorized_creds:
            try:
                plugin = auth.KeystoneStrategy(creds)
                plugin.authenticate()
                self.fail("Failed to raise NotAuthenticated when supplying "
                          "bad credentials: %r" % creds)
            except exception.NotAuthenticated:
                continue  # Expected

        no_strategy_creds = {
            'username': 'user1',
            'tenant': 'tenant-ok',
            'auth_url': 'http://localhost/redirect/v2.0/',
            'password': 'pass'
        }

        try:
            plugin = auth.KeystoneStrategy(no_strategy_creds)
            plugin.authenticate()
            self.fail("Failed to raise MissingCredentialError when "
                      "supplying no strategy: %r" % no_strategy_creds)
        except exception.MissingCredentialError:
            pass  # Expected

        bad_strategy_creds = {
            'username': 'user1',
            'tenant': 'tenant-ok',
            'auth_url': 'http://localhost/redirect/v2.0/',
            'password': 'pass',
            'strategy': 'keypebble'
        }

        try:
            plugin = auth.KeystoneStrategy(bad_strategy_creds)
            plugin.authenticate()
            self.fail("Failed to raise BadAuthStrategy when supplying "
                      "bad auth strategy: %r" % bad_strategy_creds)
        except exception.BadAuthStrategy:
            pass  # Expected

        mock_token = V2Token()

        good_creds = [
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0/',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
            },  # auth_url with trailing '/'
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
            }   # auth_url without trailing '/'
        ]

        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertIsNone(plugin.authenticate())
