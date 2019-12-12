# Copyright 2011 OpenStack Foundation
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

import os.path
import shutil

import fixtures
import oslo_middleware

from glance.api.middleware import context
from glance.common import config
from glance.tests import utils as test_utils


class TestPasteApp(test_utils.BaseTestCase):

    def setUp(self):
        super(TestPasteApp, self).setUp()

    def _do_test_load_paste_app(self,
                                expected_app_type,
                                make_paste_file=True,
                                paste_flavor=None,
                                paste_config_file=None,
                                paste_append=None):

        def _writeto(path, str):
            with open(path, 'w') as f:
                f.write(str or '')
                f.flush()

        def _appendto(orig, copy, str):
            shutil.copy(orig, copy)
            with open(copy, 'a') as f:
                f.write(str or '')
                f.flush()

        self.config(flavor=paste_flavor,
                    config_file=paste_config_file,
                    group='paste_deploy')

        temp_dir = self.useFixture(fixtures.TempDir()).path
        temp_file = os.path.join(temp_dir, 'testcfg.conf')

        _writeto(temp_file, '[DEFAULT]\n')

        config.parse_args(['--config-file', temp_file])

        paste_to = temp_file.replace('.conf', '-paste.ini')
        if not paste_config_file and make_paste_file:
            paste_from = os.path.join(os.getcwd(),
                                      'etc/glance-api-paste.ini')
            _appendto(paste_from, paste_to, paste_append)

        app = config.load_paste_app('glance-api')

        self.assertIsInstance(app, expected_app_type)

    def test_load_paste_app(self):
        expected_middleware = oslo_middleware.CORS
        self._do_test_load_paste_app(expected_middleware)

    def test_load_paste_app_paste_config_not_found(self):
        expected_middleware = context.UnauthenticatedContextMiddleware
        self.assertRaises(RuntimeError, self._do_test_load_paste_app,
                          expected_middleware, make_paste_file=False)

    def test_load_paste_app_with_paste_flavor(self):
        pipeline = ('[pipeline:glance-api-incomplete]\n'
                    'pipeline = context rootapp')
        expected_middleware = context.ContextMiddleware
        self._do_test_load_paste_app(expected_middleware,
                                     paste_flavor='incomplete',
                                     paste_append=pipeline)

    def test_load_paste_app_with_paste_config_file(self):
        paste_config_file = os.path.join(os.getcwd(),
                                         'etc/glance-api-paste.ini')
        expected_middleware = oslo_middleware.CORS
        self._do_test_load_paste_app(expected_middleware,
                                     paste_config_file=paste_config_file)

    def test_load_paste_app_with_paste_config_file_but_not_exist(self):
        paste_config_file = os.path.abspath("glance-api-paste.ini")
        expected_middleware = oslo_middleware.Healthcheck
        self.assertRaises(RuntimeError, self._do_test_load_paste_app,
                          expected_middleware,
                          paste_config_file=paste_config_file)

    def test_get_path_non_exist(self):
        self.assertRaises(RuntimeError, config._get_deployment_config_file)


class TestDefaultConfig(test_utils.BaseTestCase):

    def setUp(self):
        super(TestDefaultConfig, self).setUp()
        self.CONF = config.cfg.CONF
        self.CONF.import_group('profiler', 'glance.common.wsgi')

    def test_osprofiler_disabled(self):
        self.assertFalse(self.CONF.profiler.enabled)
        self.assertFalse(self.CONF.profiler.trace_sqlalchemy)
