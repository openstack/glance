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

    def _sync_db(self):
        with open(self.conf_filepath, 'w') as conf_file:
            conf_file.write('[DEFAULT]\n')
            conf_file.write(self.connection)
            conf_file.flush()

        cmd = ('%s -m glance.cmd.manage --config-file %s db sync' %
               (sys.executable, self.conf_filepath))
        execute(cmd, raise_error=True)

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
        self._sync_db()

        for table in ['images', 'image_tags', 'image_locations',
                      'image_members', 'image_properties']:
            self._assert_table_exists(table)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_sync(self):
        """Test DB sync which internally calls EMC"""
        self._sync_db()
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        cmd = ("sqlite3 {0} \"SELECT version_num FROM alembic_version\""
               ).format(self.db_filepath)
        exitcode, out, err = execute(cmd, raise_error=True)
        self.assertEqual(contract_head, out.rstrip().decode("utf-8"))
