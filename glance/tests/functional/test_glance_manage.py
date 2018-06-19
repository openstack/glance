# Copyright 2012 Red Hat, Inc
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

"""Functional test cases for glance-manage"""

import os
import sys

from oslo_config import cfg
from oslo_db import options as db_options

from glance.common import utils
from glance.db import migration as db_migration
from glance.db.sqlalchemy import alembic_migrations
from glance.db.sqlalchemy.alembic_migrations import data_migrations
from glance.db.sqlalchemy import api as db_api
from glance.tests import functional
from glance.tests.utils import depends_on_exe
from glance.tests.utils import execute
from glance.tests.utils import skip_if_disabled

CONF = cfg.CONF


class TestGlanceManage(functional.FunctionalTest):
    """Functional tests for glance-manage"""

    def setUp(self):
        super(TestGlanceManage, self).setUp()
        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.conf_filepath = os.path.join(conf_dir, 'glance-manage.conf')
        self.db_filepath = os.path.join(self.test_dir, 'tests.sqlite')
        self.connection = ('sql_connection = sqlite:///%s' %
                           self.db_filepath)
        db_options.set_defaults(CONF, connection='sqlite:///%s' %
                                                 self.db_filepath)

    def _db_command(self, db_method):
        with open(self.conf_filepath, 'w') as conf_file:
            conf_file.write('[DEFAULT]\n')
            conf_file.write(self.connection)
            conf_file.flush()

        cmd = ('%s -m glance.cmd.manage --config-file %s db %s' %
               (sys.executable, self.conf_filepath, db_method))
        return execute(cmd, raise_error=True)

    def _check_db(self, expected_exitcode):
        with open(self.conf_filepath, 'w') as conf_file:
            conf_file.write('[DEFAULT]\n')
            conf_file.write(self.connection)
            conf_file.flush()

        cmd = ('%s -m glance.cmd.manage --config-file %s db check' %
               (sys.executable, self.conf_filepath))
        exitcode, out, err = execute(cmd, raise_error=True,
                                     expected_exitcode=expected_exitcode)
        return exitcode, out

    def _assert_table_exists(self, db_table):
        cmd = ("sqlite3 {0} \"SELECT name FROM sqlite_master WHERE "
               "type='table' AND name='{1}'\"").format(self.db_filepath,
                                                       db_table)
        exitcode, out, err = execute(cmd, raise_error=True)
        msg = "Expected table {0} was not found in the schema".format(db_table)
        self.assertEqual(out.rstrip().decode("utf-8"), db_table, msg)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_db_creation(self):
        """Test schema creation by db_sync on a fresh DB"""
        self._db_command(db_method='sync')

        for table in ['images', 'image_tags', 'image_locations',
                      'image_members', 'image_properties']:
            self._assert_table_exists(table)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_sync(self):
        """Test DB sync which internally calls EMC"""
        self._db_command(db_method='sync')
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        cmd = ("sqlite3 {0} \"SELECT version_num FROM alembic_version\""
               ).format(self.db_filepath)
        exitcode, out, err = execute(cmd, raise_error=True)
        self.assertEqual(contract_head, out.rstrip().decode("utf-8"))

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_check(self):
        exitcode, out = self._check_db(3)
        self.assertEqual(3, exitcode)

        self._db_command(db_method='expand')
        if data_migrations.has_pending_migrations(db_api.get_engine()):
            exitcode, out = self._check_db(4)
            self.assertEqual(4, exitcode)

        self._db_command(db_method='migrate')
        exitcode, out = self._check_db(5)
        self.assertEqual(5, exitcode)

        self._db_command(db_method='contract')
        exitcode, out = self._check_db(0)
        self.assertEqual(0, exitcode)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_expand(self):
        """Test DB expand"""
        self._db_command(db_method='expand')
        expand_head = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)

        cmd = ("sqlite3 {0} \"SELECT version_num FROM alembic_version\""
               ).format(self.db_filepath)
        exitcode, out, err = execute(cmd, raise_error=True)
        self.assertEqual(expand_head, out.rstrip().decode("utf-8"))
        exitcode, out, err = self._db_command(db_method='expand')
        self.assertIn('Database expansion is up to date. '
                      'No expansion needed.', str(out))

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_migrate(self):
        """Test DB migrate"""
        self._db_command(db_method='expand')
        if data_migrations.has_pending_migrations(db_api.get_engine()):
            self._db_command(db_method='migrate')
        expand_head = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)

        cmd = ("sqlite3 {0} \"SELECT version_num FROM alembic_version\""
               ).format(self.db_filepath)
        exitcode, out, err = execute(cmd, raise_error=True)
        self.assertEqual(expand_head, out.rstrip().decode("utf-8"))
        self.assertEqual(False, data_migrations.has_pending_migrations(
            db_api.get_engine()))
        if data_migrations.has_pending_migrations(db_api.get_engine()):
            exitcode, out, err = self._db_command(db_method='migrate')
            self.assertIn('Database migration is up to date. No migration '
                          'needed.', str(out))

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_contract(self):
        """Test DB contract"""
        self._db_command(db_method='expand')
        if data_migrations.has_pending_migrations(db_api.get_engine()):
            self._db_command(db_method='migrate')
        self._db_command(db_method='contract')
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        cmd = ("sqlite3 {0} \"SELECT version_num FROM alembic_version\""
               ).format(self.db_filepath)
        exitcode, out, err = execute(cmd, raise_error=True)
        self.assertEqual(contract_head, out.rstrip().decode("utf-8"))
        exitcode, out, err = self._db_command(db_method='contract')
        self.assertIn('Database is up to date. No migrations needed.',
                      str(out))
