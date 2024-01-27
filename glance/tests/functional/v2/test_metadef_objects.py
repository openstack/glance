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


class TestMetadefObjects(metadef_base.MetadefFunctionalTestBase):

    def setUp(self):
        super(TestMetadefObjects, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def test_metadata_objects_lifecycle(self):
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
        }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Metadata objects should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace/objects/object1')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create a object
        path = self._url('/v2/metadefs/namespaces/MyNamespace/objects')
        headers = self._headers({'content-type': 'application/json'})
        metadata_object_name = "object1"
        data = jsonutils.dumps(
            {
                "name": metadata_object_name,
                "description": "object1 description.",
                "required": [
                    "property1"
                ],
                "properties": {
                    "property1": {
                        "type": "integer",
                        "title": "property1",
                        "description": "property1 description",
                        "operators": ["<all-in>"],
                        "default": 100,
                        "minimum": 100,
                        "maximum": 30000369
                    },
                    "property2": {
                        "type": "string",
                        "title": "property2",
                        "description": "property2 description ",
                        "default": "value2",
                        "minLength": 2,
                        "maxLength": 50
                    }
                }
            }
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Get the metadata object created above
        path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                         (namespace_name, metadata_object_name))
        response = requests.get(path,
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        metadata_object = jsonutils.loads(response.text)
        self.assertEqual("object1", metadata_object['name'])

        # Returned object should match the created object
        metadata_object = jsonutils.loads(response.text)
        checked_keys = set([
            'name',
            'description',
            'properties',
            'required',
            'self',
            'schema',
            'created_at',
            'updated_at'
        ])
        self.assertEqual(set(metadata_object.keys()), checked_keys)
        expected_metadata_object = {
            "name": metadata_object_name,
            "description": "object1 description.",
            "required": [
                "property1"
            ],
            "properties": {
                'property1': {
                    'type': 'integer',
                    "title": "property1",
                    'description': 'property1 description',
                    'operators': ['<all-in>'],
                    'default': 100,
                    'minimum': 100,
                    'maximum': 30000369
                },
                "property2": {
                    "type": "string",
                    "title": "property2",
                    "description": "property2 description ",
                    "default": "value2",
                    "minLength": 2,
                    "maxLength": 50
                }
            },
            "self": "/v2/metadefs/namespaces/%("
                    "namespace)s/objects/%(object)s" %
                    {'namespace': namespace_name,
                     'object': metadata_object_name},
            "schema": "v2/schemas/metadefs/object"
        }

        # Simple key values
        checked_values = set([
            'name',
            'description',
        ])
        for key, value in expected_metadata_object.items():
            if key in checked_values:
                self.assertEqual(metadata_object[key], value, key)
        # Complex key values - properties
        for key, value in (
                expected_metadata_object["properties"]['property2'].items()):
            self.assertEqual(
                metadata_object["properties"]["property2"][key],
                value, key
            )

        # The metadata_object should be mutable
        path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                         (namespace_name, metadata_object_name))
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        metadata_object_name = "object1-UPDATED"
        data = jsonutils.dumps(
            {
                "name": metadata_object_name,
                "description": "desc-UPDATED",
                "required": [
                    "property2"
                ],
                "properties": {
                    'property1': {
                        'type': 'integer',
                        "title": "property1",
                        'description': 'p1 desc-UPDATED',
                        'default': 500,
                        'minimum': 500,
                        'maximum': 1369
                    },
                    "property2": {
                        "type": "string",
                        "title": "property2",
                        "description": "p2 desc-UPDATED",
                        'operators': ['<or>'],
                        "default": "value2-UPDATED",
                        "minLength": 5,
                        "maxLength": 150
                    }
                }
            }
        )
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned metadata_object should reflect the changes
        metadata_object = jsonutils.loads(response.text)
        self.assertEqual('object1-UPDATED', metadata_object['name'])
        self.assertEqual('desc-UPDATED', metadata_object['description'])
        self.assertEqual('property2', metadata_object['required'][0])
        updated_property1 = metadata_object['properties']['property1']
        updated_property2 = metadata_object['properties']['property2']
        self.assertEqual('integer', updated_property1['type'])
        self.assertEqual('p1 desc-UPDATED', updated_property1['description'])
        self.assertEqual('500', updated_property1['default'])
        self.assertEqual(500, updated_property1['minimum'])
        self.assertEqual(1369, updated_property1['maximum'])
        self.assertEqual(['<or>'], updated_property2['operators'])
        self.assertEqual('string', updated_property2['type'])
        self.assertEqual('p2 desc-UPDATED', updated_property2['description'])
        self.assertEqual('value2-UPDATED', updated_property2['default'])
        self.assertEqual(5, updated_property2['minLength'])
        self.assertEqual(150, updated_property2['maxLength'])

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                         (namespace_name, metadata_object_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        self.assertEqual('object1-UPDATED', metadata_object['name'])
        self.assertEqual('desc-UPDATED', metadata_object['description'])
        self.assertEqual('property2', metadata_object['required'][0])
        updated_property1 = metadata_object['properties']['property1']
        updated_property2 = metadata_object['properties']['property2']
        self.assertEqual('integer', updated_property1['type'])
        self.assertEqual('p1 desc-UPDATED', updated_property1['description'])
        self.assertEqual('500', updated_property1['default'])
        self.assertEqual(500, updated_property1['minimum'])
        self.assertEqual(1369, updated_property1['maximum'])
        self.assertEqual(['<or>'], updated_property2['operators'])
        self.assertEqual('string', updated_property2['type'])
        self.assertEqual('p2 desc-UPDATED', updated_property2['description'])
        self.assertEqual('value2-UPDATED', updated_property2['default'])
        self.assertEqual(5, updated_property2['minLength'])
        self.assertEqual(150, updated_property2['maxLength'])

        # Deletion of metadata_object object1
        path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                         (namespace_name, metadata_object_name))
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # metadata_object object1 should not exist
        path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                         (namespace_name, metadata_object_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

    def _create_object(self, namespaces):
        objects = []
        for namespace in namespaces:
            headers = self._headers({'X-Tenant-Id': namespace['owner']})
            data = {
                "name": "object_of_%s" % (namespace['namespace']),
                "description": "object description.",
                "required": [
                    "property1"
                ],
                "properties": {
                    "property1": {
                        "type": "integer",
                        "title": "property1",
                        "description": "property1 description",
                    },
                }
            }
            path = self._url('/v2/metadefs/namespaces/%s/objects' %
                             namespace['namespace'])
            response = requests.post(path, headers=headers, json=data)
            self.assertEqual(http.CREATED, response.status_code)
            obj_metadata = response.json()
            metadef_objects = dict()
            metadef_objects[namespace['namespace']] = obj_metadata['name']
            objects.append(metadef_objects)

        return objects

    def _update_object(self, path, headers, data, namespace):
        response = requests.put(path, headers=headers, json=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        expected_object = {
            'description': data['description'],
            'name': data['name'],
            'properties': data['properties'],
            'required': data['required'],
            'schema': '/v2/schemas/metadefs/object',
            'self': '/v2/metadefs/namespaces/%s/objects/%s' % (namespace,
                                                               data['name'])
        }
        # Returned metadata_object should reflect the changes
        metadata_object = response.json()
        metadata_object.pop('created_at')
        metadata_object.pop('updated_at')
        self.assertEqual(metadata_object, expected_object)

        # Updates should persist across requests
        response = requests.get(path, headers=self._headers())
        metadata_object = response.json()
        metadata_object.pop('created_at')
        metadata_object.pop('updated_at')
        self.assertEqual(metadata_object, expected_object)

    def test_role_base_metadata_objects_lifecycle(self):
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

        # Create a metadef object for each namespace created above
        tenant1_objects = self._create_object(tenant1_namespaces)
        tenant2_objects = self._create_object(tenant2_namespaces)

        def _check_object_access(objects, tenant):
            headers = self._headers({'content-type': 'application/json',
                                     'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for obj in objects:
                for namespace, object_name in obj.items():
                    path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                                     (namespace, object_name))
                    headers = headers
                    response = requests.get(path, headers=headers)
                    if namespace.split('_')[1] == 'public':
                        expected = http.OK
                    else:
                        expected = http.NOT_FOUND

                    self.assertEqual(expected, response.status_code)

                    path = self._url(
                        '/v2/metadefs/namespaces/%s/objects' % namespace)
                    response = requests.get(path, headers=headers)
                    self.assertEqual(expected, response.status_code)
                    if expected == http.OK:
                        resp_objs = response.json()['objects']
                        self.assertEqual(
                            sorted(obj.values()),
                            sorted([x['name'] for x in resp_objs]))

        # Check Tenant 1 can access objects of all public namespace
        # and cannot access object of private namespace of Tenant 2
        _check_object_access(tenant2_objects, self.tenant1)

        # Check Tenant 2 can access objects of public namespace and
        # cannot access objects of private namespace of Tenant 1
        _check_object_access(tenant1_objects, self.tenant2)

        # Update objects with admin and non admin role
        total_objects = tenant1_objects + tenant2_objects
        for obj in total_objects:
            for namespace, object_name in obj.items():
                data = {
                    "name": object_name,
                    "description": "desc-UPDATED",
                    "required": [
                        "property1"
                    ],
                    "properties": {
                        'property1': {
                            'type': 'integer',
                            "title": "property1",
                            'description': 'p1 desc-UPDATED',
                        }
                    }
                }
                # Update object should fail with non admin role
                path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                                 (namespace, object_name))
                headers['X-Roles'] = "reader,member"
                response = requests.put(path, headers=headers, json=data)
                self.assertEqual(http.FORBIDDEN, response.status_code)

                # Should work with admin role
                headers = self._headers({
                    'X-Tenant-Id': namespace.split('_')[0]})
                self._update_object(path, headers, data, namespace)

        # Delete object should not be allowed to non admin role
        for obj in total_objects:
            for namespace, object_name in obj.items():
                path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                                 (namespace, object_name))
                response = requests.delete(
                    path, headers=self._headers({
                        'X-Roles': 'reader,member',
                        'X-Tenant-Id': namespace.split('_')[0]
                    }))
                self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete all metadef objects
        headers = self._headers()
        for obj in total_objects:
            for namespace, object_name in obj.items():
                path = self._url('/v2/metadefs/namespaces/%s/objects/%s' %
                                 (namespace, object_name))
                response = requests.delete(path, headers=headers)
                self.assertEqual(http.NO_CONTENT, response.status_code)

                # Deleted objects should not be exist
                response = requests.get(path, headers=headers)
                self.assertEqual(http.NOT_FOUND, response.status_code)
