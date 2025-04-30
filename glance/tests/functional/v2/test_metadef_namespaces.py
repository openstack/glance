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

from glance.tests.functional.v2 import metadef_base


class TestNamespaces(metadef_base.MetadefFunctionalTestBase):

    def setUp(self):
        super(TestNamespaces, self).setUp()
        self.start_server(enable_cache=False)

    def test_namespace_lifecycle(self):
        # Namespace should not exist
        path = '/v2/metadefs/namespaces/MyNamespace'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a namespace
        path = '/v2/metadefs/namespaces'
        headers = self._headers({'content-type': 'application/json'})
        namespace_name = 'MyNamespace'
        data = {
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description"
        }
        response = self.api_post(path, headers=headers, json=data)
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
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Get the namespace using the returned Location header
        response = self.api_get(namespace_loc_header, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual(namespace_name, namespace['namespace'])
        self.assertNotIn('object', namespace)
        self.assertEqual(self.tenant1, namespace['owner'])
        self.assertEqual('private', namespace['visibility'])
        self.assertFalse(namespace['protected'])

        # The namespace should be mutable
        path = '/v2/metadefs/namespaces/%s' % namespace_name
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        namespace_name = "MyNamespace-UPDATED"
        data = {
            "namespace": namespace_name,
            "display_name": "display_name-UPDATED",
            "description": "description-UPDATED",
            "visibility": "private",  # Not changed
            "protected": True,
            "owner": self.tenant2
        }
        response = self.api_put(path, headers=headers, json=data)
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
        path = '/v2/metadefs/namespaces/%s' % namespace_name
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual('MyNamespace-UPDATED', namespace['namespace'])
        self.assertEqual('display_name-UPDATED', namespace['display_name'])
        self.assertEqual('description-UPDATED', namespace['description'])
        self.assertEqual('private', namespace['visibility'])
        self.assertTrue(namespace['protected'])
        self.assertEqual(self.tenant2, namespace['owner'])

        # Deletion should not work on protected namespaces
        path = '/v2/metadefs/namespaces/%s' % namespace_name
        response = self.api_delete(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Unprotect namespace for deletion
        path = '/v2/metadefs/namespaces/%s' % namespace_name
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
        response = self.api_put(path, headers=headers, json=doc)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting namespace MyNamespace
        path = '/v2/metadefs/namespaces/%s' % namespace_name
        response = self.api_delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Namespace should not exist
        path = '/v2/metadefs/namespaces/MyNamespace'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

    def _update_namespace(self, path, headers, data):
        # The namespace should be mutable
        response = self.api_put(path, headers=headers, json=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned namespace should reflect the changes
        namespace = jsonutils.loads(response.text)
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
        path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        namespace = jsonutils.loads(response.text)
        namespace.pop('created_at')
        namespace.pop('updated_at')
        self.assertEqual(namespace, expected_namespace)

        return namespace

    def test_role_based_namespace_lifecycle(self):
        # Create public and private namespaces for tenant1 and tenant2
        path = '/v2/metadefs/namespaces'
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
                namespace = jsonutils.loads(namespace.text)
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
            path = '/v2/metadefs/namespaces'
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            response = self.api_get(path, headers=headers)
            self.assertEqual(http.OK, response.status_code)
            namespaces = jsonutils.loads(response.text)['namespaces']
            expected_namespaces = _get_expected_namespaces(tenant)
            self.assertEqual(sorted(x['namespace'] for x in namespaces),
                             sorted(expected_namespaces))

        def _check_namespace_access(namespaces, tenant):
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for namespace in namespaces:
                path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
                response = self.api_get(path, headers=headers)
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
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            headers = self._headers({
                'X-Tenant-Id': namespace['owner'],
            })
            # Update namespace should fail with non admin role
            headers['X-Roles'] = "reader,member"
            response = self.api_put(path, headers=headers, json=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Should work with admin role
            headers['X-Roles'] = "admin"
            namespace = self._update_namespace(path, headers, data)

            # Deletion should fail as namespaces are protected now
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            headers['X-Roles'] = "admin"
            response = self.api_delete(path, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Deletion should not be allowed for non admin roles
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            response = self.api_delete(
                path, headers=self._headers({
                    'X-Roles': 'reader,member',
                    'X-Tenant-Id': namespace['owner']
                }))
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Unprotect the namespaces before deletion
        headers = self._headers()
        for namespace in total_ns:
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            data = {
                "namespace": namespace['namespace'],
                "protected": False,
            }
            response = self.api_put(path, headers=headers, json=data)
            self.assertEqual(http.OK, response.status_code)

        # Get updated namespace set again
        path = '/v2/metadefs/namespaces'
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        self.assertFalse(namespace['protected'])
        namespaces = jsonutils.loads(response.text)['namespaces']

        # Verify that deletion is not allowed for unprotected namespaces with
        # non admin role
        for namespace in namespaces:
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            response = self.api_delete(
                path, headers=self._headers({
                    'X-Roles': 'reader,member',
                    'X-Tenant-Id': namespace['owner']
                }))
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete namespaces of all tenants
        for namespace in total_ns:
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            response = self.api_delete(path, headers=headers)
            self.assertEqual(http.NO_CONTENT, response.status_code)

            # Deleted namespace should not be returned
            path = '/v2/metadefs/namespaces/%s' % namespace['namespace']
            response = self.api_get(path, headers=headers)
            self.assertEqual(http.NOT_FOUND, response.status_code)
