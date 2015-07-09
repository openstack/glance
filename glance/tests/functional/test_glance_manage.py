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

from glance.common import utils
from glance.tests import functional
from glance.tests.utils import depends_on_exe
from glance.tests.utils import execute
from glance.tests.utils import skip_if_disabled


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

    def _sync_db(self):
        with open(self.conf_filepath, 'wb') as conf_file:
            conf_file.write('[DEFAULT]\n')
            conf_file.write(self.connection)
            conf_file.flush()

        cmd = ('%s -m glance.cmd.manage --config-file %s db sync' %
               (sys.executable, self.conf_filepath))
        execute(cmd, raise_error=True)

    def _assert_tables(self):
        cmd = "sqlite3 %s '.schema'" % self.db_filepath
        exitcode, out, err = execute(cmd, raise_error=True)

        self.assertIn('CREATE TABLE images', out)
        self.assertIn('CREATE TABLE image_tags', out)
        self.assertIn('CREATE TABLE image_locations', out)

        # NOTE(bcwaldon): For some reason we need double-quotes around
        # these two table names
        # NOTE(vsergeyev): There are some cases when we have no double-quotes
        self.assertTrue(
            'CREATE TABLE "image_members"' in out or
            'CREATE TABLE image_members' in out)
        self.assertTrue(
            'CREATE TABLE "image_properties"' in out or
            'CREATE TABLE image_properties' in out)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_db_creation(self):
        """Test DB creation by db_sync on a fresh DB"""
        self._sync_db()

        self._assert_tables()
