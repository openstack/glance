# Copyright 2011 OpenStack Foundation
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

"""
This auth module is intended to allow OpenStack client-tools to select from a
variety of authentication strategies, including NoAuth (the default), and
Keystone (an identity management system).

::

   > auth_plugin = AuthPlugin(creds)

   > auth_plugin.authenticate()

   > auth_plugin.auth_token
    abcdefg

"""

import urllib.parse as urlparse

import httplib2
from oslo_serialization import jsonutils

from glance.common import exception
from glance.i18n import _


class BaseStrategy(object):
    def __init__(self):
        self.auth_token = None

    def authenticate(self):
        raise NotImplementedError

    @property
    def is_authenticated(self):
        raise NotImplementedError

    @property
    def strategy(self):
        raise NotImplementedError


class NoAuthStrategy(BaseStrategy):
    def authenticate(self):
        pass

    @property
    def is_authenticated(self):
        return True

    @property
    def strategy(self):
        return 'noauth'


class KeystoneStrategy(BaseStrategy):
    MAX_REDIRECTS = 10

    def __init__(self, creds, insecure=False):
        self.creds = creds
        self.insecure = insecure
        super(KeystoneStrategy, self).__init__()

    def check_auth_params(self):
        for required in ('username', 'password', 'auth_url', 'project',
                         'strategy', 'user_domain_id', 'project_domain_id'):
            if self.creds.get(required) is None:
                raise exception.MissingCredentialError(required=required)
        if self.creds['strategy'] != 'keystone':
            raise exception.BadAuthStrategy(expected='keystone',
                                            received=self.creds['strategy'])

    def authenticate(self):
        """Authenticate with the Keystone service.
        """
        def _authenticate(auth_url):
            # If OS_AUTH_URL is missing a trailing slash add one
            if not auth_url.endswith('/'):
                auth_url += '/'

            token_url = urlparse.urljoin(auth_url, "auth/tokens")
            self._auth(token_url)

        self.check_auth_params()
        auth_url = self.creds['auth_url']
        for redirect_iter in range(self.MAX_REDIRECTS):
            try:
                _authenticate(auth_url)
            except exception.AuthorizationRedirect as e:
                # Keystone may redirect us
                auth_url = e.url
            else:
                # If we successfully auth'd, then memorize the correct auth_url
                # for future use.
                self.creds['auth_url'] = auth_url
                break
        else:
            # Guard against a redirection loop
            raise exception.MaxRedirectsExceeded(redirects=self.MAX_REDIRECTS)

    def _auth(self, token_url):
        creds = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.creds['username'],
                            "domain": {"id": self.creds['user_domain_id']},
                            "password": self.creds['password']
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": self.creds['project'],
                        "domain": {
                            "id": self.creds['project_domain_id']
                        }
                    }
                }
            }
        }

        headers = {'Content-Type': 'application/json'}
        req_body = jsonutils.dumps(creds)

        resp, _ = self._do_request(
            token_url, 'POST', headers=headers, body=req_body)

        if resp.status == 201:
            self.auth_token = resp['x-subject-token']
        elif resp.status == 305:
            raise exception.RedirectException(resp['location'])
        elif resp.status == 400:
            raise exception.AuthBadRequest(url=token_url)
        elif resp.status == 401:
            raise exception.NotAuthenticated()
        else:
            raise Exception(_('Unknown response code: %d') % resp.status)

    @property
    def is_authenticated(self):
        return self.auth_token is not None

    @property
    def strategy(self):
        return 'keystone'

    def _do_request(self, url, method, headers=None, body=None):
        headers = headers or {}
        conn = httplib2.Http()
        conn.force_exception_to_status_code = True
        conn.disable_ssl_certificate_validation = self.insecure
        headers['User-Agent'] = 'glance-client'
        resp, resp_body = conn.request(url, method, headers=headers, body=body)
        return resp, resp_body


def get_plugin_from_strategy(strategy, creds=None, insecure=False):
    if strategy == 'noauth':
        return NoAuthStrategy()
    elif strategy == 'keystone':
        return KeystoneStrategy(creds, insecure)
    else:
        raise Exception(_("Unknown auth strategy '%s'") % strategy)
