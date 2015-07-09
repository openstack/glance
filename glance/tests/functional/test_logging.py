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

"""Functional test case that tests logging output"""

import os
import stat

import httplib2

from glance.tests import functional


class TestLogging(functional.FunctionalTest):

    """Functional tests for Glance's logging output"""

    def test_verbose_debug(self):
        """
        Test logging output proper when verbose and debug
        is on.
        """
        self.cleanup()
        self.start_servers()

        # The default functional test case has both verbose
        # and debug on. Let's verify that debug statements
        # appear in both the API and registry logs.

        self.assertTrue(os.path.exists(self.api_server.log_file))

        api_log_out = open(self.api_server.log_file, 'r').read()

        self.assertIn('DEBUG glance', api_log_out)

        self.assertTrue(os.path.exists(self.registry_server.log_file))

        registry_log_out = open(self.registry_server.log_file, 'r').read()

        self.assertIn('DEBUG glance', registry_log_out)

        self.stop_servers()

    def test_no_verbose_no_debug(self):
        """
        Test logging output proper when verbose and debug
        is off.
        """
        self.cleanup()
        self.start_servers(debug=False, verbose=False)

        self.assertTrue(os.path.exists(self.api_server.log_file))

        api_log_out = open(self.api_server.log_file, 'r').read()

        self.assertNotIn('DEBUG glance', api_log_out)

        self.assertTrue(os.path.exists(self.registry_server.log_file))

        registry_log_out = open(self.registry_server.log_file, 'r').read()

        self.assertNotIn('DEBUG glance', registry_log_out)

        self.stop_servers()

    def assertNotEmptyFile(self, path):
        self.assertTrue(os.path.exists(path))
        self.assertNotEqual(os.stat(path)[stat.ST_SIZE], 0)

    def test_logrotate(self):
        """
        Test that we notice when our log file has been rotated
        """
        self.cleanup()
        self.start_servers()

        self.assertNotEmptyFile(self.api_server.log_file)

        os.rename(self.api_server.log_file, self.api_server.log_file + ".1")

        path = "http://%s:%d/" % ("127.0.0.1", self.api_port)
        response, content = httplib2.Http().request(path, 'GET')
        self.assertEqual(300, response.status)

        self.assertNotEmptyFile(self.api_server.log_file)

        self.stop_servers()
