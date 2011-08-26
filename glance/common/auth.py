# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
This auth module is intended to allow Openstack client-tools to select from a
variety of authentication strategies, including NoAuth (the default), and
Keystone (an identity management system).

    > auth_plugin = AuthPlugin(creds)

    > auth_plugin.authenticate()

    > auth_plugin.auth_token
    abcdefg

    > auth_plugin.management_url
    http://service_endpoint/
"""
import httplib2
import json
import urlparse

from glance.common import exception


class BaseStrategy(object):
    def __init__(self, creds):
        self.creds = creds
        self.auth_token = None

        # TODO(sirp): For now we're just dealing with one endpoint, eventually
        # this should expose the entire service catalog so that the client can
        # choose which service/region/(public/private net) combo they want.
        self.management_url = None

    def authenticate(self):
        raise NotImplementedError

    @property
    def is_authenticated(self):
        raise NotImplementedError


class NoAuthStrategy(BaseStrategy):
    def authenticate(self):
        pass

    @property
    def is_authenticated(self):
        return True


class KeystoneStrategy(BaseStrategy):
    MAX_REDIRECTS = 10

    def authenticate(self):
        """Authenticate with the Keystone service.

        There are a few scenarios to consider here:

        1. Which version of Keystone are we using? v1 which uses headers to
           pass the credentials, or v2 which uses a JSON encoded request body?

        2. Keystone may respond back with a redirection using a 305 status
           code.

        3. We may attempt a v1 auth when v2 is what's called for. In this
           case, we rewrite the url to contain /v2.0/ and retry using the v2
           protocol.
        """
        def _authenticate(auth_url):
            token_url = urlparse.urljoin(auth_url, "tokens")

            # 1. Check Keystone version
            is_v2 = auth_url.rstrip('/').endswith('v2.0')
            if is_v2:
                self._v2_auth(token_url)
            else:
                self._v1_auth(token_url)

        for required in ('username', 'password', 'auth_url'):
            if required not in self.creds:
                raise Exception(_("'%s' must be included in creds") %
                                required)

        auth_url = self.creds['auth_url']
        for _ in range(self.MAX_REDIRECTS):
            try:
                _authenticate(auth_url)
            except exception.RedirectException as e:
                # 2. Keystone may redirect us
                auth_url = e.url
            except exception.AuthorizationFailure:
                # 3. In some configurations nova makes redirection to
                # v2.0 keystone endpoint. Also, new location does not
                # contain real endpoint, only hostname and port.
                if  'v2.0' not in auth_url:
                    auth_url = urlparse.urljoin(auth_url, 'v2.0/')
            else:
                # If we sucessfully auth'd, then memorize the correct auth_url
                # for future use.
                self.creds['auth_url'] = auth_url
                break
        else:
            # Guard against a redirection loop
            raise Exception(_("Exceeded max redirects %s") % MAX_REDIRECTS)

    def _v1_auth(self, token_url):
        creds = self.creds

        headers = {}
        headers['X-Auth-User'] = creds['username']
        headers['X-Auth-Key'] = creds['password']

        tenant = creds.get('tenant')
        if tenant:
            headers['X-Auth-Tenant'] = tenant

        resp, resp_body = self._do_request(token_url, 'GET', headers=headers)

        if resp.status in (200, 204):
            try:
                self.management_url = resp['x-server-management-url']
                self.auth_token = resp['x-auth-token']
            except KeyError:
                raise exception.AuthorizationFailure()
        elif resp.status == 305:
            raise exception.RedirectException(resp['location'])
        elif resp.status == 401:
            raise exception.NotAuthorized()
        else:
            raise Exception(_('Unexpected response: %s' % resp.status))

    def _v2_auth(self, token_url):
        creds = self.creds

        creds = {"passwordCredentials": {"username": creds['username'],
                                         "password": creds['password']}}

        tenant = creds.get('tenant')
        if tenant:
            creds['passwordCredentials']['tenantId'] = tenant

        headers = {}
        headers['Content-Type'] = 'application/json'
        req_body = json.dumps(creds)

        resp, resp_body = self._do_request(
                token_url, 'POST', headers=headers, body=req_body)

        if resp.status == 200:
            resp_auth = json.loads(resp_body)['auth']

            # FIXME(sirp): for now just using the first endpoint we get back
            # from the service catalog for glance, and using the public url.
            glance_info = resp_auth['serviceCatalog']['glance']
            glance_endpoint = glance_info[0]['publicURL']

            self.management_url = glance_endpoint
            self.auth_token = resp_auth['token']['id']
        elif resp.status == 305:
            raise RedirectException(resp['location'])
        elif resp.status == 401:
            raise exception.NotAuthorized()
        else:
            raise Exception(_('Unexpected response: %s') % resp.status)

    @property
    def is_authenticated(self):
        return self.auth_token is not None

    @staticmethod
    def _do_request(url, method, headers=None, body=None):
        headers = headers or {}
        conn = httplib2.Http()
        conn.force_exception_to_status_code = True
        headers['User-Agent'] = 'glance-client'
        resp, resp_body = conn.request(url, method, headers=headers, body=body)
        return resp, resp_body


def get_plugin_from_strategy(strategy):
    if strategy == 'noauth':
        return NoAuthStrategy
    elif strategy == 'keystone':
        return KeystoneStrategy
    else:
        raise Exception(_("Unknown auth strategy '%s'") % strategy)
