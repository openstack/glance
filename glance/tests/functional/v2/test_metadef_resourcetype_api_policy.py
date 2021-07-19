# Copyright 2021 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from unittest import mock

import oslo_policy.policy

from glance.api import policy
from glance.tests import functional


NAME_SPACE1 = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}

RESOURCETYPE_1 = {
    "name": "MyResourceType",
    "prefix": "prefix_",
    "properties_target": "temp"
}

RESOURCETYPE_2 = {
    "name": "MySecondResourceType",
    "prefix": "temp_prefix_",
    "properties_target": "temp_2"
}


class TestMetadefResourceTypesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMetadefResourceTypesPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def load_data(self, create_resourcetypes=False):
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        if create_resourcetypes:
            namespace = md_resource['namespace']
            path = '/v2/metadefs/namespaces/%s/resource_types' % namespace
            for resource in [RESOURCETYPE_1, RESOURCETYPE_2]:
                md_resource = self._create_metadef_resource(path=path,
                                                            data=resource)
                self.assertEqual(resource['name'], md_resource['name'])

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestMetadefResourceTypesPolicy, self).start_server()

    def _verify_forbidden_converted_to_not_found(self, path, method,
                                                 json=None):
        # Note for other reviewers, these tests runs by default using
        # admin role, to test this scenario we need private namespace
        # of current project to be accessed by other projects non-admin
        # user.
        headers = self._headers({
            'X-Tenant-Id': 'fake-tenant-id',
            'X-Roles': 'member',
        })
        resp = self.api_request(method, path, headers=headers, json=json)
        self.assertEqual(404, resp.status_code)

    def test_namespace_resourcetypes_list_basic(self):
        self.start_server()
        # Create namespace and resourcetypes
        self.load_data(create_resourcetypes=True)
        # First make sure list resourcetypes works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/resource_types' % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(2, len(md_resource['resource_type_associations']))

        # Now disable list_metadef_resource_types permissions and make
        # sure any other attempts fail
        self.set_policy_rules({
            'list_metadef_resource_types': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'list_metadef_resource_types': '!',
            'get_metadef_namespace': '!',
        })
        resp = self.api_get(path)
        # Note for reviewers, this causes our "check get if list fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Now enable list_metadef_resource_types and disable
        # get_metadef_resource_type permission to make sure that you will get
        # empty list as a response
        self.set_policy_rules({
            'list_metadef_resource_types': '@',
            'get_metadef_resource_type': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(0, len(md_resource['resource_type_associations']))

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'list_metadef_resource_types': '@',
            'get_metadef_resource_type': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_resourcetypes_list_basic(self):
        self.start_server()
        # Create namespace and resourcetypes
        self.load_data(create_resourcetypes=True)
        # First make sure list resourcetypes works with default policy
        path = '/v2/metadefs/resource_types'
        resp = self.api_get(path)
        md_resource = resp.json
        # NOTE(abhishekk): /v2/metadefs/resource_types returns list which
        # contains all resource_types in a dictionary, so the length will
        # always be 1 here.
        self.assertEqual(1, len(md_resource))

        # Now disable get_metadef_resource_type permissions and make
        # sure any other attempts fail
        self.set_policy_rules({
            'list_metadef_resource_types': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

    def test_resourcetype_create_basic(self):
        self.start_server()
        # Create namespace
        self.load_data()
        # First make sure create resourcetype works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/resource_types' % namespace
        md_resource = self._create_metadef_resource(path=path,
                                                    data=RESOURCETYPE_1)
        self.assertEqual('MyResourceType', md_resource['name'])

        # Now disable add_metadef_resource_type_association permissions
        # and make sure any other attempts fail
        self.set_policy_rules({
            'add_metadef_resource_type_association': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_post(path, json=RESOURCETYPE_2)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_metadef_resource_type_association': '!',
            'get_metadef_namespace': '!',
        })
        resp = self.api_post(path, json=RESOURCETYPE_2)
        # Note for reviewers, this causes our "check get if create fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'add_metadef_resource_type_association': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'POST',
                                                      json=RESOURCETYPE_2)

    def test_object_delete_basic(self):
        self.start_server()
        # Create namespace and objects
        self.load_data(create_resourcetypes=True)
        # Now ensure you are able to delete the resource_types
        path = '/v2/metadefs/namespaces/%s/resource_types/%s' % (
            NAME_SPACE1['namespace'], RESOURCETYPE_1['name'])
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)

        # Verify that resource_type is deleted
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/resource_types' % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        # assert namespace has only one resource type association
        self.assertEqual(1, len(md_resource['resource_type_associations']))
        # assert deleted association is not present in response
        for resource in md_resource['resource_type_associations']:
            self.assertNotEqual(RESOURCETYPE_1['name'], resource['name'])

        # Now disable remove_metadef_resource_type_association permissions
        # and make sure any other attempts fail
        path = '/v2/metadefs/namespaces/%s/resource_types/%s' % (
            NAME_SPACE1['namespace'], RESOURCETYPE_2['name'])
        self.set_policy_rules({
            'remove_metadef_resource_type_association': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'remove_metadef_resource_type_association': '!',
            'get_metadef_namespace': '!',
        })
        resp = self.api_delete(path)
        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'remove_metadef_resource_type_association': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')
