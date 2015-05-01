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

from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslotest import moxstubout
import webob

from glance.api import authorization
from glance.common import auth
from glance.common import exception
import glance.domain
from glance.tests.unit import utils as unittest_utils
from glance.tests import utils


TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'


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

    def add_service_no_type(self):
        catalog = self.tok['access']['serviceCatalog']
        service_type = {"name": "glance_no_type"}
        catalog.append(service_type)
        service = catalog[-1]
        service['endpoints'] = [self.base_endpoint]

    def add_service(self, s_type, region_list=None):
        if region_list is None:
            region_list = []

        catalog = self.tok['access']['serviceCatalog']
        service_type = {"type": s_type, "name": "glance"}
        catalog.append(service_type)
        service = catalog[-1]
        endpoint_list = []

        if region_list == []:
            endpoint_list.append(self.base_endpoint)
        else:
            for region in region_list:
                endpoint = self.base_endpoint
                endpoint['region'] = region
                endpoint_list.append(endpoint)

        service['endpoints'] = endpoint_list

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
        mox_fixture = self.useFixture(moxstubout.MoxStubout())
        self.stubs = mox_fixture.stubs

    def test_get_plugin_from_strategy_keystone(self):
        strategy = auth.get_plugin_from_strategy('keystone')
        self.assertIsInstance(strategy, auth.KeystoneStrategy)
        self.assertTrue(strategy.configure_via_auth)

    def test_get_plugin_from_strategy_keystone_configure_via_auth_false(self):
        strategy = auth.get_plugin_from_strategy('keystone',
                                                 configure_via_auth=False)
        self.assertIsInstance(strategy, auth.KeystoneStrategy)
        self.assertFalse(strategy.configure_via_auth)

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
            resp.status = 400
            return FakeResponse(resp), ""

        self.stubs.Set(auth.KeystoneStrategy, '_do_request', fake_do_request)

        bad_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/badauthurl/',
            'password': 'pass',
            'strategy': 'keystone',
            'region': 'RegionOne'
        }

        plugin = auth.KeystoneStrategy(bad_creds)
        self.assertRaises(exception.AuthBadRequest, plugin.authenticate)

    def test_invalid_auth_url_v2(self):
        """
        Test that a 400 during authenticate raises exception.AuthBadRequest
        """
        def fake_do_request(*args, **kwargs):
            resp = webob.Response()
            resp.status = 400
            return FakeResponse(resp), ""

        self.stubs.Set(auth.KeystoneStrategy, '_do_request', fake_do_request)

        bad_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/badauthurl/v2.0/',
            'password': 'pass',
            'tenant': 'tenant1',
            'strategy': 'keystone',
            'region': 'RegionOne'
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
                resp.status = 401
            else:
                resp.status = 200
                resp.headers.update({"x-image-management-url": "example.com"})

            return FakeResponse(resp), ""

        self.stubs.Set(auth.KeystoneStrategy, '_do_request', fake_do_request)

        unauthorized_creds = [
            {
                'username': 'wronguser',
                'auth_url': 'http://localhost/badauthurl/',
                'strategy': 'keystone',
                'region': 'RegionOne',
                'password': 'pass'
            },  # wrong username
            {
                'username': 'user1',
                'auth_url': 'http://localhost/badauthurl/',
                'strategy': 'keystone',
                'region': 'RegionOne',
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
            'password': 'pass',
            'region': 'RegionOne'
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
                'strategy': 'keystone',
                'region': 'RegionOne'
            }
        ]

        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertIsNone(plugin.authenticate())
            self.assertEqual("example.com", plugin.management_url)

        # Assert it does not update management_url via auth response
        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds, configure_via_auth=False)
            self.assertIsNone(plugin.authenticate())
            self.assertIsNone(plugin.management_url)

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
                resp.status = 401
            else:
                resp.status = 200
                body = mock_token.token

            return FakeResponse(resp), jsonutils.dumps(body)

        mock_token = V2Token()
        mock_token.add_service('image', ['RegionOne'])
        self.stubs.Set(auth.KeystoneStrategy, '_do_request', fake_do_request)

        unauthorized_creds = [
            {
                'username': 'wronguser',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
                'region': 'RegionOne'
            },  # wrong username
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'badpass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
                'region': 'RegionOne'
            },  # bad password...
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'carterhayes',
                'strategy': 'keystone',
                'region': 'RegionOne'
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

        no_region_creds = {
            'username': 'user1',
            'tenant': 'tenant-ok',
            'auth_url': 'http://localhost/redirect/v2.0/',
            'password': 'pass',
            'strategy': 'keystone'
        }

        plugin = auth.KeystoneStrategy(no_region_creds)
        self.assertIsNone(plugin.authenticate())
        self.assertEqual('http://localhost:9292', plugin.management_url)

        # Add another image service, with a different region
        mock_token.add_service('image', ['RegionTwo'])

        try:
            plugin = auth.KeystoneStrategy(no_region_creds)
            plugin.authenticate()
            self.fail("Failed to raise RegionAmbiguity when no region present "
                      "and multiple regions exist: %r" % no_region_creds)
        except exception.RegionAmbiguity:
            pass  # Expected

        wrong_region_creds = {
            'username': 'user1',
            'tenant': 'tenant-ok',
            'auth_url': 'http://localhost/redirect/v2.0/',
            'password': 'pass',
            'strategy': 'keystone',
            'region': 'NonExistentRegion'
        }

        try:
            plugin = auth.KeystoneStrategy(wrong_region_creds)
            plugin.authenticate()
            self.fail("Failed to raise NoServiceEndpoint when supplying "
                      "wrong region: %r" % wrong_region_creds)
        except exception.NoServiceEndpoint:
            pass  # Expected

        no_strategy_creds = {
            'username': 'user1',
            'tenant': 'tenant-ok',
            'auth_url': 'http://localhost/redirect/v2.0/',
            'password': 'pass',
            'region': 'RegionOne'
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
            'region': 'RegionOne',
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
        mock_token.add_service('image', ['RegionOne', 'RegionTwo'])

        good_creds = [
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0/',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
                'region': 'RegionOne'
            },  # auth_url with trailing '/'
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
                'region': 'RegionOne'
            },   # auth_url without trailing '/'
            {
                'username': 'user1',
                'auth_url': 'http://localhost/v2.0',
                'password': 'pass',
                'tenant': 'tenant-ok',
                'strategy': 'keystone',
                'region': 'RegionTwo'
            }   # Second region
        ]

        for creds in good_creds:
            plugin = auth.KeystoneStrategy(creds)
            self.assertIsNone(plugin.authenticate())
            self.assertEqual('http://localhost:9292', plugin.management_url)

        ambiguous_region_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/v2.0/',
            'password': 'pass',
            'tenant': 'tenant-ok',
            'strategy': 'keystone',
            'region': 'RegionOne'
        }

        mock_token = V2Token()
        # Add two identical services
        mock_token.add_service('image', ['RegionOne'])
        mock_token.add_service('image', ['RegionOne'])

        try:
            plugin = auth.KeystoneStrategy(ambiguous_region_creds)
            plugin.authenticate()
            self.fail("Failed to raise RegionAmbiguity when "
                      "non-unique regions exist: %r" % ambiguous_region_creds)
        except exception.RegionAmbiguity:
            pass

        mock_token = V2Token()
        mock_token.add_service('bad-image', ['RegionOne'])

        good_creds = {
            'username': 'user1',
            'auth_url': 'http://localhost/v2.0/',
            'password': 'pass',
            'tenant': 'tenant-ok',
            'strategy': 'keystone',
            'region': 'RegionOne'
        }

        try:
            plugin = auth.KeystoneStrategy(good_creds)
            plugin.authenticate()
            self.fail("Failed to raise NoServiceEndpoint when bad service "
                      "type encountered")
        except exception.NoServiceEndpoint:
            pass

        mock_token = V2Token()
        mock_token.add_service_no_type()

        try:
            plugin = auth.KeystoneStrategy(good_creds)
            plugin.authenticate()
            self.fail("Failed to raise NoServiceEndpoint when bad service "
                      "type encountered")
        except exception.NoServiceEndpoint:
            pass

        try:
            plugin = auth.KeystoneStrategy(good_creds,
                                           configure_via_auth=False)
            plugin.authenticate()
        except exception.NoServiceEndpoint:
            self.fail("NoServiceEndpoint was raised when authenticate "
                      "should not check for endpoint.")


