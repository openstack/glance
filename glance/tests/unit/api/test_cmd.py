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
import sys

import glance_store as store
import mock
from oslo_config import cfg
from oslo_log import log as logging
import six

import glance.cmd.api
import glance.cmd.cache_cleaner
import glance.cmd.cache_pruner
import glance.common.config
from glance.common import exception as exc
import glance.common.wsgi
import glance.image_cache.cleaner
import glance.image_cache.pruner
from glance.tests import utils as test_utils


CONF = cfg.CONF


class TestGlanceApiCmd(test_utils.BaseTestCase):

    __argv_backup = None

    def _do_nothing(self, *args, **kwargs):
        pass

    def _raise(self, exc):
        def fake(*args, **kwargs):
            raise exc
        return fake

    def setUp(self):
        super(TestGlanceApiCmd, self).setUp()
        self.__argv_backup = sys.argv
        sys.argv = ['glance-api']
        self.stderr = six.StringIO()
        sys.stderr = self.stderr

        store.register_opts(CONF)

        self.stubs.Set(glance.common.config, 'load_paste_app',
                       self._do_nothing)
        self.stubs.Set(glance.common.wsgi.Server, 'start',
                       self._do_nothing)
        self.stubs.Set(glance.common.wsgi.Server, 'wait',
                       self._do_nothing)

    def tearDown(self):
        sys.stderr = sys.__stderr__
        sys.argv = self.__argv_backup
        super(TestGlanceApiCmd, self).tearDown()

    def test_supported_default_store(self):
        self.config(group='glance_store', default_store='file')
        glance.cmd.api.main()

    def test_unsupported_default_store(self):
        self.stubs.UnsetAll()
        self.config(group='glance_store', default_store='shouldnotexist')
        exit = self.assertRaises(SystemExit, glance.cmd.api.main)
        self.assertEqual(1, exit.code)

    def test_worker_creation_failure(self):
        failure = exc.WorkerCreationFailure(reason='test')
        self.stubs.Set(glance.common.wsgi.Server, 'start',
                       self._raise(failure))
        exit = self.assertRaises(SystemExit, glance.cmd.api.main)
        self.assertEqual(2, exit.code)

    @mock.patch.object(glance.common.config, 'parse_cache_args')
    @mock.patch.object(logging, 'setup')
    @mock.patch.object(glance.image_cache.ImageCache, 'init_driver')
    @mock.patch.object(glance.image_cache.ImageCache, 'clean')
    def test_cache_cleaner_main(self, mock_cache_clean,
                                mock_cache_init_driver, mock_log_setup,
                                mock_parse_config):
        mock_cache_init_driver.return_value = None

        manager = mock.MagicMock()
        manager.attach_mock(mock_log_setup, 'mock_log_setup')
        manager.attach_mock(mock_parse_config, 'mock_parse_config')
        manager.attach_mock(mock_cache_init_driver, 'mock_cache_init_driver')
        manager.attach_mock(mock_cache_clean, 'mock_cache_clean')
        glance.cmd.cache_cleaner.main()
        expected_call_sequence = [mock.call.mock_parse_config(),
                                  mock.call.mock_log_setup(CONF, 'glance'),
                                  mock.call.mock_cache_init_driver(),
                                  mock.call.mock_cache_clean()]
        self.assertEqual(expected_call_sequence, manager.mock_calls)

    @mock.patch.object(glance.image_cache.base.CacheApp, '__init__')
    def test_cache_cleaner_main_runtime_exception_handling(self, mock_cache):
        mock_cache.return_value = None
        self.stubs.Set(glance.image_cache.cleaner.Cleaner, 'run',
                       self._raise(RuntimeError))
        exit = self.assertRaises(SystemExit, glance.cmd.cache_cleaner.main)
        self.assertEqual('ERROR: ', exit.code)

    @mock.patch.object(glance.common.config, 'parse_cache_args')
    @mock.patch.object(logging, 'setup')
    @mock.patch.object(glance.image_cache.ImageCache, 'init_driver')
    @mock.patch.object(glance.image_cache.ImageCache, 'prune')
    def test_cache_pruner_main(self, mock_cache_prune,
                               mock_cache_init_driver, mock_log_setup,
                               mock_parse_config):
        mock_cache_init_driver.return_value = None

        manager = mock.MagicMock()
        manager.attach_mock(mock_log_setup, 'mock_log_setup')
        manager.attach_mock(mock_parse_config, 'mock_parse_config')
        manager.attach_mock(mock_cache_init_driver, 'mock_cache_init_driver')
        manager.attach_mock(mock_cache_prune, 'mock_cache_prune')
        glance.cmd.cache_pruner.main()
        expected_call_sequence = [mock.call.mock_parse_config(),
                                  mock.call.mock_log_setup(CONF, 'glance'),
                                  mock.call.mock_cache_init_driver(),
                                  mock.call.mock_cache_prune()]
        self.assertEqual(expected_call_sequence, manager.mock_calls)

    @mock.patch.object(glance.image_cache.base.CacheApp, '__init__')
    def test_cache_pruner_main_runtime_exception_handling(self, mock_cache):
        mock_cache.return_value = None
        self.stubs.Set(glance.image_cache.pruner.Pruner, 'run',
                       self._raise(RuntimeError))
        exit = self.assertRaises(SystemExit, glance.cmd.cache_pruner.main)
        self.assertEqual('ERROR: ', exit.code)
