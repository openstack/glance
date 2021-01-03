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


class TestNamespaceProperties(metadef_base.MetadefFunctionalTestBase):

    def setUp(self):
        super(TestNamespaceProperties, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def test_properties_lifecycle(self):
        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a namespace
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        namespace_name = 'MyNamespace'
        resource_type_name = 'MyResourceType'
        resource_type_prefix = 'MyPrefix'
        data = jsonutils.dumps({
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description",
            "visibility": "public",
            "protected": False,
            "owner": "The Test Owner",
            "resource_type_associations": [
                {
                    "name": resource_type_name,
                    "prefix": resource_type_prefix
                }
            ]
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Property1 should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace/properties'
                         '/property1')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a property
        path = self._url('/v2/metadefs/namespaces/MyNamespace/properties')
        headers = self._headers({'content-type': 'application/json'})
        property_name = "property1"
        data = jsonutils.dumps(
            {
                "name": property_name,
                "type": "integer",
                "title": "property1",
                "description": "property1 description",
                "default": 100,
                "minimum": 100,
                "maximum": 30000369,
                "readonly": False,
            }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Get the property created above
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        property_object = jsonutils.loads(response.text)
        self.assertEqual("integer", property_object['type'])
        self.assertEqual("property1", property_object['title'])
        self.assertEqual("property1 description", property_object[
            'description'])
        self.assertEqual('100', property_object['default'])
        self.assertEqual(100, property_object['minimum'])
        self.assertEqual(30000369, property_object['maximum'])

        # Get the property with specific resource type association
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s%s' % (
            namespace_name, property_name, '='.join(['?resource_type',
                                                    resource_type_name])))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Get the property with prefix and specific resource type association
        property_name_with_prefix = ''.join([resource_type_prefix,
                                            property_name])
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s%s' % (
            namespace_name, property_name_with_prefix, '='.join([
                '?resource_type', resource_type_name])))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        property_object = jsonutils.loads(response.text)
        self.assertEqual("integer", property_object['type'])
        self.assertEqual("property1", property_object['title'])
        self.assertEqual("property1 description", property_object[
            'description'])
        self.assertEqual('100', property_object['default'])
        self.assertEqual(100, property_object['minimum'])
        self.assertEqual(30000369, property_object['maximum'])
        self.assertFalse(property_object['readonly'])

        # Returned property should match the created property
        property_object = jsonutils.loads(response.text)
        checked_keys = set([
            'name',
            'type',
            'title',
            'description',
            'default',
            'minimum',
            'maximum',
            'readonly',
        ])
        self.assertEqual(set(property_object.keys()), checked_keys)
        expected_metadata_property = {
            "type": "integer",
            "title": "property1",
            "description": "property1 description",
            "default": '100',
            "minimum": 100,
            "maximum": 30000369,
            "readonly": False,
        }

        for key, value in expected_metadata_property.items():
            self.assertEqual(property_object[key], value, key)

        # The property should be mutable
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        property_name = "property1-UPDATED"
        data = jsonutils.dumps(
            {
                "name": property_name,
                "type": "string",
                "title": "string property",
                "description": "desc-UPDATED",
                "operators": ["<or>"],
                "default": "value-UPDATED",
                "minLength": 5,
                "maxLength": 10,
                "readonly": True,
            }
        )
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned property should reflect the changes
        property_object = jsonutils.loads(response.text)
        self.assertEqual('string', property_object['type'])
        self.assertEqual('desc-UPDATED', property_object['description'])
        self.assertEqual('value-UPDATED', property_object['default'])
        self.assertEqual(["<or>"], property_object['operators'])
        self.assertEqual(5, property_object['minLength'])
        self.assertEqual(10, property_object['maxLength'])
        self.assertTrue(property_object['readonly'])

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual('string', property_object['type'])
        self.assertEqual('desc-UPDATED', property_object['description'])
        self.assertEqual('value-UPDATED', property_object['default'])
        self.assertEqual(["<or>"], property_object['operators'])
        self.assertEqual(5, property_object['minLength'])
        self.assertEqual(10, property_object['maxLength'])

        # Deletion of property property1
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # property1 should not exist
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

    def _create_properties(self, namespaces):
        properties = []
        for namespace in namespaces:
            headers = self._headers({'X-Tenant-Id': namespace['owner']})
            data = {
                "name": "property_of_%s" % (namespace['namespace']),
                "type": "integer",
                "title": "property",
                "description": "property description",
            }
            path = self._url('/v2/metadefs/namespaces/%s/properties' %
                             namespace['namespace'])
            response = requests.post(path, headers=headers, json=data)
            self.assertEqual(http.CREATED, response.status_code)
            prop_metadata = response.json()
            metadef_property = dict()
            metadef_property[namespace['namespace']] = prop_metadata['name']
            properties.append(metadef_property)

        return properties

    def _update_property(self, path, headers, data):
        # The property should be mutable
        response = requests.put(path, headers=headers, json=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned property should reflect the changes
        property_object = response.json()
        self.assertEqual('string', property_object['type'])
        self.assertEqual(data['description'], property_object['description'])

        # Updates should persist across requests
        response = requests.get(path, headers=self._headers())
        self.assertEqual('string', property_object['type'])
        self.assertEqual(data['description'], property_object['description'])

    def test_role_base_metadata_properties_lifecycle(self):
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

        # Create a metadef property for each namespace created above
        tenant1_properties = self._create_properties(tenant1_namespaces)
        tenant2_properties = self._create_properties(tenant2_namespaces)

        def _check_properties_access(properties, tenant):
            headers = self._headers({'content-type': 'application/json',
                                     'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for prop in properties:
                for namespace, property_name in prop.items():
                    path = \
                        self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                                  (namespace, property_name))
                    response = requests.get(path, headers=headers)
                    if namespace.split('_')[1] == 'public':
                        expected = http.OK
                    else:
                        expected = http.NOT_FOUND

                    # Make sure we can see our and public properties, but not
                    # the other tenant's
                    self.assertEqual(expected, response.status_code)

                    # Make sure the same holds for listing
                    path = self._url(
                        '/v2/metadefs/namespaces/%s/properties' % namespace)
                    response = requests.get(path, headers=headers)
                    self.assertEqual(expected, response.status_code)
                    if expected == http.OK:
                        resp_props = response.json()['properties'].values()
                        self.assertEqual(
                            sorted(prop.values()),
                            sorted([x['name']
                                    for x in resp_props]))

        # Check Tenant 1 can access properties of all public namespace
        # and cannot access properties of private namespace of Tenant 2
        _check_properties_access(tenant2_properties, self.tenant1)

        # Check Tenant 2 can access properties of public namespace and
        # cannot access properties of private namespace of Tenant 1
        _check_properties_access(tenant1_properties, self.tenant2)

        # Update properties with admin and non admin role
        total_properties = tenant1_properties + tenant2_properties
        for prop in total_properties:
            for namespace, property_name in prop.items():
                data = {
                    "name": property_name,
                    "type": "string",
                    "title": "string property",
                    "description": "desc-UPDATED",
                }
                path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                                 (namespace, property_name))

                # Update property should fail with non admin role
                headers['X-Roles'] = "reader,member"
                response = requests.put(path, headers=headers, json=data)
                self.assertEqual(http.FORBIDDEN, response.status_code)

                # Should work with admin role
                headers = self._headers({
                    'X-Tenant-Id': namespace.split('_')[0]})
                self._update_property(path, headers, data)

        # Delete property should not be allowed to non admin role
        for prop in total_properties:
            for namespace, property_name in prop.items():
                path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                                 (namespace, property_name))
                response = requests.delete(
                    path, headers=self._headers({
                        'X-Roles': 'reader,member',
                        'X-Tenant-Id': namespace.split('_')[0]
                    }))
                self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete all metadef properties
        headers = self._headers()
        for prop in total_properties:
            for namespace, property_name in prop.items():
                path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                                 (namespace, property_name))
                response = requests.delete(path, headers=headers)
                self.assertEqual(http.NO_CONTENT, response.status_code)

                # Deleted property should not be exist
                response = requests.get(path, headers=headers)
                self.assertEqual(http.NOT_FOUND, response.status_code)