class TestEndpoints(utils.BaseTestCase):

    def setUp(self):
        super(TestEndpoints, self).setUp()

        self.service_catalog = [
            {
                'endpoint_links': [],
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionOne',
                        'internalURL': 'http://internalURL/',
                        'publicURL': 'http://publicURL/',
                    },
                ],
                'type': 'object-store',
                'name': 'Object Storage Service',
            }
        ]

    def test_get_endpoint_with_custom_server_type(self):
        endpoint = auth.get_endpoint(self.service_catalog,
                                     service_type='object-store')
        self.assertEqual('http://publicURL/', endpoint)

    def test_get_endpoint_with_custom_endpoint_type(self):
        endpoint = auth.get_endpoint(self.service_catalog,
                                     service_type='object-store',
                                     endpoint_type='internalURL')
        self.assertEqual('http://internalURL/', endpoint)

    def test_get_endpoint_raises_with_invalid_service_type(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          auth.get_endpoint,
                          self.service_catalog,
                          service_type='foo')

    def test_get_endpoint_raises_with_invalid_endpoint_type(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          auth.get_endpoint,
                          self.service_catalog,
                          service_type='object-store',
                          endpoint_type='foo')

    def test_get_endpoint_raises_with_invalid_endpoint_region(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          auth.get_endpoint,
                          self.service_catalog,
                          service_type='object-store',
                          endpoint_region='foo',
                          endpoint_type='internalURL')


