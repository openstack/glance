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


class TestImages(functional.FunctionalTest):

    def setUp(self):
        super(TestImages, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def _url(self, path):
        return 'http://0.0.0.0:%d%s' % (self.api_port, path)

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
    def test_image_lifecycle(self):
        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_location_header = response.headers['Location']

        # Returned image entity should have a generated id
        image = json.loads(response.text)['image']
        image_id = image['id']

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image_id)

        # Get the image using the returned Location header
        response = requests.get(image_location_header, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['image']
        self.assertEqual(image_id, image['id'])

        # The image should be mutable
        path = self._url('/v2/images/%s' % image_id)
        data = json.dumps({'name': 'image-2'})
        response = requests.put(path, headers=self._headers(), data=data)
        self.assertEqual(200, response.status_code)

        # Returned image entity should reflect the changes
        image = json.loads(response.text)['image']
        self.assertEqual('image-2', image['name'])

        # Updates should persist across requests
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['image']
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(200, response.status_code)

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        # Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        # And neither should its data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_upload_duplicate_data(self):
        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # Returned image entity should have a generated id
        image = json.loads(response.text)['image']
        image_id = image['id']

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(200, response.status_code)

        # Uploading duplicate data should be rejected with a 409
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.put(path, headers=headers, data='XXX')
        self.assertEqual(409, response.status_code)

        # Data should not have been overwritten
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        self.stop_servers()
