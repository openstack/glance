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

from glance.common import utils
from glance.tests import functional


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

        # Create an image (with a deployer-defined property)
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel', 'foo': 'bar'})
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
        self.assertEqual('bar', image['foo'])
        self.assertTrue(image['created_at'])
        self.assertTrue(image['updated_at'])
        self.assertEqual(image['updated_at'], image['created_at'])

        # The image should be mutable, including adding new properties
        path = self._url('/images/%s' % image_id)
        data = json.dumps({'name': 'image-2', 'format': 'vhd',
                           'foo': 'baz', 'ping': 'pong'})
        response = requests.put(path, headers=self._headers(), data=data)
        self.assertEqual(200, response.status_code)

        # Returned image entity should reflect the changes
        image = json.loads(response.text)['image']
        self.assertEqual('image-2', image['name'])
        self.assertEqual('vhd', image['format'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])

        # Updates should persist across requests
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['image']
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])

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
        # Create an image with a tag
        path = self._url('/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'tags': ['sniff']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Image should show a list with a single tag
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['image']['tags']
        self.assertEqual(['sniff'], tags)

        # Create another more complex tag
        path = self._url('/images/%s/tags/someone%%40example.com' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Double-check that the tags container on the image is populated
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['image']['tags']
        self.assertEqual(['sniff', 'someone@example.com'], tags)

        # The tag should be deletable
        path = self._url('/images/%s/tags/someone%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List of tags should reflect the deletion
        path = self._url('/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['image']['tags']
        self.assertEqual(['sniff'], tags)

        # Deleting the same tag should return a 404
        path = self._url('/images/%s/tags/someonei%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_get_images_with_marker_and_limit(self):
        image_ids = []

        # Image list should be empty and no next link should be present
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        self.assertEqual(0, len(images))
        self.assertTrue('next' not in json.loads(response.text))
        self.assertEqual('/v2/images', first)

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-2', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-3', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Image list should contain 3 images
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        self.assertEqual(3, len(images))
        image_ids = [image['id'] for image in images]
        self.assertEqual('/v2/images', first)
        self.assertTrue('next' not in json.loads(response.text))

        # Image list should only contain last 2 images
        # and not the first image which is the marker image
        path = self._url('/images?marker=%s' % image_ids[0])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        self.assertEqual(2, len(images))
        self.assertEqual(images[0]['id'], image_ids[1])
        self.assertEqual(images[1]['id'], image_ids[2])
        self.assertEqual('/v2/images', first)
        self.assertTrue('next' not in json.loads(response.text))

        # Ensure bad request for using a invalid marker
        path = self._url('/images?marker=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

        #Set limit as 2
        # Image list should only contain first 2 images
        path = self._url('/images?limit=2')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        next_marker = json.loads(response.text)['next']
        first = json.loads(response.text)['first']
        self.assertEqual(2, len(images))
        self.assertEqual(images[0]['id'], image_ids[0])
        self.assertEqual(images[1]['id'], image_ids[1])
        expected = '/v2/images?marker=%s&limit=2' % image_ids[1]
        self.assertEqual(expected, next_marker)
        self.assertEqual('/v2/images?limit=2', first)

        # Ensure bad request for using a invalid limit
        path = self._url('/images?limit=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

        # Ensure bad request for using a zero limit
        path = self._url('/images?limit=0')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Ensure bad request for using a negative limit
        path = self._url('/images?limit=-1')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

        # using limit and marker only second image should be returned
        path = self._url('/images?limit=1&marker=%s' % image_ids[0])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        next_marker = json.loads(response.text)['next']
        first = json.loads(response.text)['first']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image_ids[1])
        expected = '/v2/images?marker=%s&limit=1' % image_ids[1]
        self.assertEqual(expected, next_marker)
        self.assertEqual('/v2/images?limit=1', first)

        #limit greater than number of images
        path = self._url('/images?limit=10')
        response = requests.get(path, headers=self._headers())
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        self.assertEqual(3, len(images))
        self.assertTrue('next' not in json.loads(response.text))
        self.assertEqual('/v2/images?limit=10', first)

        # First link should always return link to first image and
        # the remaining parameters should be forwarded to first
        # Next link should contain the forwarded parameters
        params = 'sort_key=name&sort_dir=asc&limit=2'
        path = self._url('/images?%s' % params)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        next_marker = json.loads(response.text)['next']
        self.assertEqual(2, len(images))
        expected = '/v2/images?%s&marker=%s' % (params, image_ids[1])
        self.assertEqual(expected, next_marker)
        self.assertEqual('/v2/images?%s' % params, first)

        # Delete first image
        path = self._url('/images/%s' % image_ids[0])
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Ensure bad request for using a deleted image as marker
        path = self._url('/images?marker=%s' % image_ids[0])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

    def test_get_images_with_sorting(self):
        image_ids = []

        # Image list should be empty
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-2', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-3', 'type': 'kernel'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Image list should contain 3 images
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(3, len(images))
        image_ids = [image['id'] for image in images]

        # Sort images using name as sort key and desc as sort dir
        path = self._url('/images?sort_key=name&sort_dir=desc')
        response = requests.get(path, headers=self._headers())
        images = json.loads(response.text)['images']
        self.assertEqual(3, len(images))
        self.assertEqual(images[0]['name'], 'image-3')
        self.assertEqual(images[1]['name'], 'image-2')
        self.assertEqual(images[2]['name'], 'image-1')

        # Sort images using name as sort key and desc as sort asc
        path = self._url('/images?sort_key=name&sort_dir=asc')
        response = requests.get(path, headers=self._headers())
        images = json.loads(response.text)['images']
        self.assertEqual(3, len(images))
        self.assertEqual(images[0]['name'], 'image-1')
        self.assertEqual(images[1]['name'], 'image-2')
        self.assertEqual(images[2]['name'], 'image-3')

        # Ensure bad request for using a invalid sort_key
        path = self._url('/images?sort_key=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

        # Ensure bad request for using a invalid sort_dir
        path = self._url('/images?sort_dir=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

    def test_get_images_with_filtering(self):
        image_ids = []

        # Image list should be empty
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel', 'visibility':
        'public'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-2', 'type': 'kernel', 'visibility':
        'private', 'foo': 'bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Create an image
        path = self._url('/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-3', 'type': 'kernel', 'visibility':
        'public'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        image_id = json.loads(response.text)['image']['id']

        # Image list should contain 3 images
        path = self._url('/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(3, len(images))
        image_ids = [image['id'] for image in images]

        # Filter images using name as key
        path = self._url('/images?name=image-2')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'image-2')

        # Filter images with user defined property
        path = self._url('/images?foo=bar')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'image-2')

        # Filter images with undefined property
        path = self._url('/images?poo=bear')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Filter images with visibility key
        path = self._url('/images?visibility=private')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'image-2')

        # Filter images using name and different visibility
        path = self._url('/images?name=image-2&visibility=private')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'image-2')

        # Filter images using name and visibility
        path = self._url('/images?visibility=private&name=image-3')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))