class TestImageMutability(utils.BaseTestCase):

    def setUp(self):
        super(TestImageMutability, self).setUp()
        self.image_factory = glance.domain.ImageFactory()

    def _is_mutable(self, tenant, owner, is_admin=False):
        context = glance.context.RequestContext(tenant=tenant,
                                                is_admin=is_admin)
        image = self.image_factory.new_image(owner=owner)
        return authorization.is_image_mutable(context, image)

    def test_admin_everything_mutable(self):
        self.assertTrue(self._is_mutable(None, None, is_admin=True))
        self.assertTrue(self._is_mutable(None, TENANT1, is_admin=True))
        self.assertTrue(self._is_mutable(TENANT1, None, is_admin=True))
        self.assertTrue(self._is_mutable(TENANT1, TENANT1, is_admin=True))
        self.assertTrue(self._is_mutable(TENANT1, TENANT2, is_admin=True))

    def test_no_tenant_nothing_mutable(self):
        self.assertFalse(self._is_mutable(None, None))
        self.assertFalse(self._is_mutable(None, TENANT1))

    def test_regular_user(self):
        self.assertFalse(self._is_mutable(TENANT1, None))
        self.assertFalse(self._is_mutable(TENANT1, TENANT2))
        self.assertTrue(self._is_mutable(TENANT1, TENANT1))


