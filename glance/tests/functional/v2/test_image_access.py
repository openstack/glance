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
from glance.common import utils


TENANT1 = utils.generate_uuid()
TENANT2 = utils.generate_uuid()
TENANT3 = utils.generate_uuid()
TENANT4 = utils.generate_uuid()


class TestImageAccess(functional.FunctionalTest):
    def setUp(self):
        super(TestImageAccess, self).setUp()
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
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    @functional.runs_sql
    def test_image_access_lifecycle(self):
        # Image acccess list should be empty
        path = self._url('/access')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        self.assertEqual(0, len(access_records))

        # Other tenants shouldn't be able to share by default, and shouldn't
        # even know the image exists
        path = self._url('/access')
        data = json.dumps({'tenant_id': TENANT3, 'can_share': False})
        request_headers = {
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT2,
        }
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # Share the image with another tenant
        path = self._url('/access')
        data = json.dumps({'tenant_id': TENANT2, 'can_share': True})
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        access_location = response.headers['Location']

        # Ensure the access record was actually created
        response = requests.get(access_location, headers=self._headers())
        self.assertEqual(200, response.status_code)

        # Make sure the sharee can further share the image
        path = self._url('/access')
        data = json.dumps({'tenant_id': TENANT3, 'can_share': False})
        request_headers = {
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT2,
        }
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        access_location = response.headers['Location']

        # Ensure the access record was actually created
        response = requests.get(access_location, headers=self._headers())
        self.assertEqual(200, response.status_code)

        # The third tenant should not be able to share it further
        path = self._url('/access')
        data = json.dumps({'tenant_id': TENANT4, 'can_share': False})
        request_headers = {
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT3,
        }
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        # Image acccess list should now contain 2 entries
        path = self._url('/access')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        self.assertEqual(2, len(access_records))
        print [a['tenant_id'] for a in access_records]

        # Delete an access record
        response = requests.delete(access_location, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Ensure the access record was actually deleted
        response = requests.get(access_location, headers=self._headers())
        self.assertEqual(404, response.status_code)

        # Image acccess list should now contain 1 entry
        path = self._url('/access')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        print [a['tenant_id'] for a in access_records]
        self.assertEqual(1, len(access_records))

        self.stop_servers()
