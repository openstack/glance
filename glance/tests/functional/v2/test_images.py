# Copyright 2012 OpenStack Foundation
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

import os
import signal
import tempfile
import uuid

import requests

from glance.openstack.common import jsonutils
from glance.tests import functional
from glance.tests.functional.store import test_http


TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


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
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki', 'abc': 'xyz'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_location_header = response.headers['Location']

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        checked_keys = set([
            u'status',
            u'name',
            u'tags',
            u'created_at',
            u'updated_at',
            u'visibility',
            u'self',
            u'protected',
            u'id',
            u'file',
            u'min_disk',
            u'foo',
            u'abc',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
        ])
        self.assertEqual(set(image.keys()), checked_keys)
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'foo': 'bar',
            'abc': 'xyz',
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image_id)

        # Create another image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-2', 'type': 'kernel',
                                'bar': 'foo', 'disk_format': 'aki',
                                'container_format': 'aki', 'xyz': 'abc'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image2_id = image['id']
        checked_keys = set([
            u'status',
            u'name',
            u'tags',
            u'created_at',
            u'updated_at',
            u'visibility',
            u'self',
            u'protected',
            u'id',
            u'file',
            u'min_disk',
            u'bar',
            u'xyz',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
        ])
        self.assertEqual(set(image.keys()), checked_keys)
        expected_image = {
            'status': 'queued',
            'name': 'image-2',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image2_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image2_id,
            'min_disk': 0,
            'bar': 'foo',
            'xyz': 'abc',
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Image list should now have two entries
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(images[0]['id'], image2_id)
        self.assertEqual(images[1]['id'], image_id)

        # Image list should list only image-2 as image-1 doesn't contain the
        # property 'bar'
        path = self._url('/v2/images?bar=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Image list should list only image-1 as image-2 doesn't contain the
        # property 'foo'
        path = self._url('/v2/images?foo=bar')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image_id)

        # Image list should list only image-1 based on the filter
        # 'foo=bar&abc=xyz'
        path = self._url('/v2/images?foo=bar&abc=xyz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image_id)

        # Image list should list only image-2 based on the filter
        # 'bar=foo&xyz=abc'
        path = self._url('/v2/images?bar=foo&xyz=abc')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Image list should not list anything as the filter 'foo=baz&abc=xyz'
        # is not satisfied by either images
        path = self._url('/v2/images?foo=baz&abc=xyz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Get the image using the returned Location header
        response = requests.get(image_location_header, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertFalse('checksum' in image)
        self.assertNotIn('size', image)
        self.assertNotIn('virtual_size', image)
        self.assertEqual('bar', image['foo'])
        self.assertEqual(False, image['protected'])
        self.assertEqual('kernel', image['type'])
        self.assertTrue(image['created_at'])
        self.assertTrue(image['updated_at'])
        self.assertEqual(image['updated_at'], image['created_at'])

        # The image should be mutable, including adding and removing properties
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/name', 'value': 'image-2'},
            {'op': 'replace', 'path': '/disk_format', 'value': 'vhd'},
            {'op': 'replace', 'path': '/container_format', 'value': 'ami'},
            {'op': 'replace', 'path': '/foo', 'value': 'baz'},
            {'op': 'add', 'path': '/ping', 'value': 'pong'},
            {'op': 'replace', 'path': '/protected', 'value': True},
            {'op': 'remove', 'path': '/type'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual('image-2', image['name'])
        self.assertEqual('vhd', image['disk_format'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertTrue(image['protected'])
        self.assertFalse('type' in image, response.text)

        # Adding 11 image properties should fail since configured limit is 10
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        changes = []
        for i in range(11):
            changes.append({'op': 'add',
                            'path': '/ping%i' % i,
                            'value': 'pong'})

        data = jsonutils.dumps(changes)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(413, response.status_code, response.text)

        # Adding 3 image locations should fail since configured limit is 2
        for i in range(3):
            file_path = os.path.join(self.test_dir, 'fake_image_%i' % i)
            with open(file_path, 'w') as fap:
                fap.write('glance')

        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        changes = []
        for i in range(3):
            changes.append({'op': 'add', 'path': '/locations/-',
                            'value': {'url': 'file://{0}'.format(
                                os.path.join(self.test_dir,
                                             'fake_image_%i' % i)),
                                      'metadata': {}},
                            })

        data = jsonutils.dumps(changes)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(413, response.status_code, response.text)

        # Ensure the v2.0 json-patch content type is accepted
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([{'add': '/ding', 'value': 'dong'}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual('dong', image['ding'])

        # Updates should persist across requests
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertTrue(image['protected'])
        self.assertFalse('type' in image, response.text)

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(204, response.status_code)

        def _verify_image_checksum_and_status(checksum, status):
            # Checksum should be populated and status should be active
            path = self._url('/v2/images/%s' % image_id)
            response = requests.get(path, headers=self._headers())
            self.assertEqual(200, response.status_code)
            image = jsonutils.loads(response.text)
            self.assertEqual(checksum, image['checksum'])
            self.assertEqual(status, image['status'])

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(204, response.status_code)

        expected_checksum = '8f113e38d28a79a5a451b16048cc2b72'
        _verify_image_checksum_and_status(expected_checksum, 'active')

        # `disk_format` and `container_format` cannot
        # be replaced when the image is active.
        immutable_paths = ['/disk_format', '/container_format']
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        path = self._url('/v2/images/%s' % image_id)
        for immutable_path in immutable_paths:
            data = jsonutils.dumps([
                {'op': 'replace', 'path': immutable_path, 'value': 'ari'},
            ])
            response = requests.patch(path, headers=headers, data=data)
            self.assertEqual(403, response.status_code)

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        self.assertEqual(expected_checksum, response.headers['Content-MD5'])
        self.assertEqual(response.text, 'ZZZZZ')

        # Uploading duplicate data should be rejected with a 409. The
        # original data should remain untouched.
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='XXX')
        self.assertEqual(409, response.status_code)
        _verify_image_checksum_and_status(expected_checksum, 'active')

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        self.assertEqual(5, jsonutils.loads(response.text)['size'])

        # Deletion should not work on protected images
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(403, response.status_code)

        # Unprotect image for deletion
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Remove all locations of the image then the image size shouldn't be
        # able to access
        path = self._url('/v2/images/%s' % image2_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/locations', 'value': []}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertNotIn('size', image)
        self.assertNotIn('virtual_size', image)
        self.assertEqual('queued', image['status'])

        # Deletion should work. Deleting image-1
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

        # Image list should now contain just image-2
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Deleting image-2 should work
        path = self._url('/v2/images/%s' % image2_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_size_cap(self):
        self.api_server.image_size_cap = 128
        self.start_servers(**self.__dict__.copy())
        # create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-size-cap-test-image',
                                'type': 'kernel', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        image = jsonutils.loads(response.text)
        image_id = image['id']

        #try to populate it with oversized data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})

        class StreamSim(object):
            # Using a one-shot iterator to force chunked transfer in the PUT
            # request
            def __init__(self, size):
                self.size = size

            def __iter__(self):
                yield 'Z' * self.size

        response = requests.put(path, headers=headers, data=StreamSim(
                                self.api_server.image_size_cap + 1))
        self.assertEqual(413, response.status_code)

        # hashlib.md5('Z'*129).hexdigest()
        #     == '76522d28cb4418f12704dfa7acd6e7ee'
        # If the image has this checksum, it means that the whole stream was
        # accepted and written to the store, which should not be the case.
        path = self._url('/v2/images/{0}'.format(image_id))
        headers = self._headers({'content-type': 'application/json'})
        response = requests.get(path, headers=headers)
        image_checksum = jsonutils.loads(response.text).get('checksum')
        self.assertNotEqual(image_checksum, '76522d28cb4418f12704dfa7acd6e7ee')

    def test_permissions(self):
        # Create an image that belongs to TENANT1
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'raw',
                                'container_format': 'bare'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_id = jsonutils.loads(response.text)['id']

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(204, response.status_code)

        # TENANT1 should see the image in their list
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
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
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # TENANT2 should not be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(404, response.status_code)

        # TENANT2 should not be able to modify the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT2,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        data = jsonutils.dumps(doc)
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
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Roles': 'admin',
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # TENANT3 should now see the image in their list
        path = self._url('/v2/images')
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT3 should also be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # TENANT3 still should not be able to modify the image
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT3,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        # TENANT3 should not be able to delete the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.delete(path, headers=headers)
        self.assertEqual(403, response.status_code)

        # Image data should still be present after the failed delete
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        self.stop_servers()

    def test_property_protections_with_roles(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_roles
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        ## Create an image for role member with extra props
        # Raises 403 since user is not allowed to set 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        ## Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Returned image entity should have 'x_owner_foo'
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_owner_foo': 'o_s_bar',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Create an image for role spl_role with extra props
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps({'name': 'image-1',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'spl_create_prop': 'create_bar',
                                'spl_create_prop_policy': 'create_policy_bar',
                                'spl_read_prop': 'read_bar',
                                'spl_update_prop': 'update_bar',
                                'spl_delete_prop': 'delete_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Attempt to replace, add and remove properties which are forbidden
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/spl_read_prop', 'value': 'r'},
            {'op': 'replace', 'path': '/spl_update_prop', 'value': 'u'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)

        # Attempt to replace, add and remove properties which are forbidden
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            {'op': 'add', 'path': '/spl_new_prop', 'value': 'new'},
            {'op': 'remove', 'path': '/spl_create_prop'},
            {'op': 'remove', 'path': '/spl_delete_prop'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)

        # Attempt to replace, add and remove properties
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/spl_update_prop', 'value': 'u'},
            {'op': 'remove', 'path': '/spl_delete_prop'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_update_prop' has update permission for spl_role
        # hence the value has changed
        self.assertEqual('u', image['spl_update_prop'])

        # 'spl_delete_prop' has delete permission for spl_role
        # hence the property has been deleted
        self.assertTrue('spl_delete_prop' not in image.keys())

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_property_protections_with_policies(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_policies
        self.api_server.property_protection_rule_format = 'policies'
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        ## Create an image for role member with extra props
        # Raises 403 since user is not allowed to set 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        ## Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Returned image entity
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Create an image for role spl_role with extra props
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'spl_role, admin'})
        data = jsonutils.dumps({'name': 'image-1',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'spl_creator_policy': 'creator_bar',
                                'spl_default_policy': 'default_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('creator_bar', image['spl_creator_policy'])
        self.assertEqual('default_bar', image['spl_default_policy'])

        # Attempt to replace a property which is permitted
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': 'r'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_creator_policy' has update permission for admin
        # hence the value has changed
        self.assertEqual('r', image['spl_creator_policy'])

        # Attempt to replace a property which is forbidden
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': 'z'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)

        # Attempt to read properties
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'random_role'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        image = jsonutils.loads(response.text)
        # 'random_role' is allowed read 'spl_default_policy'.
        self.assertEqual(image['spl_default_policy'], 'default_bar')
        # 'random_role' is forbidden to read 'spl_creator_policy'.
        self.assertFalse('spl_creator_policy' in image)

        # Attempt to add and remove properties which are permitted
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/spl_creator_policy'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_creator_policy' has delete permission for admin
        # hence the value has been deleted
        self.assertFalse('spl_creator_policy' in image)

        # Attempt to read a property that is permitted
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'random_role'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual(image['spl_default_policy'], 'default_bar')

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        self.stop_servers()

    def test_property_protections_special_chars_roles(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_roles
        self.start_servers(**self.__dict__.copy())

        # Verify both admin and unknown role can create properties marked with
        # '@'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_admin': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_admin': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_joe_soap': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_joe_soap': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Verify both admin and unknown role can read properties marked with
        # '@'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can update properties marked with
        # '@'
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_all_permitted_joe_soap', 'value': '2'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertEqual('2', image['x_all_permitted_joe_soap'])
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_all_permitted_joe_soap', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertEqual('3', image['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can delete properties marked with
        # '@'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_a': '1',
            'x_all_permitted_b': '2'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_all_permitted_a'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_all_permitted_a', image.keys())
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_all_permitted_b'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_all_permitted_b', image.keys())

        # Verify neither admin nor unknown role can create a property protected
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_permitted_admin': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_permitted_joe_soap': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        # Verify neither admin nor unknown role can read properties marked with
        # '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_read': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())

        # Verify neither admin nor unknown role can update properties marked
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_update': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('1', image['x_none_update'])
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '2'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code, response.text)

        # Verify neither admin nor unknown role can delete properties marked
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_delete': '1',
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code, response.text)

        self.stop_servers()

    def test_property_protections_special_chars_policies(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_policies
        self.api_server.property_protection_rule_format = 'policies'
        self.start_servers(**self.__dict__.copy())

        # Verify both admin and unknown role can create properties marked with
        # '@'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_admin': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_admin': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_joe_soap': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'private',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_joe_soap': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(image[key], value, key)

        # Verify both admin and unknown role can read properties marked with
        # '@'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can update properties marked with
        # '@'
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_all_permitted_joe_soap', 'value': '2'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertEqual('2', image['x_all_permitted_joe_soap'])
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_all_permitted_joe_soap', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertEqual('3', image['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can delete properties marked with
        # '@'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_all_permitted_a': '1',
            'x_all_permitted_b': '2'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_all_permitted_a'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_all_permitted_a', image.keys())
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_all_permitted_b'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_all_permitted_b', image.keys())

        # Verify neither admin nor unknown role can create a property protected
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_permitted_admin': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_permitted_joe_soap': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code)

        # Verify neither admin nor unknown role can read properties marked with
        # '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_read': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())

        # Verify neither admin nor unknown role can update properties marked
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_update': '1'
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('1', image['x_none_update'])
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '2'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code, response.text)

        # Verify neither admin nor unknown role can delete properties marked
        # with '!'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({
            'name': 'image-1',
            'disk_format': 'aki',
            'container_format': 'aki',
            'x_none_delete': '1',
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(403, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(409, response.status_code, response.text)

        self.stop_servers()

    def test_tag_lifecycle(self):
        # Create an image with a tag - duplicate should be ignored
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'tags': ['sniff', 'sniff']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image_id = jsonutils.loads(response.text)['id']

        # Image should show a list with a single tag
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff'], tags)

        # Delete all tags
        for tag in tags:
            path = self._url('/v2/images/%s/tags/%s' % (image_id, tag))
            response = requests.delete(path, headers=self._headers())
            self.assertEqual(204, response.status_code)

        # Update image with too many tags via PUT
        # Configured limit is 10 tags
        for i in range(10):
            path = self._url('/v2/images/%s/tags/foo%i' % (image_id, i))
            response = requests.put(path, headers=self._headers())
            self.assertEqual(204, response.status_code)

        # 11th tag should fail
        path = self._url('/v2/images/%s/tags/fail_me' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(413, response.status_code)

        # Make sure the 11th tag was not added
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(10, len(tags))

        # Update image tags via PATCH
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [
            {
                'op': 'replace',
                'path': '/tags',
                'value': ['foo'],
            },
        ]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # Update image with too many tags via PATCH
        # Configured limit is 10 tags
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        tags = ['foo%d' % i for i in range(11)]
        doc = [
            {
                'op': 'replace',
                'path': '/tags',
                'value': tags,
            },
        ]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(413, response.status_code)

        # Tags should not have changed since request was over limit
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['foo'], tags)

        # Update image with duplicate tag - it should be ignored
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [
            {
                'op': 'replace',
                'path': '/tags',
                'value': ['sniff', 'snozz', 'snozz'],
            },
        ]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['snozz', 'sniff'], tags)

        # Image should show the appropriate tags
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['snozz', 'sniff'], tags)

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
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['gabe@example.com', 'snozz', 'sniff'], tags)

        # Query images by single tag
        path = self._url('/v2/images?tag=sniff')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by multiple tags
        path = self._url('/v2/images?tag=sniff&tag=snozz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and other attributes
        path = self._url('/v2/images?tag=sniff&status=queued')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and a nonexistent tag
        path = self._url('/v2/images?tag=sniff&tag=fake')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # The tag should be deletable
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

        # List of tags should reflect the deletion
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['snozz', 'sniff'], tags)

        # Deleting the same tag should return a 404
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(404, response.status_code)

        # The tags won't be able to to query the images after deleting
        path = self._url('/v2/images?tag=gabe%%40example.com')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_images_container(self):
        # Image list should be empty and no next link should be present
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        first = jsonutils.loads(response.text)['first']
        self.assertEqual(0, len(images))
        self.assertTrue('next' not in jsonutils.loads(response.text))
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
            data = jsonutils.dumps(fixture)
            response = requests.post(path, headers=headers, data=data)
            self.assertEqual(201, response.status_code)
            images.append(jsonutils.loads(response.text))

        # Image list should contain 7 images
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(7, len(body['images']))
        self.assertEqual('/v2/images', body['first'])
        self.assertFalse('next' in jsonutils.loads(response.text))

        # Begin pagination after the first image
        template_url = ('/v2/images?limit=2&sort_dir=asc&sort_key=name'
                        '&marker=%s&type=kernel&ping=pong')
        path = self._url(template_url % images[2]['id'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[6]['id'], images[0]['id']], response_ids)

        # Continue pagination using next link from previous request
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[5]['id'], images[1]['id']], response_ids)

        # Continue pagination - expect no results
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
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

    def test_image_visibility_to_different_users(self):
        self.cleanup()
        self.api_server.deployment_flavor = 'fakeauth'
        self.registry_server.deployment_flavor = 'fakeauth'
        self.start_servers(**self.__dict__.copy())

        owners = ['admin', 'tenant1', 'tenant2', 'none']
        visibilities = ['public', 'private']

        for owner in owners:
            for visibility in visibilities:
                path = self._url('/v2/images')
                headers = self._headers({
                    'content-type': 'application/json',
                    'X-Auth-Token': 'createuser:%s:admin' % owner,
                })
                data = jsonutils.dumps({
                    'name': '%s-%s' % (owner, visibility),
                    'visibility': visibility,
                })
                response = requests.post(path, headers=headers, data=data)
                self.assertEqual(201, response.status_code)

        def list_images(tenant, role='', visibility=None):
            auth_token = 'user:%s:%s' % (tenant, role)
            headers = {'X-Auth-Token': auth_token}
            path = self._url('/v2/images')
            if visibility is not None:
                path += '?visibility=%s' % visibility
            response = requests.get(path, headers=headers)
            self.assertEqual(response.status_code, 200)
            return jsonutils.loads(response.text)['images']

        # 1. Known user sees public and their own images
        images = list_images('tenant1')
        self.assertEqual(len(images), 5)
        for image in images:
            self.assertTrue(image['visibility'] == 'public'
                            or 'tenant1' in image['name'])

        # 2. Known user, visibility=public, sees all public images
        images = list_images('tenant1', visibility='public')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'public')

        # 3. Known user, visibility=private, sees only their private image
        images = list_images('tenant1', visibility='private')
        self.assertEqual(len(images), 1)
        image = images[0]
        self.assertEqual(image['visibility'], 'private')
        self.assertTrue('tenant1' in image['name'])

        # 4. Unknown user sees only public images
        images = list_images('none')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'public')

        # 5. Unknown user, visibility=public, sees only public images
        images = list_images('none', visibility='public')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'public')

        # 6. Unknown user, visibility=private, sees no images
        images = list_images('none', visibility='private')
        self.assertEqual(len(images), 0)

        # 7. Unknown admin sees all images
        images = list_images('none', role='admin')
        self.assertEqual(len(images), 8)

        # 8. Unknown admin, visibility=public, shows only public images
        images = list_images('none', role='admin', visibility='public')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'public')

        # 9. Unknown admin, visibility=private, sees only private images
        images = list_images('none', role='admin', visibility='private')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'private')

        # 10. Known admin sees all images
        images = list_images('admin', role='admin')
        self.assertEqual(len(images), 8)

        # 11. Known admin, visibility=public, sees all public images
        images = list_images('admin', role='admin', visibility='public')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'public')

        # 12. Known admin, visibility=private, sees all private images
        images = list_images('admin', role='admin', visibility='private')
        self.assertEqual(len(images), 4)
        for image in images:
            self.assertEqual(image['visibility'], 'private')

        self.stop_servers()

    def test_update_locations(self):
        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual(image['status'], 'queued')
        self.assertNotIn('size', image)
        self.assertNotIn('virtual_size', image)

        file_path = os.path.join(self.test_dir, 'fake_image')
        with open(file_path, 'w') as fap:
            fap.write('glance')

        # Update locations for the queued image
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([{'op': 'replace', 'path': '/locations',
                                 'value': [{'url': 'file://' + file_path,
                                            'metadata': {}}]}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code, response.text)

        # The image size should be updated
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image['size'], 6)


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
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki',
                                'visibility': 'public'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image direct_url should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertFalse('direct_url' in image)

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(204, response.status_code)

        # Image direct_url should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('direct_url' in image)

        # Image direct_url should be visible to non-owner, non-admin user
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json',
                                 'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('direct_url', image)

        # Image direct_url should be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertTrue('direct_url' in image)

        self.stop_servers()

    def test_image_multiple_location_url_visible(self):
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image locations should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        self.assertTrue(image["locations"] == [])

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(204, response.status_code)

        # Image locations should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        loc = image['locations']
        self.assertTrue(len(loc) > 0)
        loc = loc[0]
        self.assertTrue('url' in loc)
        self.assertTrue('metadata' in loc)

        self.stop_servers()

    def test_image_direct_url_not_visible(self):

        self.api_server.show_image_direct_url = False
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(204, response.status_code)

        # Image direct_url should not be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertFalse('direct_url' in image)

        # Image direct_url should not be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertFalse('direct_url' in image)

        self.stop_servers()


