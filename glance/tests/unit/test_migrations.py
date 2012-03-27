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

"""
Tests for database migrations. This test case reads the configuration
file /tests/unit/test_migrations.conf for database connection settings
to use in the tests. For each connection found in the config file,
the test case runs a series of test cases to ensure that migrations work
properly both upgrading and downgrading, and that no data loss occurs
if possible.
"""

import ConfigParser
import datetime
import os
import unittest
import urlparse

from migrate.versioning.repository import Repository
from sqlalchemy import *
from sqlalchemy.pool import NullPool

from glance.common import exception
from glance.registry.db import models
import glance.registry.db.migration as migration_api
from glance.tests.utils import execute


class TestMigrations(unittest.TestCase):

    """Test sqlalchemy-migrate migrations"""

    TEST_DATABASES = {}
    # Test machines can set the GLANCE_TEST_MIGRATIONS_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_MIGRATIONS_CONF',
                                      os.path.join('glance', 'tests', 'unit',
                                                   'test_migrations.conf'))
    REPOSITORY_PATH = os.path.join('glance', 'registry', 'db', 'migrate_repo')
    REPOSITORY = Repository(REPOSITORY_PATH)

    def __init__(self, *args, **kwargs):
        super(TestMigrations, self).__init__(*args, **kwargs)

    def setUp(self):
        # Load test databases from the config file. Only do this
        # once. No need to re-run this on each test...
        if not TestMigrations.TEST_DATABASES:
            if os.path.exists(TestMigrations.CONFIG_FILE_PATH):
                cp = ConfigParser.RawConfigParser()
                try:
                    cp.read(TestMigrations.CONFIG_FILE_PATH)
                    defaults = cp.defaults()
                    for key, value in defaults.items():
                        TestMigrations.TEST_DATABASES[key] = value
                except ConfigParser.ParsingError, e:
                    self.fail("Failed to read test_migrations.conf config "
                              "file. Got error: %s" % e)
            else:
                self.fail("Failed to find test_migrations.conf config "
                          "file.")

        self.engines = {}
        for key, value in TestMigrations.TEST_DATABASES.items():
            self.engines[key] = create_engine(value, poolclass=NullPool)

        # We start each test case with a completely blank slate.
        self._reset_databases()

    def tearDown(self):
        # We destroy the test data store between each test case,
        # and recreate it, which ensures that we have no side-effects
        # from the tests
        self._reset_databases()

    def _reset_databases(self):
        for key, engine in self.engines.items():
            conn_string = TestMigrations.TEST_DATABASES[key]
            conn_pieces = urlparse.urlparse(conn_string)
            if conn_string.startswith('sqlite'):
                # We can just delete the SQLite database, which is
                # the easiest and cleanest solution
                db_path = conn_pieces.path.strip('/')
                if os.path.exists(db_path):
                    os.unlink(db_path)
                # No need to recreate the SQLite DB. SQLite will
                # create it for us if it's not there...
            elif conn_string.startswith('mysql'):
                # We can execute the MySQL client to destroy and re-create
                # the MYSQL database, which is easier and less error-prone
                # than using SQLAlchemy to do this via MetaData...trust me.
                database = conn_pieces.path.strip('/')
                loc_pieces = conn_pieces.netloc.split('@')
                host = loc_pieces[1]
                auth_pieces = loc_pieces[0].split(':')
                user = auth_pieces[0]
                password = ""
                if len(auth_pieces) > 1:
                    if auth_pieces[1].strip():
                        password = "-p%s" % auth_pieces[1]
                sql = ("drop database if exists %(database)s; "
                       "create database %(database)s;") % locals()
                cmd = ("mysql -u%(user)s %(password)s -h%(host)s "
                       "-e\"%(sql)s\"") % locals()
                exitcode, out, err = execute(cmd)
                self.assertEqual(0, exitcode)

    def test_walk_versions(self):
        """
        Walks all version scripts for each tested database, ensuring
        that there are no errors in the version scripts for each engine
        """
        for key, engine in self.engines.items():
            options = {'sql_connection': TestMigrations.TEST_DATABASES[key]}
            self._walk_versions(options)

    def test_version_control_existing_db(self):
        """
        Creates a DB without version control information, places it
        under version control and checks that it can be upgraded
        without errors.
        """
        for key, engine in self.engines.items():
            #conf = utils.TestConfigOpts({
            #        'sql_connection': TestMigrations.TEST_DATABASES[key]})
            #conf.register_opt(cfg.StrOpt('sql_connection'))
            options = {'sql_connection': TestMigrations.TEST_DATABASES[key]}
            self._create_unversioned_001_db(engine)
            self._walk_versions(options, initial_version=1)

    def _create_unversioned_001_db(self, engine):
        # Create the initial version of the images table
        meta = MetaData()
        meta.bind = engine
        images_001 = Table('images', meta,
            Column('id', models.Integer, primary_key=True),
            Column('name', String(255)),
            Column('type', String(30)),
            Column('size', Integer),
            Column('status', String(30)),
            Column('is_public', Boolean, default=False),
            Column('location', Text),
            Column('created_at', DateTime(), nullable=False),
            Column('updated_at', DateTime()),
            Column('deleted_at', DateTime()),
            Column('deleted', Boolean(), nullable=False, default=False))
        images_001.create()

    def _walk_versions(self, options, initial_version=0):
        # Determine latest version script from the repo, then
        # upgrade from 1 through to the latest, with no data
        # in the databases. This just checks that the schema itself
        # upgrades successfully.

        # Assert we are not under version control...
        self.assertRaises(exception.DatabaseMigrationError,
                          migration_api.db_version,
                          options)
        # Place the database under version control
        migration_api.version_control(options, version=initial_version)

        cur_version = migration_api.db_version(options)
        self.assertEqual(initial_version, cur_version)

        for version in xrange(initial_version + 1,
                              TestMigrations.REPOSITORY.latest + 1):
            migration_api.db_sync(options, version)
            cur_version = migration_api.db_version(options)
            self.assertEqual(cur_version, version)

        # Now walk it back down to 0 from the latest, testing
        # the downgrade paths.
        for version in reversed(
            xrange(0, TestMigrations.REPOSITORY.latest)):
            migration_api.downgrade(options, version)
            cur_version = migration_api.db_version(options)
            self.assertEqual(cur_version, version)

    def test_no_data_loss_2_to_3_to_2(self):
        """
        Here, we test that in the case when we moved a column "type" from the
        base images table to be records in the image_properties table, that
        we don't lose any data during the migration. Similarly, we test that
        on downgrade, we don't lose any data, as the records are moved from
        the image_properties table back into the base image table.
        """
        for key, engine in self.engines.items():
            options = {'sql_connection': TestMigrations.TEST_DATABASES[key]}
            self._no_data_loss_2_to_3_to_2(engine, options)

    def _no_data_loss_2_to_3_to_2(self, engine, options):
        migration_api.version_control(options, version=0)
        migration_api.upgrade(options, 2)

        cur_version = migration_api.db_version(options)
        self.assertEquals(2, cur_version)

        # We are now on version 2. Check that the images table does
        # not contain the type column...

        images_table = Table('images', MetaData(), autoload=True,
                             autoload_with=engine)

        image_properties_table = Table('image_properties', MetaData(),
                                       autoload=True,
                                       autoload_with=engine)

        self.assertTrue('type' in images_table.c,
                        "'type' column found in images table columns! "
                        "images table columns: %s"
                        % images_table.c.keys())

        conn = engine.connect()
        sel = select([func.count("*")], from_obj=[images_table])
        orig_num_images = conn.execute(sel).scalar()
        sel = select([func.count("*")], from_obj=[image_properties_table])
        orig_num_image_properties = conn.execute(sel).scalar()

        now = datetime.datetime.now()
        inserter = images_table.insert()
        conn.execute(inserter, [
                {'deleted': False, 'created_at': now,
                 'updated_at': now, 'type': 'kernel',
                 'status': 'active', 'is_public': True},
                {'deleted': False, 'created_at': now,
                 'updated_at': now, 'type': 'ramdisk',
                 'status': 'active', 'is_public': True}])

        sel = select([func.count("*")], from_obj=[images_table])
        num_images = conn.execute(sel).scalar()
        self.assertEqual(orig_num_images + 2, num_images)
        conn.close()

        # Now let's upgrade to 3. This should move the type column
        # to the image_properties table as type properties.

        migration_api.upgrade(options, 3)

        cur_version = migration_api.db_version(options)
        self.assertEquals(3, cur_version)

        images_table = Table('images', MetaData(), autoload=True,
                             autoload_with=engine)

        self.assertTrue('type' not in images_table.c,
                        "'type' column not found in images table columns! "
                        "images table columns reported by metadata: %s\n"
                        % images_table.c.keys())

        image_properties_table = Table('image_properties', MetaData(),
                                       autoload=True,
                                       autoload_with=engine)

        conn = engine.connect()
        sel = select([func.count("*")], from_obj=[image_properties_table])
        num_image_properties = conn.execute(sel).scalar()
        self.assertEqual(orig_num_image_properties + 2, num_image_properties)
        conn.close()

        # Downgrade to 2 and check that the type properties were moved
        # to the main image table

        migration_api.downgrade(options, 2)

        images_table = Table('images', MetaData(), autoload=True,
                             autoload_with=engine)

        self.assertTrue('type' in images_table.c,
                        "'type' column found in images table columns! "
                        "images table columns: %s"
                        % images_table.c.keys())

        image_properties_table = Table('image_properties', MetaData(),
                                       autoload=True,
                                       autoload_with=engine)

        conn = engine.connect()
        sel = select([func.count("*")], from_obj=[image_properties_table])
        last_num_image_properties = conn.execute(sel).scalar()

        self.assertEqual(num_image_properties - 2, last_num_image_properties)
