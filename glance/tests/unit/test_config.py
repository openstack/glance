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
import optparse
import tempfile
import unittest

import stubout

from glance.api.middleware import version_negotiation
from glance.api.v1 import images
from glance.api.v1 import members
from glance.common import config
from glance.image_cache import pruner


class TestOptionParsing(unittest.TestCase):

    def test_common_options(self):
        parser = optparse.OptionParser()
        self.assertEquals(0, len(parser.option_groups))
        config.add_common_options(parser)
        self.assertEquals(1, len(parser.option_groups))

        expected_options = ['--verbose', '--debug', '--config-file']
        for e in expected_options:
            self.assertTrue(parser.option_groups[0].get_option(e),
                            "Missing required common option: %s" % e)

    def test_parse_options(self):
        # test empty args and that parse_options() returns a mapping
        # of typed values
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser, [])

        expected_options = {'verbose': False, 'debug': False,
                            'config_file': None}
        self.assertEquals(expected_options, parsed_options)

        # test non-empty args and that parse_options() returns a mapping
        # of typed values matching supplied args
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser, ['--verbose'])

        expected_options = {'verbose': True, 'debug': False,
                            'config_file': None}
        self.assertEquals(expected_options, parsed_options)

        # test non-empty args that contain unknown options raises
        # a SystemExit exception. Not ideal, but unfortunately optparse
        # raises a sys.exit() when it runs into an error instead of raising
        # something a bit more useful for libraries. optparse must have been
        # written by the same group that wrote unittest ;)
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        self.assertRaises(SystemExit, config.parse_options,
                          parser, ['--unknown'])


class TestConfigFiles(unittest.TestCase):

    def setUp(self):
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()

    def test_config_file_default(self):
        expected_path = '/etc/glance/glance-api.conf'

        self.stubs.Set(os.path, 'exists', lambda p: p == expected_path)

        path = config.find_config_file('glance-api', {}, [])

        self.assertEquals(expected_path, path)

    def test_config_file_option(self):
        expected_path = '/etc/glance/my-glance-api.conf'

        self.stubs.Set(os.path, 'exists', lambda p: p == expected_path)

        path = config.find_config_file('glance-api',
                                       {'config_file': expected_path}, [])

        self.assertEquals(expected_path, path)

    def test_config_file_arg(self):
        expected_path = '/etc/glance/my-glance-api.conf'

        self.stubs.Set(os.path, 'exists', lambda p: p == expected_path)

        path = config.find_config_file('glance-api', {}, [expected_path])

        self.assertEquals(expected_path, path)

    def test_config_file_tilde_arg(self):
        supplied_path = '~/my-glance-api.conf'
        expected_path = '/tmp/my-glance-api.conf'

        def fake_expanduser(p):
            if p[0] == '~':
                p = '/tmp' + p[1:]
            return p

        self.stubs.Set(os.path, 'expanduser', fake_expanduser)
        self.stubs.Set(os.path, 'exists', lambda p: p == supplied_path)

        path = config.find_config_file('glance-api', {}, [supplied_path])

        self.assertEquals(expected_path, path)

    def test_config_file_not_found(self):
        self.stubs.Set(os.path, 'exists', lambda p: False)

        self.assertRaises(RuntimeError,
                          config.find_config_file,
                          'glance-foo', {}, [])


class TestPasteConfig(unittest.TestCase):

    def test_load_paste_config(self):
        path = os.path.join(os.getcwd(), 'etc/glance-api.conf')

        conf = config.load_paste_config(path, 'glance-api')

        self.assertEquals('file', conf['default_store'])


class TestPasteApp(unittest.TestCase):

    def setUp(self):
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()

    def test_load_paste_app(self):
        path = os.path.join(os.getcwd(), 'etc/glance-api.conf')

        self.stubs.Set(config, 'setup_logging', lambda *a: None)
        self.stubs.Set(images, 'create_resource', lambda *a: None)
        self.stubs.Set(members, 'create_resource', lambda *a: None)

        conf, app = config.load_paste_app('glance-api', {}, [path])

        self.assertEquals('file', conf['default_store'])
        self.assertEquals(version_negotiation.VersionNegotiationFilter,
                          type(app))

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

        self.stubs.Set(config, 'setup_logging', lambda *a: None)
        self.stubs.Set(pruner, 'app_factory', lambda *a: 'pruner')

        conf, app = config.load_paste_app('glance-pruner', {}, [],
                                          'glance-cache')

        self.assertEquals('86400', conf['image_cache_stall_time'])
        self.assertEquals('pruner', app)
