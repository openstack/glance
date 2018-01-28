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


class TestOcataMigrate01Mixin(test_migrations.AlembicMigrationsMixin):

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='ocata_expand01')

    def _pre_upgrade_ocata_expand01(self, engine):
        images = db_utils.get_table(engine, 'images')
        image_members = db_utils.get_table(engine, 'image_members')
        now = datetime.datetime.now()

        # inserting a public image record
        public_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=True,
                           min_disk=0,
                           min_ram=0,
                           id='public_id')
        images.insert().values(public_temp).execute()

        # inserting a non-public image record for 'shared' visibility test
        shared_temp = dict(deleted=False,
                           created_at=now,
                           status='active',
                           is_public=False,
                           min_disk=0,
                           min_ram=0,
                           id='shared_id')
        images.insert().values(shared_temp).execute()

        # inserting a non-public image records for 'private' visibility test
        private_temp = dict(deleted=False,
                            created_at=now,
                            status='active',
                            is_public=False,
                            min_disk=0,
                            min_ram=0,
                            id='private_id_1')
        images.insert().values(private_temp).execute()

        private_temp = dict(deleted=False,
                            created_at=now,
                            status='active',
                            is_public=False,
                            min_disk=0,
                            min_ram=0,
                            id='private_id_2')
        images.insert().values(private_temp).execute()

        # adding an active as well as a deleted image member for checking
        # 'shared' visibility
        temp = dict(deleted=False,
                    created_at=now,
                    image_id='shared_id',
                    member='fake_member_452',
                    can_share=True,
                    id=45)
        image_members.insert().values(temp).execute()

        temp = dict(deleted=True,
                    created_at=now,
                    image_id='shared_id',
                    member='fake_member_453',
                    can_share=True,
                    id=453)
        image_members.insert().values(temp).execute()

        # adding an image member, but marking it deleted,
        # for testing 'private' visibility
        temp = dict(deleted=True,
                    created_at=now,
                    image_id='private_id_2',
                    member='fake_member_451',
                    can_share=True,
                    id=451)
        image_members.insert().values(temp).execute()

        # adding an active image member for the 'public' image,
        # to test it remains public regardless.
        temp = dict(deleted=False,
                    created_at=now,
                    image_id='public_id',
                    member='fake_member_450',
                    can_share=True,
                    id=450)
        image_members.insert().values(temp).execute()

    def _check_ocata_expand01(self, engine, data):
        images = db_utils.get_table(engine, 'images')

        # check that visibility is null for existing images
        rows = (images.select()
                .order_by(images.c.id)
                .execute()
                .fetchall())
        self.assertEqual(4, len(rows))
        for row in rows:
            self.assertIsNone(row['visibility'])

        # run data migrations
        data_migrations.migrate(engine)

        # check that visibility is set appropriately for all images
        rows = (images.select()
                .order_by(images.c.id)
                .execute()
                .fetchall())
        self.assertEqual(4, len(rows))
        # private_id_1 has private visibility
        self.assertEqual('private_id_1', rows[0]['id'])
        # TODO(rosmaita): bug #1745003
        #   self.assertEqual('private', rows[0]['visibility'])
        # private_id_2 has private visibility
        self.assertEqual('private_id_2', rows[1]['id'])
        # TODO(rosmaita): bug #1745003
        #   self.assertEqual('private', rows[1]['visibility'])
        # public_id has public visibility
        self.assertEqual('public_id', rows[2]['id'])
        # TODO(rosmaita): bug #1745003
        #   self.assertEqual('public', rows[2]['visibility'])
        # shared_id has shared visibility
        self.assertEqual('shared_id', rows[3]['id'])
        # TODO(rosmaita): bug #1745003
        #  self.assertEqual('shared', rows[3]['visibility'])


class TestOcataMigrate01MySQL(TestOcataMigrate01Mixin,
                              test_base.MySQLOpportunisticTestCase):
    pass


class TestOcataMigrate01_EmptyDBMixin(test_migrations.AlembicMigrationsMixin):
    """This mixin is used to create an initial glance database and upgrade it
    up to the ocata_expand01 revision.
    """
    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='ocata_expand01')

    def _pre_upgrade_ocata_expand01(self, engine):
        # New/empty database
        pass

    def _check_ocata_expand01(self, engine, data):
        images = db_utils.get_table(engine, 'images')

        # check that there are no rows in the images table
        rows = (images.select()
                .order_by(images.c.id)
                .execute()
                .fetchall())
        self.assertEqual(0, len(rows))

        # run data migrations
        data_migrations.migrate(engine)


class TestOcataMigrate01_EmptyDBMySQL(TestOcataMigrate01_EmptyDBMixin,
                                      test_base.MySQLOpportunisticTestCase):
    """This test runs the Ocata data migrations on an empty databse."""
    pass
