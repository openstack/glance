# Copyright 2019 RedHat Inc
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

import datetime

from oslo_db.sqlalchemy import test_base
from oslo_db.sqlalchemy import utils as db_utils

from glance.db.sqlalchemy.alembic_migrations import data_migrations
from glance.tests.functional.db import test_migrations


class TestTrainMigrate01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='train_expand01')

    def _pre_upgrade_train_expand01(self, engine):
        images = db_utils.get_table(engine, 'images')
        image_locations = db_utils.get_table(engine, 'image_locations')
        now = datetime.datetime.now()

        # inserting a public image record
        image_1 = dict(deleted=False,
                       created_at=now,
                       status='active',
                       min_disk=0,
                       min_ram=0,
                       visibility='public',
                       id='image_1')
        images.insert().values(image_1).execute()

        image_2 = dict(deleted=False,
                       created_at=now,
                       status='active',
                       min_disk=0,
                       min_ram=0,
                       visibility='public',
                       id='image_2')
        images.insert().values(image_2).execute()

        # adding records to image_locations tables
        temp = dict(deleted=False,
                    created_at=now,
                    image_id='image_1',
                    value='image_location_1',
                    meta_data='{"backend": "fast"}',
                    id=1)
        image_locations.insert().values(temp).execute()

        temp = dict(deleted=False,
                    created_at=now,
                    image_id='image_2',
                    value='image_location_2',
                    meta_data='{"backend": "cheap"}',
                    id=2)
        image_locations.insert().values(temp).execute()

    def _check_train_expand01(self, engine, data):
        image_locations = db_utils.get_table(engine, 'image_locations')

        # check that meta_data has 'backend' key for existing image_locations
        rows = (image_locations.select()
                .order_by(image_locations.c.id)
                .execute()
                .fetchall())
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn('"backend":', row['meta_data'])

        # run data migrations
        data_migrations.migrate(engine, release='train')

        # check that meta_data has 'backend' key replaced with 'store'
        rows = (image_locations.select()
                .order_by(image_locations.c.id)
                .execute()
                .fetchall())
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertNotIn('"backend":', row['meta_data'])
            self.assertIn('"store":', row['meta_data'])


class TestTrainMigrate01MySQL(TestTrainMigrate01Mixin,
                              test_base.MySQLOpportunisticTestCase):
    pass


class TestTrain01PostgresSQL(TestTrainMigrate01Mixin,
                             test_base.PostgreSQLOpportunisticTestCase):
    pass


class TestTrainMigrate01_EmptyDBMixin(test_migrations.AlembicMigrationsMixin):
    """This mixin is used to create an initial glance database and upgrade it
    up to the train_expand01 revision.
    """
    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='train_expand01')

    def _pre_upgrade_train_expand01(self, engine):
        # New/empty database
        pass

    def _check_train_expand01(self, engine, data):
        images = db_utils.get_table(engine, 'images')

        # check that there are no rows in the images table
        rows = (images.select()
                .order_by(images.c.id)
                .execute()
                .fetchall())
        self.assertEqual(0, len(rows))

        # run data migrations
        data_migrations.migrate(engine)


class TestTrainMigrate01_EmptyDBMySQL(TestTrainMigrate01_EmptyDBMixin,
                                      test_base.MySQLOpportunisticTestCase):
    pass


class TestTrainMigrate01_PySQL(TestTrainMigrate01_EmptyDBMixin,
                               test_base.PostgreSQLOpportunisticTestCase):
    pass
