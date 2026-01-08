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

import http.client as http
import logging
import logging.handlers
import os
import stat

from glance.tests import functional


class TestLogging(functional.SynchronousAPIBase):

    """Functional tests for Glance's logging output"""

    def setUp(self):
        super(TestLogging, self).setUp()
        # Set up log file path
        self.log_file = os.path.join(self.test_dir, "api.log")
        self.file_handler = None

    def tearDown(self):
        # Clean up file handler if it was added
        if self.file_handler:
            glance_logger = logging.getLogger('glance')
            glance_logger.removeHandler(self.file_handler)
            self.file_handler.close()
        super(TestLogging, self).tearDown()

    def _setup_file_logging(self, debug=False, use_watched=False):
        """Set up file logging for the glance logger."""
        glance_logger = logging.getLogger('glance')
        # Remove existing file handler if any
        if self.file_handler:
            glance_logger.removeHandler(self.file_handler)
            self.file_handler.close()

        # Create a new file handler (WatchedFileHandler for rotation support)
        if use_watched:
            self.file_handler = logging.handlers.WatchedFileHandler(
                self.log_file)
        else:
            self.file_handler = logging.FileHandler(self.log_file)
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s [%(name)s] %(message)s')
        self.file_handler.setFormatter(formatter)
        if debug:
            self.file_handler.setLevel(logging.DEBUG)
            glance_logger.setLevel(logging.DEBUG)
        else:
            self.file_handler.setLevel(logging.INFO)
            glance_logger.setLevel(logging.INFO)
        glance_logger.addHandler(self.file_handler)

    def test_debug(self):
        """
        Test logging output proper when debug is on.
        """
        # Configure logging to write to file with debug enabled
        self.config(debug=True)
        self._setup_file_logging(debug=True)
        self.start_server()

        # Make an API call to generate log output
        response = self.api_get('/v2/images')
        self.assertEqual(http.OK, response.status_code)

        # Flush the handler to ensure all logs are written
        self.file_handler.flush()

        # Verify that debug statements appear in the API logs
        self.assertTrue(os.path.exists(self.log_file))

        with open(self.log_file, 'r') as f:
            api_log_out = f.read()

        self.assertIn('DEBUG [glance', api_log_out)

    def test_no_debug(self):
        """
        Test logging output proper when debug is off.
        """
        # Configure logging to write to file with debug disabled
        self.config(debug=False)
        self._setup_file_logging(debug=False)
        self.start_server()

        # Make an API call to generate log output
        response = self.api_get('/v2/images')
        self.assertEqual(http.OK, response.status_code)

        # Flush the handler to ensure all logs are written
        self.file_handler.flush()

        # Verify that debug statements do not appear in the API logs
        self.assertTrue(os.path.exists(self.log_file))

        with open(self.log_file, 'r') as f:
            api_log_out = f.read()

        self.assertNotIn('DEBUG [glance', api_log_out)

    def assertNotEmptyFile(self, path):
        self.assertTrue(os.path.exists(path))
        self.assertNotEqual(os.stat(path)[stat.ST_SIZE], 0)

    def test_logrotate(self):
        """
        Test that we notice when our log file has been rotated
        """
        # Configure logging to write to file using WatchedFileHandler
        # which can detect log rotation
        self.config(debug=True)
        self._setup_file_logging(debug=True, use_watched=True)
        self.start_server()

        # Make an API call to generate log output
        response = self.api_get('/v2/images')
        self.assertEqual(http.OK, response.status_code)

        # Flush the handler to ensure all logs are written
        self.file_handler.flush()

        # Verify log file exists and is not empty
        self.assertNotEmptyFile(self.log_file)

        # Rotate the log file
        os.rename(self.log_file, self.log_file + ".1")

        # Force a log message to trigger WatchedFileHandler to check
        # if the file was rotated and create a new one
        glance_logger = logging.getLogger('glance')
        glance_logger.info("Test log message after rotation")

        # Make another API call - WatchedFileHandler should detect
        # the rotation and create a new log file
        response = self.api_get('/v2/images')
        self.assertEqual(http.OK, response.status_code)

        # Flush the handler
        self.file_handler.flush()

        # Verify a new log file was created
        self.assertNotEmptyFile(self.log_file)
