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

import optparse
import tempfile
import unittest

from glance.common import config


class TestConfig(unittest.TestCase):

    def test_common_options(self):
        parser = optparse.OptionParser()
        self.assertEquals(0, len(parser.option_groups))
        config.add_common_options(parser)
        self.assertEquals(1, len(parser.option_groups))

        expected_options = ['--verbose', '--debug']
        for e in expected_options:
            self.assertTrue(parser.option_groups[0].get_option(e),
                            "Missing required common option: %s" % e)

    def test_parse_options(self):
        # test empty args and that parse_options() returns a mapping
        # of typed values
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser)

        expected_options = {'verbose': False, 'debug': False}
        self.assertEquals(expected_options, parsed_options)

        # test non-empty args and that parse_options() returns a mapping
        # of typed values matching supplied args
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser, ['--verbose'])

        expected_options = {'verbose': True, 'debug': False}
        self.assertEquals(expected_options, parsed_options)

        # test non-empty args that contain unknown options raises
        # a SystemExit exception. Not ideal, but unfortunately optparse
        # raises a sys.exit() when it runs into an error instead of raising
        # something a bit more useful for libraries. optparse must have been
        # written by the same group that wrote unittest ;)
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        self.assertRaises(SystemExit, config.parse_options,
                          parser,['--unknown'])

    def test_options_to_conf(self):
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser)
        conf_options = config.options_to_conf(parsed_options)

        expected_options = {'verbose': 'False', 'debug': 'False'}
        self.assertEquals(expected_options, conf_options)

    def test_get_config_file_options(self):

        # Test when no conf files are found...
        expected_options = {}
        conf_options = config.get_config_file_options(conf_dirs=['tests'])
        self.assertEquals(expected_options, conf_options)

        # Test when a conf file is supplied and only DEFAULT
        # section is present
        with tempfile.NamedTemporaryFile() as f:
            contents = """[DEFAULT]
verbose = True
"""
            f.write(contents)
            f.flush()
            conf_file = f.name
            
            expected_options = {'verbose': 'True'}
            conf_options = config.get_config_file_options(conf_file)
            self.assertEquals(expected_options, conf_options)

        # Test when a conf file is supplied and it has a DEFAULT
        # section and another section called glance-api, with
        # no specified app_name when calling get_config_file_options()
        with tempfile.NamedTemporaryFile() as f:
            contents = """[DEFAULT]
verbose = True

[glance-api]
default_store = swift
"""
            f.write(contents)
            f.flush()
            conf_file = f.name
            
            expected_options = {'verbose': 'True',
                                'default_store': 'swift'}
            conf_options = config.get_config_file_options(conf_file)
            self.assertEquals(expected_options, conf_options)

        # Test when a conf file is supplied and it has a DEFAULT
        # section and another section called glance-api, with
        # specified app_name is NOT glance-api
        with tempfile.NamedTemporaryFile() as f:
            contents = """[DEFAULT]
verbose = True

[glance-api]
default_store = swift
"""
            f.write(contents)
            f.flush()
            conf_file = f.name
            
            expected_options = {'verbose': 'True'}
            app_name = 'glance-registry'
            conf_options = config.get_config_file_options(conf_file,
                                                          app_name=app_name)
            self.assertEquals(expected_options, conf_options)

        # Test when a conf file is supplied and it has a DEFAULT
        # section and two other sections. Check that the later section
        # overrides the value of the former section...
        with tempfile.NamedTemporaryFile() as f:
            contents = """[DEFAULT]
verbose = True

[glance-api]
default_store = swift

[glance-combined]
default_store = s3
"""
            f.write(contents)
            f.flush()
            conf_file = f.name
            
            expected_options = {'verbose': 'True',
                                'default_store': 's3'}
            conf_options = config.get_config_file_options(conf_file)
            self.assertEquals(expected_options, conf_options)

    def test_parse_options_with_defaults(self):
        # Test the integration of parse_options() with a set
        # of defaults. These defaults generally come from a
        # configuration file
        defaults = {'verbose': 'on'}
        parser = optparse.OptionParser()
        config.add_common_options(parser)
        parsed_options, args = config.parse_options(parser, defaults=defaults)

        expected_options = {'verbose': True, 'debug': False}
        self.assertEquals(expected_options, parsed_options)

        # Write a sample conf file and merge the conf file defaults
        # with the parsed options.
        with tempfile.NamedTemporaryFile() as f:
            contents = """[DEFAULT]
verbose = True
debug = off
"""
            f.write(contents)
            f.flush()
            conf_file = f.name
            
            expected_options = {'verbose': True,
                                'debug': False}
            conf_options = config.get_config_file_options(conf_file)
            parser = optparse.OptionParser()
            config.add_common_options(parser)
            parsed_options, args = config.parse_options(parser,
                                                        defaults=conf_options)

            self.assertEquals(expected_options, parsed_options)