class TestImageLocationSelectionStrategy(functional.FunctionalTest):

    def setUp(self):
        super(TestImageLocationSelectionStrategy, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.foo_image_file = tempfile.NamedTemporaryFile()
        self.foo_image_file.write("foo image file")
        self.foo_image_file.flush()
        self.addCleanup(self.foo_image_file.close)
        ret = test_http.http_server("foo_image_id", "foo_image")
        self.http_server_pid, self.http_port = ret

    def tearDown(self):
        if self.http_server_pid is not None:
            os.kill(self.http_server_pid, signal.SIGKILL)

        super(TestImageLocationSelectionStrategy, self).tearDown()

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

    def test_image_locations_with_order_strategy(self):
        self.api_server.show_image_direct_url = True
        self.api_server.show_multiple_locations = True
        self.image_location_quota = 10
        self.api_server.location_strategy = 'location_order'
        preference = "http, swift, filesystem"
        self.api_server.store_type_location_strategy_preference = preference
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image locations should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        self.assertTrue(image["locations"] == [])

       # Update image locations via PATCH
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        values = [{'url': 'file://%s' % self.foo_image_file.name,
                   'metadata': {'idx': '1'}},
                  {'url': 'http://127.0.0.1:%s/foo_image' % self.http_port,
                   'metadata': {'idx': '0'}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        # Image locations should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        self.assertEqual(image['locations'], values)
        self.assertTrue('direct_url' in image)
        self.assertEqual(image['direct_url'], values[0]['url'])

        self.stop_servers()

    def test_image_locatons_with_store_type_strategy(self):
        self.api_server.show_image_direct_url = True
        self.api_server.show_multiple_locations = True
        self.image_location_quota = 10
        self.api_server.location_strategy = 'store_type'
        preference = "http, swift, filesystem"
        self.api_server.store_type_location_strategy_preference = preference
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image locations should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        self.assertTrue(image["locations"] == [])

       # Update image locations via PATCH
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        values = [{'url': 'file://%s' % self.foo_image_file.name,
                   'metadata': {'idx': '1'}},
                  {'url': 'http://127.0.0.1:%s/foo_image' % self.http_port,
                   'metadata': {'idx': '0'}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

        values.sort(key=lambda loc: int(loc['metadata']['idx']))

        # Image locations should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(200, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertTrue('locations' in image)
        self.assertEqual(image['locations'], values)
        self.assertTrue('direct_url' in image)
        self.assertEqual(image['direct_url'], values[0]['url'])

        self.stop_servers()


class TestImageMembers(functional.FunctionalTest):

    def setUp(self):
        super(TestImageMembers, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'fakeauth'
        self.registry_server.deployment_flavor = 'fakeauth'
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

    def test_image_member_lifecycle(self):

        def get_header(tenant, role=''):
            auth_token = 'user:%s:%s' % (tenant, role)
            headers = {'X-Auth-Token': auth_token}
            return headers

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        owners = ['tenant1', 'tenant2', 'admin']
        visibilities = ['public', 'private']
        image_fixture = []
        for owner in owners:
            for visibility in visibilities:
                path = self._url('/v2/images')
                headers = self._headers({
                    'content-type': 'application/json',
                    'X-Auth-Token': 'createuser:%s:admin' % owner,
                })
                data = jsonutils.dumps({
                    'name': '%s-%s' % (owner, visibility),
                    'visibility': visibility,
                })
                response = requests.post(path, headers=headers, data=data)
                self.assertEqual(201, response.status_code)
                image_fixture.append(jsonutils.loads(response.text))

        # Image list should contain 4 images for tenant1
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 3 images for TENANT3
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Add Image member for tenant1-private image
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        body = jsonutils.dumps({'member': TENANT3})
        response = requests.post(path, headers=get_header('tenant1'),
                                 data=body)
        self.assertEqual(200, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[1]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertTrue('created_at' in image_member)
        self.assertTrue('updated_at' in image_member)
        self.assertEqual('pending', image_member['status'])

        # Image list should contain 3 images for TENANT3
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Image list should contain 0 shared images for TENANT3
        # because default is accepted
        path = self._url('/v2/images?visibility=shared')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 4 images for TENANT3 with status pending
        path = self._url('/v2/images?member_status=pending')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 4 images for TENANT3 with status all
        path = self._url('/v2/images?member_status=all')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 1 image for TENANT3 with status pending
        # and visibility shared
        path = self._url('/v2/images?member_status=pending&visibility=shared')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'tenant1-private')

        # Image list should contain 0 image for TENANT3 with status rejected
        # and visibility shared
        path = self._url('/v2/images?member_status=rejected&visibility=shared')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility shared
        path = self._url('/v2/images?member_status=accepted&visibility=shared')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility private
        path = self._url('/v2/images?visibility=private')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image tenant2-private's image members list should contain no members
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        response = requests.get(path, headers=get_header('tenant2'))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Tenant 1, who is the owner cannot change status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_header('tenant1'), data=body)
        self.assertEqual(403, response.status_code)

        # Tenant 1, who is the owner can get status of its own image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(body['status'], 'pending')
        self.assertEqual(body['image_id'], image_fixture[1]['id'])
        self.assertEqual(body['member_id'], TENANT3)

        # Tenant 3, who is the member can get status of its own status
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(body['status'], 'pending')
        self.assertEqual(body['image_id'], image_fixture[1]['id'])
        self.assertEqual(body['member_id'], TENANT3)

        # Tenant 2, who not the owner cannot get status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_header('tenant2'))
        self.assertEqual(404, response.status_code)

        # Tenant 3 can change status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_header(TENANT3), data=body)
        self.assertEqual(200, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[1]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertEqual('accepted', image_member['status'])

        # Image list should contain 4 images for TENANT3 because status is
        # accepted
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_header(TENANT3))
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Tenant 3 invalid status change
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'invalid-status'})
        response = requests.put(path, headers=get_header(TENANT3), data=body)
        self.assertEqual(400, response.status_code)

        # Owner cannot change status of image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_header('tenant1'), data=body)
        self.assertEqual(403, response.status_code)

        # Add Image member for tenant2-private image
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        body = jsonutils.dumps({'member': TENANT4})
        response = requests.post(path, headers=get_header('tenant2'),
                                 data=body)
        self.assertEqual(200, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
        self.assertEqual(TENANT4, image_member['member_id'])
        self.assertTrue('created_at' in image_member)
        self.assertTrue('updated_at' in image_member)

        # Add Image member to public image
        path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
        body = jsonutils.dumps({'member': TENANT2})
        response = requests.post(path, headers=get_header('tenant1'),
                                 data=body)
        self.assertEqual(403, response.status_code)

        # Image tenant1-private's members list should contain 1 member
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Admin can see any members
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        response = requests.get(path, headers=get_header('tenant1', 'admin'))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Image members not found for private image not owned by TENANT 1
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(404, response.status_code)

        # Image members forbidden for public image
        path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(403, response.status_code)

        # Image Member Cannot delete Image membership
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_header(TENANT3))
        self.assertEqual(403, response.status_code)

        # Delete Image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_header('tenant1'))
        self.assertEqual(204, response.status_code)

        # Now the image has only no members
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(200, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Adding 11 image members should fail since configured limit is 10
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        for i in range(10):
            body = jsonutils.dumps({'member': str(uuid.uuid4())})
            response = requests.post(path, headers=get_header('tenant1'),
                                     data=body)
            self.assertEqual(200, response.status_code)

        body = jsonutils.dumps({'member': str(uuid.uuid4())})
        response = requests.post(path, headers=get_header('tenant1'),
                                 data=body)
        self.assertEqual(413, response.status_code)

        # Delete Image members not found for public image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[0]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_header('tenant1'))
        self.assertEqual(404, response.status_code)

        self.stop_servers()


class TestQuotas(functional.FunctionalTest):

    def setUp(self):
        super(TestQuotas, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.user_storage_quota = 100
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

    def _upload_image_test(self, data_src, expected_status):
        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image (with a deployer-defined property)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'testimg',
                                'type': 'kernel',
                                'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # upload data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=data_src)
        self.assertEqual(expected_status, response.status_code)

        # Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(204, response.status_code)

    def test_image_upload_under_quota(self):
        data = 'x' * (self.user_storage_quota - 1)
        self._upload_image_test(data, 204)

    def test_image_upload_exceed_quota(self):
        data = 'x' * (self.user_storage_quota + 1)
        self._upload_image_test(data, 413)

    def test_chunked_image_upload_under_quota(self):
        def data_gen():
            yield 'x' * (self.user_storage_quota - 1)

        self._upload_image_test(data_gen(), 204)

    def test_chunked_image_upload_exceed_quota(self):
        def data_gen():
            yield 'x' * (self.user_storage_quota + 1)

        self._upload_image_test(data_gen(), 413)
