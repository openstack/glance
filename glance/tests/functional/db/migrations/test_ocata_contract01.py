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


class TestOcataContract01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='ocata_contract01')

    def _pre_upgrade_ocata_contract01(self, engine):
        images = db_utils.get_table(engine, 'images')
        now = datetime.datetime.now()
        self.assertIn('is_public', images.c)
        self.assertIn('visibility', images.c)
        self.assertTrue(images.c.is_public.nullable)
        self.assertTrue(images.c.visibility.nullable)

        # inserting a public image record
        public_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=True,
                           min_disk=0,
                           min_ram=0,
                           id='public_id_before_expand')
        images.insert().values(public_temp).execute()

        # inserting a private image record
        shared_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=False,
                           min_disk=0,
                           min_ram=0,
                           id='private_id_before_expand')
        images.insert().values(shared_temp).execute()

        data_migrations.migrate(engine=engine, release='ocata')

    def _check_ocata_contract01(self, engine, data):
        # check that after contract 'is_public' column is dropped
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('is_public', images.c)
        self.assertIn('visibility', images.c)


class TestOcataContract01MySQL(TestOcataContract01Mixin,
                               test_base.MySQLOpportunisticTestCase):
    pass
