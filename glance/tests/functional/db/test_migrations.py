# Copyright 2016 Rackspace
# Copyright 2016 Intel Corporation
#
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

import collections
import os

from alembic import command as alembic_command
from alembic import script as alembic_script
from oslo_db.sqlalchemy import enginefacade
from oslo_db.sqlalchemy import test_fixtures
from oslo_db.sqlalchemy import test_migrations
from sqlalchemy import sql
import sqlalchemy.types as types

from glance.db.sqlalchemy import alembic_migrations
from glance.db.sqlalchemy.alembic_migrations import versions
from glance.db.sqlalchemy import models
from glance.db.sqlalchemy import models_metadef
import glance.tests.utils as test_utils


class TestVersions(test_utils.BaseTestCase):
    def test_phase_and_naming(self):
        """Test that migrations follow the conventional rules.

        Each release should have at least one file for each of the required
        phases, if it has one for any of them. They should also be named
        in a consistent way going forward.
        """

        # These are the phases that we require. Each release should have a
        # version for each of these phases, even if some are empty.
        required_phases = set(['expand', 'migrate', 'contract'])

        # The initial migration is special, and mitaka was not done according
        # to convention. Both of those are exceptions to these rules which
        # need not be enforced.
        # NOTE(danms): Do not add anything else to this list! New migrations
        # should follow the rules!
        exception_releases = ['liberty', 'mitaka']

        versions_path, _ = os.path.split(versions.__file__)
        version_files = os.listdir(versions_path)
        version_files += os.listdir(os.path.join(versions_path,
                                                 '..', 'data_migrations'))
        releases = collections.defaultdict(set)
        for version_file in [v for v in version_files if v[0] != '_']:
            # Exception releases get ignored
            if any([version_file.startswith(prefix)
                    for prefix in exception_releases]):
                continue

            # For legacy database scripts does not starts with
            # YYYY i.e. pre Antelope
            if not version_file.split('_', 2)[0].isnumeric():
                # File format should be release_phaseNN_description.py
                try:
                    _rest = ''  # noqa
                    release, phasever, _rest = version_file.split('_', 2)
                except ValueError:
                    release = phasever = ''
                phase = ''.join(x for x in phasever if x.isalpha())
                # Grab the non-numeric part of phaseNN
                if phase not in required_phases:
                    # Help make sure that going forward developers stick to the
                    # consistent format.
                    self.fail('Migration files should be in the form of: '
                              'release_phaseNN_some_description.py '
                              '(while processing %r)' % version_file)
                releases[release].add(phase)
            else:
                # For new database scripts i.e. Antelope onwards
                # File format should be
                # releaseYear_releaseN_phaseNN_description.py
                # For example 2023_1_expand01_empty.py
                try:
                    _rest = ''  # noqa
                    release_y, release_n, phasever, _rest = version_file.split(
                        '_', 3)
                except ValueError:
                    release_y = phasever = ''
                phase = ''.join(x for x in phasever if x.isalpha())
                # Grab the non-numeric part of phaseNN
                if phase not in required_phases:
                    # Help make sure that going forward developers stick to the
                    # consistent format.
                    self.fail('Migration files should be in the form of: '
                              'releaseYear_releaseN_phaseNN_description.py '
                              '(while processing %r)' % version_file)
                releases[release_y].add(phase)

        for release, phases in releases.items():
            missing = required_phases - phases
            if missing:
                self.fail('Release %s missing migration phases %s' % (
                    release, ','.join(missing)))


class AlembicMigrationsMixin(object):

    def setUp(self):
        super(AlembicMigrationsMixin, self).setUp()

        self.engine = enginefacade.writer.get_engine()

    def _get_revisions(self, config, head=None):
        head = head or 'heads'
        scripts_dir = alembic_script.ScriptDirectory.from_config(config)
        revisions = list(scripts_dir.walk_revisions(base='base',
                                                    head=head))
        revisions = list(reversed(revisions))
        revisions = [rev.revision for rev in revisions]
        return revisions

    def _migrate_up(self, config, engine, revision, with_data=False):
        if with_data:
            data = None
            pre_upgrade = getattr(self, '_pre_upgrade_%s' % revision, None)
            if pre_upgrade:
                data = pre_upgrade(engine)

        alembic_command.upgrade(config, revision)

        if with_data:
            check = getattr(self, '_check_%s' % revision, None)
            if check:
                check(engine, data)

    def test_walk_versions(self):
        alembic_config = alembic_migrations.get_alembic_config(self.engine)
        for revision in self._get_revisions(alembic_config):
            self._migrate_up(alembic_config, self.engine, revision,
                             with_data=True)


