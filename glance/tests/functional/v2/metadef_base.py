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

from oslo_utils.fixture import uuidsentinel as uuids
import requests

from glance.tests import functional


class MetadefFunctionalTestBase(functional.FunctionalTest):
    """A basic set of assertions and utilities for testing the metadef API."""

    def setUp(self):
        super().setUp()
        self.tenant1 = uuids.owner1
        self.tenant2 = uuids.owner2

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': self.tenant1,
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def assertNamespacesEqual(self, actual, expected):
        """Assert two namespace dictionaries are the same."""
        actual.pop('created_at', None)
        actual.pop('updated_at', None)
        expected_namespace = {
            "namespace": expected['namespace'],
            "display_name": expected['display_name'],
            "description": expected['description'],
            "visibility": expected['visibility'],
            "protected": False,
            "owner": expected['owner'],
            "self": "/v2/metadefs/namespaces/%s" % expected['namespace'],
            "schema": "/v2/schemas/metadefs/namespace"
        }
        self.assertEqual(actual, expected_namespace)

    def create_namespace(self, path, headers, namespace):
        """Create a metadef namespace.

        :param path: string representing the namespace API path
        :param headers: dictionary with the headers to use for the request
        :param namespace: dictionary representing the namespace to create

        :returns: a dictionary of the namespace in the response
        """
        return requests.post(path, headers=headers, json=namespace).json()
