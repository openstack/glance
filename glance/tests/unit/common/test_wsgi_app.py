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
import glance.async_
from glance.common import exception
from glance.common import wsgi_app
from glance.tests import utils as test_utils


class TestWsgiAppInit(test_utils.BaseTestCase):
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    def test_wsgi_init_sets_thread_settings(self, mock_config_files,
                                            mock_set_model,
                                            mock_load):
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
    def test_wsgi_init_registers_exit_handler(self, mock_config_files,
                                              mock_set_model,
                                              mock_load, mock_exit):
        mock_config_files.return_value = []
        wsgi_app.init_app()
        mock_exit.assert_called_once_with(wsgi_app.drain_threadpools)

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_drain_threadpools(self):
        # Initialize the thread pool model and tasks_pool, like API
        # under WSGI would, and so we have a pointer to that exact
        # pool object in the cache
        glance.async_.set_threadpool_model('native')
        model = common.get_thread_pool('tasks_pool')

        with mock.patch.object(model.pool, 'shutdown') as mock_shutdown:
            wsgi_app.drain_threadpools()
            # Make sure that shutdown() was called on the tasks_pool
            # ThreadPoolExecutor
            mock_shutdown.assert_called_once_with()

    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    def test_policy_enforcement_kills_service_if_misconfigured(
            self, mock_load_app, mock_set, mock_config_files):
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_secure_rbac=False)
        self.assertRaises(exception.ServerError, wsgi_app.init_app)

        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_secure_rbac=True)
        self.assertRaises(exception.ServerError, wsgi_app.init_app)

    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    def test_policy_enforcement_valid_truthy_configuration(
            self, mock_load_app, mock_set, mock_config_files):
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_secure_rbac=True)
        self.assertTrue(wsgi_app.init_app())

    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    def test_policy_enforcement_valid_falsy_configuration(
            self, mock_load_app, mock_set, mock_config_files):
        # This is effectively testing the default values, but we're doing that
        # to make sure nothing bad happens at runtime in the default case when
        # validating policy enforcement configuration.
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_secure_rbac=False)
        self.assertTrue(wsgi_app.init_app())

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('threading.Thread')
    @mock.patch('glance.housekeeping.StagingStoreCleaner')
    def test_runs_staging_cleanup(self, mock_cleaner, mock_Thread, mock_conf,
                                  mock_load):
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
    def test_run_cache_prefetcher(self, mock_prefetcher,
                                  mock_Timer, mock_conf,
                                  mock_load):
        self.config(cache_prefetcher_interval=10)
        self.config(flavor='keystone+cachemanagement', group='paste_deploy')
        mock_conf.return_value = []
        wsgi_app.init_app()
        mock_Timer.assert_called_once_with(10, mock.ANY, (mock_prefetcher(),))
        mock_Timer.return_value.start.assert_called_once_with()

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    @mock.patch('threading.Timer')
    @mock.patch('glance.image_cache.prefetcher.Prefetcher')
    def test_run_cache_prefetcher_middleware_disabled(
            self, mock_prefetcher, mock_Timer, mock_conf, mock_load):
        mock_conf.return_value = []
        wsgi_app.init_app()
        mock_Timer.assert_not_called()
