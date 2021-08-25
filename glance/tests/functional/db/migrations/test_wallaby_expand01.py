#    Copyright (c) 2021 RedHat, Inc.
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


class TestWallabyExpand01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='wallaby_expand01')

    def _pre_upgrade_wallaby_expand01(self, engine):
        tasks = db_utils.get_table(engine, 'tasks')
        self.assertNotIn('image_id', tasks.c)
        self.assertNotIn('request_id', tasks.c)
        self.assertNotIn('user_id', tasks.c)
        self.assertFalse(db_utils.index_exists(engine, 'tasks',
                                               'ix_tasks_image_id'))

    def _check_wallaby_expand01(self, engine, data):
        # check that after migration, 'image_id', 'request_id', 'user'
        # columns are added
        tasks = db_utils.get_table(engine, 'tasks')
        self.assertIn('image_id', tasks.c)
        self.assertIn('request_id', tasks.c)
        self.assertIn('user_id', tasks.c)
        self.assertTrue(tasks.c.image_id.nullable)
        self.assertTrue(tasks.c.request_id.nullable)
        self.assertTrue(tasks.c.user_id.nullable)
        self.assertTrue(db_utils.index_exists(engine, 'tasks',
                                              'ix_tasks_image_id'),
                        'Index %s on table %s does not exist' %
                        ('ix_tasks_image_id', 'tasks'))


class TestWallabyExpand01MySQL(
    TestWallabyExpand01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture
