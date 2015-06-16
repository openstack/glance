#    Copyright 2014 Rackspace
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

import fixtures

from glance.common import exception
from glance.common import swift_store_utils
from glance.tests.unit import base


class TestSwiftParams(base.IsolatedUnitTest):

    def setUp(self):
        super(TestSwiftParams, self).setUp()
        conf_file = "glance-swift.conf"
        test_dir = self.useFixture(fixtures.TempDir()).path
        self.swift_config_file = self._copy_data_file(conf_file, test_dir)
        self.config(swift_store_config_file=self.swift_config_file)

    def tearDown(self):
        super(TestSwiftParams, self).tearDown()

    def test_multiple_swift_account_enabled(self):
        self.config(swift_store_config_file="glance-swift.conf")
        self.assertTrue(
            swift_store_utils.is_multiple_swift_store_accounts_enabled())

    def test_multiple_swift_account_disabled(self):
        self.config(swift_store_config_file=None)
        self.assertFalse(
            swift_store_utils.is_multiple_swift_store_accounts_enabled())

    def test_swift_config_file_doesnt_exist(self):
        self.config(swift_store_config_file='fake-file.conf')
        self.assertRaises(exception.InvalidSwiftStoreConfiguration,
                          swift_store_utils.SwiftParams)

    def test_swift_config_uses_default_values_multiple_account_disabled(self):
        default_user = 'user_default'
        default_key = 'key_default'
        default_auth_address = 'auth@default.com'
        default_account_reference = 'ref_default'
        confs = {'swift_store_config_file': None,
                 'swift_store_user': default_user,
                 'swift_store_key': default_key,
                 'swift_store_auth_address': default_auth_address,
                 'default_swift_reference': default_account_reference}
        self.config(**confs)
        swift_params = swift_store_utils.SwiftParams().params
        self.assertEqual(1, len(swift_params.keys()))
        self.assertEqual(default_user,
                         swift_params[default_account_reference]['user']
                         )
        self.assertEqual(default_key,
                         swift_params[default_account_reference]['key']
                         )
        self.assertEqual(default_auth_address,
                         swift_params[default_account_reference]
                         ['auth_address']
                         )

    def test_swift_store_config_validates_for_creds_auth_address(self):
        swift_params = swift_store_utils.SwiftParams().params
        self.assertEqual('tenant:user1',
                         swift_params['ref1']['user']
                         )
        self.assertEqual('key1',
                         swift_params['ref1']['key']
                         )
        self.assertEqual('example.com',
                         swift_params['ref1']['auth_address'])
        self.assertEqual('user2',
                         swift_params['ref2']['user'])
        self.assertEqual('key2',
                         swift_params['ref2']['key'])
        self.assertEqual('http://example.com',
                         swift_params['ref2']['auth_address']
                         )
