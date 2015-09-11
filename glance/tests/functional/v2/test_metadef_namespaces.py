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
TENANT2 = str(uuid.uuid4())


class TestNamespaces(functional.FunctionalTest):

    def setUp(self):
        super(TestNamespaces, self).setUp()
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

    def test_namespace_lifecycle(self):
        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

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
        self.assertEqual(201, response.status_code)
        namespace_loc_header = response.headers['Location']

        # Returned namespace should match the created namespace with default
        # values of visibility=private, protected=False and owner=Context
        # Tenant
        namespace = jsonutils.loads(response.text)
        checked_keys = set([
            u'namespace',
            u'display_name',
            u'description',
            u'visibility',
            u'self',
            u'schema',
            u'protected',
            u'owner',
            u'created_at',
            u'updated_at'
        ])
        self.assertEqual(set(namespace.keys()), checked_keys)
        expected_namespace = {
            "namespace": namespace_name,
            "display_name": "My User Friendly Namespace",
            "description": "My description",
            "visibility": "private",
            "protected": False,
            "owner": TENANT1,
            "self": "/v2/metadefs/namespaces/%s" % namespace_name,
            "schema": "/v2/schemas/metadefs/namespace"
        }
        for key, value in expected_namespace.items():
            self.assertEqual(namespace[key], value, key)

        # Attempt to insert a duplicate
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code)

        # Get the namespace using the returned Location header
        response = requests.get(namespace_loc_header, headers=self._headers())
        self.assertEqual(200, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual(namespace_name, namespace['namespace'])
        self.assertNotIn('object', namespace)
        self.assertEqual(TENANT1, namespace['owner'])
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
                "owner": TENANT2
            }
        )
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned namespace should reflect the changes
        namespace = jsonutils.loads(response.text)
        self.assertEqual('MyNamespace-UPDATED', namespace_name)
        self.assertEqual('display_name-UPDATED', namespace['display_name'])
        self.assertEqual('description-UPDATED', namespace['description'])
        self.assertEqual('private', namespace['visibility'])
        self.assertTrue(namespace['protected'])
        self.assertEqual(TENANT2, namespace['owner'])

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        namespace = jsonutils.loads(response.text)
        self.assertEqual('MyNamespace-UPDATED', namespace['namespace'])
        self.assertEqual('display_name-UPDATED', namespace['display_name'])
        self.assertEqual('description-UPDATED', namespace['description'])
        self.assertEqual('private', namespace['visibility'])
        self.assertTrue(namespace['protected'])
        self.assertEqual(TENANT2, namespace['owner'])

        # Deletion should not work on protected namespaces
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(403, response.status_code)

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
            "owner": TENANT2
        }
        data = jsonutils.dumps(doc)
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Deletion should work. Deleting namespace MyNamespace
        path = self._url('/v2/metadefs/namespaces/%s' % namespace_name)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Namespace should not exist
        path = self._url('/v2/metadefs/namespaces/MyNamespace')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)
