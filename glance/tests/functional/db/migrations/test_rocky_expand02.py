#    Copyright (c) 2018 Verizon Wireless
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

from oslo_db.sqlalchemy import test_fixtures
from oslo_db.sqlalchemy import utils as db_utils

from glance.tests.functional.db import test_migrations
import glance.tests.utils as test_utils


class TestRockyExpand02Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='rocky_expand02')

    def _pre_upgrade_rocky_expand02(self, engine):
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('os_hash_algo', images.c)
        self.assertNotIn('os_hash_value', images.c)

    def _check_rocky_expand02(self, engine, data):
        images = db_utils.get_table(engine, 'images')
        self.assertIn('os_hash_algo', images.c)
        self.assertTrue(images.c.os_hash_algo.nullable)
        self.assertIn('os_hash_value', images.c)
        self.assertTrue(images.c.os_hash_value.nullable)


class TestRockyExpand02MySQL(
    TestRockyExpand02Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture
