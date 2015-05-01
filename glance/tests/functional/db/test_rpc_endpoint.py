# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from oslo_serialization import jsonutils
import requests

from glance.tests import functional


class TestRegistryURLVisibility(functional.FunctionalTest):

    def setUp(self):
        super(TestRegistryURLVisibility, self).setUp()
        self.cleanup()
        self.registry_server.deployment_flavor = ''
        self.req_body = jsonutils.dumps([{"command": "image_get_all"}])

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.registry_port, path)

    def _headers(self, custom_headers=None):
        base_headers = {
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_v2_not_enabled(self):
        self.registry_server.enable_v2_registry = False
        self.start_servers(**self.__dict__.copy())
        path = self._url('/rpc')
        response = requests.post(path, headers=self._headers(),
                                 data=self.req_body)
        self.assertEqual(404, response.status_code)
        self.stop_servers()

    def test_v2_enabled(self):
        self.registry_server.enable_v2_registry = True
        self.start_servers(**self.__dict__.copy())
        path = self._url('/rpc')
        response = requests.post(path, headers=self._headers(),
                                 data=self.req_body)
        self.assertEqual(200, response.status_code)
        self.stop_servers()
