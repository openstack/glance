# -*- coding: utf-8 -*-
# Copyright 2020, Red Hat, Inc.
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

from unittest import mock

from glance.api import common
from glance.api.v2 import cached_images
import glance.async_
from glance.common import exception
from glance.common import wsgi_app
from glance import sqlite_migration
from glance.tests import utils as test_utils


class TestWsgiAppInit(test_utils.BaseTestCase):
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_wsgi_init_sets_thread_settings(self, mock_migrate_db,
                                            mock_config_files,
                                            mock_set_model,
                                            mock_load):
        mock_migrate_db.return_value = False
        mock_config_files.return_value = []
        self.config(task_pool_threads=123, group='wsgi')
        common.DEFAULT_POOL_SIZE = 1024
        wsgi_app.init_app()
        # Make sure we declared the system threadpool model as native
        mock_set_model.assert_called_once_with('native')
        # Make sure we set the default pool size
        self.assertEqual(123, common.DEFAULT_POOL_SIZE)
        mock_load.assert_called_once_with('glance-api')

    @mock.patch('atexit.register')
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_wsgi_init_registers_exit_handler(self, mock_migrate_db,
                                              mock_config_files,
                                              mock_set_model,
                                              mock_load, mock_exit):
        mock_migrate_db.return_value = False
        mock_config_files.return_value = []
        wsgi_app.init_app()
        mock_exit.assert_called_once_with(wsgi_app.drain_workers)

    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_uwsgi_init_registers_exit_handler(self, mock_migrate_db,
                                               mock_config_files,
                                               mock_set_model,
                                               mock_load):
        mock_migrate_db.return_value = False
        mock_config_files.return_value = []
        with mock.patch.object(wsgi_app, 'uwsgi') as mock_u:
            wsgi_app.init_app()
            self.assertEqual(mock_u.atexit, wsgi_app.drain_workers)

    @mock.patch('glance.api.v2.cached_images.WORKER')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_drain_workers(self, mock_cache_worker):
        # Initialize the thread pool model and tasks_pool, like API
        # under WSGI would, and so we have a pointer to that exact
        # pool object in the cache
        glance.async_.set_threadpool_model('native')
        model = common.get_thread_pool('tasks_pool')

        with mock.patch.object(model.pool, 'shutdown') as mock_shutdown:
            wsgi_app.drain_workers()
            # Make sure that shutdown() was called on the tasks_pool
            # ThreadPoolExecutor
            mock_shutdown.assert_called_once_with()

            # Make sure we terminated the cache worker, if present.
            mock_cache_worker.terminate.assert_called_once_with()

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_drain_workers_no_cache(self):
        glance.async_.set_threadpool_model('native')
        model = common.get_thread_pool('tasks_pool')

        with mock.patch.object(model.pool, 'shutdown'):
            # Make sure that with no WORKER initialized, we do not fail
            wsgi_app.drain_workers()
            self.assertIsNone(cached_images.WORKER)

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('threading.Thread')
    @mock.patch('glance.housekeeping.StagingStoreCleaner')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_runs_staging_cleanup(self, mock_migrate_db, mock_cleaner,
                                  mock_Thread, mock_conf,
                                  mock_load):
        mock_migrate_db.return_value = False
        mock_conf.return_value = []
        wsgi_app.init_app()
        mock_Thread.assert_called_once_with(
            target=mock_cleaner().clean_orphaned_staging_residue,
            daemon=True)
        mock_Thread.return_value.start.assert_called_once_with()

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('threading.Timer')
    @mock.patch('glance.image_cache.prefetcher.Prefetcher')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_run_cache_prefetcher_middleware_disabled(
            self, mock_migrate_db, mock_prefetcher, mock_Timer, mock_conf,
            mock_load):
        mock_migrate_db.return_value = False
        mock_conf.return_value = []
        wsgi_app.init_app()
        mock_Timer.assert_not_called()

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app', new=mock.MagicMock())
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_staging_store_uri_assertion(self, mock_migrate_db, mock_conf):
        mock_migrate_db.return_value = False
        self.config(node_staging_uri='http://good.luck')
        mock_conf.return_value = []
        # Make sure a staging URI with a bad scheme will abort startup
        self.assertRaises(exception.GlanceException, wsgi_app.init_app)

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app', new=mock.MagicMock())
    @mock.patch('os.path.exists')
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    def test_staging_store_path_check(self, mock_migrate_db, mock_exists,
                                      mock_conf):
        mock_migrate_db.return_value = False
        mock_exists.return_value = False
        mock_conf.return_value = []
        with mock.patch.object(wsgi_app, 'LOG') as mock_log:
            wsgi_app.init_app()
            # Make sure that a missing staging directory will log a warning.
            mock_log.warning.assert_called_once_with(
                'Import methods are enabled but staging directory '
                '%(path)s does not exist; Imports will fail!',
                {'path': '/tmp/staging/'})

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app', new=mock.MagicMock())
    @mock.patch('os.path.exists')
    @mock.patch('glance.sqlite_migration.get_db_path')
    @mock.patch('glance.sqlite_migration.Migrate.migrate')
    def test_sqlite_migrate(self, mock_migrate, mock_path,
                            mock_exists, mock_conf):
        self.config(flavor='keystone+cache', group='paste_deploy')
        self.config(image_cache_driver='centralized_db')
        self.config(worker_self_reference_url='http://workerx')
        mock_path.return_value = 'fake_path'
        mock_exists.return_value = False
        mock_conf.return_value = []
        wsgi_app.init_app()
        self.assertEqual(1, mock_migrate.call_count)

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app', new=mock.MagicMock())
    @mock.patch('glance.sqlite_migration.Migrate.migrate')
    def test_sqlite_migrate_not_called(self, mock_migrate,
                                       mock_conf):
        self.config(flavor='keystone+cache', group='paste_deploy')
        self.config(image_cache_driver='sqlite')
        self.config(worker_self_reference_url='http://workerx')
        mock_conf.return_value = []
        wsgi_app.init_app()
        self.assertEqual(0, mock_migrate.call_count)

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app', new=mock.MagicMock())
    @mock.patch('os.path.exists')
    @mock.patch('os.path.join', new=mock.MagicMock())
    @mock.patch('glance.sqlite_migration.can_migrate_to_central_db')
    @mock.patch('glance.sqlite_migration.Migrate.migrate')
    def test_sqlite_migrate_db_not_exist(self, mock_migrate, mock_can_migrate,
                                         mock_exists, mock_conf):
        self.config(flavor='keystone+cache', group='paste_deploy')
        self.config(image_cache_driver='centralized_db')
        self.config(worker_self_reference_url='http://workerx')
        mock_can_migrate.return_value = True
        mock_exists.return_value = False
        mock_conf.return_value = []
        with mock.patch.object(sqlite_migration, 'LOG') as mock_log:
            wsgi_app.init_app()
            mock_log.debug.assert_called_once_with(
                'SQLite caching database not located, skipping migration')

            self.assertEqual(0, mock_migrate.call_count)

    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_worker_self_reference_url_not_set(self, mock_conf):
        self.config(flavor='keystone+cache', group='paste_deploy')
        self.config(image_cache_driver='centralized_db')
        mock_conf.return_value = []
        self.assertRaises(RuntimeError, wsgi_app.init_app)
