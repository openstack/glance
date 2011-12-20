# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack, LLC
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

import httplib2

from glance.tests import functional


class TestMultiprocessing(functional.FunctionalTest):
    """Functional tests for the bin/glance CLI tool"""

    def setUp(self):
        self.workers = 2
        super(TestMultiprocessing, self).setUp()

    def test_multiprocessing(self):
        """Spin up the api servers with multiprocessing on"""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')
        self.stop_servers()
