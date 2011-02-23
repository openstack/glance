# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import os
import unittest

import glance.registry.db.migration as migration_api
import glance.common.config as config


class TestMigrations(unittest.TestCase):
    """Test sqlalchemy-migrate migrations"""

    def setUp(self):
        self.db_path = "glance_test_migration.sqlite"
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        self.options = dict(sql_connection="sqlite:///%s" % self.db_path,
                            verbose=False)
        config.setup_logging(self.options)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_db_sync_downgrade_then_upgrade(self):
        migration_api.db_sync(self.options)

        latest = migration_api.db_version(self.options)

        migration_api.downgrade(self.options, latest - 1)
        cur_version = migration_api.db_version(self.options)
        self.assertEqual(cur_version, latest - 1)

        migration_api.upgrade(self.options, cur_version + 1)
        cur_version = migration_api.db_version(self.options)
        self.assertEqual(cur_version, latest)
