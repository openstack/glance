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


class TestImageTags(functional.FunctionalTest):

    def setUp(self):
        super(TestImageTags, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

        # Create an image for our tests
        path = 'http://0.0.0.0:%d/v2/images' % self.api_port
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        self.image_url = response.headers['Location']

    def _url(self, path):
        return '%s%s' % (self.image_url, path)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': '38b7149a-b564-48dd-a0a5-aa7e643368c0',
            'X-Roles': 'member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    @functional.runs_sql
    def test_image_tag_lifecycle(self):
        # List of image tags should be empty
        path = self._url('/tags')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual([], tags)

        # Create a tag
        path = self._url('/tags/sniff')
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should now have an entry
        path = self._url('/tags')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff'], tags)

        # Create a more complex tag
        path = self._url('/tags/someone%40example.com')
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should reflect our new tag
        path = self._url('/tags')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff', 'someone@example.com'], tags)

        # The tag should be deletable
        path = self._url('/tags/someone%40example.com')
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should reflect the deletion
        path = self._url('/tags')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff'], tags)

        # Deleting the same tag should return a 404
        path = self._url('/tags/someone%40example.com')
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()