class TestImmutableImage(utils.BaseTestCase):
    def setUp(self):
        super(TestImmutableImage, self).setUp()
        image_factory = glance.domain.ImageFactory()
        self.context = glance.context.RequestContext(tenant=TENANT1)
        image = image_factory.new_image(
            image_id=UUID1,
            name='Marvin',
            owner=TENANT1,
            disk_format='raw',
            container_format='bare',
            extra_properties={'foo': 'bar'},
            tags=['ping', 'pong'],
        )
        self.image = authorization.ImmutableImageProxy(image, self.context)

    def _test_change(self, attr, value):
        self.assertRaises(exception.Forbidden,
                          setattr, self.image, attr, value)
        self.assertRaises(exception.Forbidden,
                          delattr, self.image, attr)

    def test_change_id(self):
        self._test_change('image_id', UUID2)

    def test_change_name(self):
        self._test_change('name', 'Freddie')

    def test_change_owner(self):
        self._test_change('owner', TENANT2)

    def test_change_min_disk(self):
        self._test_change('min_disk', 100)

    def test_change_min_ram(self):
        self._test_change('min_ram', 1024)

    def test_change_disk_format(self):
        self._test_change('disk_format', 'vhd')

    def test_change_container_format(self):
        self._test_change('container_format', 'ova')

    def test_change_visibility(self):
        self._test_change('visibility', 'public')

    def test_change_status(self):
        self._test_change('status', 'active')

    def test_change_created_at(self):
        self._test_change('created_at', timeutils.utcnow())

    def test_change_updated_at(self):
        self._test_change('updated_at', timeutils.utcnow())

    def test_change_locations(self):
        self._test_change('locations', ['http://a/b/c'])
        self.assertRaises(exception.Forbidden,
                          self.image.locations.append, 'http://a/b/c')
        self.assertRaises(exception.Forbidden,
                          self.image.locations.extend, ['http://a/b/c'])
        self.assertRaises(exception.Forbidden,
                          self.image.locations.insert, 'foo')
        self.assertRaises(exception.Forbidden,
                          self.image.locations.pop)
        self.assertRaises(exception.Forbidden,
                          self.image.locations.remove, 'foo')
        self.assertRaises(exception.Forbidden,
                          self.image.locations.reverse)
        self.assertRaises(exception.Forbidden,
                          self.image.locations.sort)
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__delitem__, 0)
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__delslice__, 0, 2)
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__setitem__, 0, 'foo')
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__setslice__,
                          0, 2, ['foo', 'bar'])
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__iadd__, 'foo')
        self.assertRaises(exception.Forbidden,
                          self.image.locations.__imul__, 2)

    def test_change_size(self):
        self._test_change('size', 32)

    def test_change_tags(self):
        self.assertRaises(exception.Forbidden,
                          delattr, self.image, 'tags')
        self.assertRaises(exception.Forbidden,
                          setattr, self.image, 'tags', ['king', 'kong'])
        self.assertRaises(exception.Forbidden, self.image.tags.pop)
        self.assertRaises(exception.Forbidden, self.image.tags.clear)
        self.assertRaises(exception.Forbidden, self.image.tags.add, 'king')
        self.assertRaises(exception.Forbidden, self.image.tags.remove, 'ping')
        self.assertRaises(exception.Forbidden,
                          self.image.tags.update, set(['king', 'kong']))
        self.assertRaises(exception.Forbidden,
                          self.image.tags.intersection_update, set([]))
        self.assertRaises(exception.Forbidden,
                          self.image.tags.difference_update, set([]))
        self.assertRaises(exception.Forbidden,
                          self.image.tags.symmetric_difference_update,
                          set([]))

    def test_change_properties(self):
        self.assertRaises(exception.Forbidden,
                          delattr, self.image, 'extra_properties')
        self.assertRaises(exception.Forbidden,
                          setattr, self.image, 'extra_properties', {})
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.__delitem__, 'foo')
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.__setitem__, 'foo', 'b')
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.__setitem__, 'z', 'j')
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.pop)
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.popitem)
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.setdefault, 'p', 'j')
        self.assertRaises(exception.Forbidden,
                          self.image.extra_properties.update, {})

    def test_delete(self):
        self.assertRaises(exception.Forbidden, self.image.delete)

    def test_set_data(self):
        self.assertRaises(exception.Forbidden,
                          self.image.set_data, 'blah', 4)

    def test_get_data(self):
        class FakeImage(object):
            def get_data(self):
                return 'tiddlywinks'

        image = glance.api.authorization.ImmutableImageProxy(
            FakeImage(), self.context)
        self.assertEqual('tiddlywinks', image.get_data())


class TestImageFactoryProxy(utils.BaseTestCase):
    def setUp(self):
        super(TestImageFactoryProxy, self).setUp()
        factory = glance.domain.ImageFactory()
        self.context = glance.context.RequestContext(tenant=TENANT1)
        self.image_factory = authorization.ImageFactoryProxy(factory,
                                                             self.context)

    def test_default_owner_is_set(self):
        image = self.image_factory.new_image()
        self.assertEqual(TENANT1, image.owner)

    def test_wrong_owner_cannot_be_set(self):
        self.assertRaises(exception.Forbidden,
                          self.image_factory.new_image, owner=TENANT2)

    def test_cannot_set_owner_to_none(self):
        self.assertRaises(exception.Forbidden,
                          self.image_factory.new_image, owner=None)

    def test_admin_can_set_any_owner(self):
        self.context.is_admin = True
        image = self.image_factory.new_image(owner=TENANT2)
        self.assertEqual(TENANT2, image.owner)

    def test_admin_can_set_owner_to_none(self):
        self.context.is_admin = True
        image = self.image_factory.new_image(owner=None)
        self.assertIsNone(image.owner)

    def test_admin_still_gets_default_tenant(self):
        self.context.is_admin = True
        image = self.image_factory.new_image()
        self.assertEqual(TENANT1, image.owner)


