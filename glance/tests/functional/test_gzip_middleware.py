# Copyright 2013 Red Hat, Inc
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

"""Tests gzip middleware."""

from glance.tests import functional
from glance.tests import utils


class GzipMiddlewareTest(functional.SynchronousAPIBase):

    def setUp(self):
        super(GzipMiddlewareTest, self).setUp()
        self.start_server()

    @utils.skip_if_disabled
    def test_gzip_requests(self):
        # Accept-Encoding: Identity
        headers = self._headers({'Accept-Encoding': 'identity'})
        response = self.api_get('/v2/images', headers=headers)
        # When identity is requested, Content-Encoding should not be set
        self.assertIsNone(response.headers.get('content-encoding'))

        # Accept-Encoding: gzip
        headers = self._headers({'Accept-Encoding': 'gzip'})
        response = self.api_get('/v2/images', headers=headers)
        # When gzip is requested, Content-Encoding should be set to gzip
        self.assertEqual('gzip', response.headers.get('content-encoding'))
