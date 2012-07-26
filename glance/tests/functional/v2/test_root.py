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

import json

import requests

from glance.tests import functional


class TestRoot(functional.FunctionalTest):

    def test_root_request(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        path = "http://%s:%d/v2/" % ("127.0.0.1", self.api_port)
        response = requests.get(path)
        self.assertEqual(response.status_code, 200)
        expected = {
            'links': [
                {'href': "/v2/schemas", "rel": "schemas"},
                {"href": "/v2/images", "rel": "images"},
            ],
        }
        self.assertEqual(json.loads(response.text), expected)
