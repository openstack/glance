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

TAG1 = {
    "name": "MyTag"
}

TAG2 = {
    "name": "MySecondTag"
}

NAME_SPACE1 = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}


class TestMetadefTagsPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMetadefTagsPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def load_data(self, create_tags=False):
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        if create_tags:
            namespace = md_resource['namespace']
            for tag in [TAG1, TAG2]:
                path = '/v2/metadefs/namespaces/%s/tags/%s' % (
                    namespace, tag['name'])
                md_resource = self._create_metadef_resource(path=path)
                self.assertEqual(tag['name'], md_resource['name'])

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestMetadefTagsPolicy, self).start_server()

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

    def test_tag_create_basic(self):
        self.start_server()
        # Create namespace
        self.load_data()
        # First make sure create tag works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            namespace, TAG1['name'])
        md_resource = self._create_metadef_resource(path=path)
        self.assertEqual('MyTag', md_resource['name'])

        # Now disable add_metadef_tag permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'add_metadef_tag': '!',
            'get_metadef_namespace': ''
        })
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            namespace, TAG2['name'])
        resp = self.api_post(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_metadef_tag': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_post(path)
        # Note for reviewers, this causes our "check get if add fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'add_metadef_tag': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'POST')

    def test_tags_create_basic(self):
        self.start_server()
        # Create namespace
        self.load_data()
        # First make sure create tags works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        data = {"tags": [TAG1, TAG2]}
        md_resource = self._create_metadef_resource(path=path,
                                                    data=data)
        self.assertEqual(2, len(md_resource['tags']))

        # Now disable add_metadef_tags permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'add_metadef_tags': '!',
            'get_metadef_namespace': ''
        })
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        data = {
            "tags": [{
                "name": "sampe-tag-1"
            }, {
                "name": "sampe-tag-2"
            }]
        }
        resp = self.api_post(path, json=data)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_metadef_tags': '!',
            'get_metadef_namespace': '!'
        })
        resp = self.api_post(path, json=data)
        # Note for reviewers, this causes our "check get if add fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'add_metadef_tags': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'POST',
                                                      json=data)

    def test_tag_list_basic(self):
        self.start_server()
        # Create namespace and tags
        self.load_data(create_tags=True)
        # First make sure list tag works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(2, len(md_resource['tags']))

        # Now disable get_metadef_tags permissions and make sure
        # any other attempts fail
        self.set_policy_rules({
            'get_metadef_tags': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable bot permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_tags': '!',
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
            'get_metadef_tags': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_tag_get_basic(self):
        self.start_server()
        # Create namespace and tags
        self.load_data(create_tags=True)
        # First make sure get tag works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            namespace, TAG1['name'])
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual('MyTag', md_resource['name'])

        # Now disable get_metadef_tag permissions and make sure
        # any other attempts fail
        self.set_policy_rules({
            'get_metadef_tag': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_metadef_tag': '!',
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
            'get_metadef_tag': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'GET')

    def test_tag_update_basic(self):
        self.start_server()
        # Create namespace and tags
        self.load_data(create_tags=True)
        # First make sure modify tag works with default policy
        namespace = NAME_SPACE1['namespace']
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            namespace, TAG1['name'])
        data = {
            'name': "MyTagUpdated"
        }
        resp = self.api_put(path, json=data)
        md_resource = resp.json
        self.assertEqual('MyTagUpdated', md_resource['name'])

        # Now disable modify_metadef_tag permissions and make sure
        # any other attempts fail
        self.set_policy_rules({
            'modify_metadef_tag': '!',
            'get_metadef_namespace': ''
        })
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            namespace, TAG2['name'])
        data = {
            'name': "MySecondTagUpdated"
        }
        resp = self.api_put(path, json=data)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'modify_metadef_tag': '!',
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
            'get_metadef_tag': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'PUT',
                                                      json=data)

    def test_tag_delete_basic(self):
        self.start_server()
        # Create namespace and tags
        self.load_data(create_tags=True)
        # Now ensure you are able to delete the tag
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            NAME_SPACE1['namespace'], TAG1['name'])
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)

        # Verify that property is deleted
        path = "/v2/metadefs/namespaces/%s/tags/%s" % (
            NAME_SPACE1['namespace'], TAG1['name'])
        resp = self.api_get(path)
        self.assertEqual(404, resp.status_code)

        # Now disable delete_metadef_tag permissions and make sure
        # any other attempts fail
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (
            NAME_SPACE1['namespace'], TAG2['name'])
        self.set_policy_rules({
            'delete_metadef_tag': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'delete_metadef_tag': '!',
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
            'delete_metadef_tag': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')

    def test_tags_delete_basic(self):
        self.start_server()
        # Create namespace and tags
        self.load_data(create_tags=True)
        # Now ensure you are able to delete all the tags
        path = '/v2/metadefs/namespaces/%s/tags' % NAME_SPACE1['namespace']
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)

        # Verify that tags are deleted
        path = "/v2/metadefs/namespaces/%s/tags" % NAME_SPACE1['namespace']
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(0, len(md_resource['tags']))

        # Now disable delete_metadef_tags permissions and make sure
        # any other attempts fail
        path = "/v2/metadefs/namespaces/%s/tags" % NAME_SPACE1['namespace']
        self.set_policy_rules({
            'delete_metadef_tags': '!',
            'get_metadef_namespace': ''
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'delete_metadef_tags': '!',
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
            'delete_metadef_tags': '',
            'get_metadef_namespace': ''
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')
