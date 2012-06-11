
import webob

from glance.common import context
from glance.tests.unit import base


class TestContextMiddleware(base.IsolatedUnitTest):
    def _build_request(self, roles=None, identity_status='Confirmed'):
        req = webob.Request.blank('/')
        req.headers['x-auth-token'] = 'token1'
        req.headers['x-identity-status'] = identity_status
        req.headers['x-user-id'] = 'user1'
        req.headers['x-tenant-id'] = 'tenant1'
        _roles = roles or ['role1', 'role2']
        req.headers['x-roles'] = ','.join(_roles)

        return req

    def _build_middleware(self):
        return context.ContextMiddleware(None)

    def test_header_parsing(self):
        req = self._build_request()
        self._build_middleware().process_request(req)
        self.assertEqual(req.context.auth_tok, 'token1')
        self.assertEqual(req.context.user, 'user1')
        self.assertEqual(req.context.tenant, 'tenant1')
        self.assertEqual(req.context.roles, ['role1', 'role2'])

    def test_is_admin_flag(self):
        # is_admin check should look for 'admin' role by default
        req = self._build_request(roles=['admin', 'role2'])
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

        # without the 'admin' role, is_admin shoud be False
        req = self._build_request()
        self._build_middleware().process_request(req)
        self.assertFalse(req.context.is_admin)

        # if we change the admin_role attribute, we should be able to use it
        req = self._build_request()
        self.config(admin_role='role1')
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

    def test_anonymous_access_enabled(self):
        req = self._build_request(identity_status='Nope')
        self.config(allow_anonymous_access=True)
        middleware = self._build_middleware()
        middleware.process_request(req)
        self.assertEqual(req.context.auth_tok, None)
        self.assertEqual(req.context.user, None)
        self.assertEqual(req.context.tenant, None)
        self.assertEqual(req.context.roles, [])
        self.assertFalse(req.context.is_admin)
        self.assertTrue(req.context.read_only)

    def test_anonymous_access_defaults_to_disabled(self):
        req = self._build_request(identity_status='Nope')
        middleware = self._build_middleware()
        self.assertRaises(webob.exc.HTTPUnauthorized,
                          middleware.process_request, req)


class TestUnauthenticatedContextMiddleware(base.IsolatedUnitTest):
    def test_request(self):
        middleware = context.UnauthenticatedContextMiddleware(None)
        req = webob.Request.blank('/')
        middleware.process_request(req)
        self.assertEqual(req.context.auth_tok, None)
        self.assertEqual(req.context.user, None)
        self.assertEqual(req.context.tenant, None)
        self.assertEqual(req.context.roles, [])
        self.assertTrue(req.context.is_admin)
