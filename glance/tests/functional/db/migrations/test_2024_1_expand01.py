#    Copyright (c) 2023 RedHat, Inc.
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
import sqlalchemy

from glance.tests.functional.db import test_migrations
import glance.tests.utils as test_utils


class Test2024_1Expand01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='2024_1_expand01')

    def _pre_upgrade_2024_1_expand01(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'node_reference')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'cached_images')

    def _check_2024_1_expand01(self, engine, data):
        # check that after migration, 'node_reference' and 'cached_images'
        # tables are created with expected columns and indexes
        node_reference = db_utils.get_table(engine, 'node_reference')
        self.assertIn('node_reference_id', node_reference.c)
        self.assertIn('node_reference_url', node_reference.c)
        self.assertTrue(db_utils.index_exists(
            engine, 'node_reference',
            'uq_node_reference_node_reference_url'),
            'Index %s on table %s does not exist' %
            ('uq_node_reference_node_reference_url', 'node_reference'))

        cached_images = db_utils.get_table(engine, 'cached_images')
        self.assertIn('id', cached_images.c)
        self.assertIn('image_id', cached_images.c)
        self.assertIn('last_accessed', cached_images.c)
        self.assertIn('last_modified', cached_images.c)
        self.assertIn('size', cached_images.c)
        self.assertIn('hits', cached_images.c)
        self.assertIn('checksum', cached_images.c)
        self.assertIn('node_reference_id', cached_images.c)
        self.assertTrue(db_utils.index_exists(
            engine, 'cached_images',
            'ix_cached_images_image_id_node_reference_id'),
            'Index %s on table %s does not exist' %
            ('ix_cached_images_image_id_node_reference_id', 'cached_images'))


class Test2024_1Expand01MySQL(
    Test2024_1Expand01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture
