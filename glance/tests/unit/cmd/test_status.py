# Copyright 2020 Red Hat, Inc
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
import glance_store
from oslo_config import cfg
from oslo_upgradecheck import upgradecheck

from glance.cmd.status import Checks
from glance.tests import utils as test_utils

CONF = cfg.CONF


class TestUpgradeChecks(test_utils.BaseTestCase):
    def setUp(self):
        super(TestUpgradeChecks, self).setUp()
        glance_store.register_opts(CONF)
        self.checker = Checks()

    def test_sheepdog_removal_no_config(self):
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

    def test_sheepdog_removal_enabled_backends(self):
        self.config(enabled_backends=None)
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(enabled_backends={})
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(enabled_backends={'foo': 'bar'})
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(enabled_backends={'sheepdog': 'foobar'})
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.FAILURE)

    def test_sheepdog_removal_glance_store_stores(self):
        self.config(stores=None, group='glance_store')
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(stores='', group='glance_store')
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(stores='foo', group='glance_store')
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.SUCCESS)

        self.config(stores='sheepdog', group='glance_store')
        self.assertEqual(self.checker._check_sheepdog_store().code,
                         upgradecheck.Code.FAILURE)

    def test_owner_is_tenant_removal(self):
        self.config(owner_is_tenant=True)
        self.assertEqual(self.checker._check_owner_is_tenant().code,
                         upgradecheck.Code.SUCCESS)

        self.config(owner_is_tenant=False)
        self.assertEqual(self.checker._check_owner_is_tenant().code,
                         upgradecheck.Code.FAILURE)
