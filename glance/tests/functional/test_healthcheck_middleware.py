# Copyright 2015 Hewlett Packard
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

"""Tests healthcheck middleware."""

import http.client
import os

from glance.tests import functional
from glance.tests import utils


class HealthcheckMiddlewareTest(functional.SynchronousAPIBase):
    def setUp(self):
        super().setUp()
        self.disable_file = '/tmp/test_path'
        self.addCleanup(self._remove_disable_file)

    def _remove_disable_file(self):
        # Delete the disable file so that it does not pollute future test runs.
        try:
            os.remove(self.disable_file)
        except FileNotFoundError:
            # Should the tests fail before the "disable file" has been created,
            # this cleanup function will not be able to delete it. This should
            # not raise an exception, though, so ignore it.
            pass

    # NOTE(cyril): as /tmp/test_path is hardcoded in the paste configuration
    # for SynchronousAPIBase, if we were to add more tests, and since they
    # would be run in parallel, we would run into issues because multiple tests
    # would rely on the existence/absence of /tmp/test_path. Should we want to
    # add tests in this class in the future, we would have to pass the path to
    # our disable file at runtime and randomize it to avoid running into this
    # issue.
    @utils.skip_if_disabled
    def test_healthcheck(self):
        # First, let's see what happens without /tmp/test_path
        self.start_server(enable_cache=False)
        response = self.api_get('/healthcheck')
        self.assertEqual(b'OK', response.body)
        self.assertEqual(http.client.OK, response.status_code)

        # Then, let's check that healthcheck is disabled by file when
        # /tmp/test_path exists
        with open(self.disable_file, 'w'):
            response = self.api_get('/healthcheck')
            self.assertEqual(b'DISABLED BY FILE', response.body)
            self.assertEqual('503 Service Unavailable', response.status)
