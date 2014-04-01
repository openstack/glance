# Copyright 2014 Rackspace Hosting
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

import fixtures
import mock
import testtools

import glance
from glance.cmd import manage
from glance.db import migration as db_migration
from glance.db.sqlalchemy import api as db_api
from glance.openstack.common.db.sqlalchemy import migration


class TestManageBase(testtools.TestCase):

    def setUp(self):
        super(TestManageBase, self).setUp()

        def clear_conf():
            manage.CONF.reset()
            manage.CONF.unregister_opt(manage.command_opt)
            manage.CONF.db_enforce_mysql_charset = True
        self.addCleanup(clear_conf)

        self.patcher = mock.patch('glance.db.sqlalchemy.api.get_engine')
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _main_test_helper(self, argv, func_name=None, *exp_args, **exp_kwargs):
        self.useFixture(fixtures.MonkeyPatch('sys.argv', argv))
        manage.main()
        func_name.assert_called_once_with(*exp_args, **exp_kwargs)


class TestLegacyManage(TestManageBase):

    def test_legacy_db_version(self):
        migration.db_version = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_version'],
                               glance.openstack.common.db.sqlalchemy.
                               migration.db_version,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, 0)

    def test_legacy_db_sync(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_sync'],
                               glance.openstack.common.db.sqlalchemy.
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None,
                               sanity_check=True)

    def test_legacy_db_upgrade(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_upgrade'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None,
                               sanity_check=True)

    def test_legacy_db_version_control(self):
        migration.db_version_control = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_version_control'],
                               migration.db_version_control,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None)

    def test_legacy_db_sync_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_sync', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_legacy_db_upgrade_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_upgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_legacy_db_downgrade_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_downgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_legacy_db_sync_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db_sync', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=False)

    def test_legacy_db_upgrade_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db_upgrade', '40'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '40',
                               sanity_check=False)

    def test_legacy_db_downgrade_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db_downgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=False)


class TestManage(TestManageBase):

    def test_db_version(self):
        migration.db_version = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'version'],
                               migration.db_version,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, 0)

    def test_db_sync(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'sync'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None,
                               sanity_check=True)

    def test_db_upgrade(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'upgrade'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None,
                               sanity_check=True)

    def test_db_version_control(self):
        migration.db_version_control = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'version_control'],
                               migration.db_version_control,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, None)

    def test_db_sync_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'sync', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_db_upgrade_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'upgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_db_downgrade_version(self):
        migration.db_sync = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'downgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=True)

    def test_db_sync_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db', 'sync', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, u'20',
                               sanity_check=False)

    def test_db_upgrade_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db', 'upgrade', '40'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '40',
                               sanity_check=False)

    def test_db_downgrade_version_without_sanity_check(self):
        migration.db_sync = mock.Mock()
        manage.CONF.db_enforce_mysql_charset = False
        self._main_test_helper(['glance.cmd.manage', 'db', 'downgrade', '20'],
                               migration.db_sync,
                               db_api.get_engine(),
                               db_migration.MIGRATE_REPO_PATH, '20',
                               sanity_check=False)
