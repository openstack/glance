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

from unittest import mock

from glance.db.sqlalchemy.alembic_migrations import data_migrations
from glance.tests import utils as test_utils


class TestDataMigrationFramework(test_utils.BaseTestCase):

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_no_migrations(self, mock_find):
        mock_find.return_value = None
        self.assertFalse(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_one_migration_no_pending(self, mock_find):
        mock_migration1 = mock.Mock()
        mock_migration1.has_migrations.return_value = False
        mock_find.return_value = [mock_migration1]

        self.assertFalse(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_one_migration_with_pending(self,
                                                               mock_find):
        mock_migration1 = mock.Mock()
        mock_migration1.has_migrations.return_value = True
        mock_find.return_value = [mock_migration1]

        self.assertTrue(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_mult_migration_no_pending(self, mock_find):
        mock_migration1 = mock.Mock()
        mock_migration1.has_migrations.return_value = False
        mock_migration2 = mock.Mock()
        mock_migration2.has_migrations.return_value = False
        mock_migration3 = mock.Mock()
        mock_migration3.has_migrations.return_value = False

        mock_find.return_value = [mock_migration1, mock_migration2,
                                  mock_migration3]

        self.assertFalse(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_mult_migration_one_pending(self,
                                                               mock_find):
        mock_migration1 = mock.Mock()
        mock_migration1.has_migrations.return_value = False
        mock_migration2 = mock.Mock()
        mock_migration2.has_migrations.return_value = True
        mock_migration3 = mock.Mock()
        mock_migration3.has_migrations.return_value = False

        mock_find.return_value = [mock_migration1, mock_migration2,
                                  mock_migration3]

        self.assertTrue(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('glance.db.sqlalchemy.alembic_migrations.data_migrations'
                '._find_migration_modules')
    def test_has_pending_migrations_mult_migration_some_pending(self,
                                                                mock_find):
        mock_migration1 = mock.Mock()
        mock_migration1.has_migrations.return_value = False
        mock_migration2 = mock.Mock()
        mock_migration2.has_migrations.return_value = True
        mock_migration3 = mock.Mock()
        mock_migration3.has_migrations.return_value = False
        mock_migration4 = mock.Mock()
        mock_migration4.has_migrations.return_value = True

        mock_find.return_value = [mock_migration1, mock_migration2,
                                  mock_migration3, mock_migration4]

        self.assertTrue(data_migrations.has_pending_migrations(mock.Mock()))

    @mock.patch('importlib.import_module')
    @mock.patch('pkgutil.iter_modules')
    def test_find_migrations(self, mock_iter, mock_import):
        def fake_iter_modules(blah):
            yield 'blah', 'zebra01', 'blah'
            yield 'blah', 'zebra02', 'blah'
            yield 'blah', 'yellow01', 'blah'
            yield 'blah', 'xray01', 'blah'
            yield 'blah', 'wrinkle01', 'blah'

        mock_iter.side_effect = fake_iter_modules

        zebra1 = mock.Mock()
        zebra1.has_migrations.return_value = mock.Mock()
        zebra1.migrate.return_value = mock.Mock()
        zebra2 = mock.Mock()
        zebra2.has_migrations.return_value = mock.Mock()
        zebra2.migrate.return_value = mock.Mock()

        fake_imported_modules = [zebra1, zebra2]
        mock_import.side_effect = fake_imported_modules

        actual = data_migrations._find_migration_modules('zebra')
        self.assertEqual(2, len(actual))
        self.assertEqual(fake_imported_modules, actual)

    @mock.patch('pkgutil.iter_modules')
    def test_find_migrations_no_migrations(self, mock_iter):
        def fake_iter_modules(blah):
            yield 'blah', 'zebra01', 'blah'
            yield 'blah', 'yellow01', 'blah'
            yield 'blah', 'xray01', 'blah'
            yield 'blah', 'wrinkle01', 'blah'
            yield 'blah', 'victor01', 'blah'

        mock_iter.side_effect = fake_iter_modules

        actual = data_migrations._find_migration_modules('umbrella')
        self.assertEqual(0, len(actual))
        self.assertEqual([], actual)

    def test_run_migrations(self):
        zebra1 = mock.Mock()
        zebra1.has_migrations.return_value = True
        zebra1.migrate.return_value = 100
        zebra2 = mock.Mock()
        zebra2.has_migrations.return_value = True
        zebra2.migrate.return_value = 50
        migrations = [zebra1, zebra2]

        engine = mock.Mock()
        actual = data_migrations._run_migrations(engine, migrations)
        self.assertEqual(150, actual)
        zebra1.has_migrations.assert_called_once_with(engine)
        zebra1.migrate.assert_called_once_with(engine)
        zebra2.has_migrations.assert_called_once_with(engine)
        zebra2.migrate.assert_called_once_with(engine)

    def test_run_migrations_with_one_pending_migration(self):
        zebra1 = mock.Mock()
        zebra1.has_migrations.return_value = False
        zebra1.migrate.return_value = 0
        zebra2 = mock.Mock()
        zebra2.has_migrations.return_value = True
        zebra2.migrate.return_value = 50
        migrations = [zebra1, zebra2]

        engine = mock.Mock()
        actual = data_migrations._run_migrations(engine, migrations)
        self.assertEqual(50, actual)
        zebra1.has_migrations.assert_called_once_with(engine)
        zebra1.migrate.assert_not_called()
        zebra2.has_migrations.assert_called_once_with(engine)
        zebra2.migrate.assert_called_once_with(engine)

    def test_run_migrations_with_no_migrations(self):
        migrations = []

        actual = data_migrations._run_migrations(mock.Mock(), migrations)
        self.assertEqual(0, actual)

    @mock.patch('glance.db.migration.CURRENT_RELEASE', 'zebra')
    @mock.patch('importlib.import_module')
    @mock.patch('pkgutil.iter_modules')
    def test_migrate(self, mock_iter, mock_import):
        def fake_iter_modules(blah):
            yield 'blah', 'zebra01', 'blah'
            yield 'blah', 'zebra02', 'blah'
            yield 'blah', 'yellow01', 'blah'
            yield 'blah', 'xray01', 'blah'
            yield 'blah', 'xray02', 'blah'

        mock_iter.side_effect = fake_iter_modules

        zebra1 = mock.Mock()
        zebra1.has_migrations.return_value = True
        zebra1.migrate.return_value = 100
        zebra2 = mock.Mock()
        zebra2.has_migrations.return_value = True
        zebra2.migrate.return_value = 50

        fake_imported_modules = [zebra1, zebra2]
        mock_import.side_effect = fake_imported_modules

        engine = mock.Mock()
        actual = data_migrations.migrate(engine, 'zebra')
        self.assertEqual(150, actual)
        zebra1.has_migrations.assert_called_once_with(engine)
        zebra1.migrate.assert_called_once_with(engine)
        zebra2.has_migrations.assert_called_once_with(engine)
        zebra2.migrate.assert_called_once_with(engine)
