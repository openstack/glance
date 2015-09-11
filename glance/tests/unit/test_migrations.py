# Copyright 2010-2011 OpenStack Foundation
# All Rights Reserved.
# Copyright 2013 IBM Corp.
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

"""
Tests for database migrations. This test case reads the configuration
file /tests/unit/test_migrations.conf for database connection settings
to use in the tests. For each connection found in the config file,
the test case runs a series of test cases to ensure that migrations work
properly both upgrading and downgrading, and that no data loss occurs
if possible.
"""

from __future__ import print_function

import datetime
import os
import pickle
import uuid

from migrate.versioning import api as migration_api
from migrate.versioning.repository import Repository
from oslo_config import cfg
from oslo_db.sqlalchemy import test_base
from oslo_db.sqlalchemy import test_migrations
from oslo_db.sqlalchemy import utils as db_utils
from oslo_serialization import jsonutils
from oslo_utils import timeutils
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import sqlalchemy
from sqlalchemy import inspect

from glance.common import crypt
from glance.common import exception
from glance.common import utils
from glance.db import migration
from glance.db.sqlalchemy import migrate_repo
from glance.db.sqlalchemy.migrate_repo.schema import from_migration_import
from glance.db.sqlalchemy import models
from glance.db.sqlalchemy import models_artifacts
from glance.db.sqlalchemy import models_metadef

from glance import i18n

_ = i18n._

CONF = cfg.CONF
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


def index_exist(index, table, engine):
    inspector = sqlalchemy.inspect(engine)
    return index in [i['name'] for i in inspector.get_indexes(table)]


def unique_constraint_exist(constraint, table, engine):
    inspector = sqlalchemy.inspect(engine)
    return constraint in [c['name'] for c in
                          inspector.get_unique_constraints(table)]


