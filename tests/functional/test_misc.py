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

import unittest

from tests import functional
from tests.utils import execute


class TestMiscellaneous(functional.FunctionalTest):

    """Some random tests for various bugs and stuff"""

    def test_exception_not_eaten_from_registry_to_api(self):
        """
        A test for LP bug #704854 -- Exception thrown by registry
        server is consumed by API server.

        We start both servers daemonized.

        We then use curl to try adding an image that does not
        meet validation requirements on the registry server and test
        that the error returned from the API server to curl is appropriate

        We also fire the glance-upload tool against the API server
        and verify that glance-upload doesn't eat the exception either...
        """

        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        cmd = "curl -X POST -H 'Content-Type: application/octet-stream' "\
              "-H 'X-Image-Meta-Name: ImageName' "\
              "-H 'X-Image-Meta-Disk-Format: Invalid' "\
              "http://0.0.0.0:%d/images" % api_port
        ignored, out, err = execute(cmd)

        self.assertTrue('Invalid disk format' in out,
                        "Could not find 'Invalid disk format' "
                        "in output: %s" % out)

        self.stop_servers()
