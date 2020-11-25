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

import webob

from glance.api.middleware import context
import glance.context
from glance.tests.unit import base


class TestContextMiddleware(base.IsolatedUnitTest):
    def _build_request(self, roles=None, identity_status='Confirmed',
                       service_catalog=None):
        req = webob.Request.blank('/')
        req.headers['x-auth-token'] = 'token1'
        req.headers['x-identity-status'] = identity_status
        req.headers['x-user-id'] = 'user1'
        req.headers['x-tenant-id'] = 'tenant1'
        _roles = roles or ['role1', 'role2']
        req.headers['x-roles'] = ','.join(_roles)
        if service_catalog:
            req.headers['x-service-catalog'] = service_catalog

        return req

    def _build_middleware(self):
        return context.ContextMiddleware(None)

    def test_header_parsing(self):
        req = self._build_request()
        self._build_middleware().process_request(req)
        self.assertEqual('token1', req.context.auth_token)
        self.assertEqual('user1', req.context.user_id)
        self.assertEqual('tenant1', req.context.project_id)
        self.assertEqual(['role1', 'role2'], req.context.roles)

    def test_is_admin_flag(self):
        # is_admin check should look for 'admin' role by default
        req = self._build_request(roles=['admin', 'role2'])
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

        # without the 'admin' role, is_admin should be False
        req = self._build_request()
        self._build_middleware().process_request(req)
        self.assertFalse(req.context.is_admin)

        # the admin_role config option was removed in Wallaby
        from oslo_config.cfg import NoSuchOptError
        self.assertRaises(NoSuchOptError,
                          self.config,
                          admin_role='role1')

    def test_roles_case_insensitive(self):
        # accept role from request
        req = self._build_request(roles=['Admin', 'role2'])
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

    def test_roles_stripping(self):
        # stripping extra spaces in request
        req = self._build_request(roles=['\trole1'])
        self._build_middleware().process_request(req)
        self.assertIn('role1', req.context.roles)

    def test_anonymous_access_enabled(self):
        req = self._build_request(identity_status='Nope')
        self.config(allow_anonymous_access=True)
        middleware = self._build_middleware()
        middleware.process_request(req)
        self.assertIsNone(req.context.auth_token)
        self.assertIsNone(req.context.user_id)
        self.assertIsNone(req.context.project_id)
        self.assertEqual([], req.context.roles)
        self.assertFalse(req.context.is_admin)
        self.assertTrue(req.context.read_only)

    def test_anonymous_access_defaults_to_disabled(self):
        req = self._build_request(identity_status='Nope')
        middleware = self._build_middleware()
        self.assertRaises(webob.exc.HTTPUnauthorized,
                          middleware.process_request, req)

    def test_service_catalog(self):
        catalog_json = "[{}]"
        req = self._build_request(service_catalog=catalog_json)
        self._build_middleware().process_request(req)
        self.assertEqual([{}], req.context.service_catalog)

    def test_invalid_service_catalog(self):
        catalog_json = "bad json"
        req = self._build_request(service_catalog=catalog_json)
        middleware = self._build_middleware()
        self.assertRaises(webob.exc.HTTPInternalServerError,
                          middleware.process_request, req)

    def test_response(self):
        req = self._build_request()
        req.context = glance.context.RequestContext()
        request_id = req.context.request_id

        resp = webob.Response()
        resp.request = req
        self._build_middleware().process_response(resp)
        self.assertEqual(request_id, resp.headers['x-openstack-request-id'])
        resp_req_id = resp.headers['x-openstack-request-id']
        # Validate that request-id do not starts with 'req-req-'
        if isinstance(resp_req_id, bytes):
            resp_req_id = resp_req_id.decode('utf-8')
        self.assertFalse(resp_req_id.startswith('req-req-'))
        self.assertTrue(resp_req_id.startswith('req-'))


class TestUnauthenticatedContextMiddleware(base.IsolatedUnitTest):
    def test_request(self):
        middleware = context.UnauthenticatedContextMiddleware(None)
        req = webob.Request.blank('/')
        middleware.process_request(req)
        self.assertIsNone(req.context.auth_token)
        self.assertIsNone(req.context.user_id)
        self.assertIsNone(req.context.project_id)
        self.assertEqual([], req.context.roles)
        self.assertTrue(req.context.is_admin)

    def test_response(self):
        middleware = context.UnauthenticatedContextMiddleware(None)
        req = webob.Request.blank('/')
        req.context = glance.context.RequestContext()
        request_id = req.context.request_id

        resp = webob.Response()
        resp.request = req
        middleware.process_response(resp)
        self.assertEqual(request_id, resp.headers['x-openstack-request-id'])
        resp_req_id = resp.headers['x-openstack-request-id']
        if isinstance(resp_req_id, bytes):
            resp_req_id = resp_req_id.decode('utf-8')
        # Validate that request-id do not starts with 'req-req-'
        self.assertFalse(resp_req_id.startswith('req-req-'))
        self.assertTrue(resp_req_id.startswith('req-'))