class TestImageRepoProxy(utils.BaseTestCase):

    class ImageRepoStub(object):
        def __init__(self, fixtures):
            self.fixtures = fixtures

        def get(self, image_id):
            for f in self.fixtures:
                if f.image_id == image_id:
                    return f
            else:
                raise ValueError(image_id)

        def list(self, *args, **kwargs):
            return self.fixtures

    def setUp(self):
        super(TestImageRepoProxy, self).setUp()
        image_factory = glance.domain.ImageFactory()
        self.fixtures = [
            image_factory.new_image(owner=TENANT1),
            image_factory.new_image(owner=TENANT2, visibility='public'),
            image_factory.new_image(owner=TENANT2),
        ]
        self.context = glance.context.RequestContext(tenant=TENANT1)
        image_repo = self.ImageRepoStub(self.fixtures)
        self.image_repo = authorization.ImageRepoProxy(image_repo,
                                                       self.context)

    def test_get_mutable_image(self):
        image = self.image_repo.get(self.fixtures[0].image_id)
        self.assertEqual(image.image_id, self.fixtures[0].image_id)

    def test_get_immutable_image(self):
        image = self.image_repo.get(self.fixtures[1].image_id)
        self.assertRaises(exception.Forbidden,
                          setattr, image, 'name', 'Vince')

    def test_list(self):
        images = self.image_repo.list()
        self.assertEqual(images[0].image_id, self.fixtures[0].image_id)
        self.assertRaises(exception.Forbidden,
                          setattr, images[1], 'name', 'Wally')
        self.assertRaises(exception.Forbidden,
                          setattr, images[2], 'name', 'Calvin')


class TestImmutableTask(utils.BaseTestCase):
    def setUp(self):
        super(TestImmutableTask, self).setUp()
        task_factory = glance.domain.TaskFactory()
        self.context = glance.context.RequestContext(tenant=TENANT2)
        task_type = 'import'
        owner = TENANT2
        task = task_factory.new_task(task_type, owner)
        self.task = authorization.ImmutableTaskProxy(task)

    def _test_change(self, attr, value):
        self.assertRaises(
            exception.Forbidden,
            setattr,
            self.task,
            attr,
            value
        )
        self.assertRaises(
            exception.Forbidden,
            delattr,
            self.task,
            attr
        )

    def test_change_id(self):
        self._test_change('task_id', UUID2)

    def test_change_type(self):
        self._test_change('type', 'fake')

    def test_change_status(self):
        self._test_change('status', 'success')

    def test_change_owner(self):
        self._test_change('owner', 'fake')

    def test_change_expires_at(self):
        self._test_change('expires_at', 'fake')

    def test_change_created_at(self):
        self._test_change('created_at', 'fake')

    def test_change_updated_at(self):
        self._test_change('updated_at', 'fake')

    def test_begin_processing(self):
        self.assertRaises(
            exception.Forbidden,
            self.task.begin_processing
        )

    def test_succeed(self):
        self.assertRaises(
            exception.Forbidden,
            self.task.succeed,
            'result'
        )

    def test_fail(self):
        self.assertRaises(
            exception.Forbidden,
            self.task.fail,
            'message'
        )


class TestImmutableTaskStub(utils.BaseTestCase):
    def setUp(self):
        super(TestImmutableTaskStub, self).setUp()
        task_factory = glance.domain.TaskFactory()
        self.context = glance.context.RequestContext(tenant=TENANT2)
        task_type = 'import'
        owner = TENANT2
        task = task_factory.new_task(task_type, owner)
        self.task = authorization.ImmutableTaskStubProxy(task)

    def _test_change(self, attr, value):
        self.assertRaises(
            exception.Forbidden,
            setattr,
            self.task,
            attr,
            value
        )
        self.assertRaises(
            exception.Forbidden,
            delattr,
            self.task,
            attr
        )

    def test_change_id(self):
        self._test_change('task_id', UUID2)

    def test_change_type(self):
        self._test_change('type', 'fake')

    def test_change_status(self):
        self._test_change('status', 'success')

    def test_change_owner(self):
        self._test_change('owner', 'fake')

    def test_change_expires_at(self):
        self._test_change('expires_at', 'fake')

    def test_change_created_at(self):
        self._test_change('created_at', 'fake')

    def test_change_updated_at(self):
        self._test_change('updated_at', 'fake')


