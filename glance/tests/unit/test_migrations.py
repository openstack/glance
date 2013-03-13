# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import commands
import ConfigParser
import datetime
import os
import urlparse

from migrate.versioning.repository import Repository
from oslo.config import cfg
import sqlalchemy

from glance.common import crypt
import glance.db.migration as migration
import glance.db.sqlalchemy.migrate_repo
from glance.db.sqlalchemy.migration import versioning_api as migration_api
from glance.db.sqlalchemy import models
from glance.openstack.common import log as logging
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
from glance.tests import utils


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
            % locals())


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
    as models will be far out of sync with the current data."""
    metadata = sqlalchemy.schema.MetaData()
    metadata.bind = engine
    return sqlalchemy.Table(name, metadata, autoload=True)


class TestMigrations(utils.BaseTestCase):
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
            except ConfigParser.ParsingError, e:
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
            status, output = commands.getstatusoutput(cmd)
            LOG.debug(output)
            self.assertEqual(0, status)
        for key, engine in self.engines.items():
            conn_string = self.test_databases[key]
            conn_pieces = urlparse.urlparse(conn_string)
            engine.dispose()
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
                        password = "-p\"%s\"" % auth_pieces[1]
                sql = ("drop database if exists %(database)s; "
                       "create database %(database)s;") % locals()
                cmd = ("mysql -u \"%(user)s\" %(password)s -h %(host)s "
                       "-e \"%(sql)s\"") % locals()
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
                                "~/.pgpass && chmod 0600 ~/.pgpass" % locals())
                execute_cmd(createpgpass)
                # note(boris-42): We must create and drop database, we can't
                # drop database which we have connected to, so for such
                # operations there is a special database template1.
                sqlcmd = ("psql -w -U %(user)s -h %(host)s -c"
                          " '%(sql)s' -d template1")
                sql = ("drop database if exists %(database)s;") % locals()
                droptable = sqlcmd % locals()
                execute_cmd(droptable)
                sql = ("create database %(database)s;") % locals()
                createtable = sqlcmd % locals()
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

        # Place the database under version control
        init_version = migration.INIT_VERSION
        if initial_version is not None:
            init_version = initial_version
        migration_api.version_control(engine, TestMigrations.REPOSITORY,
                                      init_version)
        self.assertEqual(init_version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

        migration_api.upgrade(engine, TestMigrations.REPOSITORY,
                              init_version + 1)

        LOG.debug('latest version is %s' % TestMigrations.REPOSITORY.latest)

        for version in xrange(init_version + 2,
                              TestMigrations.REPOSITORY.latest + 1):
            # upgrade -> downgrade -> upgrade
            self._migrate_up(engine, version, with_data=True)
            if snake_walk:
                self._migrate_down(engine, version)
                self._migrate_up(engine, version)

        if downgrade:
            # Now walk it back down to 0 from the latest, testing
            # the downgrade paths.
            for version in reversed(
                xrange(init_version + 2,
                       TestMigrations.REPOSITORY.latest + 1)):
                # downgrade -> upgrade -> downgrade
                self._migrate_down(engine, version)
                if snake_walk:
                    self._migrate_up(engine, version)
                    self._migrate_down(engine, version)

    def _migrate_down(self, engine, version):
        migration_api.downgrade(engine,
                                TestMigrations.REPOSITORY,
                                version)
        self.assertEqual(version,
                         migration_api.db_version(engine,
                                                  TestMigrations.REPOSITORY))

    def _migrate_up(self, engine, version, with_data=False):
        """migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _prerun_### and
        _check_### functions in the main test.
        """
        if with_data:
            data = None
            prerun = getattr(self, "_prerun_%3.3d" % version, None)
            if prerun:
                data = prerun(engine)

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

    def _prerun_003(self, engine):
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

    def _prerun_004(self, engine):
        """Insert checksum data sample to check if migration goes fine with
        data"""
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
        self.assertEquals(images.c['checksum'].type.length, 32)

    def _prerun_005(self, engine):
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

    def _prerun_006(self, engine):
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

    def _prerun_015(self, engine):
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
            temp.update(location=location, id=uuidutils.generate_uuid())
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

    def _prerun_016(self, engine):
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

    def _prerun_017(self, engine):
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
            temp.update(location=location, id=uuidutils.generate_uuid())
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
            if not location in actual_location:
                self.fail(_("location: %s data lost") % location)

    def _prerun_019(self, engine):
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
