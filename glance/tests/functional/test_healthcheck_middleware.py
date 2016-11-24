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

import tempfile

import httplib2
from six.moves import http_client

from glance.tests import functional
from glance.tests import utils


class HealthcheckMiddlewareTest(functional.FunctionalTest):

    def request(self):
        url = 'http://127.0.0.1:%s/healthcheck' % self.api_port
        http = httplib2.Http()
        return http.request(url, 'GET')

    @utils.skip_if_disabled
    def test_healthcheck_enabled(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        response, content = self.request()
        self.assertEqual(b'OK', content)
        self.assertEqual(http_client.OK, response.status)

        self.stop_servers()

    def test_healthcheck_disabled(self):
        with tempfile.NamedTemporaryFile() as test_disable_file:
            self.cleanup()
            self.api_server.disable_path = test_disable_file.name
            self.start_servers(**self.__dict__.copy())

            response, content = self.request()
            self.assertEqual(b'DISABLED BY FILE', content)
            self.assertEqual(http_client.SERVICE_UNAVAILABLE, response.status)

            self.stop_servers()
