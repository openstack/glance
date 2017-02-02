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

from glance.tests.functional.db import test_migrations


class TestOcataExpand01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='ocata_expand01')

    def _pre_upgrade_ocata_expand01(self, engine):
        images = db_utils.get_table(engine, 'images')
        now = datetime.datetime.now()
        self.assertIn('is_public', images.c)
        self.assertNotIn('visibility', images.c)
        self.assertFalse(images.c.is_public.nullable)

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

    def _check_ocata_expand01(self, engine, data):
        # check that after migration, 'visibility' column is introduced
        images = db_utils.get_table(engine, 'images')
        self.assertIn('visibility', images.c)
        self.assertIn('is_public', images.c)
        self.assertTrue(images.c.is_public.nullable)
        self.assertTrue(images.c.visibility.nullable)

        # tests visibility set to None for existing images
        rows = (images.select()
                .where(images.c.id.like('%_before_expand'))
                .order_by(images.c.id)
                .execute()
                .fetchall())

        self.assertEqual(2, len(rows))
        # private image first
        self.assertEqual(0, rows[0]['is_public'])
        self.assertEqual('private_id_before_expand', rows[0]['id'])
        self.assertIsNone(rows[0]['visibility'])
        # then public image
        self.assertEqual(1, rows[1]['is_public'])
        self.assertEqual('public_id_before_expand', rows[1]['id'])
        self.assertIsNone(rows[1]['visibility'])

        self._test_trigger_old_to_new(images)
        self._test_trigger_new_to_old(images)

    def _test_trigger_new_to_old(self, images):
        now = datetime.datetime.now()
        # inserting a public image record after expand
        public_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           visibility='public',
                           min_disk=0,
                           min_ram=0,
                           id='public_id_new_to_old')
        images.insert().values(public_temp).execute()

        # inserting a private image record after expand
        shared_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           visibility='private',
                           min_disk=0,
                           min_ram=0,
                           id='private_id_new_to_old')
        images.insert().values(shared_temp).execute()

        # inserting a shared image record after expand
        shared_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           visibility='shared',
                           min_disk=0,
                           min_ram=0,
                           id='shared_id_new_to_old')
        images.insert().values(shared_temp).execute()

        # test visibility is set appropriately by the trigger for new images
        rows = (images.select()
                .where(images.c.id.like('%_new_to_old'))
                .order_by(images.c.id)
                .execute()
                .fetchall())

        self.assertEqual(3, len(rows))
        # private image first
        self.assertEqual(0, rows[0]['is_public'])
        self.assertEqual('private_id_new_to_old', rows[0]['id'])
        self.assertEqual('private', rows[0]['visibility'])
        # then public image
        self.assertEqual(1, rows[1]['is_public'])
        self.assertEqual('public_id_new_to_old', rows[1]['id'])
        self.assertEqual('public', rows[1]['visibility'])
        # then shared image
        self.assertEqual(0, rows[2]['is_public'])
        self.assertEqual('shared_id_new_to_old', rows[2]['id'])
        self.assertEqual('shared', rows[2]['visibility'])

    def _test_trigger_old_to_new(self, images):
        now = datetime.datetime.now()
        # inserting a public image record after expand
        public_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=True,
                           min_disk=0,
                           min_ram=0,
                           id='public_id_old_to_new')
        images.insert().values(public_temp).execute()
        # inserting a private image record after expand
        shared_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=False,
                           min_disk=0,
                           min_ram=0,
                           id='private_id_old_to_new')
        images.insert().values(shared_temp).execute()
        # tests visibility is set appropriately by the trigger for new images
        rows = (images.select()
                .where(images.c.id.like('%_old_to_new'))
                .order_by(images.c.id)
                .execute()
                .fetchall())
        self.assertEqual(2, len(rows))
        # private image first
        self.assertEqual(0, rows[0]['is_public'])
        self.assertEqual('private_id_old_to_new', rows[0]['id'])
        self.assertEqual('shared', rows[0]['visibility'])
        # then public image
        self.assertEqual(1, rows[1]['is_public'])
        self.assertEqual('public_id_old_to_new', rows[1]['id'])
        self.assertEqual('public', rows[1]['visibility'])


class TestOcataExpand01MySQL(TestOcataExpand01Mixin,
                             test_base.MySQLOpportunisticTestCase):
    pass
