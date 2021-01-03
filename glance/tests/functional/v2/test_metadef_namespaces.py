# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import http.client as http

from oslo_serialization import jsonutils
import requests

from glance.tests.functional.v2 import metadef_base


class TestNamespaces(metadef_base.MetadefFunctionalTestBase):

    def setUp(self):
        super(TestNamespaces, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def test_namespace_lifecycle(self):
        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a namespace
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        namespace_name = 'MyNamespace'
        data = jsonutils.dumps({
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description"
        }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        namespace_loc_header = response.headers['Location']

        # Returned namespace should match the created namespace with default
        # values of visibility=private, protected=False and owner=Context
        # Tenant
        namespace = jsonutils.loads(response.text)
        checked_keys = set([
            'namespace',
            'display_name',
            'description',
            'visibility',
            'self',
            'schema',
            'protected',
            'owner',
            'created_at',
            'updated_at'
        ])
        self.assertEqual(set(namespace.keys()), checked_keys)
        expected_namespace = {
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description",
            "visibility": "private",
            "protected": False,
            "owner": self.tenant1,
            "self": "/v2/metadefs/namespaces/%s" % namespace_name,
            "schema": "/v2/schemas/metadefs/namespace"
        }
        for key, value in expected_namespace.items():
            self.assertEqual(namespace[key], value, key)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Get the namespace using the returned Location header
        response = requests.get(namespace_loc_header, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual(namespace_name, namespace['namespace'])
        self.assertNotIn('object', namespace)
        self.assertEqual(self.tenant1, namespace['owner'])
        self.assertEqual('private', namespace['visibility'])
        self.assertFalse(namespace['protected'])

        # The namespace should be mutable
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        namespace_name = "MyNamespace-UPDATED"
        data = jsonutils.dumps(
            {
                "namespace": namespace_name,
                "display_name": "display_name-UPDATED",
                "description": "description-UPDATED",
                "visibility": "private",  # Not changed
                "protected": True,
                "owner": self.tenant2
            }
        )
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned namespace should reflect the changes
        namespace = jsonutils.loads(response.text)
        self.assertEqual('MyNamespace-UPDATED', namespace_name)
        self.assertEqual('display_name-UPDATED', namespace['display_name'])
        self.assertEqual('description-UPDATED', namespace['description'])
        self.assertEqual('private', namespace['visibility'])
        self.assertTrue(namespace['protected'])
        self.assertEqual(self.tenant2, namespace['owner'])

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual('MyNamespace-UPDATED', namespace['namespace'])
        self.assertEqual('display_name-UPDATED', namespace['display_name'])
        self.assertEqual('description-UPDATED', namespace['description'])
        self.assertEqual('private', namespace['visibility'])
        self.assertTrue(namespace['protected'])
        self.assertEqual(self.tenant2, namespace['owner'])

        # Deletion should not work on protected namespaces
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Unprotect namespace for deletion
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        doc = {
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description",
            "visibility": "public",
            "protected": False,
            "owner": self.tenant2
        }
        data = jsonutils.dumps(doc)
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting namespace MyNamespace
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

    def test_metadef_dont_accept_illegal_bodies(self):
        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/bodytest')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a namespace
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        namespace_name = 'bodytest'
        data = jsonutils.dumps({
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description"
        }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Test all the urls that supply data
        data_urls = [
            '/v2/schemas/metadefs/namespace',
            '/v2/schemas/metadefs/namespaces',
            '/v2/schemas/metadefs/resource_type',
            '/v2/schemas/metadefs/resource_types',
            '/v2/schemas/metadefs/property',
            '/v2/schemas/metadefs/properties',
            '/v2/schemas/metadefs/object',
            '/v2/schemas/metadefs/objects',
            '/v2/schemas/metadefs/tag',
            '/v2/schemas/metadefs/tags',
            '/v2/metadefs/resource_types',
        ]
        for value in data_urls:
            path = self._url(value)
            data = jsonutils.dumps(["body"])
            response = requests.get(path, headers=self._headers(), data=data)
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Put the namespace into the url
        test_urls = [
            ('/v2/metadefs/namespaces/%s/resource_types', 'get'),
            ('/v2/metadefs/namespaces/%s/resource_types/type', 'delete'),
            ('/v2/metadefs/namespaces/%s', 'get'),
            ('/v2/metadefs/namespaces/%s', 'delete'),
            ('/v2/metadefs/namespaces/%s/objects/name', 'get'),
            ('/v2/metadefs/namespaces/%s/objects/name', 'delete'),
            ('/v2/metadefs/namespaces/%s/properties', 'get'),
            ('/v2/metadefs/namespaces/%s/tags/test', 'get'),
            ('/v2/metadefs/namespaces/%s/tags/test', 'post'),
            ('/v2/metadefs/namespaces/%s/tags/test', 'delete'),
        ]

        for link, method in test_urls:
            path = self._url(link % namespace_name)
            data = jsonutils.dumps(["body"])
            response = getattr(requests, method)(
                path, headers=self._headers(), data=data)
            self.assertEqual(http.BAD_REQUEST, response.status_code)

    def _update_namespace(self, path, headers, data):
        # The namespace should be mutable
        response = requests.put(path, headers=headers, json=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned namespace should reflect the changes
        namespace = response.json()
        expected_namespace = {
            "namespace": data['namespace'],
            "display_name": data['display_name'],
            "description": data['description'],
            "visibility": data['visibility'],
            "protected": True,
            "owner": data['owner'],
            "self": "/v2/metadefs/namespaces/%s" % data['namespace'],
            "schema": "/v2/schemas/metadefs/namespace"
        }
        namespace.pop('created_at')
        namespace.pop('updated_at')
        self.assertEqual(namespace, expected_namespace)

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s' % namespace['namespace'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = response.json()
        namespace.pop('created_at')
        namespace.pop('updated_at')
        self.assertEqual(namespace, expected_namespace)

        return namespace

    def test_role_based_namespace_lifecycle(self):
        # Create public and private namespaces for tenant1 and tenant2
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        tenant_namespaces = dict()
        for tenant in [self.tenant1, self.tenant2]:
            headers['X-Tenant-Id'] = tenant
            for visibility in ['public', 'private']:
                namespace_data = {
                    "namespace": "%s_%s_namespace" % (tenant, visibility),
                    "display_name": "My User Friendly Namespace",
                    "description": "My description",
                    "visibility": visibility,
                    "owner": tenant
                }
                namespace = self.create_namespace(path, headers,
                                                  namespace_data)
                self.assertNamespacesEqual(namespace, namespace_data)
                tenant_namespaces.setdefault(tenant, list())
                tenant_namespaces[tenant].append(namespace)

        # Check Tenant 1 and Tenant 2 will be able to see total 3 namespaces
        # (two of own and 1 public of other tenant)
        def _get_expected_namespaces(tenant):
            expected_namespaces = []
            for x in tenant_namespaces[tenant]:
                expected_namespaces.append(x['namespace'])
            if tenant == self.tenant1:
                expected_namespaces.append(
                    tenant_namespaces[self.tenant2][0]['namespace'])
            else:
                expected_namespaces.append(
                    tenant_namespaces[self.tenant1][0]['namespace'])

            return expected_namespaces

        # Check Tenant 1 and Tenant 2 will be able to see total 3 namespaces
        # (two of own and 1 public of other tenant)
        for tenant in [self.tenant1, self.tenant2]:
            path = self._url('/v2/metadefs/namespaces')
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            response = requests.get(path, headers=headers)
            self.assertEqual(http.OK, response.status_code)
            namespaces = response.json()['namespaces']
            expected_namespaces = _get_expected_namespaces(tenant)
            self.assertEqual(sorted(x['namespace'] for x in namespaces),
                             sorted(expected_namespaces))

        def _check_namespace_access(namespaces, tenant):
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for namespace in namespaces:
                path = self._url(
                    '/v2/metadefs/namespaces/%s' % namespace['namespace'])
                headers = headers
                response = requests.get(path, headers=headers)
                if namespace['visibility'] == 'public':
                    self.assertEqual(http.OK, response.status_code)
                else:
                    self.assertEqual(http.NOT_FOUND, response.status_code)

        # Check Tenant 1 can access public namespace and cannot access private
        # namespace of Tenant 2
        _check_namespace_access(tenant_namespaces[self.tenant2],
                                self.tenant1)

        # Check Tenant 2 can access public namespace and cannot access private
        # namespace of Tenant 1
        _check_namespace_access(tenant_namespaces[self.tenant1],
                                self.tenant2)

        total_ns = tenant_namespaces[self.tenant1] \
            + tenant_namespaces[self.tenant2]
        for namespace in total_ns:
            data = {
                "namespace": namespace['namespace'],
                "display_name": "display_name-UPDATED",
                "description": "description-UPDATED",
                "visibility": namespace['visibility'],  # Not changed
                "protected": True,  # changed
                "owner": namespace["owner"]  # Not changed
            }
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            headers = self._headers({
                'X-Tenant-Id': namespace['owner'],
            })
            # Update namespace should fail with non admin role
            headers['X-Roles'] = "reader,member"
            response = requests.put(path, headers=headers, json=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Should work with admin role
            headers['X-Roles'] = "admin"
            namespace = self._update_namespace(path, headers, data)

            # Deletion should fail as namespaces are protected now
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            headers['X-Roles'] = "admin"
            response = requests.delete(path, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Deletion should not be allowed for non admin roles
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            response = requests.delete(
                path, headers=self._headers({
                    'X-Roles': 'reader,member',
                    'X-Tenant-Id': namespace['owner']
                }))
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Unprotect the namespaces before deletion
        headers = self._headers()
        for namespace in total_ns:
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            headers = headers
            data = {
                "namespace": namespace['namespace'],
                "protected": False,
            }
            response = requests.put(path, headers=headers, json=data)
            self.assertEqual(http.OK, response.status_code)

        # Get updated namespace set again
        path = self._url('/v2/metadefs/namespaces')
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        self.assertFalse(namespace['protected'])
        namespaces = response.json()['namespaces']

        # Verify that deletion is not allowed for unprotected namespaces with
        # non admin role
        for namespace in namespaces:
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            response = requests.delete(
                path, headers=self._headers({
                    'X-Roles': 'reader,member',
                    'X-Tenant-Id': namespace['owner']
                }))
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete namespaces of all tenants
        for namespace in total_ns:
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            response = requests.delete(path, headers=headers)
            self.assertEqual(http.NO_CONTENT, response.status_code)

            # Deleted namespace should not be returned
            path = self._url(
                '/v2/metadefs/namespaces/%s' % namespace['namespace'])
            response = requests.get(path, headers=headers)
            self.assertEqual(http.NOT_FOUND, response.status_code)
