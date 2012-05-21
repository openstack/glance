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


class TestImages(functional.FunctionalTest):

    def setUp(self):
        super(TestImages, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def _url(self, path):
        return 'http://0.0.0.0:%d/v2%s' % (self.api_port, path)

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

    def test_image_lifecycle(self):
        # Image list should be empty
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_location_header = response.headers['Location']

        # Returned image entity should have a generated id
        image = json.loads(response.text)['image']
        image_id = image['id']

        # Image list should now have one entry
        path = self._url('/images')
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
        path = self._url('/images/%s' % image_id)
        data = json.dumps({'name': 'image-2'})
        response = requests.put(path, headers=self._headers(), data=data)
        self.assertEqual(200, response.status_code)

        # Returned image entity should reflect the changes
        image = json.loads(response.text)['image']
        self.assertEqual('image-2', image['name'])

        # Updates should persist across requests
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['image']
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])

        # Try to download data before its uploaded
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Upload some image data
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(200, response.status_code)

        # Try to download the data that was just uploaded
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        # Deletion should work
        path = self._url('/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        # And neither should its data
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Image list should now be empty
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_upload_duplicate_data(self):
        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # Returned image entity should have a generated id
        image = json.loads(response.text)['image']
        image_id = image['id']

        # Upload some image data
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(200, response.status_code)

        # Uploading duplicate data should be rejected with a 409
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='XXX')
        self.assertEqual(409, response.status_code)

        # Data should not have been overwritten
        path = self._url('/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        self.stop_servers()

    def test_permissions(self):
        # Create an image that belongs to TENANT1
        path = self._url('/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # TENANT1 should see the image in their list
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT1 should be able to access the image directly
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)

        # TENANT2 should not see the image in their list
        path = self._url('/images')
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # TENANT2 should not be able to access the image directly
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to modify the image, either
        path = self._url('/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT2,
        })
        data = json.dumps({'name': 'image-2'})
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to delete the image, either
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.delete(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Share the image with TENANT2
        path = self._url('/images/%s/access' % image_id)
        data = json.dumps({'tenant_id': TENANT2, 'can_share': False})
        request_headers = {'Content-Type': 'application/json'}
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # TENANT2 should see the image in their list
        path = self._url('/images')
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT2 should be able to access the image directly
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # TENANT2 should not be able to modify the image
        path = self._url('/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT2,
        })
        data = json.dumps({'name': 'image-2'})
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to delete the image, either
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.delete(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # As an unshared tenant, TENANT3 should not have access to the image
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Publicize the image as an admin of TENANT1
        path = self._url('/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/json',
            'X-Roles': 'admin',
        })
        data = json.dumps({'visibility': 'public'})
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # TENANT3 should now see the image in their list
        path = self._url('/images')
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT3 should also be able to access the image directly
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # TENANT3 still should not be able to modify the image
        path = self._url('/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT3,
        })
        data = json.dumps({'name': 'image-2'})
        response = requests.put(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # TENANT3 should not be able to delete the image, either
        path = self._url('/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.delete(path, headers=headers)
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_access_lifecycle(self):
        # Create an image for our tests
        path = self._url('/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Image acccess list should be empty
        path = self._url('/images/%s/access' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        self.assertEqual(0, len(access_records))

        # Other tenants shouldn't be able to share by default, and shouldn't
        # even know the image exists
        path = self._url('/images/%s/access' % image_id)
        data = json.dumps({'tenant_id': TENANT3, 'can_share': False})
        request_headers = {
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT2,
        }
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # Share the image with another tenant
        path = self._url('/images/%s/access' % image_id)
        data = json.dumps({'tenant_id': TENANT2, 'can_share': True})
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        access_location = response.headers['Location']

        # Ensure the access record was actually created
        response = requests.get(access_location, headers=self._headers())
        self.assertEqual(200, response.status_code)

        # Make sure the sharee can further share the image
        path = self._url('/images/%s/access' % image_id)
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
        path = self._url('/images/%s/access' % image_id)
        data = json.dumps({'tenant_id': TENANT4, 'can_share': False})
        request_headers = {
            'Content-Type': 'application/json',
            'X-Tenant-Id': TENANT3,
        }
        headers = self._headers(request_headers)
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        # Image acccess list should now contain 2 entries
        path = self._url('/images/%s/access' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        self.assertEqual(2, len(access_records))

        # Delete an access record
        response = requests.delete(access_location, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Ensure the access record was actually deleted
        response = requests.get(access_location, headers=self._headers())
        self.assertEqual(404, response.status_code)

        # Image acccess list should now contain 1 entry
        path = self._url('/images/%s/access' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        access_records = json.loads(response.text)['access_records']
        self.assertEqual(1, len(access_records))

        self.stop_servers()

    def test_tag_lifecycle(self):
        # Create an image for our tests
        path = self._url('/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # List of image tags should be empty
        path = self._url('/images/%s/tags' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual([], tags)

        # Create a tag
        path = self._url('/images/%s/tags/sniff' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should now have an entry
        path = self._url('/images/%s/tags' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff'], tags)

        # Create a more complex tag
        path = self._url('/images/%s/tags/someone%%40example.com' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should reflect our new tag
        path = self._url('/images/%s/tags' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff', 'someone@example.com'], tags)

        # The tag should be deletable
        path = self._url('/images/%s/tags/someone%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List should reflect the deletion
        path = self._url('/images/%s/tags' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)
        self.assertEqual(['sniff'], tags)

        # Deleting the same tag should return a 404
        path = self._url('/images/%s/tags/someonei%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()
