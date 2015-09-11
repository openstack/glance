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

import uuid

from oslo_serialization import jsonutils
import requests

from glance.tests import functional

TENANT1 = str(uuid.uuid4())


class TestNamespaceProperties(functional.FunctionalTest):

    def setUp(self):
        super(TestNamespaceProperties, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_properties_lifecycle(self):
        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

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
        self.assertEqual(201, response.status_code)

        # Property1 should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace/properties'
                         '/property1')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

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
        self.assertEqual(201, response.status_code)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code)

        # Get the property created above
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
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
        self.assertEqual(404, response.status_code)

        # Get the property with prefix and specific resource type association
        property_name_with_prefix = ''.join([resource_type_prefix,
                                            property_name])
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s%s' % (
            namespace_name, property_name_with_prefix, '='.join([
                '?resource_type', resource_type_name])))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
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
            u'name',
            u'type',
            u'title',
            u'description',
            u'default',
            u'minimum',
            u'maximum',
            u'readonly',
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
        self.assertEqual(200, response.status_code, response.text)

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
        self.assertEqual(204, response.status_code)

        # property1 should not exist
        path = self._url('/v2/metadefs/namespaces/%s/properties/%s' %
                         (namespace_name, property_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)