class MigrationsMixin(test_migrations.WalkVersionsMixin):
    @property
    def INIT_VERSION(self):
        return migration.INIT_VERSION

    @property
    def REPOSITORY(self):
        migrate_file = migrate_repo.__file__
        return Repository(os.path.abspath(os.path.dirname(migrate_file)))

    @property
    def migration_api(self):
        return migration_api

    @property
    def migrate_engine(self):
        return self.engine

    def test_walk_versions(self):
        # No more downgrades
        self._walk_versions(False, False)

    def _create_unversioned_001_db(self, engine):
        # Create the initial version of the images table
        meta = sqlalchemy.schema.MetaData()
        meta.bind = engine
        images_001 = sqlalchemy.Table('images', meta,
                                      sqlalchemy.Column('id', models.Integer,
                                                        primary_key=True),
                                      sqlalchemy.Column('name',
                                                        sqlalchemy.String(255)
                                                        ),
                                      sqlalchemy.Column('type',
                                                        sqlalchemy.String(30)),
                                      sqlalchemy.Column('size',
                                                        sqlalchemy.Integer),
                                      sqlalchemy.Column('status',
                                                        sqlalchemy.String(30)),
                                      sqlalchemy.Column('is_public',
                                                        sqlalchemy.Boolean,
                                                        default=False),
                                      sqlalchemy.Column('location',
                                                        sqlalchemy.Text),
                                      sqlalchemy.Column('created_at',
                                                        sqlalchemy.DateTime(),
                                                        nullable=False),
                                      sqlalchemy.Column('updated_at',
                                                        sqlalchemy.DateTime()),
                                      sqlalchemy.Column('deleted_at',
                                                        sqlalchemy.DateTime()),
                                      sqlalchemy.Column('deleted',
                                                        sqlalchemy.Boolean(),
                                                        nullable=False,
                                                        default=False),
                                      mysql_engine='InnoDB',
                                      mysql_charset='utf8')
        images_001.create()

    def test_version_control_existing_db(self):
        """
        Creates a DB without version control information, places it
        under version control and checks that it can be upgraded
        without errors.
        """
        self._create_unversioned_001_db(self.migrate_engine)

        old_version = migration.INIT_VERSION
        # we must start from version 1
        migration.INIT_VERSION = 1
        self.addCleanup(setattr, migration, 'INIT_VERSION', old_version)

        self._walk_versions(False, False)

    def _pre_upgrade_003(self, engine):
        now = datetime.datetime.now()
        images = db_utils.get_table(engine, 'images')
        data = {'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True}
        images.insert().values(data).execute()
        return data

    def _check_003(self, engine, data):
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('type', images.c,
                         "'type' column found in images table columns! "
                         "images table columns reported by metadata: %s\n"
                         % images.c.keys())
        images_prop = db_utils.get_table(engine, 'image_properties')
        result = images_prop.select().execute()
        types = []
        for row in result:
            if row['key'] == 'type':
                types.append(row['value'])
        self.assertIn(data['type'], types)

    def _pre_upgrade_004(self, engine):
        """Insert checksum data sample to check if migration goes fine with
        data.
        """
        now = timeutils.utcnow()
        images = db_utils.get_table(engine, 'images')
        data = [
            {
                'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True,
            }
        ]
        engine.execute(images.insert(), data)
        return data

    def _check_004(self, engine, data):
        """Assure that checksum data is present on table"""
        images = db_utils.get_table(engine, 'images')
        self.assertIn('checksum', images.c)
        self.assertEqual(32, images.c['checksum'].type.length)

    def _pre_upgrade_005(self, engine):
        now = timeutils.utcnow()
        images = db_utils.get_table(engine, 'images')
        data = [
            {
                'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True,
                # Integer type signed size limit
                'size': 2147483647
            }
        ]
        engine.execute(images.insert(), data)
        return data

    def _check_005(self, engine, data):

        images = db_utils.get_table(engine, 'images')
        select = images.select().execute()

        sizes = [row['size'] for row in select if row['size'] is not None]
        migrated_data_sizes = [element['size'] for element in data]

        for migrated in migrated_data_sizes:
            self.assertIn(migrated, sizes)

    def _pre_upgrade_006(self, engine):
        now = timeutils.utcnow()
        images = db_utils.get_table(engine, 'images')
        image_data = [
            {
                'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True,
                'id': 9999,
            }
        ]
        engine.execute(images.insert(), image_data)

        images_properties = db_utils.get_table(engine, 'image_properties')
        properties_data = [
            {
                'id': 10, 'image_id': 9999, 'updated_at': now,
                'created_at': now, 'deleted': False, 'key': 'image_name'
            }
        ]
        engine.execute(images_properties.insert(), properties_data)
        return properties_data

    def _check_006(self, engine, data):
        images_properties = db_utils.get_table(engine, 'image_properties')
        select = images_properties.select().execute()

        # load names from name collumn
        image_names = [row['name'] for row in select]

        # check names from data in image names from name collumn
        for element in data:
            self.assertIn(element['key'], image_names)

    def _pre_upgrade_010(self, engine):
        """Test rows in images with NULL updated_at get updated to equal
        created_at.
        """

        initial_values = [
            (datetime.datetime(1999, 1, 2, 4, 10, 20),
             datetime.datetime(1999, 1, 2, 4, 10, 30)),
            (datetime.datetime(1999, 2, 4, 6, 15, 25),
             datetime.datetime(1999, 2, 4, 6, 15, 35)),
            (datetime.datetime(1999, 3, 6, 8, 20, 30),
             None),
            (datetime.datetime(1999, 4, 8, 10, 25, 35),
             None),
        ]

        images = db_utils.get_table(engine, 'images')
        for created_at, updated_at in initial_values:
            row = dict(deleted=False,
                       created_at=created_at,
                       updated_at=updated_at,
                       status='active',
                       is_public=True,
                       min_disk=0,
                       min_ram=0)
            images.insert().values(row).execute()

        return initial_values

    def _check_010(self, engine, data):
        values = {c: u for c, u in data}

        images = db_utils.get_table(engine, 'images')
        for row in images.select().execute():
            if row['created_at'] in values:
                # updated_at should be unchanged if not previous NULL, or
                # set to created_at if previously NULL
                updated_at = values.pop(row['created_at']) or row['created_at']
                self.assertEqual(row['updated_at'], updated_at)

        # No initial values should be remaining
        self.assertEqual(0, len(values))

    def _pre_upgrade_012(self, engine):
        """Test rows in images have id changes from int to varchar(32) and
        value changed from int to UUID. Also test image_members and
        image_properties gets updated to point to new UUID keys.
        """

        images = db_utils.get_table(engine, 'images')
        image_members = db_utils.get_table(engine, 'image_members')
        image_properties = db_utils.get_table(engine, 'image_properties')

        # Insert kernel, ramdisk and normal images
        now = timeutils.utcnow()
        data = {'created_at': now, 'updated_at': now,
                'status': 'active', 'deleted': False,
                'is_public': True, 'min_disk': 0, 'min_ram': 0}

        test_data = {}
        for name in ('kernel', 'ramdisk', 'normal'):
            data['name'] = '%s migration 012 test' % name
            result = images.insert().values(data).execute()
            test_data[name] = result.inserted_primary_key[0]

        # Insert image_members and image_properties rows
        data = {'created_at': now, 'updated_at': now, 'deleted': False,
                'image_id': test_data['normal'], 'member': 'foobar',
                'can_share': False}
        result = image_members.insert().values(data).execute()
        test_data['member'] = result.inserted_primary_key[0]

        data = {'created_at': now, 'updated_at': now, 'deleted': False,
                'image_id': test_data['normal'], 'name': 'ramdisk_id',
                'value': test_data['ramdisk']}
        result = image_properties.insert().values(data).execute()
        test_data['properties'] = [result.inserted_primary_key[0]]

        data.update({'name': 'kernel_id', 'value': test_data['kernel']})
        result = image_properties.insert().values(data).execute()
        test_data['properties'].append(result.inserted_primary_key)

        return test_data

    def _check_012(self, engine, test_data):
        images = db_utils.get_table(engine, 'images')
        image_members = db_utils.get_table(engine, 'image_members')
        image_properties = db_utils.get_table(engine, 'image_properties')

        # Find kernel, ramdisk and normal images. Make sure id has been
        # changed to a uuid
        uuids = {}
        for name in ('kernel', 'ramdisk', 'normal'):
            image_name = '%s migration 012 test' % name
            rows = images.select().where(
                images.c.name == image_name).execute().fetchall()

            self.assertEqual(1, len(rows))

            row = rows[0]
            self.assertTrue(utils.is_uuid_like(row['id']))

            uuids[name] = row['id']

        # Find all image_members to ensure image_id has been updated
        results = image_members.select().where(
            image_members.c.image_id == uuids['normal']).execute().fetchall()
        self.assertEqual(1, len(results))

        # Find all image_properties to ensure image_id has been updated
        # as well as ensure kernel_id and ramdisk_id values have been
        # updated too
        results = image_properties.select().where(
            image_properties.c.image_id == uuids['normal']
        ).execute().fetchall()
        self.assertEqual(2, len(results))
        for row in results:
            self.assertIn(row['name'], ('kernel_id', 'ramdisk_id'))

            if row['name'] == 'kernel_id':
                self.assertEqual(row['value'], uuids['kernel'])
            if row['name'] == 'ramdisk_id':
                self.assertEqual(row['value'], uuids['ramdisk'])

    def _post_downgrade_012(self, engine):
        images = db_utils.get_table(engine, 'images')
        image_members = db_utils.get_table(engine, 'image_members')
        image_properties = db_utils.get_table(engine, 'image_properties')

        # Find kernel, ramdisk and normal images. Make sure id has been
        # changed back to an integer
        ids = {}
        for name in ('kernel', 'ramdisk', 'normal'):
            image_name = '%s migration 012 test' % name
            rows = images.select().where(
                images.c.name == image_name).execute().fetchall()
            self.assertEqual(1, len(rows))

            row = rows[0]
            self.assertFalse(utils.is_uuid_like(row['id']))

            ids[name] = row['id']

        # Find all image_members to ensure image_id has been updated
        results = image_members.select().where(
            image_members.c.image_id == ids['normal']).execute().fetchall()
        self.assertEqual(1, len(results))

        # Find all image_properties to ensure image_id has been updated
        # as well as ensure kernel_id and ramdisk_id values have been
        # updated too
        results = image_properties.select().where(
            image_properties.c.image_id == ids['normal']).execute().fetchall()
        self.assertEqual(2, len(results))
        for row in results:
            self.assertIn(row['name'], ('kernel_id', 'ramdisk_id'))

            if row['name'] == 'kernel_id':
                self.assertEqual(row['value'], str(ids['kernel']))
            if row['name'] == 'ramdisk_id':
                self.assertEqual(row['value'], str(ids['ramdisk']))

    def _assert_invalid_swift_uri_raises_bad_store_uri(self,
                                                       legacy_parse_uri_fn):
        invalid_uri = ('swift://http://acct:usr:pass@example.com'
                       '/container/obj-id')
        # URI cannot contain more than one occurrence of a scheme.
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_uri,
                          True)

        invalid_scheme_uri = ('http://acct:usr:pass@example.com'
                              '/container/obj-id')
        self.assertRaises(AssertionError,
                          legacy_parse_uri_fn,
                          invalid_scheme_uri,
                          True)

        invalid_account_missing_uri = 'swift+http://container/obj-id'
        # Badly formed S3 URI: swift+http://container/obj-id
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_account_missing_uri,
                          True)

        invalid_container_missing_uri = ('swift+http://'
                                         'acct:usr:pass@example.com/obj-id')
        # Badly formed S3 URI: swift+http://acct:usr:pass@example.com/obj-id
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_container_missing_uri,
                          True)

        invalid_object_missing_uri = ('swift+http://'
                                      'acct:usr:pass@example.com/container')
        # Badly formed S3 URI: swift+http://acct:usr:pass@example.com/container
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_object_missing_uri,
                          True)

        invalid_user_without_pass_uri = ('swift://acctusr@example.com'
                                         '/container/obj-id')
        # Badly formed credentials '%(creds)s' in Swift URI
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_user_without_pass_uri,
                          True)

        # Badly formed credentials in Swift URI.
        self.assertRaises(exception.BadStoreUri,
                          legacy_parse_uri_fn,
                          invalid_user_without_pass_uri,
                          False)

    def test_legacy_parse_swift_uri_015(self):
        (legacy_parse_uri,) = from_migration_import(
            '015_quote_swift_credentials', ['legacy_parse_uri'])

        uri = legacy_parse_uri(
            'swift://acct:usr:pass@example.com/container/obj-id',
            True)
        self.assertTrue(uri, 'swift://acct%3Ausr:pass@example.com'
                             '/container/obj-id')

        self._assert_invalid_swift_uri_raises_bad_store_uri(legacy_parse_uri)

    def _pre_upgrade_015(self, engine):
        images = db_utils.get_table(engine, 'images')
        unquoted_locations = [
            'swift://acct:usr:pass@example.com/container/obj-id',
            'file://foo',
        ]
        now = datetime.datetime.now()
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0)
        data = []
        for i, location in enumerate(unquoted_locations):
            temp.update(location=location, id=str(uuid.uuid4()))
            data.append(temp)
            images.insert().values(temp).execute()
        return data

    def _check_015(self, engine, data):
        images = db_utils.get_table(engine, 'images')
        quoted_locations = [
            'swift://acct%3Ausr:pass@example.com/container/obj-id',
            'file://foo',
        ]
        result = images.select().execute()
        locations = map(lambda x: x['location'], result)
        for loc in quoted_locations:
            self.assertIn(loc, locations)

    def _pre_upgrade_016(self, engine):
        images = db_utils.get_table(engine, 'images')
        now = datetime.datetime.now()
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id='fake-image-id1')
        images.insert().values(temp).execute()
        image_members = db_utils.get_table(engine, 'image_members')
        now = datetime.datetime.now()
        data = {'deleted': False,
                'created_at': now,
                'member': 'fake-member',
                'updated_at': now,
                'can_share': False,
                'image_id': 'fake-image-id1'}
        image_members.insert().values(data).execute()
        return data

    def _check_016(self, engine, data):
        image_members = db_utils.get_table(engine, 'image_members')
        self.assertIn('status', image_members.c,
                      "'status' column found in image_members table "
                      "columns! image_members table columns: %s"
                      % image_members.c.keys())

    def test_legacy_parse_swift_uri_017(self):
        metadata_encryption_key = 'a' * 16
        CONF.set_override('metadata_encryption_key', metadata_encryption_key)
        self.addCleanup(CONF.reset)
        (legacy_parse_uri, encrypt_location) = from_migration_import(
            '017_quote_encrypted_swift_credentials', ['legacy_parse_uri',
                                                      'encrypt_location'])

        uri = legacy_parse_uri('swift://acct:usr:pass@example.com'
                               '/container/obj-id', True)
        self.assertTrue(uri, encrypt_location(
            'swift://acct%3Ausr:pass@example.com/container/obj-id'))

        self._assert_invalid_swift_uri_raises_bad_store_uri(legacy_parse_uri)

    def _pre_upgrade_017(self, engine):
        metadata_encryption_key = 'a' * 16
        CONF.set_override('metadata_encryption_key', metadata_encryption_key)
        self.addCleanup(CONF.reset)
        images = db_utils.get_table(engine, 'images')
        unquoted = 'swift://acct:usr:pass@example.com/container/obj-id'
        encrypted_unquoted = crypt.urlsafe_encrypt(
            metadata_encryption_key,
            unquoted, 64)
        data = []
        now = datetime.datetime.now()
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    location=encrypted_unquoted,
                    id='fakeid1')
        images.insert().values(temp).execute()

        locations = [
            'file://ab',
            'file://abc',
            'swift://acct3A%foobar:pass@example.com/container/obj-id2'
        ]

        now = datetime.datetime.now()
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0)
        for i, location in enumerate(locations):
            temp.update(location=location, id=str(uuid.uuid4()))
            data.append(temp)
            images.insert().values(temp).execute()
        return data

    def _check_017(self, engine, data):
        metadata_encryption_key = 'a' * 16
        quoted = 'swift://acct%3Ausr:pass@example.com/container/obj-id'
        images = db_utils.get_table(engine, 'images')
        result = images.select().execute()
        locations = map(lambda x: x['location'], result)
        actual_location = []
        for location in locations:
            if location:
                try:
                    temp_loc = crypt.urlsafe_decrypt(metadata_encryption_key,
                                                     location)
                    actual_location.append(temp_loc)
                except TypeError:
                    actual_location.append(location)
                except ValueError:
                    actual_location.append(location)

        self.assertIn(quoted, actual_location)
        loc_list = ['file://ab',
                    'file://abc',
                    'swift://acct3A%foobar:pass@example.com/container/obj-id2']

        for location in loc_list:
            if location not in actual_location:
                self.fail(_("location: %s data lost") % location)

    def _pre_upgrade_019(self, engine):
        images = db_utils.get_table(engine, 'images')
        now = datetime.datetime.now()
        base_values = {
            'deleted': False,
            'created_at': now,
            'updated_at': now,
            'status': 'active',
            'is_public': True,
            'min_disk': 0,
            'min_ram': 0,
        }
        data = [
            {'id': 'fake-19-1', 'location': 'http://glance.example.com'},
            # NOTE(bcwaldon): images with a location of None should
            # not be migrated
            {'id': 'fake-19-2', 'location': None},
        ]
        map(lambda image: image.update(base_values), data)
        for image in data:
            images.insert().values(image).execute()
        return data

    def _check_019(self, engine, data):
        image_locations = db_utils.get_table(engine, 'image_locations')
        records = image_locations.select().execute().fetchall()
        locations = {il.image_id: il.value for il in records}
        self.assertEqual('http://glance.example.com',
                         locations.get('fake-19-1'))

    def _check_020(self, engine, data):
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('location', images.c)

    def _pre_upgrade_026(self, engine):
        image_locations = db_utils.get_table(engine, 'image_locations')

        now = datetime.datetime.now()
        image_id = 'fake_id'
        url = 'file:///some/place/onthe/fs'

        images = db_utils.get_table(engine, 'images')
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id=image_id)
        images.insert().values(temp).execute()

        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    image_id=image_id,
                    value=url)
        image_locations.insert().values(temp).execute()
        return image_id

    def _check_026(self, engine, data):
        image_locations = db_utils.get_table(engine, 'image_locations')
        results = image_locations.select().where(
            image_locations.c.image_id == data).execute()

        r = list(results)
        self.assertEqual(1, len(r))
        self.assertEqual('file:///some/place/onthe/fs', r[0]['value'])
        self.assertIn('meta_data', r[0])
        x = pickle.loads(r[0]['meta_data'])
        self.assertEqual({}, x)

    def _check_027(self, engine, data):
        table = "images"
        index = "checksum_image_idx"
        columns = ["checksum"]

        meta = sqlalchemy.MetaData()
        meta.bind = engine

        new_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in new_table.indexes]

        self.assertIn((index, columns), index_data)

    def _check_028(self, engine, data):
        owner_index = "owner_image_idx"
        columns = ["owner"]

        images_table = db_utils.get_table(engine, 'images')

        index_data = [(idx.name, idx.columns.keys())
                      for idx in images_table.indexes
                      if idx.name == owner_index]

        self.assertIn((owner_index, columns), index_data)

    def _post_downgrade_028(self, engine):
        owner_index = "owner_image_idx"
        columns = ["owner"]

        images_table = db_utils.get_table(engine, 'images')

        index_data = [(idx.name, idx.columns.keys())
                      for idx in images_table.indexes
                      if idx.name == owner_index]

        self.assertNotIn((owner_index, columns), index_data)

    def _pre_upgrade_029(self, engine):
        image_locations = db_utils.get_table(engine, 'image_locations')

        meta_data = {'somelist': ['a', 'b', 'c'], 'avalue': 'hello',
                     'adict': {}}

        now = datetime.datetime.now()
        image_id = 'fake_029_id'
        url = 'file:///some/place/onthe/fs029'

        images = db_utils.get_table(engine, 'images')
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id=image_id)
        images.insert().values(temp).execute()

        pickle_md = pickle.dumps(meta_data)
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    image_id=image_id,
                    value=url,
                    meta_data=pickle_md)
        image_locations.insert().values(temp).execute()

        return meta_data, image_id

    def _check_029(self, engine, data):
        meta_data = data[0]
        image_id = data[1]
        image_locations = db_utils.get_table(engine, 'image_locations')

        records = image_locations.select().where(
            image_locations.c.image_id == image_id).execute().fetchall()

        for r in records:
            d = jsonutils.loads(r['meta_data'])
            self.assertEqual(d, meta_data)

    def _post_downgrade_029(self, engine):
        image_id = 'fake_029_id'

        image_locations = db_utils.get_table(engine, 'image_locations')

        records = image_locations.select().where(
            image_locations.c.image_id == image_id).execute().fetchall()

        for r in records:
            md = r['meta_data']
            d = pickle.loads(md)
            self.assertIsInstance(d, dict)

    def _check_030(self, engine, data):
        table = "tasks"
        index_type = ('ix_tasks_type', ['type'])
        index_status = ('ix_tasks_status', ['status'])
        index_owner = ('ix_tasks_owner', ['owner'])
        index_deleted = ('ix_tasks_deleted', ['deleted'])
        index_updated_at = ('ix_tasks_updated_at', ['updated_at'])

        meta = sqlalchemy.MetaData()
        meta.bind = engine

        tasks_table = sqlalchemy.Table(table, meta, autoload=True)

        index_data = [(idx.name, idx.columns.keys())
                      for idx in tasks_table.indexes]

        self.assertIn(index_type, index_data)
        self.assertIn(index_status, index_data)
        self.assertIn(index_owner, index_data)
        self.assertIn(index_deleted, index_data)
        self.assertIn(index_updated_at, index_data)

        expected = [u'id',
                    u'type',
                    u'status',
                    u'owner',
                    u'input',
                    u'result',
                    u'message',
                    u'expires_at',
                    u'created_at',
                    u'updated_at',
                    u'deleted_at',
                    u'deleted']

        # NOTE(flwang): Skip the column type checking for now since Jenkins is
        # using sqlalchemy.dialects.postgresql.base.TIMESTAMP instead of
        # DATETIME which is using by mysql and sqlite.
        col_data = [col.name for col in tasks_table.columns]
        self.assertEqual(expected, col_data)

    def _post_downgrade_030(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'tasks')

    def _pre_upgrade_031(self, engine):
        images = db_utils.get_table(engine, 'images')
        now = datetime.datetime.now()
        image_id = 'fake_031_id'
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id=image_id)
        images.insert().values(temp).execute()

        locations_table = db_utils.get_table(engine, 'image_locations')
        locations = [
            ('file://ab', '{"a": "yo yo"}'),
            ('file://ab', '{}'),
            ('file://ab', '{}'),
            ('file://ab1', '{"a": "that one, please"}'),
            ('file://ab1', '{"a": "that one, please"}'),
        ]
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    image_id=image_id)

        for location, metadata in locations:
            temp.update(value=location, meta_data=metadata)
            locations_table.insert().values(temp).execute()
        return image_id

    def _check_031(self, engine, image_id):
        locations_table = db_utils.get_table(engine, 'image_locations')
        result = locations_table.select().where(
            locations_table.c.image_id == image_id).execute().fetchall()

        locations = set([(x['value'], x['meta_data']) for x in result])
        actual_locations = set([
            ('file://ab', '{"a": "yo yo"}'),
            ('file://ab', '{}'),
            ('file://ab1', '{"a": "that one, please"}'),
        ])
        self.assertFalse(actual_locations.symmetric_difference(locations))

    def _pre_upgrade_032(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'task_info')

        tasks = db_utils.get_table(engine, 'tasks')
        now = datetime.datetime.now()
        base_values = {
            'deleted': False,
            'created_at': now,
            'updated_at': now,
            'status': 'active',
            'owner': 'TENANT',
            'type': 'import',
        }
        data = [
            {
                'id': 'task-1',
                'input': 'some input',
                'message': None,
                'result': 'successful'
            },
            {
                'id': 'task-2',
                'input': None,
                'message': None,
                'result': None
            },
        ]
        map(lambda task: task.update(base_values), data)
        for task in data:
            tasks.insert().values(task).execute()
        return data

    def _check_032(self, engine, data):
        task_info_table = db_utils.get_table(engine, 'task_info')

        task_info_refs = task_info_table.select().execute().fetchall()

        self.assertEqual(2, len(task_info_refs))

        for x in range(len(task_info_refs)):
            self.assertEqual(task_info_refs[x].task_id, data[x]['id'])
            self.assertEqual(task_info_refs[x].input, data[x]['input'])
            self.assertEqual(task_info_refs[x].result, data[x]['result'])
            self.assertIsNone(task_info_refs[x].message)

        tasks_table = db_utils.get_table(engine, 'tasks')
        self.assertNotIn('input', tasks_table.c)
        self.assertNotIn('result', tasks_table.c)
        self.assertNotIn('message', tasks_table.c)

    def _post_downgrade_032(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'task_info')

        tasks_table = db_utils.get_table(engine, 'tasks')
        records = tasks_table.select().execute().fetchall()
        self.assertEqual(2, len(records))

        tasks = {t.id: t for t in records}

        task_1 = tasks.get('task-1')
        self.assertEqual('some input', task_1.input)
        self.assertEqual('successful', task_1.result)
        self.assertIsNone(task_1.message)

        task_2 = tasks.get('task-2')
        self.assertIsNone(task_2.input)
        self.assertIsNone(task_2.result)
        self.assertIsNone(task_2.message)

    def _pre_upgrade_033(self, engine):
        images = db_utils.get_table(engine, 'images')
        image_locations = db_utils.get_table(engine, 'image_locations')

        now = datetime.datetime.now()
        image_id = 'fake_id_028_%d'
        url = 'file:///some/place/onthe/fs_%d'
        status_list = ['active', 'saving', 'queued', 'killed',
                       'pending_delete', 'deleted']
        image_id_list = []

        for (idx, status) in enumerate(status_list):
            temp = dict(deleted=False,
                        created_at=now,
                        updated_at=now,
                        status=status,
                        is_public=True,
                        min_disk=0,
                        min_ram=0,
                        id=image_id % idx)
            images.insert().values(temp).execute()

            temp = dict(deleted=False,
                        created_at=now,
                        updated_at=now,
                        image_id=image_id % idx,
                        value=url % idx)
            image_locations.insert().values(temp).execute()

            image_id_list.append(image_id % idx)
        return image_id_list

    def _check_033(self, engine, data):
        image_locations = db_utils.get_table(engine, 'image_locations')

        self.assertIn('status', image_locations.c)
        self.assertEqual(30, image_locations.c['status'].type.length)

        status_list = ['active', 'active', 'active',
                       'deleted', 'pending_delete', 'deleted']

        for (idx, image_id) in enumerate(data):
            results = image_locations.select().where(
                image_locations.c.image_id == image_id).execute()
            r = list(results)
            self.assertEqual(1, len(r))
            self.assertIn('status', r[0])
            self.assertEqual(r[0]['status'], status_list[idx])

    def _post_downgrade_033(self, engine):
        image_locations = db_utils.get_table(engine, 'image_locations')
        self.assertNotIn('status', image_locations.c)

    def _pre_upgrade_034(self, engine):
        images = db_utils.get_table(engine, 'images')

        now = datetime.datetime.now()
        image_id = 'fake_id_034'
        temp = dict(deleted=False,
                    created_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id=image_id)
        images.insert().values(temp).execute()

    def _check_034(self, engine, data):
        images = db_utils.get_table(engine, 'images')
        self.assertIn('virtual_size', images.c)

        result = (images.select()
                  .where(images.c.id == 'fake_id_034')
                  .execute().fetchone())
        self.assertIsNone(result.virtual_size)

    def _post_downgrade_034(self, engine):
        images = db_utils.get_table(engine, 'images')
        self.assertNotIn('virtual_size', images.c)

    def _pre_upgrade_035(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_namespaces')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_properties')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_objects')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_resource_types')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'metadef_namespace_resource_types')

    def _check_035(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # metadef_namespaces
        table = sqlalchemy.Table("metadef_namespaces", meta, autoload=True)
        index_namespace = ('ix_namespaces_namespace', ['namespace'])
        index_data = [(idx.name, idx.columns.keys())
                      for idx in table.indexes]
        self.assertIn(index_namespace, index_data)

        expected_cols = [u'id',
                         u'namespace',
                         u'display_name',
                         u'description',
                         u'visibility',
                         u'protected',
                         u'owner',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_objects
        table = sqlalchemy.Table("metadef_objects", meta, autoload=True)
        index_namespace_id_name = (
            'ix_objects_namespace_id_name', ['namespace_id', 'name'])
        index_data = [(idx.name, idx.columns.keys())
                      for idx in table.indexes]
        self.assertIn(index_namespace_id_name, index_data)

        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'description',
                         u'required',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_properties
        table = sqlalchemy.Table("metadef_properties", meta, autoload=True)
        index_namespace_id_name = (
            'ix_metadef_properties_namespace_id_name',
            ['namespace_id', 'name'])
        index_data = [(idx.name, idx.columns.keys())
                      for idx in table.indexes]
        self.assertIn(index_namespace_id_name, index_data)

        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_resource_types
        table = sqlalchemy.Table(
            "metadef_resource_types", meta, autoload=True)
        index_resource_types_name = (
            'ix_metadef_resource_types_name', ['name'])
        index_data = [(idx.name, idx.columns.keys())
                      for idx in table.indexes]
        self.assertIn(index_resource_types_name, index_data)

        expected_cols = [u'id',
                         u'name',
                         u'protected',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_namespace_resource_types
        table = sqlalchemy.Table(
            "metadef_namespace_resource_types", meta, autoload=True)
        index_ns_res_types_res_type_id_ns_id = (
            'ix_metadef_ns_res_types_res_type_id_ns_id',
            ['resource_type_id', 'namespace_id'])
        index_data = [(idx.name, idx.columns.keys())
                      for idx in table.indexes]
        self.assertIn(index_ns_res_types_res_type_id_ns_id, index_data)

        expected_cols = [u'resource_type_id',
                         u'namespace_id',
                         u'properties_target',
                         u'prefix',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

    def _post_downgrade_035(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_namespaces')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_properties')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_objects')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_resource_types')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'metadef_namespace_resource_types')

    def _pre_upgrade_036(self, engine):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # metadef_objects
        table = sqlalchemy.Table("metadef_objects", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'description',
                         u'required',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_properties
        table = sqlalchemy.Table("metadef_properties", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

    def _check_036(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # metadef_objects
        table = sqlalchemy.Table("metadef_objects", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'description',
                         u'required',
                         u'json_schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_properties
        table = sqlalchemy.Table("metadef_properties", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'json_schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

    def _post_downgrade_036(self, engine):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # metadef_objects
        table = sqlalchemy.Table("metadef_objects", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'description',
                         u'required',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

        # metadef_properties
        table = sqlalchemy.Table("metadef_properties", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'schema',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

    def _check_037(self, engine, data):
        if engine.name == 'mysql':
            self.assertFalse(unique_constraint_exist('image_id',
                                                     'image_properties',
                                                     engine))

            self.assertTrue(unique_constraint_exist(
                'ix_image_properties_image_id_name',
                'image_properties',
                engine))

        image_members = db_utils.get_table(engine, 'image_members')
        images = db_utils.get_table(engine, 'images')

        self.assertFalse(image_members.c.status.nullable)
        self.assertFalse(images.c.protected.nullable)

        now = datetime.datetime.now()
        temp = dict(
            deleted=False,
            created_at=now,
            status='active',
            is_public=True,
            min_disk=0,
            min_ram=0,
            id='fake_image_035'
        )
        images.insert().values(temp).execute()

        image = (images.select()
                 .where(images.c.id == 'fake_image_035')
                 .execute().fetchone())

        self.assertFalse(image['protected'])

        temp = dict(
            deleted=False,
            created_at=now,
            image_id='fake_image_035',
            member='fake_member',
            can_share=True,
            id=3
        )

        image_members.insert().values(temp).execute()

        image_member = (image_members.select()
                        .where(image_members.c.id == 3)
                        .execute().fetchone())

        self.assertEqual('pending', image_member['status'])

    def _post_downgrade_037(self, engine):
        if engine.name == 'mysql':
            self.assertTrue(unique_constraint_exist('image_id',
                                                    'image_properties',
                                                    engine))

        if engine.name == 'postgresql':
            self.assertTrue(index_exist('ix_image_properties_image_id_name',
                                        'image_properties', engine))

            self.assertFalse(unique_constraint_exist(
                'ix_image_properties_image_id_name',
                'image_properties',
                engine))

        image_members = db_utils.get_table(engine, 'image_members')
        images = db_utils.get_table(engine, 'images')

        self.assertTrue(image_members.c.status.nullable)
        self.assertTrue(images.c.protected.nullable)

        now = datetime.datetime.now()
        temp = dict(
            deleted=False,
            created_at=now,
            status='active',
            is_public=True,
            min_disk=0,
            min_ram=0,
            id='fake_image_035_d'
        )
        images.insert().values(temp).execute()

        image = (images.select()
                 .where(images.c.id == 'fake_image_035_d')
                 .execute().fetchone())

        self.assertIsNone(image['protected'])

        temp = dict(
            deleted=False,
            created_at=now,
            image_id='fake_image_035_d',
            member='fake_member',
            can_share=True,
            id=4
        )

        image_members.insert().values(temp).execute()

        image_member = (image_members.select()
                        .where(image_members.c.id == 4)
                        .execute().fetchone())

        self.assertIsNone(image_member['status'])

    def _pre_upgrade_038(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_tags')

    def _check_038(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        # metadef_tags
        table = sqlalchemy.Table("metadef_tags", meta, autoload=True)
        expected_cols = [u'id',
                         u'namespace_id',
                         u'name',
                         u'created_at',
                         u'updated_at']
        col_data = [col.name for col in table.columns]
        self.assertEqual(expected_cols, col_data)

    def _post_downgrade_038(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine, 'metadef_tags')

    def _check_039(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        metadef_namespaces = sqlalchemy.Table('metadef_namespaces', meta,
                                              autoload=True)
        metadef_properties = sqlalchemy.Table('metadef_properties', meta,
                                              autoload=True)
        metadef_objects = sqlalchemy.Table('metadef_objects', meta,
                                           autoload=True)
        metadef_ns_res_types = sqlalchemy.Table(
            'metadef_namespace_resource_types',
            meta, autoload=True)
        metadef_resource_types = sqlalchemy.Table('metadef_resource_types',
                                                  meta, autoload=True)

        tables = [metadef_namespaces, metadef_properties, metadef_objects,
                  metadef_ns_res_types, metadef_resource_types]

        for table in tables:
            for index_name in ['ix_namespaces_namespace',
                               'ix_objects_namespace_id_name',
                               'ix_metadef_properties_namespace_id_name']:
                self.assertFalse(index_exist(index_name, table.name, engine))
            for uc_name in ['resource_type_id', 'namespace', 'name',
                            'namespace_id',
                            'metadef_objects_namespace_id_name_key',
                            'metadef_properties_namespace_id_name_key']:
                self.assertFalse(unique_constraint_exist(uc_name, table.name,
                                                         engine))

        self.assertTrue(index_exist('ix_metadef_ns_res_types_namespace_id',
                                    metadef_ns_res_types.name, engine))

        self.assertTrue(index_exist('ix_metadef_namespaces_namespace',
                                    metadef_namespaces.name, engine))

        self.assertTrue(index_exist('ix_metadef_namespaces_owner',
                                    metadef_namespaces.name, engine))

        self.assertTrue(index_exist('ix_metadef_objects_name',
                                    metadef_objects.name, engine))

        self.assertTrue(index_exist('ix_metadef_objects_namespace_id',
                                    metadef_objects.name, engine))

        self.assertTrue(index_exist('ix_metadef_properties_name',
                                    metadef_properties.name, engine))

        self.assertTrue(index_exist('ix_metadef_properties_namespace_id',
                                    metadef_properties.name, engine))

    def _post_downgrade_039(self, engine):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        metadef_namespaces = sqlalchemy.Table('metadef_namespaces', meta,
                                              autoload=True)
        metadef_properties = sqlalchemy.Table('metadef_properties', meta,
                                              autoload=True)
        metadef_objects = sqlalchemy.Table('metadef_objects', meta,
                                           autoload=True)
        metadef_ns_res_types = sqlalchemy.Table(
            'metadef_namespace_resource_types',
            meta, autoload=True)
        metadef_resource_types = sqlalchemy.Table('metadef_resource_types',
                                                  meta, autoload=True)

        self.assertFalse(index_exist('ix_metadef_ns_res_types_namespace_id',
                                     metadef_ns_res_types.name, engine))

        self.assertFalse(index_exist('ix_metadef_namespaces_namespace',
                                     metadef_namespaces.name, engine))

        self.assertFalse(index_exist('ix_metadef_namespaces_owner',
                                     metadef_namespaces.name, engine))

        self.assertFalse(index_exist('ix_metadef_objects_name',
                                     metadef_objects.name, engine))

        self.assertFalse(index_exist('ix_metadef_objects_namespace_id',
                                     metadef_objects.name, engine))

        self.assertFalse(index_exist('ix_metadef_properties_name',
                                     metadef_properties.name, engine))

        self.assertFalse(index_exist('ix_metadef_properties_namespace_id',
                                     metadef_properties.name, engine))

        self.assertTrue(index_exist('ix_namespaces_namespace',
                                    metadef_namespaces.name, engine))

        self.assertTrue(index_exist('ix_objects_namespace_id_name',
                                    metadef_objects.name, engine))

        self.assertTrue(index_exist('ix_metadef_properties_namespace_id_name',
                                    metadef_properties.name, engine))

        if engine.name == 'postgresql':
            inspector = inspect(engine)

            self.assertEqual(1, len(inspector.get_unique_constraints(
                'metadef_objects')))

            self.assertEqual(1, len(inspector.get_unique_constraints(
                'metadef_properties')))

        if engine.name == 'mysql':
            self.assertTrue(unique_constraint_exist(
                'namespace_id', metadef_properties.name, engine))

            self.assertTrue(unique_constraint_exist(
                'namespace_id', metadef_objects.name, engine))

            self.assertTrue(unique_constraint_exist(
                'resource_type_id', metadef_ns_res_types.name, engine))

            self.assertTrue(unique_constraint_exist(
                'namespace', metadef_namespaces.name, engine))

            self.assertTrue(unique_constraint_exist(
                'name', metadef_resource_types.name, engine))

    def _check_040(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine
        metadef_tags = sqlalchemy.Table('metadef_tags', meta, autoload=True)

        if engine.name == 'mysql':
            self.assertFalse(index_exist('namespace_id',
                             metadef_tags.name, engine))

    def _pre_upgrade_041(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifacts')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifact_tags')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifact_properties')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifact_blobs')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifact_dependencies')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'artifact_locations')

    def _check_041(self, engine, data):
        artifacts_indices = [('ix_artifact_name_and_version',
                              ['name', 'version_prefix', 'version_suffix']),
                             ('ix_artifact_type',
                              ['type_name',
                               'type_version_prefix',
                               'type_version_suffix']),
                             ('ix_artifact_state', ['state']),
                             ('ix_artifact_visibility', ['visibility']),
                             ('ix_artifact_owner', ['owner'])]
        artifacts_columns = ['id',
                             'name',
                             'type_name',
                             'type_version_prefix',
                             'type_version_suffix',
                             'type_version_meta',
                             'version_prefix',
                             'version_suffix',
                             'version_meta',
                             'description',
                             'visibility',
                             'state',
                             'owner',
                             'created_at',
                             'updated_at',
                             'deleted_at',
                             'published_at']
        self.assert_table(engine, 'artifacts', artifacts_indices,
                          artifacts_columns)

        tags_indices = [('ix_artifact_tags_artifact_id', ['artifact_id']),
                        ('ix_artifact_tags_artifact_id_tag_value',
                         ['artifact_id',
                          'value'])]
        tags_columns = ['id',
                        'artifact_id',
                        'value',
                        'created_at',
                        'updated_at']
        self.assert_table(engine, 'artifact_tags', tags_indices, tags_columns)

        prop_indices = [
            ('ix_artifact_properties_artifact_id', ['artifact_id']),
            ('ix_artifact_properties_name', ['name'])]
        prop_columns = ['id',
                        'artifact_id',
                        'name',
                        'string_value',
                        'int_value',
                        'numeric_value',
                        'bool_value',
                        'text_value',
                        'created_at',
                        'updated_at',
                        'position']
        self.assert_table(engine, 'artifact_properties', prop_indices,
                          prop_columns)

        blobs_indices = [
            ('ix_artifact_blobs_artifact_id', ['artifact_id']),
            ('ix_artifact_blobs_name', ['name'])]
        blobs_columns = ['id',
                         'artifact_id',
                         'size',
                         'checksum',
                         'name',
                         'item_key',
                         'position',
                         'created_at',
                         'updated_at']
        self.assert_table(engine, 'artifact_blobs', blobs_indices,
                          blobs_columns)

        dependencies_indices = [
            ('ix_artifact_dependencies_source_id', ['artifact_source']),
            ('ix_artifact_dependencies_direct_dependencies',
             ['artifact_source', 'is_direct']),
            ('ix_artifact_dependencies_dest_id', ['artifact_dest']),
            ('ix_artifact_dependencies_origin_id', ['artifact_origin'])]
        dependencies_columns = ['id',
                                'artifact_source',
                                'artifact_dest',
                                'artifact_origin',
                                'is_direct',
                                'position',
                                'name',
                                'created_at',
                                'updated_at']
        self.assert_table(engine, 'artifact_dependencies',
                          dependencies_indices,
                          dependencies_columns)

        locations_indices = [
            ('ix_artifact_blob_locations_blob_id', ['blob_id'])]
        locations_columns = ['id',
                             'blob_id',
                             'value',
                             'created_at',
                             'updated_at',
                             'position',
                             'status']
        self.assert_table(engine, 'artifact_blob_locations', locations_indices,
                          locations_columns)

    def _pre_upgrade_042(self, engine):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        metadef_namespaces = sqlalchemy.Table('metadef_namespaces', meta,
                                              autoload=True)
        metadef_objects = sqlalchemy.Table('metadef_objects', meta,
                                           autoload=True)
        metadef_properties = sqlalchemy.Table('metadef_properties', meta,
                                              autoload=True)
        metadef_tags = sqlalchemy.Table('metadef_tags', meta, autoload=True)
        metadef_resource_types = sqlalchemy.Table('metadef_resource_types',
                                                  meta, autoload=True)
        metadef_ns_res_types = sqlalchemy.Table(
            'metadef_namespace_resource_types',
            meta, autoload=True)

        # These will be dropped and recreated as unique constraints.
        self.assertTrue(index_exist('ix_metadef_namespaces_namespace',
                                    metadef_namespaces.name, engine))
        self.assertTrue(index_exist('ix_metadef_objects_namespace_id',
                                    metadef_objects.name, engine))
        self.assertTrue(index_exist('ix_metadef_properties_namespace_id',
                                    metadef_properties.name, engine))
        self.assertTrue(index_exist('ix_metadef_tags_namespace_id',
                                    metadef_tags.name, engine))
        self.assertTrue(index_exist('ix_metadef_resource_types_name',
                                    metadef_resource_types.name, engine))

        # This one will be dropped - not needed
        self.assertTrue(index_exist(
            'ix_metadef_ns_res_types_res_type_id_ns_id',
            metadef_ns_res_types.name, engine))

        # The rest must remain
        self.assertTrue(index_exist('ix_metadef_namespaces_owner',
                                    metadef_namespaces.name, engine))
        self.assertTrue(index_exist('ix_metadef_objects_name',
                                    metadef_objects.name, engine))
        self.assertTrue(index_exist('ix_metadef_properties_name',
                                    metadef_properties.name, engine))
        self.assertTrue(index_exist('ix_metadef_tags_name',
                                    metadef_tags.name, engine))
        self.assertTrue(index_exist('ix_metadef_ns_res_types_namespace_id',
                                    metadef_ns_res_types.name, engine))

        # To be created
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_objects_namespace_id_name',
                          metadef_objects.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_properties_namespace_id_name',
                          metadef_properties.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_tags_namespace_id_name',
                          metadef_tags.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_namespaces_namespace',
                          metadef_namespaces.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_resource_types_name',
                          metadef_resource_types.name, engine)
                         )

    def _check_042(self, engine, data):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        metadef_namespaces = sqlalchemy.Table('metadef_namespaces', meta,
                                              autoload=True)
        metadef_objects = sqlalchemy.Table('metadef_objects', meta,
                                           autoload=True)
        metadef_properties = sqlalchemy.Table('metadef_properties', meta,
                                              autoload=True)
        metadef_tags = sqlalchemy.Table('metadef_tags', meta, autoload=True)
        metadef_resource_types = sqlalchemy.Table('metadef_resource_types',
                                                  meta, autoload=True)
        metadef_ns_res_types = sqlalchemy.Table(
            'metadef_namespace_resource_types',
            meta, autoload=True)

        # Dropped for unique constraints
        self.assertFalse(index_exist('ix_metadef_namespaces_namespace',
                                     metadef_namespaces.name, engine))
        self.assertFalse(index_exist('ix_metadef_objects_namespace_id',
                                     metadef_objects.name, engine))
        self.assertFalse(index_exist('ix_metadef_properties_namespace_id',
                                     metadef_properties.name, engine))
        self.assertFalse(index_exist('ix_metadef_tags_namespace_id',
                                     metadef_tags.name, engine))
        self.assertFalse(index_exist('ix_metadef_resource_types_name',
                                     metadef_resource_types.name, engine))

        # Dropped - not needed because of the existing primary key
        self.assertFalse(index_exist(
            'ix_metadef_ns_res_types_res_type_id_ns_id',
            metadef_ns_res_types.name, engine))

        # Still exist as before
        self.assertTrue(index_exist('ix_metadef_namespaces_owner',
                                    metadef_namespaces.name, engine))
        self.assertTrue(index_exist('ix_metadef_ns_res_types_namespace_id',
                                    metadef_ns_res_types.name, engine))
        self.assertTrue(index_exist('ix_metadef_objects_name',
                                    metadef_objects.name, engine))
        self.assertTrue(index_exist('ix_metadef_properties_name',
                                    metadef_properties.name, engine))
        self.assertTrue(index_exist('ix_metadef_tags_name',
                                    metadef_tags.name, engine))

        self.assertTrue(unique_constraint_exist
                        ('uq_metadef_namespaces_namespace',
                         metadef_namespaces.name, engine)
                        )
        self.assertTrue(unique_constraint_exist
                        ('uq_metadef_objects_namespace_id_name',
                         metadef_objects.name, engine)
                        )
        self.assertTrue(unique_constraint_exist
                        ('uq_metadef_properties_namespace_id_name',
                         metadef_properties.name, engine)
                        )
        self.assertTrue(unique_constraint_exist
                        ('uq_metadef_tags_namespace_id_name',
                         metadef_tags.name, engine)
                        )
        self.assertTrue(unique_constraint_exist
                        ('uq_metadef_resource_types_name',
                         metadef_resource_types.name, engine)
                        )

    def _post_downgrade_042(self, engine):
        meta = sqlalchemy.MetaData()
        meta.bind = engine

        metadef_namespaces = sqlalchemy.Table('metadef_namespaces', meta,
                                              autoload=True)
        metadef_objects = sqlalchemy.Table('metadef_objects', meta,
                                           autoload=True)
        metadef_properties = sqlalchemy.Table('metadef_properties', meta,
                                              autoload=True)
        metadef_tags = sqlalchemy.Table('metadef_tags', meta, autoload=True)
        metadef_resource_types = sqlalchemy.Table('metadef_resource_types',
                                                  meta, autoload=True)
        metadef_ns_res_types = sqlalchemy.Table(
            'metadef_namespace_resource_types',
            meta, autoload=True)

        # These have been recreated
        self.assertTrue(index_exist('ix_metadef_namespaces_namespace',
                                    metadef_namespaces.name, engine))
        self.assertTrue(index_exist('ix_metadef_objects_namespace_id',
                                    metadef_objects.name, engine))
        self.assertTrue(index_exist('ix_metadef_properties_namespace_id',
                                    metadef_properties.name, engine))
        self.assertTrue(index_exist('ix_metadef_tags_namespace_id',
                                    metadef_tags.name, engine))
        self.assertTrue(index_exist('ix_metadef_resource_types_name',
                                    metadef_resource_types.name, engine))

        self.assertTrue(index_exist(
            'ix_metadef_ns_res_types_res_type_id_ns_id',
            metadef_ns_res_types.name, engine))

        # The rest must remain
        self.assertTrue(index_exist('ix_metadef_namespaces_owner',
                                    metadef_namespaces.name, engine))
        self.assertTrue(index_exist('ix_metadef_objects_name',
                                    metadef_objects.name, engine))
        self.assertTrue(index_exist('ix_metadef_properties_name',
                                    metadef_properties.name, engine))
        self.assertTrue(index_exist('ix_metadef_tags_name',
                                    metadef_tags.name, engine))
        self.assertTrue(index_exist('ix_metadef_ns_res_types_namespace_id',
                                    metadef_ns_res_types.name, engine))

        # Dropped
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_objects_namespace_id_name',
                          metadef_objects.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_properties_namespace_id_name',
                          metadef_properties.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_tags_namespace_id_name',
                          metadef_tags.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_namespaces_namespace',
                          metadef_namespaces.name, engine)
                         )
        self.assertFalse(unique_constraint_exist
                         ('uq_metadef_resource_types_name',
                          metadef_resource_types.name, engine)
                         )

    def assert_table(self, engine, table_name, indices, columns):
        table = db_utils.get_table(engine, table_name)
        index_data = [(index.name, index.columns.keys()) for index in
                      table.indexes]
        column_data = [column.name for column in table.columns]
        # instead of calling assertItemsEqual, which is not present in py26
        # asserting equality of lengths and sorted collections
        self.assertEqual(len(columns), len(column_data))
        self.assertEqual(sorted(columns), sorted(column_data))
        self.assertEqual(len(indices), len(index_data))
        self.assertEqual(sorted(indices), sorted(index_data))


class TestMysqlMigrations(test_base.MySQLOpportunisticTestCase,
                          MigrationsMixin):

    def test_mysql_innodb_tables(self):
        migration.db_sync(engine=self.migrate_engine)

        total = self.migrate_engine.execute(
            "SELECT COUNT(*) "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA='%s'"
            % self.migrate_engine.url.database)
        self.assertTrue(total.scalar() > 0, "No tables found. Wrong schema?")

        noninnodb = self.migrate_engine.execute(
            "SELECT count(*) "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA='%s' "
            "AND ENGINE!='InnoDB' "
            "AND TABLE_NAME!='migrate_version'"
            % self.migrate_engine.url.database)
        count = noninnodb.scalar()
        self.assertEqual(count, 0, "%d non InnoDB tables created" % count)


class TestPostgresqlMigrations(test_base.PostgreSQLOpportunisticTestCase,
                               MigrationsMixin):
    pass


class TestSqliteMigrations(test_base.DbTestCase,
                           MigrationsMixin):
    def test_walk_versions(self):
        # No more downgrades
        self._walk_versions(False, False)


class ModelsMigrationSyncMixin(object):

    def get_metadata(self):
        for table in models_metadef.BASE_DICT.metadata.sorted_tables:
            models.BASE.metadata._add_table(table.name, table.schema, table)
        for table in models_artifacts.BASE.metadata.sorted_tables:
            models.BASE.metadata._add_table(table.name, table.schema, table)
        return models.BASE.metadata

    def get_engine(self):
        return self.engine

    def db_sync(self, engine):
        migration.db_sync(engine=engine)

    def include_object(self, object_, name, type_, reflected, compare_to):
        if name in ['migrate_version'] and type_ == 'table':
            return False
        return True


class ModelsMigrationsSyncMysql(ModelsMigrationSyncMixin,
                                test_migrations.ModelsMigrationsSync,
                                test_base.MySQLOpportunisticTestCase):
    pass


class ModelsMigrationsSyncPostgres(ModelsMigrationSyncMixin,
                                   test_migrations.ModelsMigrationsSync,
                                   test_base.PostgreSQLOpportunisticTestCase):
    pass


class ModelsMigrationsSyncSQLite(ModelsMigrationSyncMixin,
                                 test_migrations.ModelsMigrationsSync,
                                 test_base.DbTestCase):
    pass
