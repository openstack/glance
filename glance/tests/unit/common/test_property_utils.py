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

import webob.exc

from glance.common import property_utils
from glance.tests import utils

CONFIG_SECTIONS = [
    '^x_owner_.*',
    'spl_create_prop',
    'spl_read_prop',
    'spl_read_only_prop',
    'spl_update_prop',
    'spl_update_only_prop',
    'spl_delete_prop',
    '.*'
]


class TestPropertyRules(utils.BaseTestCase):

    def setUp(self):
        super(TestPropertyRules, self).setUp()
        self.set_property_protections()

    def tearDown(self):
        for section in property_utils.CONFIG.sections():
            property_utils.CONFIG.remove_section(section)
        super(TestPropertyRules, self).tearDown()

    def test_is_property_protections_enabled_true(self):
        self.config(property_protection_file="property-protections.conf")
        self.assertTrue(property_utils.is_property_protection_enabled())

    def test_is_property_protections_enabled_false(self):
        self.config(property_protection_file=None)
        self.assertFalse(property_utils.is_property_protection_enabled())

    def test_property_protection_file_doesnt_exist(self):
        self.config(property_protection_file='fake-file.conf')
        self.assertRaises(webob.exc.HTTPInternalServerError,
                          property_utils.PropertyRules)

    def test_property_protection_with_malformed_rule(self):
        malformed_rules = {'^[0-9)': {'create': ['fake-role'],
                                      'read': ['fake-role'],
                                      'update': ['fake-role'],
                                      'delete': ['fake-role']}}
        self.set_property_protection_rules(malformed_rules)
        self.assertRaises(webob.exc.HTTPInternalServerError,
                          property_utils.PropertyRules)

    def test_property_protection_with_missing_operation(self):
        rules_with_missing_operation = {'^[0-9]': {'create': ['fake-role'],
                                                   'update': ['fake-role'],
                                                   'delete': ['fake-role']}}
        self.set_property_protection_rules(rules_with_missing_operation)
        self.assertRaises(webob.exc.HTTPInternalServerError,
                          property_utils.PropertyRules)

    def test_property_protection_with_misspelt_operation(self):
        rules_with_misspelt_operation = {'^[0-9]': {'create': ['fake-role'],
                                                    'rade': ['fake-role'],
                                                    'update': ['fake-role'],
                                                    'delete': ['fake-role']}}
        self.set_property_protection_rules(rules_with_misspelt_operation)
        self.assertRaises(webob.exc.HTTPInternalServerError,
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
                        'read', ['member']))
        self.assertTrue(self.rules_checker.check_property_rules('test_prop_1',
                        'read', ['fake-role']))

    def test_check_property_rules_invalid_action(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'hall', ['admin']))

    def test_check_property_rules_read_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'read', ['admin']))

    def test_check_property_rules_read_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'read', ['member']))

    def test_check_property_rules_read_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'read', ['member']))

    def test_check_property_rules_create_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'create', ['admin']))

    def test_check_property_rules_create_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'create', ['member']))

    def test_check_property_rules_create_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'create', ['member']))

    def test_check_property_rules_update_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'update', ['admin']))

    def test_check_property_rules_update_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'update', ['member']))

    def test_check_property_rules_update_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'update', ['member']))

    def test_check_property_rules_delete_permitted_admin_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules('test_prop',
                        'delete', ['admin']))

    def test_check_property_rules_delete_permitted_specific_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertTrue(self.rules_checker.check_property_rules(
                        'x_owner_prop', 'delete', ['member']))

    def test_check_property_rules_delete_unpermitted_role(self):
        self.rules_checker = property_utils.PropertyRules()
        self.assertFalse(self.rules_checker.check_property_rules('test_prop',
                         'delete', ['member']))

    def test_property_config_loaded_in_order(self):
        """
        Verify the order of loaded config sections matches that from the
        configuration file
        """
        self.rules_checker = property_utils.PropertyRules()
        self.assertEqual(property_utils.CONFIG.sections(), CONFIG_SECTIONS)

    def test_property_rules_loaded_in_order(self):
        """
        Verify rules are iterable in the same order as read from the config
        file
        """
        self.rules_checker = property_utils.PropertyRules()
        for i in xrange(len(property_utils.CONFIG.sections())):
            self.assertEqual(property_utils.CONFIG.sections()[i],
                             self.rules_checker.rules[i][0].pattern)
