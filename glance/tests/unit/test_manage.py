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

from __future__ import absolute_import

import fixtures
import mock
from six.moves import StringIO

from glance.cmd import manage
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import metadata as db_metadata
from glance.tests import utils as test_utils


class TestManageBase(test_utils.BaseTestCase):

    def setUp(self):
        super(TestManageBase, self).setUp()

        def clear_conf():
            manage.CONF.reset()
            manage.CONF.unregister_opt(manage.command_opt)
        clear_conf()
        self.addCleanup(clear_conf)

        self.useFixture(fixtures.MonkeyPatch(
            'oslo_log.log.setup', lambda product_name, version='test': None))

        patcher = mock.patch('glance.db.sqlalchemy.api.get_engine')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _main_test_helper(self, argv, func_name=None, *exp_args, **exp_kwargs):
        self.useFixture(fixtures.MonkeyPatch('sys.argv', argv))
        manage.main()
        func_name.assert_called_once_with(*exp_args, **exp_kwargs)


class TestLegacyManage(TestManageBase):

    @mock.patch.object(manage.DbCommands, 'version')
    def test_legacy_db_version(self, db_upgrade):
        self._main_test_helper(['glance.cmd.manage', 'db_version'],
                               manage.DbCommands.version)

    @mock.patch.object(manage.DbCommands, 'sync')
    def test_legacy_db_sync(self, db_sync):
        self._main_test_helper(['glance.cmd.manage', 'db_sync'],
                               manage.DbCommands.sync, None)

    @mock.patch.object(manage.DbCommands, 'upgrade')
    def test_legacy_db_upgrade(self, db_upgrade):
        self._main_test_helper(['glance.cmd.manage', 'db_upgrade'],
                               manage.DbCommands.upgrade, None)

    @mock.patch.object(manage.DbCommands, 'version_control')
    def test_legacy_db_version_control(self, db_version_control):
        self._main_test_helper(['glance.cmd.manage', 'db_version_control'],
                               manage.DbCommands.version_control, None)

    @mock.patch.object(manage.DbCommands, 'sync')
    def test_legacy_db_sync_version(self, db_sync):
        self._main_test_helper(['glance.cmd.manage', 'db_sync', 'liberty'],
                               manage.DbCommands.sync, 'liberty')

    @mock.patch.object(manage.DbCommands, 'upgrade')
    def test_legacy_db_upgrade_version(self, db_upgrade):
        self._main_test_helper(['glance.cmd.manage', 'db_upgrade', 'liberty'],
                               manage.DbCommands.upgrade, 'liberty')

    @mock.patch.object(manage.DbCommands, 'expand')
    def test_legacy_db_expand(self, db_expand):
        self._main_test_helper(['glance.cmd.manage', 'db_expand'],
                               manage.DbCommands.expand)

    @mock.patch.object(manage.DbCommands, 'migrate')
    def test_legacy_db_migrate(self, db_migrate):
        self._main_test_helper(['glance.cmd.manage', 'db_migrate'],
                               manage.DbCommands.migrate)

    @mock.patch.object(manage.DbCommands, 'contract')
    def test_legacy_db_contract(self, db_contract):
        self._main_test_helper(['glance.cmd.manage', 'db_contract'],
                               manage.DbCommands.contract)

    def test_db_metadefs_unload(self):
        db_metadata.db_unload_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_unload_metadefs'],
                               db_metadata.db_unload_metadefs,
                               db_api.get_engine())

    def test_db_metadefs_load(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_load_metadefs'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               None, None, None, None)

    def test_db_metadefs_load_with_specified_path(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_load_metadefs',
                                '/mock/'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', None, None, None)

    def test_db_metadefs_load_from_path_merge(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_load_metadefs',
                                '/mock/', 'True'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', 'True', None, None)

    def test_db_metadefs_load_from_merge_and_prefer_new(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_load_metadefs',
                                '/mock/', 'True', 'True'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', 'True', 'True', None)

    def test_db_metadefs_load_from_merge_and_prefer_new_and_overwrite(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_load_metadefs',
                                '/mock/', 'True', 'True', 'True'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', 'True', 'True', 'True')

    def test_db_metadefs_export(self):
        db_metadata.db_export_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_export_metadefs'],
                               db_metadata.db_export_metadefs,
                               db_api.get_engine(),
                               None)

    def test_db_metadefs_export_with_specified_path(self):
        db_metadata.db_export_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db_export_metadefs',
                               '/mock/'],
                               db_metadata.db_export_metadefs,
                               db_api.get_engine(),
                               '/mock/')


class TestManage(TestManageBase):

    def setUp(self):
        super(TestManage, self).setUp()
        self.db = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    @mock.patch('glance.db.sqlalchemy.api.get_engine')
    @mock.patch(
        'glance.db.sqlalchemy.alembic_migrations.data_migrations.'
        'has_pending_migrations')
    @mock.patch(
        'glance.db.sqlalchemy.alembic_migrations.get_current_alembic_heads')
    @mock.patch(
        'glance.db.sqlalchemy.alembic_migrations.get_alembic_branch_head')
    def test_db_check_result(self, mock_get_alembic_branch_head,
                             mock_get_current_alembic_heads,
                             mock_has_pending_migrations,
                             get_mock_engine):

        get_mock_engine.return_value = mock.Mock()
        engine = get_mock_engine.return_value
        engine.engine.name = 'postgresql'
        exit = self.assertRaises(SystemExit, self.db.check)
        self.assertIn('Rolling upgrades are currently supported only for '
                      'MySQL and Sqlite', exit.code)

        engine = get_mock_engine.return_value
        engine.engine.name = 'mysql'

        mock_get_current_alembic_heads.return_value = ['ocata_contract01']
        mock_get_alembic_branch_head.return_value = 'pike_expand01'
        exit = self.assertRaises(SystemExit, self.db.check)
        self.assertEqual(3, exit.code)
        self.assertIn('Your database is not up to date. '
                      'Your first step is to run `glance-manage db expand`.',
                      self.output.getvalue())

        mock_get_current_alembic_heads.return_value = ['pike_expand01']
        mock_get_alembic_branch_head.side_effect = ['pike_expand01', None]
        mock_has_pending_migrations.return_value = [mock.Mock()]
        exit = self.assertRaises(SystemExit, self.db.check)
        self.assertEqual(4, exit.code)
        self.assertIn('Your database is not up to date. '
                      'Your next step is to run `glance-manage db migrate`.',
                      self.output.getvalue())

        mock_get_current_alembic_heads.return_value = ['pike_expand01']
        mock_get_alembic_branch_head.side_effect = ['pike_expand01',
                                                    'pike_contract01']
        mock_has_pending_migrations.return_value = None
        exit = self.assertRaises(SystemExit, self.db.check)
        self.assertEqual(5, exit.code)
        self.assertIn('Your database is not up to date. '
                      'Your next step is to run `glance-manage db contract`.',
                      self.output.getvalue())

        mock_get_current_alembic_heads.return_value = ['pike_contract01']
        mock_get_alembic_branch_head.side_effect = ['pike_expand01',
                                                    'pike_contract01']
        mock_has_pending_migrations.return_value = None
        self.assertRaises(SystemExit, self.db.check)
        self.assertIn('Database is up to date. No upgrades needed.',
                      self.output.getvalue())

    @mock.patch.object(manage.DbCommands, 'version')
    def test_db_version(self, version):
        self._main_test_helper(['glance.cmd.manage', 'db', 'version'],
                               manage.DbCommands.version)

    @mock.patch.object(manage.DbCommands, 'check')
    def test_db_check(self, check):
        self._main_test_helper(['glance.cmd.manage', 'db', 'check'],
                               manage.DbCommands.check)

    @mock.patch.object(manage.DbCommands, 'sync')
    def test_db_sync(self, sync):
        self._main_test_helper(['glance.cmd.manage', 'db', 'sync'],
                               manage.DbCommands.sync)

    @mock.patch.object(manage.DbCommands, 'upgrade')
    def test_db_upgrade(self, upgrade):
        self._main_test_helper(['glance.cmd.manage', 'db', 'upgrade'],
                               manage.DbCommands.upgrade)

    @mock.patch.object(manage.DbCommands, 'version_control')
    def test_db_version_control(self, version_control):
        self._main_test_helper(['glance.cmd.manage', 'db', 'version_control'],
                               manage.DbCommands.version_control)

    @mock.patch.object(manage.DbCommands, 'sync')
    def test_db_sync_version(self, sync):
        self._main_test_helper(['glance.cmd.manage', 'db', 'sync', 'liberty'],
                               manage.DbCommands.sync, 'liberty')

    @mock.patch.object(manage.DbCommands, 'upgrade')
    def test_db_upgrade_version(self, upgrade):
        self._main_test_helper(['glance.cmd.manage', 'db',
                                'upgrade', 'liberty'],
                               manage.DbCommands.upgrade, 'liberty')

    @mock.patch.object(manage.DbCommands, 'expand')
    def test_db_expand(self, expand):
        self._main_test_helper(['glance.cmd.manage', 'db', 'expand'],
                               manage.DbCommands.expand)

    @mock.patch.object(manage.DbCommands, 'migrate')
    def test_db_migrate(self, migrate):
        self._main_test_helper(['glance.cmd.manage', 'db', 'migrate'],
                               manage.DbCommands.migrate)

    @mock.patch.object(manage.DbCommands, 'contract')
    def test_db_contract(self, contract):
        self._main_test_helper(['glance.cmd.manage', 'db', 'contract'],
                               manage.DbCommands.contract)

    def test_db_metadefs_unload(self):
        db_metadata.db_unload_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'unload_metadefs'],
                               db_metadata.db_unload_metadefs,
                               db_api.get_engine())

    def test_db_metadefs_load(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               None, False, False, False)

    def test_db_metadefs_load_with_specified_path(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--path', '/mock/'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', False, False, False)

    def test_db_metadefs_load_prefer_new_with_path(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--path', '/mock/', '--merge', '--prefer_new'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', True, True, False)

    def test_db_metadefs_load_prefer_new(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--merge', '--prefer_new'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               None, True, True, False)

    def test_db_metadefs_load_overwrite_existing(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--merge', '--overwrite'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               None, True, False, True)

    def test_db_metadefs_load_prefer_new_and_overwrite_existing(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--merge', '--prefer_new', '--overwrite'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               None, True, True, True)

    def test_db_metadefs_load_from_path_overwrite_existing(self):
        db_metadata.db_load_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'load_metadefs',
                                '--path', '/mock/', '--merge', '--overwrite'],
                               db_metadata.db_load_metadefs,
                               db_api.get_engine(),
                               '/mock/', True, False, True)

    def test_db_metadefs_export(self):
        db_metadata.db_export_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'export_metadefs'],
                               db_metadata.db_export_metadefs,
                               db_api.get_engine(),
                               None)

    def test_db_metadefs_export_with_specified_path(self):
        db_metadata.db_export_metadefs = mock.Mock()
        self._main_test_helper(['glance.cmd.manage', 'db', 'export_metadefs',
                                '--path', '/mock/'],
                               db_metadata.db_export_metadefs,
                               db_api.get_engine(),
                               '/mock/')
