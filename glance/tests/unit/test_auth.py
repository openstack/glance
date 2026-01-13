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

from keystoneauth1 import fixture as ksa_fixture
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


class TestKeystoneAuthPlugin(utils.BaseTestCase):
    """Test that the Keystone auth plugin works properly"""

    def setUp(self):
        super(TestKeystoneAuthPlugin, self).setUp()

    def test_get_plugin_from_strategy_keystone(self):
        strategy = auth.get_plugin_from_strategy('keystone')
        self.assertIsInstance(strategy, auth.KeystoneStrategy)

    def test_required_creds(self):
        """
        Test that plugin created without required
        credential pieces raises an exception
        """
        bad_creds = [
            {},  # missing everything
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'project': 'project1',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone',
                'password': 'pass'
            },  # missing auth_url
            {
                'user_domain_id': 'userdomain',
                'password': 'pass',
                'project': 'project1',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone',
                'auth_url': 'http://localhost'
            },  # missing username
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'project': 'project1',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone',
                'auth_url': 'http://localhost',
            },  # missing password
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'project_domain_id': 'projectdomain',
                'password': 'pass',
                'strategy': 'keystone',
                'auth_url': 'http://localhost'
            },  # missing project
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'password': 'pass',
                'project': 'project1',
                'project_domain_id': 'projectdomain',
                'auth_url': 'http://localhost'
            },  # missing strategy
            {
                'username': None,
                'user_domain_id': 'userdomain',
                'project': 'project1',
                'project_domain_id': 'projectdomain',
                'password': 'pass',
                'auth_url': 'http://localhost'
            }   # None parameter
        ]
        for creds in bad_creds:
            try:
                plugin = auth.KeystoneStrategy(creds)
                plugin.authenticate()
                self.fail("Failed to raise correct exception when supplying "
                          "bad credentials: %r" % creds)
            except exception.MissingCredentialError:
                continue  # Expected

    def test_invalid_auth_url(self):
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
            'user_domain_id': 'userdomain',
            'auth_url': 'http://localhost/badauthurl/v3',
            'password': 'pass',
            'project': 'project1',
            'project_domain_id': 'projectdomain',
            'strategy': 'keystone'
        }

        plugin = auth.KeystoneStrategy(bad_creds)
        self.assertRaises(exception.AuthBadRequest, plugin.authenticate)

    def test_v3_auth(self):
        """Test v3 auth code paths"""
        mock_token = None

        def fake_do_request(cls, url, method, headers=None, body=None):
            creds = jsonutils.loads(body)['auth']
            username = creds['identity']['password']['user']['name']
            password = creds['identity']['password']['user']['password']
            project = creds['scope']['project']['name']
            resp = webob.Response()

            if (username != 'user1' or password != 'pass' or
                    project != 'project-ok'):
                resp.status = http.UNAUTHORIZED
            else:
                resp.status = http.CREATED
                body = mock_token

            return FakeResponse(resp), jsonutils.dumps(body)

        mock_token = ksa_fixture.V3Token()

        self.mock_object(auth.KeystoneStrategy, '_do_request', fake_do_request)

        unauthorized_creds = [
            {
                'username': 'wronguser',
                'user_domain_id': 'userdomain',
                'auth_url': 'http://localhost/identity',
                'password': 'pass',
                'project': 'project-ok',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone'
            },  # wrong username
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'auth_url': 'http://localhost/identity',
                'password': 'badpass',
                'project': 'project-ok',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone'
            },  # bad password...
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'auth_url': 'http://localhost/identity',
                'password': 'pass',
                'project': 'carterhayes',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone'
            },  # bad project...
        ]

        for creds in unauthorized_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertRaises(exception.NotAuthenticated, plugin.authenticate)

        no_strategy_creds = {
            'username': 'user1',
            'user_domain_id': 'userdomain',
            'project': 'project-ok',
            'project_domain_id': 'projectdomain',
            'auth_url': 'http://localhost/redirect/',
            'password': 'pass'
        }

        plugin = auth.KeystoneStrategy(no_strategy_creds)
        self.assertRaises(exception.MissingCredentialError,
                          plugin.authenticate)

        bad_strategy_creds = {
            'username': 'user1',
            'user_domain_id': 'userdomain',
            'project': 'project-ok',
            'project_domain_id': 'projectdomain',
            'auth_url': 'http://localhost/redirect/',
            'password': 'pass',
            'strategy': 'keypebble'
        }

        plugin = auth.KeystoneStrategy(bad_strategy_creds)
        self.assertRaises(exception.BadAuthStrategy, plugin.authenticate)

        good_creds = [
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'auth_url': 'http://localhost/',
                'password': 'pass',
                'project': 'project-ok',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone'
            },  # auth_url with trailing '/'
            {
                'username': 'user1',
                'user_domain_id': 'userdomain',
                'auth_url': 'http://localhost',
                'password': 'pass',
                'project': 'project-ok',
                'project_domain_id': 'projectdomain',
                'strategy': 'keystone'
            }   # auth_url without trailing '/'
        ]

        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertIsNone(plugin.authenticate())
