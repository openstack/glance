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
