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

import http.client

from glance.tests import functional


class TestCORSMiddleware(functional.SynchronousAPIBase):
    '''Provide a basic smoke test to ensure CORS middleware is active.

    The tests below provide minimal confirmation that the CORS middleware
    is active, and may be configured. For comprehensive tests, please consult
    the test suite in oslo_middleware.
    '''

    def setUp(self):
        super(TestCORSMiddleware, self).setUp()
        self.start_server(enable_cors=True, enable_cache=False)

    def test_valid_cors_get_request(self):
        headers = self._headers({
            'Origin': 'http://valid.example.com',
            'Access-Control-Request-Method': 'GET'
        })
        response = self.api_request('GET', '/v2/images', headers=headers)

        self.assertEqual(http.client.OK, response.status_code)
        self.assertIn('access-control-allow-origin', response.headers)
        self.assertEqual('http://valid.example.com',
                         response.headers['access-control-allow-origin'])

    def test_invalid_cors_get_request(self):
        headers = self._headers({
            'Origin': 'http://invalid.example.com',
        })
        response = self.api_request('GET', '/v2/images', headers=headers)

        self.assertEqual(http.client.OK, response.status_code)
        self.assertNotIn('access-control-allow-origin', response.headers)
