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

import os
import unittest

from tests import functional
from tests.utils import execute


class TestLogging(functional.FunctionalTest):

    """Tests that logging can be configured correctly"""

    def test_logfile(self):
        """
        A test that logging can be configured properly from the
        glance.conf file with the log_file option.

        We start both servers daemonized with a temporary config
        file that has some logging options in it.

        We then use curl to issue a few requests and verify that each server's
        logging statements were logged to the one log file
        """
        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        cmd = "curl -X POST -H 'Content-Type: application/octet-stream' "\
              "-H 'X-Image-Meta-Name: ImageName' "\
              "-H 'X-Image-Meta-Disk-Format: Invalid' "\
              "http://0.0.0.0:%d/images" % api_port
        ignored, out, err = execute(cmd)

        self.assertTrue('Invalid disk format' in out,
                        "Could not find 'Invalid disk format' "
                        "in output: %s" % out)

        self.assertTrue(os.path.exists(self.api_log_file),
                        "API Logfile %s does not exist!"
                        % self.api_log_file)
        self.assertTrue(os.path.exists(self.registry_log_file),
                        "Registry Logfile %s does not exist!"
                        % self.registry_log_file)

        api_logfile_contents = open(self.api_log_file, 'rb').read()
        registry_logfile_contents = open(self.registry_log_file, 'rb').read()

        # Check that BOTH the glance API and registry server
        # modules are logged to their respective logfiles.
        self.assertTrue('[glance.server]'
                        in api_logfile_contents,
                        "Could not find '[glance.server]' "
                        "in API logfile: %s" % api_logfile_contents)
        self.assertTrue('[glance.registry.server]'
                        in registry_logfile_contents,
                        "Could not find '[glance.registry.server]' "
                        "in Registry logfile: %s" % registry_logfile_contents)

        # Test that the error we caused above is in the log
        self.assertTrue('Invalid disk format' in api_logfile_contents,
                        "Could not find 'Invalid disk format' "
                        "in API logfile: %s" % api_logfile_contents)

        self.stop_servers()
