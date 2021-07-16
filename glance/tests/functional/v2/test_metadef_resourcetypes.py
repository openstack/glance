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
from six.moves import http_client as http

from glance.tests import functional

TENANT1 = str(uuid.uuid4())


class TestMetadefResourceTypes(functional.FunctionalTest):

    def setUp(self):
        super(TestMetadefResourceTypes, self).setUp()
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
            if(key in checked_values):
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
