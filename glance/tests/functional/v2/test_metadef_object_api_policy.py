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

OBJECT1 = {
    "name": "MyObject",
    "description": "My object for My namespace",
    "properties": {
        "test_property": {
            "title": "test_property",
            "description": "Test property for My object",
            "type": "string"
        },
    }
}

OBJECT2 = {
    "name": "MySecondObject",
    "description": "My object for My namespace",
    "properties": {
        "test_property_2": {
            "title": "test_property_2",
            "description": "Test property for My second object",
            "type": "string"
        },
    }
}

NAME_SPACE1 = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}


class TestMetadefObjectsPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMetadefObjectsPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def load_data(self, create_objects=False):
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        if create_objects:
            namespace = md_resource['namespace']
            path = '/v2/metadefs/namespaces/%s/objects' % namespace
            for obj in [OBJECT1, OBJECT2]:
                md_resource = self._create_metadef_resource(path=path,
                                                            data=obj)
                self.assertEqual(obj['name'], md_resource['name'])

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestMetadefObjectsPolicy, self).start_server()

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

    def test_object_create_basic(self):
        self.start_server()
        # Create namespace
        self.load_data()
        # First make sure create object works with default policy
        path = '/v2/metadefs/namespaces/%s/objects' % NAME_SPACE1['namespace']
        md_resource = self._create_metadef_resource(path=path,
                                                    data=OBJECT1)
        self.assertEqual('MyObject', md_resource['name'])

        # Now disable add_metadef_object permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'add_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_post(path, json=OBJECT2)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_metadef_object': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_post(path, json=OBJECT2)
        # Note for reviewers, this causes our "check get if add fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'add_metadef_object': '@',
            'get_metadef_namespace': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'POST',
                                                      json=OBJECT2)

    def test_object_list_basic(self):
        self.start_server()
        # Create namespace and objects
        self.load_data(create_objects=True)
        # First make sure list object works with default policy
        path = '/v2/metadefs/namespaces/%s/objects' % NAME_SPACE1['namespace']
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(2, len(md_resource['objects']))

        # Now disable get_metadef_objects permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'get_metadef_objects': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_objects': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_get(path)
        # Note for reviewers, this causes our "check get if list fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Now enable get_metadef_objects and disable
        # get_metadef_object permission to make sure that you will get
        # empty list as a response
        self.set_policy_rules({
            'get_metadef_objects': '@',
            'get_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(0, len(md_resource['objects']))

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'get_metadef_objects': '@',
            'get_metadef_object': '@',
            'get_metadef_namespace': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_object_get_basic(self):
        self.start_server()
        # Create namespace and objects
        self.load_data(create_objects=True)
        # First make sure get object works with default policy
        path = '/v2/metadefs/namespaces/%s/objects/%s' % (
            NAME_SPACE1['namespace'], OBJECT1['name'])
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(OBJECT1['name'], md_resource['name'])

        # Now disable get_metadef_object permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'get_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_object': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_get(path)
        # Note for reviewers, this causes our "check get if get fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'get_metadef_object': '@',
            'get_metadef_namespace': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_object_update_basic(self):
        self.start_server()
        # Create namespace and objects
        self.load_data(create_objects=True)
        # First make sure list object works with default policy
        path = '/v2/metadefs/namespaces/%s/objects/%s' % (
            NAME_SPACE1['namespace'], OBJECT1['name'])
        data = {
            "name": OBJECT1['name'],
            "description": "My updated description"
        }
        resp = self.api_put(path, json=data)
        md_resource = resp.json
        self.assertEqual(data['description'], md_resource['description'])

        # Now disable modify_metadef_object permissions and make sure any other
        # attempts fail
        data = {
            "name": OBJECT2['name'],
            "description": "My updated description"
        }
        path = '/v2/metadefs/namespaces/%s/objects/%s' % (
            NAME_SPACE1['namespace'], OBJECT2['name'])
        self.set_policy_rules({
            'modify_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_put(path, json=data)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'modify_metadef_object': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_put(path, json=data)
        # Note for reviewers, this causes our "check get if modify fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'modify_metadef_object': '@',
            'get_metadef_namespace': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'PUT', json=data)

    def test_object_delete_basic(self):
        self.start_server()
        # Create namespace and objects
        self.load_data(create_objects=True)
        # Now ensure you are able to delete the object
        path = '/v2/metadefs/namespaces/%s/objects/%s' % (
            NAME_SPACE1['namespace'], OBJECT1['name'])
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)

        # Verify that object is deleted
        path = "/v2/metadefs/namespaces/%s/objects/%s" % (
            NAME_SPACE1['namespace'], OBJECT1['name'])
        resp = self.api_get(path)
        self.assertEqual(404, resp.status_code)

        # Now disable delete_metadef_object permissions and make sure
        # any other attempts fail
        path = '/v2/metadefs/namespaces/%s/objects/%s' % (
            NAME_SPACE1['namespace'], OBJECT2['name'])
        self.set_policy_rules({
            'delete_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'delete_metadef_object': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_delete(path)
        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'delete_metadef_object': '@',
            'get_metadef_namespace': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')
