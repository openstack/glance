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


GLOBAL_NAMESPACE_DATA = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description",
    "resource_type_associations": [{
        "name": "MyResourceType",
        "prefix": "prefix_",
        "properties_target": "temp"
    }],
    "objects": [{
        "name": "MyObject",
        "description": "My object for My namespace",
        "properties": {
            "test_property": {
                "title": "test_property",
                "description": "Test property for My object",
                "type": "string"
            },
        }
    }],
    "tags": [{
        "name": "MyTag",
    }],
    "properties": {
        "TestProperty": {
            "title": "MyTestProperty",
            "description": "Test Property for My namespace",
            "type": "string"
        },
    },
}

NAME_SPACE1 = {
    "namespace": "MyNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}

NAME_SPACE2 = {
    "namespace": "MySecondNamespace",
    "display_name": "My User Friendly Namespace",
    "description": "My description"
}


class TestMetadefNamespacesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMetadefNamespacesPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestMetadefNamespacesPolicy, self).start_server()

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

    def test_namespace_list_basic(self):
        self.start_server()
        # First make sure create private namespace works with default policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # First make sure create public namespace works with default policy
        path = '/v2/metadefs/namespaces'
        NAME_SPACE2["visibility"] = 'public'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE2)
        self.assertEqual('MySecondNamespace', md_resource['namespace'])

        # Now make sure 'get_metadef_namespaces' allows user to get all the
        # namespaces
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(2, len(md_resource['namespaces']))

        # Now disable get_metadef_namespaces permissions and make sure any
        # other attempts fail
        self.set_policy_rules({
            'get_metadef_namespaces': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

    def test_namespace_list_with_resource_types(self):
        self.start_server()
        # First make sure create namespace works with default policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=GLOBAL_NAMESPACE_DATA)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # Now make sure 'get_metadef_namespaces' allows user to get all the
        # namespaces with associated resource types
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(1, len(md_resource['namespaces']))
        # Verify that response includes associated resource types as well
        for namespace_obj in md_resource['namespaces']:
            self.assertIn('resource_type_associations', namespace_obj)

        # Now disable list_metadef_resource_types permissions and make sure
        # you get forbidden response
        self.set_policy_rules({
            'get_metadef_namespaces': '@',
            'get_metadef_namespace': '@',
            'list_metadef_resource_types': '!'
        })
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now enable list_metadef_resource_types and  get_metadef_namespaces
        # permissions and disable get_metadef_namespace permission to make sure
        # you will get empty list as a response
        self.set_policy_rules({
            'get_metadef_namespaces': '@',
            'get_metadef_namespace': '!',
            'list_metadef_resource_types': '@'
        })
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual(0, len(md_resource['namespaces']))
        # Verify that response does not includes associated resource types
        for namespace_obj in md_resource['namespaces']:
            self.assertNotIn('resource_type_associations', namespace_obj)

    def test_namespace_create_basic(self):
        self.start_server()
        # First make sure create namespace works with default policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # Now disable add_metadef_namespace permissions and make sure any other
        # attempts fail
        self.set_policy_rules({
            'add_metadef_namespace': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_post(path, json=NAME_SPACE2)
        self.assertEqual(403, resp.status_code)

    def test_namespace_create_with_resource_type_associations(self):
        self.start_server()
        # First make sure you can create namespace and resource type
        # associations with default policy
        path = '/v2/metadefs/namespaces'
        data = {
            "resource_type_associations": [{
                "name": "MyResourceType",
                "prefix": "prefix_",
                "properties_target": "temp"
            }],
        }
        data.update(NAME_SPACE1)
        md_resource = self._create_metadef_resource(path=path,
                                                    data=data)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual(
            'MyResourceType',
            md_resource['resource_type_associations'][0]['name'])

        # Now disable add_metadef_resource_type_association permissions and
        # make sure that even you have permission to create namespace the
        # request will fail
        self.set_policy_rules({
            'add_metadef_resource_type_association': '!',
            'get_metadef_namespace': '@'
        })
        data.update(NAME_SPACE2)
        resp = self.api_post(path, json=data)
        self.assertEqual(403, resp.status_code)

    def test_namespace_create_with_objects(self):
        self.start_server()
        # First make sure you can create namespace and objects
        # with default policy
        path = '/v2/metadefs/namespaces'
        data = {
            "objects": [{
                "name": "MyObject",
                "description": "My object for My namespace",
                "properties": {
                    "test_property": {
                        "title": "test_property",
                        "description": "Test property for My object",
                        "type": "string"
                    },
                }
            }],
        }
        data.update(NAME_SPACE1)
        md_resource = self._create_metadef_resource(path=path,
                                                    data=data)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual(
            'MyObject',
            md_resource['objects'][0]['name'])

        # Now disable add_metadef_object permissions and
        # make sure that even you have permission to create namespace the
        # request will fail
        self.set_policy_rules({
            'add_metadef_object': '!',
            'get_metadef_namespace': '@'
        })
        data.update(NAME_SPACE2)
        resp = self.api_post(path, json=data)
        self.assertEqual(403, resp.status_code)

    def test_namespace_create_with_tags(self):
        self.start_server()
        # First make sure you can create namespace and tags
        # with default policy
        path = '/v2/metadefs/namespaces'
        data = {
            "tags": [{
                "name": "MyTag",
            }],
        }
        data.update(NAME_SPACE1)
        md_resource = self._create_metadef_resource(path=path,
                                                    data=data)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual(
            'MyTag',
            md_resource['tags'][0]['name'])

        # Now disable add_metadef_object permissions and
        # make sure that even you have permission to create namespace the
        # request will fail
        data.update(NAME_SPACE2)
        self.set_policy_rules({
            'add_metadef_tag': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_post(path, json=data)
        self.assertEqual(403, resp.status_code)

    def test_namespace_create_with_properties(self):
        self.start_server()
        # First make sure you can create namespace and properties
        # with default policy
        path = '/v2/metadefs/namespaces'
        data = {
            "properties": {
                "TestProperty": {
                    "title": "MyTestProperty",
                    "description": "Test Property for My namespace",
                    "type": "string"
                },
            }
        }
        data.update(NAME_SPACE1)
        md_resource = self._create_metadef_resource(path=path,
                                                    data=data)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual(
            'MyTestProperty',
            md_resource['properties']['TestProperty']['title'])

        # Now disable add_metadef_property permissions and
        # make sure that even you have permission to create namespace the
        # request will fail
        data.update(NAME_SPACE2)
        self.set_policy_rules({
            'add_metadef_property': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_post(path, json=data)
        self.assertEqual(403, resp.status_code)

    def test_namespace_get_basic(self):
        self.start_server()
        # First make sure create namespace works with default policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=GLOBAL_NAMESPACE_DATA)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # Now make sure get_metadef_namespace will return all associated
        # resources in the response as every policy is open.
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertIn('objects', md_resource)
        self.assertIn('resource_type_associations', md_resource)
        self.assertIn('tags', md_resource)
        self.assertIn('properties', md_resource)

        # Now disable get_metadef_namespace policy to ensure that you are
        # forbidden to fulfill the request and get 404 not found
        self.set_policy_rules({'get_metadef_namespace': '!'})
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(404, resp.status_code)

        # Now try to get the same namespace by different user
        self.set_policy_rules({'get_metadef_namespace': '@'})
        self._verify_forbidden_converted_to_not_found(path, 'GET')

        # Now disable get_metadef_objects policy to ensure that you will
        # get forbidden response
        self.set_policy_rules({
            'get_metadef_objects': '!',
            'get_metadef_namespace': '@',
            'list_metadef_resource_types': '@',
            'get_metadef_properties': '@',
            'get_metadef_tags': '@'
        })
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable list_metadef_resource_types policy to ensure that you
        # will get forbidden response
        self.set_policy_rules({
            'get_metadef_objects': '@',
            'get_metadef_namespace': '@',
            'list_metadef_resource_types': '!',
            'get_metadef_properties': '@',
            'get_metadef_tags': '@'
        })
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable get_metadef_properties policy to ensure that you will
        # ger forbidden response
        self.set_policy_rules({
            'get_metadef_objects': '@',
            'get_metadef_namespace': '@',
            'list_metadef_resource_types': '@',
            'get_metadef_properties': '!',
            'get_metadef_tags': '@'
        })
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

        # Now disable get_metadef_tags policy to ensure that you will
        # get forbidden response
        self.set_policy_rules({
            'get_metadef_objects': '@',
            'get_metadef_namespace': '@',
            'list_metadef_resource_types': '@',
            'get_metadef_properties': '@',
            'get_metadef_tags': '!'
        })
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(403, resp.status_code)

    def test_namespace_update_basic(self):
        self.start_server()
        # First make sure create namespace works with default policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path=path,
                                                    data=NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual('private', md_resource['visibility'])

        # Now ensure you are able to update the namespace
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        data = {
            'visibility': 'public',
            'namespace': md_resource['namespace'],
        }
        resp = self.api_put(path, json=data)
        md_resource = resp.json
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual('public', md_resource['visibility'])

        # Now disable modify_metadef_namespace permissions and make sure
        # any other attempts results in 403 forbidden
        self.set_policy_rules({
            'modify_metadef_namespace': '!',
            'get_metadef_namespace': '@',
        })

        resp = self.api_put(path, json=data)
        self.assertEqual(403, resp.status_code)

        # Now enable modify_metadef_namespace and get_metadef_namespace
        # permissions and make sure modifying non existing results in
        # 404 NotFound
        self.set_policy_rules({
            'modify_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        path = '/v2/metadefs/namespaces/non-existing'
        resp = self.api_put(path, json=data)
        self.assertEqual(404, resp.status_code)

        # Note for reviewers, this causes our "check get if modify fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.set_policy_rules({
            'modify_metadef_namespace': '!',
            'get_metadef_namespace': '!',
        })
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        resp = self.api_put(path, json=data)
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'modify_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        # Reset visibility to private
        # Now ensure you are able to update the namespace
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        data = {
            'visibility': 'private',
            'namespace': md_resource['namespace'],
        }
        resp = self.api_put(path, json=data)
        md_resource = resp.json
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertEqual('private', md_resource['visibility'])

        # Now try to update the same namespace by different user
        self._verify_forbidden_converted_to_not_found(path, 'PUT',
                                                      json=data)

    def test_namespace_delete_basic(self):
        def _create_private_namespace(fn_call, data):
            path = '/v2/metadefs/namespaces'
            return fn_call(path=path, data=data)

        self.start_server()
        # First make sure create namespace works with default policy
        md_resource = _create_private_namespace(
            self._create_metadef_resource, NAME_SPACE1)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # Now ensure you are able to delete the namespace
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)
        # Verify that namespace is deleted
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        self.assertEqual(404, resp.status_code)

        # Now create another namespace to check deletion is not allowed
        md_resource = _create_private_namespace(
            self._create_metadef_resource, NAME_SPACE2)
        self.assertEqual('MySecondNamespace', md_resource['namespace'])

        # Now disable delete_metadef_namespace permissions and make sure
        # any other attempts fail
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now enable both permissions and make sure deleting non
        # exsting namespace returns 404 NotFound
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@'
        })
        path = '/v2/metadefs/namespaces/non-existing'
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '!',
        })
        path = '/v2/metadefs/namespaces/%s' % md_resource['namespace']
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')

    def test_namespace_delete_objects_basic(self):
        self.start_server()
        # First make sure create namespace  and object works with default
        # policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path,
                                                    data=GLOBAL_NAMESPACE_DATA)
        self.assertEqual('MyNamespace', md_resource['namespace'])
        self.assertIn('objects', md_resource)

        # Now ensure you are able to delete the object(s) from namespace
        path = '/v2/metadefs/namespaces/%s/objects' % md_resource['namespace']
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)
        # Verify that object from namespace is deleted but namespace is
        # available
        path = "/v2/metadefs/namespaces/%s" % md_resource['namespace']
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertNotIn('objects', md_resource)
        self.assertEqual('MyNamespace', md_resource['namespace'])

        # Now add another object to the namespace
        path = '/v2/metadefs/namespaces/%s/objects' % md_resource['namespace']
        data = {
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
        md_object = self._create_metadef_resource(path, data=data)
        self.assertEqual('MyObject', md_object['name'])

        # Now disable delete_metadef_namespace permissions and make sure
        # any other attempts to delete objects fails
        path = '/v2/metadefs/namespaces/%s/objects' % md_resource['namespace']
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now enable both permissions and make sure
        # deleting objects for non existing namespace returns 404 Not found
        path = '/v2/metadefs/namespaces/non-existing/objects'
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metaded_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '!',
        })
        path = '/v2/metadefs/namespaces/%s/objects' % md_resource['namespace']
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')

    def test_namespace_delete_properties_basic(self):
        self.start_server()
        # First make sure create namespace  and properties works with default
        # policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path,
                                                    data=GLOBAL_NAMESPACE_DATA)
        namespace = md_resource['namespace']
        self.assertEqual('MyNamespace', namespace)
        self.assertIn('properties', md_resource)

        # Now ensure you are able to delete all properties from namespace
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)
        # Verify that properties from namespace are deleted but namespace is
        # available
        path = "/v2/metadefs/namespaces/%s" % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertNotIn('properties', md_resource)
        self.assertEqual('MyNamespace', namespace)

        # Now add another property to the namespace
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        data = {
            "name": "MyProperty",
            "title": "test_property",
            "description": "Test property for My Namespace",
            "type": "string"
        }
        md_resource = self._create_metadef_resource(path,
                                                    data=data)
        self.assertEqual('MyProperty', md_resource['name'])

        # Now disable delete_metadef_namespace permissions and make sure
        # any other attempts to delete properties fails
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '@',
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now disable both permissions and make sure
        # deleting properties for non existing namespace returns 404 Not found
        path = '/v2/metadefs/namespaces/non-existing/properties'
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '!',
        })
        path = '/v2/metadefs/namespaces/%s/properties' % namespace
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@',
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')

    def test_namespace_delete_tags_basic(self):
        self.start_server()
        # First make sure create namespace  and tags works with default
        # policy
        path = '/v2/metadefs/namespaces'
        md_resource = self._create_metadef_resource(path,
                                                    data=GLOBAL_NAMESPACE_DATA)
        namespace = md_resource['namespace']
        self.assertEqual('MyNamespace', namespace)
        self.assertIn('tags', md_resource)

        # Now ensure you are able to delete all properties from namespace
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        resp = self.api_delete(path)
        self.assertEqual(204, resp.status_code)
        # Verify that tags from namespace are deleted but namespace is
        # available
        path = "/v2/metadefs/namespaces/%s" % namespace
        resp = self.api_get(path)
        md_resource = resp.json
        self.assertNotIn('tags', md_resource)
        self.assertEqual('MyNamespace', namespace)

        # Now add another tag to the namespace
        tag_name = "MyTag"
        path = '/v2/metadefs/namespaces/%s/tags/%s' % (namespace,
                                                       tag_name)
        md_resource = self._create_metadef_resource(path)
        self.assertEqual('MyTag', md_resource['name'])

        # Now disable delete_metadef_namespace permissions and make sure
        # any other attempts to delete tags fails
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now enable delete_metadef_namespace permissions and and disable
        # delete_metadef_tags to make sure
        # any other attempts to delete tags fails
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'delete_metadef_tags': '!',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(403, resp.status_code)

        # Now enable all permissions and make sure deleting tags for
        # non existing namespace will return 404 Not found
        path = '/v2/metadefs/namespaces/non-existing/tags'
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'delete_metadef_tags': '@',
            'get_metadef_namespace': '@'
        })
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Note for reviewers, this causes our "check get if delete fails"
        # logic to return 404 as we expect, but not related to the latest
        # rev that checks the namespace get operation first.
        self.set_policy_rules({
            'delete_metadef_namespace': '!',
            'get_metadef_namespace': '!',
            'delete_metadef_tags': '!'
        })
        path = '/v2/metadefs/namespaces/%s/tags' % namespace
        resp = self.api_delete(path)
        self.assertEqual(404, resp.status_code)

        # Ensure accessing non visible namespace will catch 403 and
        # return 404 to user
        self.set_policy_rules({
            'delete_metadef_namespace': '@',
            'get_metadef_namespace': '@',
            'delete_metadef_tags': '@'
        })
        self._verify_forbidden_converted_to_not_found(path, 'DELETE')
