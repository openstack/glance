#    Copyright (c) 2018 RedHat, Inc.
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


class TestRockyExpand01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='rocky_expand01')

    def _pre_upgrade_rocky_expand01(self, engine):
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('os_hidden', images.c)

    def _check_rocky_expand01(self, engine, data):
        # check that after migration, 'os_hidden' column is introduced
        images = db_utils.get_table(engine, 'images')
        self.assertIn('os_hidden', images.c)
        self.assertFalse(images.c.os_hidden.nullable)


class TestRockyExpand01MySQL(
    TestRockyExpand01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture
