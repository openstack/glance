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

PROPERTY1 = {
    "name": "MyProperty",
    "title": "My Property",
    "description": "My Property for My Namespace",
    "type": "string"
}

PROPERTY2 = {
    "name": "MySecondProperty",
    "title": "My Second Property",
    "description": "My Second Property for My Namespace",
    "type": "string"
}

NAME_SPACE1 = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}


class TestMetadefPropertiesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMetadefPropertiesPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def load_data(self, create_properties=False):
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        if create_properties:
            namespace = md_resource['namespace']
            path = '/v2/metadefs/namespaces/%s/properties' % namespace
            for prop in [PROPERTY1, PROPERTY2]:
                md_resource = self._create_metadef_resource(path=path,
                                                            data=prop)
                self.assertEqual(prop['name'], md_resource['name'])

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestMetadefPropertiesPolicy, self).start_server()

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

    def test_property_list_basic(self):
        self.start_server()
        # Create namespace and properties
        self.load_data(create_properties=True)
        # First make sure list property works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(2, len(md_resource['properties']))

        # Now disable get_metadef_properties permissions and make sure
        # any other attempts fail
        self.set_policy_rules({
            'get_metadef_properties': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_properties': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_get(path)
        # Note for reviewers, this causes our "check get if list fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'get_metadef_properties': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_property_get_basic(self):
        self.start_server()
        # Create namespace and properties
        self.load_data(create_properties=True)
        # First make sure get property works with default policy
        path = '/v2/metadefs/namespaces/%s/properties/%s' % (
            NAME_SPACE1['namespace'], PROPERTY1['name'])
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(PROPERTY1['name'], md_resource['name'])

        # Now disable get_metadef_property permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'get_metadef_property': '!',
            'get_metadef_namespace': '',
            'get_metadef_resource_type': ''
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable get_metadef_resource_type permissions and make sure
        # any other attempts fail
        self.set_policy_rules({
            'get_metadef_property': '',
            'get_metadef_namespace': '',
            'get_metadef_resource_type': '!'
        })
        url_path = "%s?resource_type='abcd'" % path
        resp = self.api_get(url_path)
        self.assertEqual(403, resp.status_code)

        # Now disable all permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_property': '!',
            'get_metadef_namespace': '!',
            'get_metadef_resource_type': '!'
        })
        resp = self.api_get(path)
        # Note for reviewers, this causes our "check get if get fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'get_metadef_property': '',
            'get_metadef_namespace': '',
            'get_metadef_resource_type': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_property_create_basic(self):
        self.start_server()
        # Create namespace
        self.load_data()
        # First make sure create property works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        md_resource = self._create_metadef_resource(path=path,
                                                    data=PROPERTY1)
        self.assertEqual('MyProperty', md_resource['name'])

        # Now disable add_metadef_property permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'add_metadef_property': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_post(path, json=PROPERTY2)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_metadef_property': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_post(path, json=PROPERTY2)
        # Note for reviewers, this causes our "check get if get fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'add_metadef_property': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'POST',
                                                      json=PROPERTY2)

    def test_property_update_basic(self):
        self.start_server()
        # Create namespace and properties
        self.load_data(create_properties=True)
        # First make sure update property works with default policy
        path = '/v2/metadefs/namespaces/%s/properties/%s' % (
            NAME_SPACE1['namespace'], PROPERTY1['name'])
        data = {
            "name": PROPERTY1['name'],
            "title": PROPERTY1['title'],
            "type": PROPERTY1['type'],
            "description": "My updated description"
        }
        resp = self.api_put(path, json=data)
        md_resource = resp.json
        self.assertEqual(data['description'], md_resource['description'])

        # Now disable modify_metadef_property permissions and make sure
        # any other attempts fail
        data = {
            "name": PROPERTY2['name'],
            "title": PROPERTY2['title'],
            "type": PROPERTY2['type'],
            "description": "My updated description"
        }
        path = '/v2/metadefs/namespaces/%s/properties/%s' % (
            NAME_SPACE1['namespace'], PROPERTY2['name'])
        self.set_policy_rules({
            'modify_metadef_property': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_put(path, json=data)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'modify_metadef_property': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_put(path, json=data)
        # Note for reviewers, this causes our "check get if get fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'modify_metadef_property': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'PUT',
                                                      json=data)

    def test_property_delete_basic(self):
        self.start_server()
        # Create namespace and properties
        self.load_data(create_properties=True)
        # Now ensure you are able to delete the property
        path = '/v2/metadefs/namespaces/%s/properties/%s' % (
            NAME_SPACE1['namespace'], PROPERTY1['name'])
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)

        # Verify that property is deleted
        path = "/v2/metadefs/namespaces/%s/properties/%s" % (
            NAME_SPACE1['namespace'], PROPERTY1['name'])
        resp = self.api_get(path)
        self.assertEqual(404, resp.status_code)

        # Now disable remove_metadef_property permissions and make sure
        # any other attempts fail
        path = '/v2/metadefs/namespaces/%s/properties/%s' % (
            NAME_SPACE1['namespace'], PROPERTY2['name'])
        self.set_policy_rules({
            'remove_metadef_property': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'remove_metadef_property': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_delete(path)
        # Note for reviewers, this causes our "check get if get fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'remove_metadef_property': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')
