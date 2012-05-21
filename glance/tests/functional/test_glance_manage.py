# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

from glance.common import utils
from glance.tests import functional
from glance.tests.utils import execute, depends_on_exe, skip_if_disabled


class TestGlanceManage(functional.FunctionalTest):
    """Functional tests for glance-manage"""

    def setUp(self):
        super(TestGlanceManage, self).setUp()
        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.conf_filepath = os.path.join(conf_dir, 'glance-manage.conf')
        self.db_filepath = os.path.join(conf_dir, 'test.sqlite')
        self.connection = ('sql_connection = sqlite:///%s' %
                           self.db_filepath)

    def _sync_db(self, auto_create):
        with open(self.conf_filepath, 'wb') as conf_file:
            conf_file.write('[DEFAULT]\n')
            conf_file.write('db_auto_create = %r\n' % auto_create)
            conf_file.write(self.connection)
            conf_file.flush()

        cmd = ('bin/glance-manage db_sync --config-file %s' %
               self.conf_filepath)
        execute(cmd, raise_error=True)

    def _assert_tables(self):
        cmd = "sqlite3 %s '.schema'" % self.db_filepath
        exitcode, out, err = execute(cmd, raise_error=True)

        self.assertTrue('CREATE TABLE images' in out)
        self.assertTrue('CREATE TABLE image_tags' in out)
        self.assertTrue('CREATE TABLE image_members' in out)
        self.assertTrue('CREATE TABLE image_properties' in out)

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_db_creation(self):
        """Test DB creation by db_sync on a fresh DB"""
        self._sync_db(True)

        self._assert_tables()

        self.stop_servers()

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_db_creation_auto_create_overridden(self):
        """Test DB creation with db_auto_create False"""
        self._sync_db(False)

        self._assert_tables()

        self.stop_servers()