class TestMysqlMigrations(test_fixtures.OpportunisticDBTestMixin,
                          AlembicMigrationsMixin,
                          test_utils.BaseTestCase):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture

    def test_mysql_innodb_tables(self):
        test_utils.db_sync(engine=self.engine)

        with self.engine.connect() as conn:
            total = conn.execute(
                sql.text(
                    "SELECT COUNT(*) "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=:database"
                ),
                {'database': self.engine.url.database},
            )
        self.assertGreater(total.scalar(), 0, "No tables found. Wrong schema?")

        with self.engine.connect() as conn:
            noninnodb = conn.execute(
                sql.text(
                    "SELECT count(*) "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=:database "
                    "AND ENGINE!='InnoDB' "
                    "AND TABLE_NAME!='migrate_version'"
                ),
                {'database': self.engine.url.database},
            )
            count = noninnodb.scalar()
        self.assertEqual(0, count, "%d non InnoDB tables created" % count)


class TestPostgresqlMigrations(test_fixtures.OpportunisticDBTestMixin,
                               AlembicMigrationsMixin,
                               test_utils.BaseTestCase):
    FIXTURE = test_fixtures.PostgresqlOpportunisticFixture


class TestSqliteMigrations(test_fixtures.OpportunisticDBTestMixin,
                           AlembicMigrationsMixin,
                           test_utils.BaseTestCase):
    pass


class TestMigrations(test_fixtures.OpportunisticDBTestMixin,
                     test_utils.BaseTestCase):

    def test_no_downgrade(self):
        migrate_file = versions.__path__[0]
        for parent, dirnames, filenames in os.walk(migrate_file):
            for filename in filenames:
                if filename.split('.')[1] == 'py':
                    model_name = filename.split('.')[0]
                    model = __import__(
                        'glance.db.sqlalchemy.alembic_migrations.versions.' +
                        model_name)
                    obj = getattr(getattr(getattr(getattr(getattr(
                        model, 'db'), 'sqlalchemy'), 'alembic_migrations'),
                        'versions'), model_name)
                    func = getattr(obj, 'downgrade', None)
                    self.assertIsNone(func)


class ModelsMigrationSyncMixin(object):
    def setUp(self):
        super(ModelsMigrationSyncMixin, self).setUp()
        self.engine = enginefacade.writer.get_engine()

    def get_metadata(self):
        for table in models_metadef.BASE_DICT.metadata.sorted_tables:
            models.BASE.metadata._add_table(table.name, table.schema, table)
        return models.BASE.metadata

    def get_engine(self):
        return self.engine

    def db_sync(self, engine):
        test_utils.db_sync(engine=engine)

    # TODO(akamyshikova): remove this method as soon as comparison with Variant
    # will be implemented in oslo.db or alembic
    def compare_type(self, ctxt, insp_col, meta_col, insp_type, meta_type):
        if isinstance(meta_type, types.Variant):
            meta_orig_type = meta_col.type
            insp_orig_type = insp_col.type
            meta_col.type = meta_type.impl
            insp_col.type = meta_type.impl

            try:
                return self.compare_type(ctxt, insp_col, meta_col, insp_type,
                                         meta_type.impl)
            finally:
                meta_col.type = meta_orig_type
                insp_col.type = insp_orig_type
        else:
            ret = super(ModelsMigrationSyncMixin, self).compare_type(
                ctxt, insp_col, meta_col, insp_type, meta_type)
            if ret is not None:
                return ret
            return ctxt.impl.compare_type(insp_col, meta_col)

    def include_object(self, object_, name, type_, reflected, compare_to):
        if name in ['migrate_version'] and type_ == 'table':
            return False
        return True


class ModelsMigrationsSyncMysql(ModelsMigrationSyncMixin,
                                test_migrations.ModelsMigrationsSync,
                                test_fixtures.OpportunisticDBTestMixin,
                                test_utils.BaseTestCase):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture


class ModelsMigrationsSyncPostgres(ModelsMigrationSyncMixin,
                                   test_migrations.ModelsMigrationsSync,
                                   test_fixtures.OpportunisticDBTestMixin,
                                   test_utils.BaseTestCase):
    FIXTURE = test_fixtures.PostgresqlOpportunisticFixture


class ModelsMigrationsSyncSqlite(ModelsMigrationSyncMixin,
                                 test_migrations.ModelsMigrationsSync,
                                 test_fixtures.OpportunisticDBTestMixin,
                                 test_utils.BaseTestCase):
    pass
