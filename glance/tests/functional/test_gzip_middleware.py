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

import httplib2

from glance.tests import functional
from glance.tests import utils


class GzipMiddlewareTest(functional.FunctionalTest):

    @utils.skip_if_disabled
    def test_gzip_requests(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        def request(path, headers=None):
            # We don't care what version we're using here so,
            # sticking with latest
            url = 'http://127.0.0.1:%s/v2/%s' % (self.api_port, path)
            http = httplib2.Http()
            return http.request(url, 'GET', headers=headers)

        # Accept-Encoding: Identity
        headers = {'Accept-Encoding': 'identity'}
        response, content = request('images', headers=headers)
        self.assertIsNone(response.get("-content-encoding"))

        # Accept-Encoding: gzip
        headers = {'Accept-Encoding': 'gzip'}
        response, content = request('images', headers=headers)
        self.assertEqual('gzip', response.get("-content-encoding"))

        self.stop_servers()
