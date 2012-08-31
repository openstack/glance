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
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

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
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image (with a deployer-defined property)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel', 'foo': 'bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_location_header = response.headers['Location']

        # Returned image entity should have a generated id and status
        image = json.loads(response.text)
        image_id = image['id']
        self.assertEqual(image['status'], 'queued')

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
        image = json.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertFalse('checksum' in image)
        self.assertFalse('size' in image)
        self.assertEqual('bar', image['foo'])
        self.assertEqual(False, image['protected'])
        self.assertEqual('kernel', image['type'])
        self.assertTrue(image['created_at'])
        self.assertTrue(image['updated_at'])
        self.assertEqual(image['updated_at'], image['created_at'])

        # The image should be mutable, including adding and removing properties
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = json.dumps([
            {'replace': '/name', 'value': 'image-2'},
            {'replace': '/disk_format', 'value': 'vhd'},
            {'replace': '/foo', 'value': 'baz'},
            {'add': '/ping', 'value': 'pong'},
            {'replace': '/protected', 'value': True},
            {'remove': '/type'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = json.loads(response.text)
        self.assertEqual('image-2', image['name'])
        self.assertEqual('vhd', image['disk_format'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertEqual(True, image['protected'])
        self.assertFalse('type' in image, response.text)

        # Updates should persist across requests
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertEqual(True, image['protected'])
        self.assertFalse('type' in image, response.text)

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(201, response.status_code)

        # Checksum should be populated automatically
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)
        self.assertEqual('8f113e38d28a79a5a451b16048cc2b72', image['checksum'])

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual('8f113e38d28a79a5a451b16048cc2b72',
                         response.headers['Content-MD5'])
        self.assertEqual(response.text, 'ZZZZZ')

        # Uploading duplicate data should be rejected with a 409
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='XXX')
        self.assertEqual(409, response.status_code)

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(5, json.loads(response.text)['size'])

        # Deletion should not work on protected images
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(403, response.status_code)

        # Unprotect image for deletion
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = json.dumps([{'replace': '/protected', 'value': False}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

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

    def test_permissions(self):
        # Create an image that belongs to TENANT1
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_id = json.loads(response.text)['id']

        # TENANT1 should see the image in their list
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT1 should be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)

        # TENANT2 should not see the image in their list
        path = self._url('/v2/images')
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # TENANT2 should not be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to modify the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.0-json-patch',
            'X-Tenant-Id': TENANT2,
        })
        data = json.dumps([{'replace': '/name', 'value': 'image-2'}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to delete the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.delete(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # Publicize the image as an admin of TENANT1
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.0-json-patch',
            'X-Roles': 'admin',
        })
        data = json.dumps([{'replace': '/visibility', 'value': 'public'}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # TENANT3 should now see the image in their list
        path = self._url('/v2/images')
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT3 should also be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # TENANT3 still should not be able to modify the image
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.0-json-patch',
            'X-Tenant-Id': TENANT3,
        })
        data = json.dumps([{'replace': '/name', 'value': 'image-2'}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(404, response.status_code)

        # TENANT3 should not be able to delete the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.delete(path, headers=headers)
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_tag_lifecycle(self):
        # Create an image with a tag - duplicate should be ignored
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'tags': ['sniff', 'sniff']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_id = json.loads(response.text)['id']

        # Image should show a list with a single tag
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['tags']
        self.assertEqual(['sniff'], tags)

        # Update image with duplicate tag - it should be ignored
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = json.dumps([{'replace': '/tags',
                            'value': ['sniff', 'snozz', 'snozz']}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['tags']
        self.assertEqual(['snozz', 'sniff'], tags)

        # Image should show the appropriate tags
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], tags)

        # Attempt to tag the image with a duplicate should be ignored
        path = self._url('/v2/images/%s/tags/snozz' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Create another more complex tag
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Double-check that the tags container on the image is populated
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz', 'gabe@example.com'], tags)

        # The tag should be deletable
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List of tags should reflect the deletion
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = json.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], tags)

        # Deleting the same tag should return a 404
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_images_container(self):
        # Image list should be empty and no next link should be present
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        first = json.loads(response.text)['first']
        self.assertEqual(0, len(images))
        self.assertTrue('next' not in json.loads(response.text))
        self.assertEqual('/v2/images', first)

        # Create 7 images
        images = []
        fixtures = [
            {'name': 'image-3', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-4', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-1', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-3', 'type': 'ramdisk', 'ping': 'pong'},
            {'name': 'image-2', 'type': 'kernel', 'ping': 'ding'},
            {'name': 'image-3', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-2', 'type': 'kernel', 'ping': 'pong'},
        ]
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        for fixture in fixtures:
            data = json.dumps(fixture)
            response = requests.post(path, headers=headers, data=data)
            self.assertEqual(201, response.status_code)
            images.append(json.loads(response.text))

        # Image list should contain 7 images
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = json.loads(response.text)
        self.assertEqual(7, len(body['images']))
        self.assertEqual('/v2/images', body['first'])
        self.assertFalse('next' in json.loads(response.text))

        # Begin pagination after the first image
        template_url = ('/v2/images?limit=2&sort_dir=asc&sort_key=name'
                        '&marker=%s&type=kernel&ping=pong')
        path = self._url(template_url % images[2]['id'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = json.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[6]['id'], images[0]['id']], response_ids)

        # Continue pagination using next link from previous request
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = json.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[5]['id'], images[1]['id']], response_ids)

        # Continue pagination - expect no results
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = json.loads(response.text)
        self.assertEqual(0, len(body['images']))

        # Delete first image
        path = self._url('/v2/images/%s' % images[0]['id'])
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Ensure bad request for using a deleted image as marker
        path = self._url('/v2/images?marker=%s' % images[0]['id'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(400, response.status_code)

        self.stop_servers()


class TestImageDirectURLVisibility(functional.FunctionalTest):

    def setUp(self):
        super(TestImageDirectURLVisibility, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

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

    def test_v2_not_enabled(self):
        self.api_server.enable_v2_api = False
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(300, response.status_code)
        self.stop_servers()

    def test_v2_enabled(self):
        self.api_server.enable_v2_api = True
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        self.stop_servers()

    def test_image_direct_url_visible(self):

        self.api_server.show_image_direct_url = True
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel', 'foo': 'bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = json.loads(response.text)
        image_id = image['id']

        # Image direct_url should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)
        self.assertFalse('direct_url' in image)

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(201, response.status_code)

        # Image direct_url should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)
        self.assertTrue('direct_url' in image)

        # Image direct_url should be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['images'][0]
        self.assertTrue('direct_url' in image)

        self.stop_servers()

    def test_image_direct_url_not_visible(self):

        self.api_server.show_image_direct_url = False
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = json.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = json.dumps({'name': 'image-1', 'type': 'kernel', 'foo': 'bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = json.loads(response.text)
        image_id = image['id']

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(201, response.status_code)

        # Image direct_url should not be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)
        self.assertFalse('direct_url' in image)

        # Image direct_url should not be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = json.loads(response.text)['images'][0]
        self.assertFalse('direct_url' in image)

        self.stop_servers()
