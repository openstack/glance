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

from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids
import requests
from six.moves import http_client as http

from glance.tests import functional

TENANT1 = uuids.owner1
TENANT2 = uuids.owner2


class TestMetadefTags(functional.FunctionalTest):

    def setUp(self):
        super(TestMetadefTags, self).setUp()
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

    def test_metadata_tags_lifecycle(self):
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
            "owner": "The Test Owner"}
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Metadata tag should not exist
        metadata_tag_name = "tag1"
        path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                         (namespace_name, metadata_tag_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create the metadata tag
        headers = self._headers({'content-type': 'application/json'})
        response = requests.post(path, headers=headers)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the metadata tag created above
        response = requests.get(path,
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        metadata_tag = jsonutils.loads(response.text)
        self.assertEqual(metadata_tag_name, metadata_tag['name'])

        # Returned tag should match the created tag
        metadata_tag = jsonutils.loads(response.text)
        checked_keys = set([
            u'name',
            u'created_at',
            u'updated_at'
        ])
        self.assertEqual(checked_keys, set(metadata_tag.keys()))
        expected_metadata_tag = {
            "name": metadata_tag_name
        }

        # Simple key values
        checked_values = set([
            u'name'
        ])
        for key, value in expected_metadata_tag.items():
            if(key in checked_values):
                self.assertEqual(metadata_tag[key], value, key)

        # Try to create a duplicate metadata tag
        headers = self._headers({'content-type': 'application/json'})
        response = requests.post(path, headers=headers)
        self.assertEqual(http.CONFLICT, response.status_code)

        # The metadata_tag should be mutable
        path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                         (namespace_name, metadata_tag_name))
        media_type = 'application/json'
        headers = self._headers({'content-type': media_type})
        metadata_tag_name = "tag1-UPDATED"
        data = jsonutils.dumps(
            {
                "name": metadata_tag_name
            }
        )
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned metadata_tag should reflect the changes
        metadata_tag = jsonutils.loads(response.text)
        self.assertEqual('tag1-UPDATED', metadata_tag['name'])

        # Updates should persist across requests
        path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                         (namespace_name, metadata_tag_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual('tag1-UPDATED', metadata_tag['name'])

        # Deletion of metadata_tag_name
        path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                         (namespace_name, metadata_tag_name))
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # metadata_tag_name should not exist
        path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                         (namespace_name, metadata_tag_name))
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create multiple tags.
        path = self._url('/v2/metadefs/namespaces/%s/tags' %
                         (namespace_name))
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps(
            {"tags": [{"name": "tag1"}, {"name": "tag2"}, {"name": "tag3"}]}
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # List out the three new tags.
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(3, len(tags))

        # Attempt to create bogus duplicate tag4
        data = jsonutils.dumps(
            {"tags": [{"name": "tag4"}, {"name": "tag5"}, {"name": "tag4"}]}
        )
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code)

        # Verify the previous 3 still exist
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(3, len(tags))

    def _create_namespace(self, path, headers, data):
        response = requests.post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        return response.json()

    def _create_tags(self, namespaces):
        tags = []
        for namespace in namespaces:
            headers = self._headers({'X-Tenant-Id': namespace['owner']})
            tag_name = "tag_of_%s" % (namespace['namespace'])
            path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                             (namespace['namespace'], tag_name))
            response = requests.post(path, headers=headers)
            self.assertEqual(http.CREATED, response.status_code)
            tag_metadata = response.json()
            metadef_tags = dict()
            metadef_tags[namespace['namespace']] = tag_metadata['name']
            tags.append(metadef_tags)

        return tags

    def _update_tags(self, path, headers, data):
        # The tag should be mutable
        response = requests.put(path, headers=headers, json=data)
        self.assertEqual(http.OK, response.status_code, response.text)
        # Returned metadata_tag should reflect the changes
        metadata_tag = response.json()
        self.assertEqual(data['name'], metadata_tag['name'])

        # Updates should persist across requests
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(data['name'], metadata_tag['name'])

    def test_role_base_metadata_tags_lifecycle(self):
        # Create public and private namespaces for tenant1 and tenant2
        path = self._url('/v2/metadefs/namespaces')
        headers = self._headers({'content-type': 'application/json'})
        tenant1_namespaces = []
        tenant2_namespaces = []
        for tenant in [TENANT1, TENANT2]:
            headers['X-Tenant-Id'] = tenant
            for visibility in ['public', 'private']:
                data = {
                    "namespace": "%s_%s_namespace" % (tenant, visibility),
                    "display_name": "My User Friendly Namespace",
                    "description": "My description",
                    "visibility": visibility,
                    "owner": tenant
                }
                namespace = self._create_namespace(path, headers, data)
                if tenant == TENANT1:
                    tenant1_namespaces.append(namespace)
                else:
                    tenant2_namespaces.append(namespace)

        # Create a metadef tags for each namespace created above
        tenant1_tags = self._create_tags(tenant1_namespaces)
        tenant2_tags = self._create_tags(tenant2_namespaces)

        def _check_tag_access(tags, tenant):
            headers = self._headers({'content-type': 'application/json',
                                     'X-Tenant-Id': tenant,
                                     'X-Roles': 'reader,member'})
            for tag in tags:
                for namespace, tag_name in tag.items():
                    path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                                     (namespace, tag_name))
                    response = requests.get(path, headers=headers)
                    if namespace.split('_')[1] == 'public':
                        expected = http.OK
                    else:
                        expected = http.NOT_FOUND

                    # Make sure we can see all public and own private tags,
                    # but not the private tags of other tenant's
                    self.assertEqual(expected, response.status_code)

                    # Make sure the same holds for listing
                    path = self._url(
                        '/v2/metadefs/namespaces/%s/tags' % namespace)
                    response = requests.get(path, headers=headers)
                    self.assertEqual(expected, response.status_code)
                    if expected == http.OK:
                        resp_props = response.json()['tags']
                        self.assertEqual(
                            sorted(tag.values()),
                            sorted([x['name']
                                    for x in resp_props]))

        # Check Tenant 1 can access tags of all public namespace
        # and cannot access tags of private namespace of Tenant 2
        _check_tag_access(tenant2_tags, TENANT1)

        # Check Tenant 2 can access tags of public namespace and
        # cannot access tags of private namespace of Tenant 1
        _check_tag_access(tenant1_tags, TENANT2)

        # Update tags with admin and non admin role
        total_tags = tenant1_tags + tenant2_tags
        for tag in total_tags:
            for namespace, tag_name in tag.items():
                data = {
                    "name": tag_name}
                path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                                 (namespace, tag_name))

                # Update tag should fail with non admin role
                headers['X-Roles'] = "reader,member"
                response = requests.put(path, headers=headers, json=data)
                self.assertEqual(http.FORBIDDEN, response.status_code)

                # Should work with admin role
                headers = self._headers({
                    'X-Tenant-Id': namespace.split('_')[0]})
                self._update_tags(path, headers, data)

        # Delete tags should not be allowed to non admin role
        for tag in total_tags:
            for namespace, tag_name in tag.items():
                path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                                 (namespace, tag_name))
                response = requests.delete(
                    path, headers=self._headers({
                        'X-Roles': 'reader,member',
                        'X-Tenant-Id': namespace.split('_')[0]
                    }))
                self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete all metadef tags
        headers = self._headers()
        for tag in total_tags:
            for namespace, tag_name in tag.items():
                path = self._url('/v2/metadefs/namespaces/%s/tags/%s' %
                                 (namespace, tag_name))
                response = requests.delete(path, headers=headers)
                self.assertEqual(http.NO_CONTENT, response.status_code)

                # Deleted tags should not be exist
                response = requests.get(path, headers=headers)
                self.assertEqual(http.NOT_FOUND, response.status_code)

        # Create multiple tags should not be allowed to non admin role
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'reader,member'})
        data = {
            "tags": [{"name": "tag1"}, {"name": "tag2"}, {"name": "tag3"}]
        }
        for namespace in tenant1_namespaces:
            path = self._url('/v2/metadefs/namespaces/%s/tags' %
                             (namespace['namespace']))
            response = requests.post(path, headers=headers, json=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Create multiple tags.
        headers = self._headers({'content-type': 'application/json'})
        for namespace in tenant1_namespaces:
            path = self._url('/v2/metadefs/namespaces/%s/tags' %
                             (namespace['namespace']))
            response = requests.post(path, headers=headers, json=data)
            self.assertEqual(http.CREATED, response.status_code)

        # Delete multiple tags should not be allowed with non admin role
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'reader,member'})
        for namespace in tenant1_namespaces:
            path = self._url('/v2/metadefs/namespaces/%s/tags' %
                             (namespace['namespace']))
            response = requests.delete(path, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete multiple tags created above created tags
        headers = self._headers()
        for namespace in tenant1_namespaces:
            path = self._url('/v2/metadefs/namespaces/%s/tags' %
                             (namespace['namespace']))
            response = requests.delete(path, headers=headers)
            self.assertEqual(http.NO_CONTENT, response.status_code)
