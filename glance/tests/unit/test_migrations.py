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

import ConfigParser
import datetime
import exceptions
import os
import pickle
import subprocess
import uuid

from migrate.versioning import api as migration_api
from migrate.versioning.repository import Repository
from oslo.config import cfg
import six.moves.urllib.parse as urlparse
from six.moves import xrange
import sqlalchemy

from glance.common import crypt
from glance.common import exception
from glance.common import utils
import glance.db.migration as migration
import glance.db.sqlalchemy.migrate_repo
from glance.db.sqlalchemy.migrate_repo.schema import from_migration_import
from glance.db.sqlalchemy import models
from glance.openstack.common import jsonutils
from glance.openstack.common import log as logging
from glance.openstack.common import timeutils

from glance.tests import utils as test_utils


CONF = cfg.CONF
CONF.import_opt('metadata_encryption_key', 'glance.common.config')

LOG = logging.getLogger(__name__)


def _get_connect_string(backend,
                        user="openstack_citest",
                        passwd="openstack_citest",
                        database="openstack_citest"):
    """
    Try to get a connection with a very specific set of values, if we get
    these then we'll run the tests, otherwise they are skipped
    """
    if backend == "mysql":
        backend = "mysql+mysqldb"
    elif backend == "postgres":
        backend = "postgresql+psycopg2"

    return ("%(backend)s://%(user)s:%(passwd)s@localhost/%(database)s"
            % {'backend': backend, 'user': user, 'passwd': passwd,
               'database': database})


def _is_backend_avail(backend,
                      user="openstack_citest",
                      passwd="openstack_citest",
                      database="openstack_citest"):
    try:
        if backend == "mysql":
            connect_uri = _get_connect_string("mysql", user=user,
                                              passwd=passwd, database=database)
        elif backend == "postgres":
            connect_uri = _get_connect_string("postgres", user=user,
                                              passwd=passwd, database=database)
        engine = sqlalchemy.create_engine(connect_uri)
        connection = engine.connect()
    except Exception:
        # intentionally catch all to handle exceptions even if we don't
        # have any backend code loaded.
        return False
    else:
        connection.close()
        engine.dispose()
        return True


def _have_mysql():
    present = os.environ.get('GLANCE_TEST_MYSQL_PRESENT')
    if present is None:
        return _is_backend_avail('mysql')
    return present.lower() in ('', 'true')


def get_table(engine, name):
    """Returns an sqlalchemy table dynamically from db.

    Needed because the models don't work for us in migrations
    as models will be far out of sync with the current data.
    """
    metadata = sqlalchemy.schema.MetaData()
    metadata.bind = engine
    return sqlalchemy.Table(name, metadata, autoload=True)


