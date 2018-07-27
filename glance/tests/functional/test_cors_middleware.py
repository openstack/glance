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

"""Tests cors middleware."""

import httplib2
from six.moves import http_client

from glance.tests import functional


class TestCORSMiddleware(functional.FunctionalTest):
    '''Provide a basic smoke test to ensure CORS middleware is active.

    The tests below provide minimal confirmation that the CORS middleware
    is active, and may be configured. For comprehensive tests, please consult
    the test suite in oslo_middleware.
    '''

    def setUp(self):
        super(TestCORSMiddleware, self).setUp()
        # Cleanup is handled in teardown of the parent class.
        self.start_servers(**self.__dict__.copy())
        self.http = httplib2.Http()
        self.api_path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)

    def test_valid_cors_options_request(self):
        (r_headers, content) = self.http.request(
            self.api_path,
            'OPTIONS',
            headers={
                'Origin': 'http://valid.example.com',
                'Access-Control-Request-Method': 'GET'
            })

        self.assertEqual(http_client.OK, r_headers.status)
        self.assertIn('access-control-allow-origin', r_headers)
        self.assertEqual('http://valid.example.com',
                         r_headers['access-control-allow-origin'])

    def test_invalid_cors_options_request(self):
        (r_headers, content) = self.http.request(
            self.api_path,
            'OPTIONS',
            headers={
                'Origin': 'http://invalid.example.com',
                'Access-Control-Request-Method': 'GET'
            })

        self.assertEqual(http_client.OK, r_headers.status)
        self.assertNotIn('access-control-allow-origin', r_headers)

    def test_valid_cors_get_request(self):
        (r_headers, content) = self.http.request(
            self.api_path,
            'GET',
            headers={
                'Origin': 'http://valid.example.com'
            })

        self.assertEqual(http_client.OK, r_headers.status)
        self.assertIn('access-control-allow-origin', r_headers)
        self.assertEqual('http://valid.example.com',
                         r_headers['access-control-allow-origin'])

    def test_invalid_cors_get_request(self):
        (r_headers, content) = self.http.request(
            self.api_path,
            'GET',
            headers={
                'Origin': 'http://invalid.example.com'
            })

        self.assertEqual(http_client.OK, r_headers.status)
        self.assertNotIn('access-control-allow-origin', r_headers)
