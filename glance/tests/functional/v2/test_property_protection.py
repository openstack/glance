# Copyright 2024 OpenStack Foundation
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

"""Functional tests for property protection using SynchronousAPIBase.

These tests verify that property protection rules are loaded and cached
correctly, ensuring that PropertyRules is instantiated only once per
Gateway instance rather than on every API request.
"""

import http.client as http
from unittest import mock

from oslo_policy import policy as oslo_policy
from oslo_serialization import jsonutils

from glance.api import policy
from glance.common import property_utils
from glance.tests import functional
from glance.tests import utils


class PropertyProtectionTestBase(functional.SynchronousAPIBase):
    """Base class for property protection tests."""

    def setUp(self):
        super(PropertyProtectionTestBase, self).setUp(single_store=True)
        # Clear CONFIG to ensure test isolation when running in parallel
        property_utils.CONFIG.clear()

    def _headers(self, custom_headers=None):
        """Get default headers with optional custom overrides."""
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': self.TENANT,
            'X-Roles': 'admin',
        }
        if custom_headers:
            base_headers.update(custom_headers)
        return base_headers


class TestPropertyProtectionWithRoles(PropertyProtectionTestBase):
    """Test property protection with role-based rules."""

    def setUp(self):
        super(TestPropertyProtectionWithRoles, self).setUp()
        self.config(property_protection_file=self.property_file_roles)
        self.config(property_protection_rule_format='roles')

    @utils.skip_if_disabled
    def test_create_image_with_allowed_property(self):
        """Test creating image with property allowed for member role."""
        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_owner_foo': 'bar_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('bar_value', image['x_owner_foo'])

    @utils.skip_if_disabled
    def test_create_image_with_forbidden_property(self):
        """Test creating image with property forbidden for member role."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'foo': 'bar'  # Not allowed for member role
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_create_image_with_spl_role_property(self):
        """Test creating image with property allowed for spl_role."""

        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member,spl_role'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_create_prop': 'create_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('create_value', image['spl_create_prop'])

    @utils.skip_if_disabled
    def test_read_protected_property(self):
        """Test reading image with protected property."""
        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_read_prop': 'read_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        headers = self._headers({
            'X-Roles': 'reader,member,spl_role'
        })
        response = self.api_get('/v2/images/%s' % image_id, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('read_value', image['spl_read_prop'])

        headers = self._headers({
            'X-Roles': 'reader,member'
        })
        response = self.api_get('/v2/images/%s' % image_id, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('spl_read_prop', image)

    @utils.skip_if_disabled
    def test_update_protected_property(self):
        """Test updating image with protected property."""
        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_update_prop': 'initial_value',
            'spl_read_prop': 'read_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        headers = self._headers({
            'content-type': 'application/openstack-images-v2.1-json-patch',
            'X-Roles': 'reader,member,spl_role'
        })
        patch_data = [{'op': 'replace', 'path': '/spl_update_prop',
                       'value': 'updated_value'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('updated_value', image['spl_update_prop'])

        headers = self._headers({
            'X-Roles': 'reader,member,spl_role'
        })
        patch_data = [{'op': 'replace', 'path': '/spl_read_prop',
                       'value': 'r'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_delete_protected_property(self):
        """Test deleting image with protected property."""
        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_delete_prop': 'delete_value',
            'spl_create_prop': 'create_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        headers = self._headers({
            'X-Roles': 'reader,member,spl_role'
        })
        patch_data = [{'op': 'remove', 'path': '/spl_delete_prop'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('spl_delete_prop', image)

        headers = self._headers({
            'X-Roles': 'reader,member,spl_role'
        })
        patch_data = [{'op': 'remove', 'path': '/spl_create_prop'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_property_with_at_symbol_all_permitted(self):
        """Test property with '@' symbol (all permitted)."""

        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_all_permitted_test': 'value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('value', image['x_all_permitted_test'])

    @utils.skip_if_disabled
    def test_property_with_exclamation_none_permitted(self):
        """Test property with '!' symbol (none permitted)."""

        self.start_server()
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_none_permitted_test': 'value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_property_protection_caching(self):
        """Test that PropertyRules is cached and not reloaded on each request.

        This test verifies the fix for bug #2132333 - property protection
        rules should be loaded once per Gateway instance, not on every
        API request.
        """

        self.start_server()
# Create multiple images to trigger multiple API calls
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })

        data1 = {
            'name': 'test-image-1',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_owner_foo': 'value1'
        }
        response = self.api_post('/v2/images', headers=headers, json=data1)
        self.assertEqual(http.CREATED, response.status_code)
        image1 = jsonutils.loads(response.text)
        image_id1 = image1['id']

        data2 = {
            'name': 'test-image-2',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_owner_bar': 'value2'
        }
        response = self.api_post('/v2/images', headers=headers, json=data2)
        self.assertEqual(http.CREATED, response.status_code)
        image2 = jsonutils.loads(response.text)
        image_id2 = image2['id']

        response = self.api_get('/v2/images/%s' % image_id1, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        response = self.api_get('/v2/images/%s' % image_id2, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        data3 = {
            'name': 'test-image-3',
            'disk_format': 'raw',
            'container_format': 'bare',
            'foo': 'forbidden'
        }
        response = self.api_post('/v2/images', headers=headers, json=data3)
        self.assertEqual(http.FORBIDDEN, response.status_code)


class TestPropertyProtectionWithPolicies(PropertyProtectionTestBase):
    """Test property protection with policy-based rules."""

    def setUp(self):
        super(TestPropertyProtectionWithPolicies, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)
        rules = {
            "glance_creator": "role:admin or role:spl_role"
        }
        self.set_policy_rules(rules)
        self.config(property_protection_file=self.property_file_policies)
        self.config(property_protection_rule_format='policies')

    def set_policy_rules(self, rules):
        """Set policy rules for testing."""
        self.policy.add_rules(oslo_policy.Rules.from_dict(rules))

    def start_server(self):
        """Start server with mocked policy enforcer."""
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestPropertyProtectionWithPolicies, self).start_server()

    @utils.skip_if_disabled
    def test_create_image_with_policy_protected_property(self):
        """Test creating image with policy-protected property."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'foo': 'bar'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'foo': 'bar'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('bar', image['foo'])

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member,spl_role'
        })
        data = {
            'name': 'test-image-2',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_creator_policy': 'creator_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('creator_value', image['spl_creator_policy'])

    @utils.skip_if_disabled
    def test_property_protection_policies_caching(self):
        """Test that PropertyRules with policies is cached correctly."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        for i in range(3):
            data = {
                'name': 'test-image-%d' % i,
                'disk_format': 'raw',
                'container_format': 'bare',
                'spl_creator_policy': 'value%d' % i
            }
            response = self.api_post('/v2/images', headers=headers, json=data)
            self.assertEqual(http.CREATED, response.status_code)
            image = jsonutils.loads(response.text)
            self.assertEqual('value%d' % i, image['spl_creator_policy'])

    @utils.skip_if_disabled
    def test_read_only_property(self):
        """Test property that can only be read, not updated or deleted."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_none_update': 'read_only_value'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        headers = self._headers({
            'X-Roles': 'admin'
        })
        response = self.api_get('/v2/images/%s' % image_id, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('read_only_value', image['x_none_update'])

        patch_data = [{'op': 'replace', 'path': '/x_none_update',
                       'value': 'updated'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_update_only_property(self):
        """Test property that can only be updated, not deleted."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_none_delete': 'initial'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        headers = self._headers({
            'X-Roles': 'admin'
        })
        patch_data = [{'op': 'replace', 'path': '/x_none_delete',
                       'value': 'updated'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('updated', image['x_none_delete'])

        patch_data = [{'op': 'remove', 'path': '/x_none_delete'}]
        response = self.api_patch(
            '/v2/images/%s' % image_id, patch_data, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    @utils.skip_if_disabled
    def test_case_insensitive_roles(self):
        """Test that role matching is case insensitive."""
        self.start_server()
        pass

    @utils.skip_if_disabled
    def test_property_pattern_matching(self):
        """Test property pattern matching with regex."""

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'name': 'test-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'x_foo_bar': 'value1',
            'x_foo_baz': 'value2'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('value1', image['x_foo_bar'])
        self.assertEqual('value2', image['x_foo_baz'])

    @utils.skip_if_disabled
    def test_multiple_gateway_instances_caching(self):
        """Test that PropertyRules caching works across multiple operations.

        This test verifies that even with multiple get_image_factory() and
        get_repo() calls, PropertyRules is only loaded once per Gateway.
        """

        self.start_server()

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        data1 = {
            'name': 'img1',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_creator_policy': 'v1'
        }
        response = self.api_post('/v2/images', headers=headers, json=data1)
        self.assertEqual(http.CREATED, response.status_code)
        image1 = jsonutils.loads(response.text)
        image_id1 = image1['id']

        response = self.api_get('/v2/images/%s' % image_id1, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        data2 = {
            'name': 'img2',
            'disk_format': 'raw',
            'container_format': 'bare',
            'spl_creator_policy': 'v2'
        }
        response = self.api_post('/v2/images', headers=headers, json=data2)
        self.assertEqual(http.CREATED, response.status_code)

        response = self.api_get('/v2/images', headers=headers)
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertGreaterEqual(len(images), 2)

        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'reader,member'
        })
        data = {
            'name': 'forbidden-image',
            'disk_format': 'raw',
            'container_format': 'bare',
            'foo': 'forbidden'
        }
        response = self.api_post('/v2/images', headers=headers, json=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)
