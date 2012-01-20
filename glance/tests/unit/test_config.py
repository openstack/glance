# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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
import unittest

import stubout

from glance.common import config
from glance.common import context
from glance.image_cache import pruner
from glance.tests import utils as test_utils


class TestPasteApp(unittest.TestCase):

    def setUp(self):
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()

    def _do_test_load_paste_app(self,
                                expected_app_type,
                                paste_group={},
                                paste_copy=True,
                                paste_append=None):

        conf = test_utils.TestConfigOpts(groups=paste_group)

        def _appendto(orig, copy, str):
            shutil.copy(orig, copy)
            with open(copy, 'ab') as f:
                f.write(str or '')
                f.flush()

        if paste_copy:
            paste_from = os.path.join(os.getcwd(),
                                      'etc/glance-registry-paste.ini')
            paste_to = os.path.join(conf.temp_file.replace('.conf',
                                                       '-paste.ini'))
            _appendto(paste_from, paste_to, paste_append)

        app = config.load_paste_app(conf, 'glance-registry')

        self.assertEquals(expected_app_type, type(app))

    def test_load_paste_app(self):
        expected_middleware = context.ContextMiddleware
        self._do_test_load_paste_app(expected_middleware)

    def test_load_paste_app_with_paste_flavor(self):
        paste_group = {'paste_deploy': {'flavor': 'incomplete'}}
        pipeline = '[pipeline:glance-registry-incomplete]\n' + \
                   'pipeline = context registryapp'

        type = context.ContextMiddleware
        self._do_test_load_paste_app(type, paste_group, paste_append=pipeline)

    def test_load_paste_app_with_paste_config_file(self):
        paste_config_file = os.path.join(os.getcwd(),
                                         'etc/glance-registry-paste.ini')
        paste_group = {'paste_deploy': {'config_file': paste_config_file}}

        expected_middleware = context.ContextMiddleware
        self._do_test_load_paste_app(expected_middleware,
                                     paste_group, paste_copy=False)

    def test_load_paste_app_with_conf_name(self):
        def fake_join(*args):
            if len(args) == 2 and \
                    args[0].endswith('.glance') and \
                    args[1] == 'glance-cache.conf':
                return os.path.join(os.getcwd(), 'etc', args[1])
            else:
                return orig_join(*args)

        orig_join = os.path.join
        self.stubs.Set(os.path, 'join', fake_join)

        conf = config.GlanceCacheConfigOpts()
        conf([])

        self.stubs.Set(config, 'setup_logging', lambda *a: None)
        self.stubs.Set(pruner, 'Pruner', lambda conf, **lc: 'pruner')

        app = config.load_paste_app(conf, 'glance-pruner')

        self.assertEquals('pruner', app)
