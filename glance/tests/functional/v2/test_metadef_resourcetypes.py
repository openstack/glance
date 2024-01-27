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


class TestMetadefResourceTypes(metadef_base.MetadefFunctionalTestBase):

    def setUp(self):
        super(TestMetadefResourceTypes, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def test_metadef_resource_types_lifecycle(self):
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
            "description": "My description",
            "visibility": "public",
            "protected": False,
            "owner": "The Test Owner"
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Resource type should not exist
        path = self._url('/v2/metadefs/namespaces/%s/resource_types' %
                         (namespace_name))
        response = requests.get(path, headers=self._headers())
        metadef_resource_type = jsonutils.loads(response.text)
        self.assertEqual(
            0, len(metadef_resource_type['resource_type_associations']))

        # Create a resource type
        path = self._url('/v2/metadefs/namespaces/MyNamespace/resource_types')
        headers = self._headers({'content-type': 'application/json'})
        metadef_resource_type_name = "resource_type1"
        data = jsonutils.dumps(
            {
                "name": "resource_type1",
                "prefix": "hw_",
                "properties_target": "image",
            }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Get the metadef resource type created above
        path = self._url('/v2/metadefs/namespaces/%s/resource_types' %
                         (namespace_name))
        response = requests.get(path,
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        metadef_resource_type = jsonutils.loads(response.text)
        self.assertEqual(
            "resource_type1",
            metadef_resource_type['resource_type_associations'][0]['name'])

        # Returned resource type should match the created resource type
        resource_type = jsonutils.loads(response.text)
        checked_keys = set([
            u'name',
            u'prefix',
            u'properties_target',
            u'created_at',
            u'updated_at'
        ])
        self.assertEqual(
            set(resource_type['resource_type_associations'][0].keys()),
            checked_keys)
        expected_metadef_resource_types = {
            "name": metadef_resource_type_name,
            "prefix": "hw_",
            "properties_target": "image",
        }

        # Simple key values
        checked_values = set([
            u'name',
            u'prefix',
            u'properties_target',
        ])
        for key, value in expected_metadef_resource_types.items():
            if key in checked_values:
                self.assertEqual(
                    resource_type['resource_type_associations'][0][key],
                    value, key)

        # Deassociate of metadef resource type resource_type1
        path = self._url('/v2/metadefs/namespaces/%s/resource_types/%s' %
                         (namespace_name, metadef_resource_type_name))
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # resource_type1 should not exist
        path = self._url('/v2/metadefs/namespaces/%s/resource_types' %
                         (namespace_name))
        response = requests.get(path, headers=self._headers())
        metadef_resource_type = jsonutils.loads(response.text)
        self.assertEqual(
            0, len(metadef_resource_type['resource_type_associations']))

    def _create_resource_type(self, namespaces):
        resource_types = []
        for namespace in namespaces:
            headers = self._headers({'X-Tenant-Id': namespace['owner']})
            data = {
                "name": "resource_type_of_%s" % (namespace['namespace']),
                "prefix": "hw_",
                "properties_target": "image"
            }
            path = self._url('/v2/metadefs/namespaces/%s/resource_types' %
                             (namespace['namespace']))
            response = requests.post(path, headers=headers, json=data)
            self.assertEqual(http.CREATED, response.status_code)
            rs_type = response.json()
            resource_type = dict()
            resource_type[namespace['namespace']] = rs_type['name']
            resource_types.append(resource_type)

        return resource_types

    def test_role_base_metadef_resource_types_lifecycle(self):
        # Create public and private namespaces for tenant1 and tenant2
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        tenant1_namespaces = []
        tenant2_namespaces = []
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
                if tenant == self.tenant1:
                    tenant1_namespaces.append(namespace)
                else:
                    tenant2_namespaces.append(namespace)

        # Create a resource type for each namespace created above
        tenant1_resource_types = self._create_resource_type(
            tenant1_namespaces)
        tenant2_resource_types = self._create_resource_type(
            tenant2_namespaces)

        def _check_resource_type_access(namespaces, tenant):
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for namespace in namespaces:
                path = self._url('/v2/metadefs/namespaces/%s/resource_types' %
                                 (namespace['namespace']))
                response = requests.get(path, headers=headers)
                if namespace['visibility'] == 'public':
                    self.assertEqual(http.OK, response.status_code)
                else:
                    self.assertEqual(http.NOT_FOUND, response.status_code)

        def _check_resource_types(tenant, total_rs_types):
            # Resource types are visible across tenants for all users
            path = self._url('/v2/metadefs/resource_types')
            headers = self._headers({'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            response = requests.get(path, headers=headers)
            self.assertEqual(http.OK, response.status_code)
            metadef_resource_type = response.json()

            # The resource types list count should be same as the total
            # resource types created across the tenants.
            self.assertEqual(
                sorted(x['name']
                       for x in metadef_resource_type['resource_types']),
                sorted(value for x in total_rs_types
                       for key, value in x.items()))

        # Check Tenant 1 can access resource types of all public namespace
        # and cannot access resource type of private namespace of Tenant 2
        _check_resource_type_access(tenant2_namespaces, self.tenant1)

        # Check Tenant 2 can access public namespace and cannot access private
        # namespace of Tenant 1
        _check_resource_type_access(tenant1_namespaces, self.tenant2)

        # List all resource type irrespective of namespace & tenant are
        # accessible non admin roles
        total_resource_types = tenant1_resource_types + tenant2_resource_types
        _check_resource_types(self.tenant1, total_resource_types)
        _check_resource_types(self.tenant2, total_resource_types)

        # Disassociate resource type should not be allowed to non admin role
        for resource_type in total_resource_types:
            for namespace, rs_type in resource_type.items():
                path = \
                    self._url('/v2/metadefs/namespaces/%s/resource_types/%s' %
                              (namespace, rs_type))
                response = requests.delete(
                    path, headers=self._headers({
                        'X-Roles': 'reader,member',
                        'X-Tenant-Id': namespace.split('_')[0]
                    }))
                self.assertEqual(http.FORBIDDEN, response.status_code)

        # Disassociate of all metadef resource types
        headers = self._headers()
        for resource_type in total_resource_types:
            for namespace, rs_type in resource_type.items():
                path = \
                    self._url('/v2/metadefs/namespaces/%s/resource_types/%s' %
                              (namespace, rs_type))
                response = requests.delete(path, headers=headers)
                self.assertEqual(http.NO_CONTENT, response.status_code)

                # Disassociated resource type should not be exist
                # When the specified resource type is not associated with given
                # namespace then it returns empty list in response instead of
                # raising not found error
                path = self._url(
                    '/v2/metadefs/namespaces/%s/resource_types' % namespace)
                response = requests.get(path, headers=headers)
                metadef_resource_type = response.json()
                self.assertEqual(
                    [], metadef_resource_type['resource_type_associations'])
