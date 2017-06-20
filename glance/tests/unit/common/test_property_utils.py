# Copyright 2013 OpenStack Foundation.
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

# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.api import policy
from glance.common import exception
from glance.common import property_utils
import glance.context
from glance.tests.unit import base

CONFIG_SECTIONS = [
    '^x_owner_.*',
    'spl_create_prop',
    'spl_read_prop',
    'spl_read_only_prop',
    'spl_update_prop',
    'spl_update_only_prop',
    'spl_delete_prop',
    'spl_delete_empty_prop',
    '^x_all_permitted.*',
    '^x_none_permitted.*',
    'x_none_read',
    'x_none_update',
    'x_none_delete',
    'x_case_insensitive',
    'x_foo_matcher',
    'x_foo_*',
    '.*'
]


def create_context(policy, roles=None):
    if roles is None:
        roles = []
    return glance.context.RequestContext(roles=roles,
                                         policy_enforcer=policy)


class TestPropertyRulesWithRoles(base.IsolatedUnitTest):

    def setUp(self):
        super(TestPropertyRulesWithRoles, self).setUp()
        self.set_property_protections()
        self.policy = policy.Enforcer()

    def test_is_property_protections_enabled_true(self):
        self.config(property_protection_file="property-protections.conf")
        self.assertTrue(property_utils.is_property_protection_enabled())

    def test_is_property_protections_enabled_false(self):
        self.config(property_protection_file=None)
        self.assertFalse(property_utils.is_property_protection_enabled())

    def test_property_protection_file_doesnt_exist(self):
        self.config(property_protection_file='fake-file.conf')
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_mutually_exclusive_rule(self):
        exclusive_rules = {'.*': {'create': ['@', '!'],
                                  'read': ['fake-role'],
                                  'update': ['fake-role'],
                                  'delete': ['fake-role']}}
        self.set_property_protection_rules(exclusive_rules)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_malformed_rule(self):
        malformed_rules = {'^[0-9)': {'create': ['fake-role'],
                                      'read': ['fake-role'],
                                      'update': ['fake-role'],
                                      'delete': ['fake-role']}}
        self.set_property_protection_rules(malformed_rules)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_missing_operation(self):
        rules_with_missing_operation = {'^[0-9]': {'create': ['fake-role'],
                                                   'update': ['fake-role'],
                                                   'delete': ['fake-role']}}
        self.set_property_protection_rules(rules_with_missing_operation)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_misspelt_operation(self):
        rules_with_misspelt_operation = {'^[0-9]': {'create': ['fake-role'],
                                                    'rade': ['fake-role'],
                                                    'update': ['fake-role'],
                                                    'delete': ['fake-role']}}
        self.set_property_protection_rules(rules_with_misspelt_operation)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_whitespace(self):
        rules_whitespace = {
            '^test_prop.*': {
                'create': ['member ,fake-role'],
                'read': ['fake-role, member'],
                'update': ['fake-role,  member'],
                'delete': ['fake-role,   member']
            }
        }
        self.set_property_protection_rules(rules_whitespace)
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules('test_prop_1',
                        'read', create_context(self.policy, ['member'])))
        self.assertTrue(self.rules_checker.check_property_rules('test_prop_1',
                        'read', create_context(self.policy, ['fake-role'])))

    def test_check_property_rules_invalid_action(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'hall', create_context(self.policy, ['admin'])))

    def test_check_property_rules_read_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'read', create_context(self.policy, ['admin'])))

    def test_check_property_rules_read_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'read',
                        create_context(self.policy, ['member'])))

    def test_check_property_rules_read_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'read', create_context(self.policy, ['member'])))

    def test_check_property_rules_create_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'create', create_context(self.policy, ['admin'])))

    def test_check_property_rules_create_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'create',
                        create_context(self.policy, ['member'])))

    def test_check_property_rules_create_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'create', create_context(self.policy, ['member'])))

    def test_check_property_rules_update_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'update', create_context(self.policy, ['admin'])))

    def test_check_property_rules_update_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'update',
                        create_context(self.policy, ['member'])))

    def test_check_property_rules_update_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'update', create_context(self.policy, ['member'])))

    def test_check_property_rules_delete_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'delete', create_context(self.policy, ['admin'])))

    def test_check_property_rules_delete_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'delete',
                        create_context(self.policy, ['member'])))

    def test_check_property_rules_delete_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'delete', create_context(self.policy, ['member'])))

    def test_property_config_loaded_in_order(self):
        """
        Verify the order of loaded config sections matches that from the
        configuration file
        """
        self.rules_checker = property_utils.PropertyRules(self.policy)
        self.assertEqual(CONFIG_SECTIONS, property_utils.CONFIG.sections())

    def test_property_rules_loaded_in_order(self):
        """
        Verify rules are iterable in the same order as read from the config
        file
        """
        self.rules_checker = property_utils.PropertyRules(self.policy)
        for i in range(len(property_utils.CONFIG.sections())):
            self.assertEqual(property_utils.CONFIG.sections()[i],
                             self.rules_checker.rules[i][0].pattern)

    def test_check_property_rules_create_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'create', create_context(self.policy, [''])))

    def test_check_property_rules_read_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'read', create_context(self.policy, [''])))

    def test_check_property_rules_update_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'update', create_context(self.policy, [''])))

    def test_check_property_rules_delete_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'delete', create_context(self.policy, [''])))

    def test_check_property_rules_create_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'create', create_context(self.policy, [''])))

    def test_check_property_rules_read_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'read', create_context(self.policy, [''])))

    def test_check_property_rules_update_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'update', create_context(self.policy, [''])))

    def test_check_property_rules_delete_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'delete', create_context(self.policy, [''])))

    def test_check_property_rules_read_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_read', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'read',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'update',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'delete',
            create_context(self.policy, [''])))

    def test_check_property_rules_update_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'read',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_update', 'update',
            create_context(self.policy, [''])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'delete',
            create_context(self.policy, ['admin', 'member'])))

    def test_check_property_rules_delete_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'read',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'update',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_delete', 'delete',
            create_context(self.policy, [''])))

    def test_check_return_first_match(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'create',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'read',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'update',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'delete',
            create_context(self.policy, [''])))

    def test_check_case_insensitive_property_rules(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_case_insensitive', 'create',
            create_context(self.policy, ['member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_case_insensitive', 'read',
            create_context(self.policy, ['member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_case_insensitive', 'update',
            create_context(self.policy, ['member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_case_insensitive', 'delete',
            create_context(self.policy, ['member'])))


class TestPropertyRulesWithPolicies(base.IsolatedUnitTest):

    def setUp(self):
        super(TestPropertyRulesWithPolicies, self).setUp()
        self.set_property_protections(use_policies=True)
        self.policy = policy.Enforcer()
        self.rules_checker = property_utils.PropertyRules(self.policy)

    def test_check_property_rules_create_permitted_specific_policy(self):
        self.assertTrue(self.rules_checker.check_property_rules(
                        'spl_creator_policy', 'create',
                        create_context(self.policy, ['spl_role'])))

    def test_check_property_rules_create_unpermitted_policy(self):
        self.assertFalse(self.rules_checker.check_property_rules(
                         'spl_creator_policy', 'create',
                         create_context(self.policy, ['fake-role'])))

    def test_check_property_rules_read_permitted_specific_policy(self):
        self.assertTrue(self.rules_checker.check_property_rules(
                        'spl_creator_policy', 'read',
                        create_context(self.policy, ['spl_role'])))

    def test_check_property_rules_read_unpermitted_policy(self):
        self.assertFalse(self.rules_checker.check_property_rules(
                         'spl_creator_policy', 'read',
                         create_context(self.policy, ['fake-role'])))

    def test_check_property_rules_update_permitted_specific_policy(self):
        self.assertTrue(self.rules_checker.check_property_rules(
                        'spl_creator_policy', 'update',
                        create_context(self.policy, ['admin'])))

    def test_check_property_rules_update_unpermitted_policy(self):
        self.assertFalse(self.rules_checker.check_property_rules(
                         'spl_creator_policy', 'update',
                         create_context(self.policy, ['fake-role'])))

    def test_check_property_rules_delete_permitted_specific_policy(self):
        self.assertTrue(self.rules_checker.check_property_rules(
                        'spl_creator_policy', 'delete',
                        create_context(self.policy, ['admin'])))

    def test_check_property_rules_delete_unpermitted_policy(self):
        self.assertFalse(self.rules_checker.check_property_rules(
                         'spl_creator_policy', 'delete',
                         create_context(self.policy, ['fake-role'])))

    def test_property_protection_with_malformed_rule(self):
        malformed_rules = {'^[0-9)': {'create': ['fake-policy'],
                                      'read': ['fake-policy'],
                                      'update': ['fake-policy'],
                                      'delete': ['fake-policy']}}
        self.set_property_protection_rules(malformed_rules)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_property_protection_with_multiple_policies(self):
        malformed_rules = {'^x_.*': {'create': ['fake-policy, another_pol'],
                                     'read': ['fake-policy'],
                                     'update': ['fake-policy'],
                                     'delete': ['fake-policy']}}
        self.set_property_protection_rules(malformed_rules)
        self.assertRaises(exception.InvalidPropertyProtectionConfiguration,
                          property_utils.PropertyRules)

    def test_check_property_rules_create_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'create', create_context(self.policy, [''])))

    def test_check_property_rules_read_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'read', create_context(self.policy, [''])))

    def test_check_property_rules_update_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'update', create_context(self.policy, [''])))

    def test_check_property_rules_delete_all_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_all_permitted', 'delete', create_context(self.policy, [''])))

    def test_check_property_rules_create_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'create', create_context(self.policy, [''])))

    def test_check_property_rules_read_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'read', create_context(self.policy, [''])))

    def test_check_property_rules_update_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'update', create_context(self.policy, [''])))

    def test_check_property_rules_delete_none_permitted(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_permitted', 'delete', create_context(self.policy, [''])))

    def test_check_property_rules_read_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_read', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'read',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'update',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_read', 'delete',
            create_context(self.policy, [''])))

    def test_check_property_rules_update_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'read',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_update', 'update',
            create_context(self.policy, [''])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_update', 'delete',
            create_context(self.policy, ['admin', 'member'])))

    def test_check_property_rules_delete_none(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'create',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'read',
            create_context(self.policy, ['admin', 'member'])))
        self.assertTrue(self.rules_checker.check_property_rules(
            'x_none_delete', 'update',
            create_context(self.policy, ['admin', 'member'])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_none_delete', 'delete',
            create_context(self.policy, [''])))

    def test_check_return_first_match(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'create',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'read',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'update',
            create_context(self.policy, [''])))
        self.assertFalse(self.rules_checker.check_property_rules(
            'x_foo_matcher', 'delete',
            create_context(self.policy, [''])))