class TestMigrations(test_utils.BaseTestCase):
    """Test sqlalchemy-migrate migrations."""

    DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                       'test_migrations.conf')
    # Test machines can set the GLANCE_TEST_MIGRATIONS_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_MIGRATIONS_CONF',
                                      DEFAULT_CONFIG_FILE)
    MIGRATE_FILE = glance.db.sqlalchemy.migrate_repo.__file__
    REPOSITORY = Repository(os.path.abspath(os.path.dirname(MIGRATE_FILE)))

    def setUp(self):
        super(TestMigrations, self).setUp()

        self.snake_walk = False
        self.test_databases = {}

        # Load test databases from the config file. Only do this
        # once. No need to re-run this on each test...
        LOG.debug('config_path is %s' % TestMigrations.CONFIG_FILE_PATH)
        if os.path.exists(TestMigrations.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestMigrations.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.test_databases[key] = value
                self.snake_walk = cp.getboolean('walk_style', 'snake_walk')
            except ConfigParser.ParsingError as e:
                self.fail("Failed to read test_migrations.conf config "
                          "file. Got error: %s" % e)
        else:
            self.fail("Failed to find test_migrations.conf config "
                      "file.")

        self.engines = {}
        for key, value in self.test_databases.items():
            self.engines[key] = sqlalchemy.create_engine(value)

        # We start each test case with a completely blank slate.
        self._reset_databases()

    def tearDown(self):
        # We destroy the test data store between each test case,
        # and recreate it, which ensures that we have no side-effects
        # from the tests
        self._reset_databases()
        super(TestMigrations, self).tearDown()

    def _reset_databases(self):
        def execute_cmd(cmd=None):
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, shell=True)
            output = proc.communicate()[0]
            LOG.debug(output)
            self.assertEqual(0, proc.returncode)

        for key, engine in self.engines.items():
            conn_string = self.test_databases[key]
            conn_pieces = urlparse.urlparse(conn_string)
            engine.dispose()
            if conn_string.startswith('sqlite'):
                # We can just delete the SQLite database, which is
                # the easiest and cleanest solution
                db_path = conn_pieces.path[1:]
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
                        password = "-p\"%s\"" % auth_pieces[1]
                sql = ("drop database if exists %(database)s; create "
                       "database %(database)s;") % {'database': database}
                cmd = ("mysql -u \"%(user)s\" %(password)s -h %(host)s "
                       "-e \"%(sql)s\"") % {'user': user, 'password': password,
                                            'host': host, 'sql': sql}
                execute_cmd(cmd)
            elif conn_string.startswith('postgresql'):
                database = conn_pieces.path.strip('/')
                loc_pieces = conn_pieces.netloc.split('@')
                host = loc_pieces[1]

                auth_pieces = loc_pieces[0].split(':')
                user = auth_pieces[0]
                password = ""
                if len(auth_pieces) > 1:
                    password = auth_pieces[1].strip()
                # note(boris-42): This file is used for authentication
                # without password prompt.
                createpgpass = ("echo '*:*:*:%(user)s:%(password)s' > "
                                "~/.pgpass && chmod 0600 ~/.pgpass" %
                                {'user': user, 'password': password})
                execute_cmd(createpgpass)
                # note(boris-42): We must create and drop database, we can't
                # drop database which we have connected to, so for such
                # operations there is a special database template1.
                sqlcmd = ("psql -w -U %(user)s -h %(host)s -c"
                          " '%(sql)s' -d template1")
                sql = ("drop database if exists %(database)s;")
                sql = sql % {'database': database}
                droptable = sqlcmd % {'user': user, 'host': host,
                                      'sql': sql}
                execute_cmd(droptable)
                sql = ("create database %(database)s;")
                sql = sql % {'database': database}
                createtable = sqlcmd % {'user': user, 'host': host,
                                        'sql': sql}
                execute_cmd(createtable)

    def test_walk_versions(self):
        """
        Walks all version scripts for each tested database, ensuring
        that there are no errors in the version scripts for each engine
        """
        for key, engine in self.engines.items():
            self._walk_versions(engine, self.snake_walk)

    def test_mysql_connect_fail(self):
        """
        Test that we can trigger a mysql connection failure and we fail
        gracefully to ensure we don't break people without mysql
        """
        if _is_backend_avail('mysql', user="openstack_cifail"):
            self.fail("Shouldn't have connected")

    def test_mysql_opportunistically(self):
        # Test that table creation on mysql only builds InnoDB tables
        if not _is_backend_avail('mysql'):
            self.skipTest("mysql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("mysql")
        engine = sqlalchemy.create_engine(connect_string)
        self.engines["mysqlcitest"] = engine
        self.test_databases["mysqlcitest"] = connect_string

        # build a fully populated mysql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

        connection = engine.connect()
        # sanity check
        total = connection.execute("SELECT count(*) "
                                   "from information_schema.TABLES "
                                   "where TABLE_SCHEMA='openstack_citest'")
        self.assertTrue(total.scalar() > 0, "No tables found. Wrong schema?")

        noninnodb = connection.execute("SELECT count(*) "
                                       "from information_schema.TABLES "
                                       "where TABLE_SCHEMA='openstack_citest' "
                                       "and ENGINE!='InnoDB' "
                                       "and TABLE_NAME!='migrate_version'")
        count = noninnodb.scalar()
        self.assertEqual(count, 0, "%d non InnoDB tables created" % count)
        connection.close()

    def test_postgresql_connect_fail(self):
        """
        Test that we can trigger a postgres connection failure and we fail
        gracefully to ensure we don't break people without postgres
        """
        if _is_backend_avail('postgresql', user="openstack_cifail"):
            self.fail("Shouldn't have connected")

    def test_postgresql_opportunistically(self):
        # Test postgresql database migration walk
        if not _is_backend_avail('postgres'):
            self.skipTest("postgresql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("postgres")
        engine = sqlalchemy.create_engine(connect_string)
        self.engines["postgresqlcitest"] = engine
        self.test_databases["postgresqlcitest"] = connect_string

        # build a fully populated postgresql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

    def _walk_versions(self, engine=None, snake_walk=False, downgrade=True,
                       initial_version=None):
        # Determine latest version script from the repo, then
        # upgrade from 1 through to the latest, with no data
        # in the databases. This just checks that the schema itself
        # upgrades successfully.

        def db_version():
            return migration_api.db_version(engine, TestMigrations.REPOSITORY)

        # Place the database under version control
        init_version = migration.INIT_VERSION
        if initial_version is not None:
            init_version = initial_version
        migration_api.version_control(engine, TestMigrations.REPOSITORY,
                                      init_version)
        self.assertEqual(init_version, db_version())

        migration_api.upgrade(engine, TestMigrations.REPOSITORY,
                              init_version + 1)
        self.assertEqual(init_version + 1, db_version())

        LOG.debug('latest version is %s' % TestMigrations.REPOSITORY.latest)

        for version in xrange(init_version + 2,
                              TestMigrations.REPOSITORY.latest + 1):
            # upgrade -> downgrade -> upgrade
            self._migrate_up(engine, version, with_data=True)
            if snake_walk:
                self._migrate_down(engine, version - 1, with_data=True)
                self._migrate_up(engine, version)

        if downgrade:
            # Now walk it back down to 0 from the latest, testing
            # the downgrade paths.
            for version in reversed(
                xrange(init_version + 2,
                       TestMigrations.REPOSITORY.latest + 1)):
                # downgrade -> upgrade -> downgrade
                self._migrate_down(engine, version - 1)
                if snake_walk:
                    self._migrate_up(engine, version)
                    self._migrate_down(engine, version - 1)

            # Ensure we made it all the way back to the first migration
            self.assertEqual(init_version + 1, db_version())

    def _migrate_down(self, engine, version, with_data=False):
        migration_api.downgrade(engine,
                                TestMigrations.REPOSITORY,
                                version)
        self.assertEqual(version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

        # NOTE(sirp): `version` is what we're downgrading to (i.e. the 'target'
        # version). So if we have any downgrade checks, they need to be run for
        # the previous (higher numbered) migration.
        if with_data:
            post_downgrade = getattr(self, "_post_downgrade_%03d" %
                                           (version + 1), None)
            if post_downgrade:
                post_downgrade(engine)

    def _migrate_up(self, engine, version, with_data=False):
        """migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _pre_upgrade_### and
        _check_### functions in the main test.
        """
        if with_data:
            data = None
            pre_upgrade = getattr(self, "_pre_upgrade_%3.3d" % version, None)
            if pre_upgrade:
                data = pre_upgrade(engine)

        migration_api.upgrade(engine,
                              TestMigrations.REPOSITORY,
                              version)
        self.assertEqual(version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

        if with_data:
            check = getattr(self, "_check_%3.3d" % version, None)
            if check:
                check(engine, data)

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
                                                        default=False))
        images_001.create()

    def test_version_control_existing_db(self):
        """
        Creates a DB without version control information, places it
        under version control and checks that it can be upgraded
        without errors.
        """
        for key, engine in self.engines.items():
            self._create_unversioned_001_db(engine)
            self._walk_versions(engine, self.snake_walk, initial_version=1)

    def _pre_upgrade_003(self, engine):
        now = datetime.datetime.now()
        images = get_table(engine, 'images')
        data = {'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True}
        images.insert().values(data).execute()
        return data

    def _check_003(self, engine, data):
        images = get_table(engine, 'images')
        self.assertTrue('type' not in images.c,
                        "'type' column found in images table columns! "
                        "images table columns reported by metadata: %s\n"
                        % images.c.keys())
        images_prop = get_table(engine, 'image_properties')
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
        images = get_table(engine, 'images')
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
        images = get_table(engine, 'images')
        self.assertIn('checksum', images.c)
        self.assertEqual(images.c['checksum'].type.length, 32)

    def _pre_upgrade_005(self, engine):
        now = timeutils.utcnow()
        images = get_table(engine, 'images')
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

        images = get_table(engine, 'images')
        select = images.select().execute()

        sizes = [row['size'] for row in select if row['size'] is not None]
        migrated_data_sizes = [element['size'] for element in data]

        for migrated in migrated_data_sizes:
            self.assertIn(migrated, sizes)

    def _pre_upgrade_006(self, engine):
        now = timeutils.utcnow()
        images = get_table(engine, 'images')
        image_data = [
            {
                'deleted': False, 'created_at': now, 'updated_at': now,
                'type': 'kernel', 'status': 'active', 'is_public': True,
                'id': 9999,
            }
        ]
        engine.execute(images.insert(), image_data)

        images_properties = get_table(engine, 'image_properties')
        properties_data = [
            {
                'id': 10, 'image_id': 9999, 'updated_at': now,
                'created_at': now, 'deleted': False, 'key': 'image_name'
            }
        ]
        engine.execute(images_properties.insert(), properties_data)
        return properties_data

    def _check_006(self, engine, data):
        images_properties = get_table(engine, 'image_properties')
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

        images = get_table(engine, 'images')
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
        values = dict((c, u) for c, u in data)

        images = get_table(engine, 'images')
        for row in images.select().execute():
            if row['created_at'] in values:
                # updated_at should be unchanged if not previous NULL, or
                # set to created_at if previously NULL
                updated_at = values.pop(row['created_at']) or row['created_at']
                self.assertEqual(row['updated_at'], updated_at)

        # No initial values should be remaining
        self.assertEqual(len(values), 0)

    def _pre_upgrade_012(self, engine):
        """Test rows in images have id changes from int to varchar(32) and
        value changed from int to UUID. Also test image_members and
        image_properties gets updated to point to new UUID keys.
        """

        images = get_table(engine, 'images')
        image_members = get_table(engine, 'image_members')
        image_properties = get_table(engine, 'image_properties')

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
        images = get_table(engine, 'images')
        image_members = get_table(engine, 'image_members')
        image_properties = get_table(engine, 'image_properties')

        # Find kernel, ramdisk and normal images. Make sure id has been
        # changed to a uuid
        uuids = {}
        for name in ('kernel', 'ramdisk', 'normal'):
            image_name = '%s migration 012 test' % name
            rows = images.select()\
                         .where(images.c.name == image_name)\
                         .execute().fetchall()

            self.assertEqual(len(rows), 1)

            row = rows[0]
            self.assertTrue(utils.is_uuid_like(row['id']))

            uuids[name] = row['id']

        # Find all image_members to ensure image_id has been updated
        results = image_members.select()\
                               .where(image_members.c.image_id ==
                                      uuids['normal'])\
                               .execute().fetchall()
        self.assertEqual(len(results), 1)

        # Find all image_properties to ensure image_id has been updated
        # as well as ensure kernel_id and ramdisk_id values have been
        # updated too
        results = image_properties.select()\
                                  .where(image_properties.c.image_id ==
                                         uuids['normal'])\
                                  .execute().fetchall()
        self.assertEqual(len(results), 2)
        for row in results:
            self.assertIn(row['name'], ('kernel_id', 'ramdisk_id'))

            if row['name'] == 'kernel_id':
                self.assertEqual(row['value'], uuids['kernel'])
            if row['name'] == 'ramdisk_id':
                self.assertEqual(row['value'], uuids['ramdisk'])

    def _post_downgrade_012(self, engine):
        images = get_table(engine, 'images')
        image_members = get_table(engine, 'image_members')
        image_properties = get_table(engine, 'image_properties')

        # Find kernel, ramdisk and normal images. Make sure id has been
        # changed back to an integer
        ids = {}
        for name in ('kernel', 'ramdisk', 'normal'):
            image_name = '%s migration 012 test' % name
            rows = images.select()\
                         .where(images.c.name == image_name)\
                         .execute().fetchall()
            self.assertEqual(len(rows), 1)

            row = rows[0]
            self.assertFalse(utils.is_uuid_like(row['id']))

            ids[name] = row['id']

        # Find all image_members to ensure image_id has been updated
        results = image_members.select()\
                               .where(image_members.c.image_id ==
                                      ids['normal'])\
                               .execute().fetchall()
        self.assertEqual(len(results), 1)

        # Find all image_properties to ensure image_id has been updated
        # as well as ensure kernel_id and ramdisk_id values have been
        # updated too
        results = image_properties.select()\
                                  .where(image_properties.c.image_id ==
                                         ids['normal'])\
                                  .execute().fetchall()
        self.assertEqual(len(results), 2)
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
        self.assertRaises(exceptions.AssertionError,
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
        images = get_table(engine, 'images')
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
        images = get_table(engine, 'images')
        quoted_locations = [
            'swift://acct%3Ausr:pass@example.com/container/obj-id',
            'file://foo',
        ]
        result = images.select().execute()
        locations = map(lambda x: x['location'], result)
        for loc in quoted_locations:
            self.assertIn(loc, locations)

    def _pre_upgrade_016(self, engine):
        images = get_table(engine, 'images')
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
        image_members = get_table(engine, 'image_members')
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
        image_members = get_table(engine, 'image_members')
        self.assertTrue('status' in image_members.c,
                        "'status' column found in image_members table "
                        "columns! image_members table columns: %s"
                        % image_members.c.keys())

    def test_legacy_parse_swift_uri_017(self):
        metadata_encryption_key = 'a' * 16
        self.config(metadata_encryption_key=metadata_encryption_key)

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
        self.config(metadata_encryption_key=metadata_encryption_key)
        images = get_table(engine, 'images')
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
        images = get_table(engine, 'images')
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
        images = get_table(engine, 'images')
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
            #NOTE(bcwaldon): images with a location of None should
            # not be migrated
            {'id': 'fake-19-2', 'location': None},
        ]
        map(lambda image: image.update(base_values), data)
        for image in data:
            images.insert().values(image).execute()
        return data

    def _check_019(self, engine, data):
        image_locations = get_table(engine, 'image_locations')
        records = image_locations.select().execute().fetchall()
        locations = dict([(il.image_id, il.value) for il in records])
        self.assertEqual(locations.get('fake-19-1'),
                         'http://glance.example.com')

    def _check_020(self, engine, data):
        images = get_table(engine, 'images')
        self.assertFalse('location' in images.c)

    def _pre_upgrade_026(self, engine):
        image_locations = get_table(engine, 'image_locations')

        now = datetime.datetime.now()
        image_id = 'fake_id'
        url = 'file:///some/place/onthe/fs'

        images = get_table(engine, 'images')
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
        image_locations = get_table(engine, 'image_locations')
        results = image_locations.select()\
            .where(image_locations.c.image_id == data).execute()

        r = list(results)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['value'], 'file:///some/place/onthe/fs')
        self.assertTrue('meta_data' in r[0])
        x = pickle.loads(r[0]['meta_data'])
        self.assertEqual(x, {})

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

        images_table = get_table(engine, 'images')

        index_data = [(idx.name, idx.columns.keys())
                      for idx in images_table.indexes
                      if idx.name == owner_index]

        self.assertIn((owner_index, columns), index_data)

    def _post_downgrade_028(self, engine):
        owner_index = "owner_image_idx"
        columns = ["owner"]

        images_table = get_table(engine, 'images')

        index_data = [(idx.name, idx.columns.keys())
                      for idx in images_table.indexes
                      if idx.name == owner_index]

        self.assertNotIn((owner_index, columns), index_data)

    def _pre_upgrade_029(self, engine):
        image_locations = get_table(engine, 'image_locations')

        meta_data = {'somelist': ['a', 'b', 'c'], 'avalue': 'hello',
                     'adict': {}}

        now = datetime.datetime.now()
        image_id = 'fake_029_id'
        url = 'file:///some/place/onthe/fs029'

        images = get_table(engine, 'images')
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
        image_locations = get_table(engine, 'image_locations')

        records = image_locations.select().\
            where(image_locations.c.image_id == image_id).execute().fetchall()

        for r in records:
            d = jsonutils.loads(r['meta_data'])
            self.assertEqual(d, meta_data)

    def _post_downgrade_029(self, engine):
        image_id = 'fake_029_id'

        image_locations = get_table(engine, 'image_locations')

        records = image_locations.select().\
            where(image_locations.c.image_id == image_id).execute().fetchall()

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
                          get_table, engine, 'tasks')

    def _pre_upgrade_031(self, engine):
        images = get_table(engine, 'images')
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

        locations_table = get_table(engine, 'image_locations')
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
        locations_table = get_table(engine, 'image_locations')
        result = locations_table.select()\
                                .where(locations_table.c.image_id == image_id)\
                                .execute().fetchall()

        locations = set([(x['value'], x['meta_data']) for x in result])
        actual_locations = set([
            ('file://ab', '{"a": "yo yo"}'),
            ('file://ab', '{}'),
            ('file://ab1', '{"a": "that one, please"}'),
        ])
        self.assertFalse(actual_locations.symmetric_difference(locations))

    def _pre_upgrade_032(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'task_info')

        tasks = get_table(engine, 'tasks')
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
        task_info_table = get_table(engine, 'task_info')

        task_info_refs = task_info_table.select().execute().fetchall()

        self.assertEqual(len(task_info_refs), 2)

        for x in range(len(task_info_refs)):
            self.assertEqual(task_info_refs[x].task_id, data[x]['id'])
            self.assertEqual(task_info_refs[x].input, data[x]['input'])
            self.assertEqual(task_info_refs[x].result, data[x]['result'])
            self.assertIsNone(task_info_refs[x].message)

        tasks_table = get_table(engine, 'tasks')
        self.assertNotIn('input', tasks_table.c)
        self.assertNotIn('result', tasks_table.c)
        self.assertNotIn('message', tasks_table.c)

    def _post_downgrade_032(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'task_info')

        tasks_table = get_table(engine, 'tasks')
        records = tasks_table.select().execute().fetchall()
        self.assertEqual(len(records), 2)

        tasks = dict([(t.id, t) for t in records])

        task_1 = tasks.get('task-1')
        self.assertEqual(task_1.input, 'some input')
        self.assertEqual(task_1.result, 'successful')
        self.assertIsNone(task_1.message)

        task_2 = tasks.get('task-2')
        self.assertIsNone(task_2.input)
        self.assertIsNone(task_2.result)
        self.assertIsNone(task_2.message)

    def _pre_upgrade_033(self, engine):
        images = get_table(engine, 'images')
        image_locations = get_table(engine, 'image_locations')

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
        image_locations = get_table(engine, 'image_locations')

        self.assertIn('status', image_locations.c)
        self.assertEqual(image_locations.c['status'].type.length, 30)

        status_list = ['active', 'active', 'active',
                       'deleted', 'pending_delete', 'deleted']

        for (idx, image_id) in enumerate(data):
            results = image_locations.select()\
                .where(image_locations.c.image_id == image_id).execute()
            r = list(results)
            self.assertEqual(len(r), 1)
            self.assertTrue('status' in r[0])
            self.assertEqual(r[0]['status'], status_list[idx])

    def _post_downgrade_033(self, engine):
        image_locations = get_table(engine, 'image_locations')
        self.assertNotIn('status', image_locations.c)

    def _pre_upgrade_034(self, engine):
        images = get_table(engine, 'images')

        now = datetime.datetime.now()
        image_id = 'fake_id_034'
        temp = dict(deleted=False,
                    created_at=now,
                    updated_at=now,
                    status='active',
                    is_public=True,
                    min_disk=0,
                    min_ram=0,
                    id=image_id)
        images.insert().values(temp).execute()

    def _check_034(self, engine, data):
        images = get_table(engine, 'images')
        self.assertIn('virtual_size', images.c)

        result = (images.select()
                  .where(images.c.id == 'fake_id_034')
                  .execute().fetchone())
        self.assertIsNone(result.virtual_size)

    def _post_downgrade_034(self, engine):
        images = get_table(engine, 'images')
        self.assertNotIn('virtual_size', images.c)