class TestTaskFactoryProxy(utils.BaseTestCase):
    def setUp(self):
        super(TestTaskFactoryProxy, self).setUp()
        factory = glance.domain.TaskFactory()
        self.context = glance.context.RequestContext(tenant=TENANT1)
        self.context_owner_is_none = glance.context.RequestContext()
        self.task_factory = authorization.TaskFactoryProxy(
            factory,
            self.context
        )
        self.task_type = 'import'
        self.task_input = '{"loc": "fake"}'
        self.owner = 'foo'

        self.request1 = unittest_utils.get_fake_request(tenant=TENANT1)
        self.request2 = unittest_utils.get_fake_request(tenant=TENANT2)

    def test_task_create_default_owner(self):
        owner = self.request1.context.owner
        task = self.task_factory.new_task(task_type=self.task_type,
                                          owner=owner)
        self.assertEqual(TENANT1, task.owner)

    def test_task_create_wrong_owner(self):
        self.assertRaises(exception.Forbidden,
                          self.task_factory.new_task,
                          task_type=self.task_type,
                          task_input=self.task_input,
                          owner=self.owner)

    def test_task_create_owner_as_None(self):
        self.assertRaises(exception.Forbidden,
                          self.task_factory.new_task,
                          task_type=self.task_type,
                          task_input=self.task_input,
                          owner=None)

    def test_task_create_admin_context_owner_as_None(self):
        self.context.is_admin = True
        self.assertRaises(exception.Forbidden,
                          self.task_factory.new_task,
                          task_type=self.task_type,
                          task_input=self.task_input,
                          owner=None)


class TestTaskRepoProxy(utils.BaseTestCase):

    class TaskRepoStub(object):
        def __init__(self, fixtures):
            self.fixtures = fixtures

        def get(self, task_id):
            for f in self.fixtures:
                if f.task_id == task_id:
                    return f
            else:
                raise ValueError(task_id)

    class TaskStubRepoStub(object):
        def __init__(self, fixtures):
            self.fixtures = fixtures

        def list(self, *args, **kwargs):
            return self.fixtures

    def setUp(self):
        super(TestTaskRepoProxy, self).setUp()
        task_factory = glance.domain.TaskFactory()
        task_type = 'import'
        owner = None
        self.fixtures = [
            task_factory.new_task(task_type, owner),
            task_factory.new_task(task_type, owner),
            task_factory.new_task(task_type, owner),
        ]
        self.context = glance.context.RequestContext(tenant=TENANT1)
        task_repo = self.TaskRepoStub(self.fixtures)
        task_stub_repo = self.TaskStubRepoStub(self.fixtures)
        self.task_repo = authorization.TaskRepoProxy(
            task_repo,
            self.context
        )
        self.task_stub_repo = authorization.TaskStubRepoProxy(
            task_stub_repo,
            self.context
        )

    def test_get_mutable_task(self):
        task = self.task_repo.get(self.fixtures[0].task_id)
        self.assertEqual(task.task_id, self.fixtures[0].task_id)

    def test_get_immutable_task(self):
        task_id = self.fixtures[1].task_id
        task = self.task_repo.get(task_id)
        self.assertRaises(exception.Forbidden,
                          setattr, task, 'input', 'foo')

    def test_list(self):
        tasks = self.task_stub_repo.list()
        self.assertEqual(tasks[0].task_id, self.fixtures[0].task_id)
        self.assertRaises(exception.Forbidden,
                          setattr,
                          tasks[1],
                          'owner',
                          'foo')
        self.assertRaises(exception.Forbidden,
                          setattr,
                          tasks[2],
                          'owner',
                          'foo')
