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

import hashlib
import os
import subprocess
import tempfile
import time
import uuid

from oslo_serialization import jsonutils
from oslo_utils.secretutils import md5
from oslo_utils import units
import requests
import six
from six.moves import http_client as http
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
from six.moves import urllib

from glance.tests import functional
from glance.tests.functional import ft_utils as func_utils
from glance.tests import utils as test_utils


TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


def get_auth_header(tenant, tenant_id=None, role='', headers=None):
    """Return headers to authenticate as a specific tenant.

    :param tenant: Tenant for the auth token
    :param tenant_id: Optional tenant ID for the X-Tenant-Id header
    :param role: Optional user role
    :param headers: Optional list of headers to add to
    """
    if not headers:
        headers = {}
    auth_token = 'user:%s:%s' % (tenant, role)
    headers.update({'X-Auth-Token': auth_token})
    if tenant_id:
        headers.update({'X-Tenant-Id': tenant_id})
    return headers


class TestImages(functional.FunctionalTest):

    def setUp(self):
        super(TestImages, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server.deployment_flavor = 'noauth'
        for i in range(3):
            ret = test_utils.start_http_server("foo_image_id%d" % i,
                                               "foo_image%d" % i)
            setattr(self, 'http_server%d' % i, ret[1])
            setattr(self, 'http_port%d' % i, ret[2])
        self.api_server.send_identity_credentials = True

    def tearDown(self):
        for i in range(3):
            httpd = getattr(self, 'http_server%d' % i, None)
            if httpd:
                httpd.shutdown()
                httpd.server_close()

        super(TestImages, self).tearDown()

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

    def test_image_import_using_glance_direct(self):
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # glance-direct should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("glance-direct", discovery_calls)

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

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
            u'os_hidden',
            u'id',
            u'file',
            u'min_disk',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Upload some image data to staging area
        path = self._url('/v2/images/%s/stage' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ZZZZZ'
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Verify image is in uploading state, hashes are None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='uploading')

        # Import image to store
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
        })
        data = jsonutils.dumps({'method': {
            'name': 'glance-direct'
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=10,
                                   delay_sec=0.2)
        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(5, jsonutils.loads(response.text)['size'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_using_web_download(self):
        self.config(node_staging_uri="file:///tmp/staging/")
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # web-download should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("web-download", discovery_calls)

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

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
            u'os_hidden',
            u'id',
            u'file',
            u'min_disk',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and hashes are None
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  status='queued')

        # Import image to store
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps({'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=20,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_lifecycle(self):
        # Image list should be empty
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki', 'abc': 'xyz',
                                'protected': True})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
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
            u'os_hidden',
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
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
            u'locations',
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': True,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'foo': 'bar',
            'abc': 'xyz',
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Create another image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-2', 'type': 'kernel',
                                'bar': 'foo', 'disk_format': 'aki',
                                'container_format': 'aki', 'xyz': 'abc'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

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
            u'os_hidden',
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
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
            u'locations',
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-2',
            'tags': [],
            'visibility': 'shared',
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
            self.assertEqual(value, image[key], key)

        # Image list should now have two entries
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image_id, images[1]['id'])

        # Image list should list only image-2 as image-1 doesn't contain the
        # property 'bar'
        path = self._url('/v2/images?bar=foo')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Image list should list only image-1 as image-2 doesn't contain the
        # property 'foo'
        path = self._url('/v2/images?foo=bar')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # The "changes-since" filter shouldn't work on glance v2
        path = self._url('/v2/images?changes-since=20001007T10:10:10')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        path = self._url('/v2/images?changes-since=aaa')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list should list only image-1 based on the filter
        # 'protected=true'
        path = self._url('/v2/images?protected=true')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Image list should list only image-2 based on the filter
        # 'protected=false'
        path = self._url('/v2/images?protected=false')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Image list should return 400 based on the filter
        # 'protected=False'
        path = self._url('/v2/images?protected=False')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list should list only image-1 based on the filter
        # 'foo=bar&abc=xyz'
        path = self._url('/v2/images?foo=bar&abc=xyz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Image list should list only image-2 based on the filter
        # 'bar=foo&xyz=abc'
        path = self._url('/v2/images?bar=foo&xyz=abc')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Image list should not list anything as the filter 'foo=baz&abc=xyz'
        # is not satisfied by either images
        path = self._url('/v2/images?foo=baz&abc=xyz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Get the image using the returned Location header
        response = requests.get(image_location_header, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertIsNone(image['checksum'])
        self.assertIsNone(image['size'])
        self.assertIsNone(image['virtual_size'])
        self.assertEqual('bar', image['foo'])
        self.assertTrue(image['protected'])
        self.assertEqual('kernel', image['type'])
        self.assertTrue(image['created_at'])
        self.assertTrue(image['updated_at'])
        self.assertEqual(image['updated_at'], image['created_at'])

        # The URI file:// should return a 400 rather than a 500
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        url = ('file://')
        changes = [{
            'op': 'add',
            'path': '/locations/-',
            'value': {
                'url': url,
                'metadata': {}
            }
        }]

        data = jsonutils.dumps(changes)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

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
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual('image-2', image['name'])
        self.assertEqual('vhd', image['disk_format'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertTrue(image['protected'])
        self.assertNotIn('type', image, response.text)

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
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code,
                         response.text)

        # Adding 3 image locations should fail since configured limit is 2
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        changes = []
        for i in range(3):
            url = ('http://127.0.0.1:%s/foo_image' %
                   getattr(self, 'http_port%d' % i))
            changes.append({'op': 'add', 'path': '/locations/-',
                            'value': {'url': url, 'metadata': {}},
                            })

        data = jsonutils.dumps(changes)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code,
                         response.text)

        # Ensure the v2.0 json-patch content type is accepted
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([{'add': '/ding', 'value': 'dong'}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual('dong', image['ding'])

        # Updates should persist across requests
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertTrue(image['protected'])
        self.assertNotIn('type', image, response.text)

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ZZZZZ'
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self, image_id, expect_c,
                                                  expect_h, 'active')

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
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual('ZZZZZ', response.text)

        # Uploading duplicate data should be rejected with a 409. The
        # original data should remain untouched.
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='XXX')
        self.assertEqual(http.CONFLICT, response.status_code)
        func_utils.verify_image_hashes_and_status(self, image_id, expect_c,
                                                  expect_h, 'active')

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(5, jsonutils.loads(response.text)['size'])

        # Should be able to deactivate image
        path = self._url('/v2/images/%s/actions/deactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Change the image to public so TENANT2 can see it
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([{"replace": "/visibility", "value": "public"}])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Tenant2 should get Forbidden when deactivating the public image
        path = self._url('/v2/images/%s/actions/deactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers(
            {'X-Tenant-Id': TENANT2}))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Tenant2 should get Forbidden when reactivating the public image
        path = self._url('/v2/images/%s/actions/reactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers(
            {'X-Tenant-Id': TENANT2}))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Deactivating a deactivated image succeeds (no-op)
        path = self._url('/v2/images/%s/actions/deactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Can't download a deactivated image
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Deactivated image should still be in a listing
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image_id, images[1]['id'])

        # Should be able to reactivate a deactivated image
        path = self._url('/v2/images/%s/actions/reactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Reactivating an active image succeeds (no-op)
        path = self._url('/v2/images/%s/actions/reactivate' % image_id)
        response = requests.post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Deletion should not work on protected images
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Unprotect image for deletion
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image-1
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # And neither should its data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now contain just image-2
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Deleting image-2 should work
        path = self._url('/v2/images/%s' % image2_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create image that tries to send True should return 400
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = 'true'
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Create image that tries to send a string should return 400
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = '"hello"'
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Create image that tries to send 123 should return 400
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = '123'
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        self.stop_servers()

    def _create_qcow(self, size):
        fn = tempfile.mktemp(prefix='glance-unittest-images-',
                             suffix='.qcow')
        subprocess.check_output(
            'qemu-img create -f qcow %s %i' % (fn, size),
            shell=True)
        return fn

    def test_image_upload_qcow_virtual_size_calculation(self):
        self.start_servers(**self.__dict__.copy())

        # Create an image
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'myqcow', 'disk_format': 'qcow2',
                                'container_format': 'bare'})
        response = requests.post(self._url('/v2/images'),
                                 headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code,
                         'Failed to create: %s' % response.text)
        image = response.json()

        # Upload a qcow
        fn = self._create_qcow(128 * units.Mi)
        raw_size = os.path.getsize(fn)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(self._url('/v2/images/%s/file' % image['id']),
                                headers=headers,
                                data=open(fn, 'rb').read())
        os.remove(fn)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Check the image attributes
        response = requests.get(self._url('/v2/images/%s' % image['id']),
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = response.json()
        self.assertEqual(128 * units.Mi, image['virtual_size'])
        self.assertEqual(raw_size, image['size'])

    def test_image_import_qcow_virtual_size_calculation(self):
        self.start_servers(**self.__dict__.copy())

        # Create an image
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'myqcow', 'disk_format': 'qcow2',
                                'container_format': 'bare'})
        response = requests.post(self._url('/v2/images'),
                                 headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code,
                         'Failed to create: %s' % response.text)
        image = response.json()

        # Stage a qcow
        fn = self._create_qcow(128 * units.Mi)
        raw_size = os.path.getsize(fn)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(self._url('/v2/images/%s/stage' % image['id']),
                                headers=headers,
                                data=open(fn, 'rb').read())
        os.remove(fn)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image['id'],
                                                  status='uploading')

        # Import image to store
        path = self._url('/v2/images/%s/import' % image['id'])
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
        })
        data = jsonutils.dumps({'method': {
            'name': 'glance-direct'
        }})
        response = requests.post(
            self._url('/v2/images/%s/import' % image['id']),
            headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image['id'])
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)

        # Check the image attributes
        response = requests.get(self._url('/v2/images/%s' % image['id']),
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = response.json()
        self.assertEqual(128 * units.Mi, image['virtual_size'])
        self.assertEqual(raw_size, image['size'])

    def test_hidden_images(self):
        # Image list should be empty
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'protected': False})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

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
            u'os_hidden',
            u'id',
            u'file',
            u'min_disk',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
            u'locations',
        ])
        self.assertEqual(checked_keys, set(image.keys()))

        # Returned image entity should have os_hidden as False
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'os_hidden': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Create another image wiht hidden true
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-2', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'os_hidden': True})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

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
            u'os_hidden',
            u'id',
            u'file',
            u'min_disk',
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'os_hash_algo',
            u'os_hash_value',
            u'size',
            u'virtual_size',
            u'locations',
        ])
        self.assertEqual(checked_keys, set(image.keys()))

        # Returned image entity should have os_hidden as True
        expected_image = {
            'status': 'queued',
            'name': 'image-2',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image2_id,
            'protected': False,
            'os_hidden': True,
            'file': '/v2/images/%s/file' % image2_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entries
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Image list should list should show one image based on the filter
        # 'hidden=false'
        path = self._url('/v2/images?os_hidden=false')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Image list should list should show one image based on the filter
        # 'hidden=true'
        path = self._url('/v2/images?os_hidden=true')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Image list should return 400 based on the filter
        # 'hidden=abcd'
        path = self._url('/v2/images?os_hidden=abcd')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Upload some image data to image-1
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ZZZZZ'
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)
        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  expect_c,
                                                  expect_h,
                                                  status='active')
        # Upload some image data to image-2
        path = self._url('/v2/images/%s/file' % image2_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'WWWWW'
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)
        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image2_id,
                                                  expect_c,
                                                  expect_h,
                                                  status='active')
        # Hide image-1
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/os_hidden', 'value': True},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertTrue(image['os_hidden'])

        # Image list should now have 0 entries
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should list should show image-1, and image-2 based
        # on the filter 'hidden=true'
        path = self._url('/v2/images?os_hidden=true')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image_id, images[1]['id'])

        # Un-Hide image-1
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/os_hidden', 'value': False},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertFalse(image['os_hidden'])

        # Image list should now have 1 entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Deleting image-1 should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Deleting image-2 should work
        path = self._url('/v2/images/%s' % image2_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_update_readonly_prop(self):
        self.start_servers(**self.__dict__.copy())
        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1'})
        response = requests.post(path, headers=headers, data=data)

        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})

        props = ['/id', '/file', '/location', '/schema', '/self']

        for prop in props:
            doc = [{'op': 'replace',
                    'path': prop,
                    'value': 'value1'}]
            data = jsonutils.dumps(doc)
            response = requests.patch(path, headers=headers, data=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        for prop in props:
            doc = [{'op': 'remove',
                    'path': prop,
                    'value': 'value1'}]
            data = jsonutils.dumps(doc)
            response = requests.patch(path, headers=headers, data=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        for prop in props:
            doc = [{'op': 'add',
                    'path': prop,
                    'value': 'value1'}]
            data = jsonutils.dumps(doc)
            response = requests.patch(path, headers=headers, data=data)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        self.stop_servers()

    def test_methods_that_dont_accept_illegal_bodies(self):
        # Check images can be reached
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)

        # Test all the schemas
        schema_urls = [
            '/v2/schemas/images',
            '/v2/schemas/image',
            '/v2/schemas/members',
            '/v2/schemas/member',
        ]
        for value in schema_urls:
            path = self._url(value)
            data = jsonutils.dumps(["body"])
            response = requests.get(path, headers=self._headers(), data=data)
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Create image for use with tests
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        test_urls = [
            ('/v2/images/%s', 'get'),
            ('/v2/images/%s/actions/deactivate', 'post'),
            ('/v2/images/%s/actions/reactivate', 'post'),
            ('/v2/images/%s/tags/mytag', 'put'),
            ('/v2/images/%s/tags/mytag', 'delete'),
            ('/v2/images/%s/members', 'get'),
            ('/v2/images/%s/file', 'get'),
            ('/v2/images/%s', 'delete'),
        ]

        for link, method in test_urls:
            path = self._url(link % image_id)
            data = jsonutils.dumps(["body"])
            response = getattr(requests, method)(
                path, headers=self._headers(), data=data)
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # DELETE /images/imgid without legal json
        path = self._url('/v2/images/%s' % image_id)
        data = '{"hello"]'
        response = requests.delete(path, headers=self._headers(), data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # POST /images/imgid/members
        path = self._url('/v2/images/%s/members' % image_id)
        data = jsonutils.dumps({'member': TENANT3})
        response = requests.post(path, headers=self._headers(), data=data)
        self.assertEqual(http.OK, response.status_code)

        # GET /images/imgid/members/memid
        path = self._url('/v2/images/%s/members/%s' % (image_id, TENANT3))
        data = jsonutils.dumps(["body"])
        response = requests.get(path, headers=self._headers(), data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # DELETE /images/imgid/members/memid
        path = self._url('/v2/images/%s/members/%s' % (image_id, TENANT3))
        data = jsonutils.dumps(["body"])
        response = requests.delete(path, headers=self._headers(), data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        self.stop_servers()

    def test_download_random_access_w_range_request(self):
        """
        Test partial download 'Range' requests for images (random image access)
        """
        self.start_servers(**self.__dict__.copy())
        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-2', 'type': 'kernel',
                                'bar': 'foo', 'disk_format': 'aki',
                                'container_format': 'aki', 'xyz': 'abc'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Upload data to image
        image_data = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # test for success on satisfiable Range request.
        range_ = 'bytes=3-10'
        headers = self._headers({'Range': range_})
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.PARTIAL_CONTENT, response.status_code)
        self.assertEqual('DEFGHIJK', response.text)

        # test for failure on unsatisfiable Range request.
        range_ = 'bytes=10-5'
        headers = self._headers({'Range': range_})
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE,
                         response.status_code)

        self.stop_servers()

    def test_download_random_access_w_content_range(self):
        """
        Even though Content-Range is incorrect on requests, we support it
        for backward compatibility with clients written for pre-Pike Glance.
        The following test is for 'Content-Range' requests, which we have
        to ensure that we prevent regression.
        """
        self.start_servers(**self.__dict__.copy())
        # Create another image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-2', 'type': 'kernel',
                                'bar': 'foo', 'disk_format': 'aki',
                                'container_format': 'aki', 'xyz': 'abc'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Upload data to image
        image_data = 'Z' * 15
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        result_body = ''
        for x in range(15):
            # NOTE(flaper87): Read just 1 byte. Content-Range is
            # 0-indexed and it specifies the first byte to read
            # and the last byte to read.
            content_range = 'bytes %s-%s/15' % (x, x)
            headers = self._headers({'Content-Range': content_range})
            path = self._url('/v2/images/%s/file' % image_id)
            response = requests.get(path, headers=headers)
            self.assertEqual(http.PARTIAL_CONTENT, response.status_code)
            result_body += response.text

        self.assertEqual(result_body, image_data)

        # test for failure on unsatisfiable request for ContentRange.
        content_range = 'bytes 3-16/15'
        headers = self._headers({'Content-Range': content_range})
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE,
                         response.status_code)

        self.stop_servers()

    def test_download_policy_when_cache_is_not_enabled(self):

        rules = {'context_is_admin': 'role:admin',
                 'default': '',
                 'add_image': '',
                 'get_image': '',
                 'modify_image': '',
                 'upload_image': '',
                 'delete_image': '',
                 'download_image': '!'}
        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in six.iteritems(expected_image):
            self.assertEqual(value, image[key], key)

        # Upload data to image
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Get an image should fail
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        self.stop_servers()

    def test_download_image_not_allowed_using_restricted_policy(self):

        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }

        for key, value in six.iteritems(expected_image):
            self.assertEqual(value, image[key], key)

        # Upload data to image
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Get an image should fail
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream',
                                 'X-Roles': '_member_'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        self.stop_servers()

    def test_download_image_allowed_using_restricted_policy(self):

        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }

        for key, value in six.iteritems(expected_image):
            self.assertEqual(value, image[key], key)

        # Upload data to image
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Get an image should be allowed
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream',
                                 'X-Roles': 'member'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        self.stop_servers()

    def test_download_image_raises_service_unavailable(self):
        """Test image download returns HTTPServiceUnavailable."""
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Update image locations via PATCH
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        thread, httpd, http_port = test_utils.start_http_server(image_id,
                                                                "image-1")
        values = [{'url': 'http://127.0.0.1:%s/image-1' % http_port,
                   'metadata': {'idx': '0'}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code)

        # Download an image should work
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Stop http server used to update image location
        httpd.shutdown()
        httpd.server_close()

        # Download an image should raise HTTPServiceUnavailable
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.SERVICE_UNAVAILABLE, response.status_code)

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        self.stop_servers()

    def test_image_modification_works_for_owning_tenant_id(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "project_id:%(owner)s",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers['content-type'] = media_type
        del headers['X-Roles']
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/name', 'value': 'new-name'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code)

        self.stop_servers()

    def test_image_modification_fails_on_mismatched_tenant_ids(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "'A-Fake-Tenant-Id':%(owner)s",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers['content-type'] = media_type
        del headers['X-Roles']
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/name', 'value': 'new-name'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        self.stop_servers()

    def test_member_additions_works_for_owning_tenant_id(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "project_id:%(owner)s",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Get the image's members resource
        path = self._url('/v2/images/%s/members' % image_id)
        body = jsonutils.dumps({'member': TENANT3})
        del headers['X-Roles']
        response = requests.post(path, headers=headers, data=body)
        self.assertEqual(http.OK, response.status_code)

        self.stop_servers()

    def test_image_additions_works_only_for_specific_tenant_id(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "'{0}':%(owner)s".format(TENANT1),
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        headers['X-Tenant-Id'] = TENANT2
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        self.stop_servers()

    def test_owning_tenant_id_can_retrieve_image_information(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "project_id:%(owner)s",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Remove the admin role
        del headers['X-Roles']
        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Can retrieve the image as TENANT1
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Can retrieve the image's members as TENANT1
        path = self._url('/v2/images/%s/members' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        headers['X-Tenant-Id'] = TENANT2
        response = requests.get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        self.stop_servers()

    def test_owning_tenant_can_publicize_image(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "publicize_image": "project_id:%(owner)s",
            "get_image": "project_id:%(owner)s",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT1,
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code)

    def test_owning_tenant_can_communitize_image(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "communitize_image": "project_id:%(owner)s",
            "get_image": "project_id:%(owner)s",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT1,
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'community'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(200, response.status_code)

    def test_owning_tenant_can_delete_image(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "publicize_image": "project_id:%(owner)s",
            "get_image": "project_id:%(owner)s",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted":
            "not ('aki':%(container_format)s and role:_member_)",
            "download_image": "role:admin or rule:restricted",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

    def test_list_show_ok_when_get_location_allowed_for_admins(self):
        self.api_server.show_image_direct_url = True
        self.api_server.show_multiple_locations = True
        # setup context to allow a list locations by admin only
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "role:admin",
            "delete_image": "",
            "restricted": "",
            "download_image": "",
            "add_member": "",
        }

        self.set_policy_rules(rules)
        self.start_servers(**self.__dict__.copy())

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Tenant-Id': TENANT1})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image's ID
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Can retrieve the image as TENANT1
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Can list images as TENANT1
        path = self._url('/v2/images')
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

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
        self.assertEqual(http.CREATED, response.status_code)

        image = jsonutils.loads(response.text)
        image_id = image['id']

        # try to populate it with oversized data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})

        class StreamSim(object):
            # Using a one-shot iterator to force chunked transfer in the PUT
            # request
            def __init__(self, size):
                self.size = size

            def __iter__(self):
                yield b'Z' * self.size

        response = requests.put(path, headers=headers, data=StreamSim(
                                self.api_server.image_size_cap + 1))
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

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
        self.start_servers(**self.__dict__.copy())
        # Create an image that belongs to TENANT1
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'raw',
                                'container_format': 'bare'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        image_id = jsonutils.loads(response.text)['id']

        # Upload some image data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # TENANT1 should see the image in their list
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT1 should be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)

        # TENANT2 should not see the image in their list
        path = self._url('/v2/images')
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # TENANT2 should not be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # TENANT2 should not be able to modify the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT2,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # TENANT2 should not be able to delete the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = requests.delete(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Publicize the image as an admin of TENANT1
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Roles': 'admin',
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code)

        # TENANT3 should now see the image in their list
        path = self._url('/v2/images')
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT3 should also be able to access the image directly
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # TENANT3 still should not be able to modify the image
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT3,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # TENANT3 should not be able to delete the image, either
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = requests.delete(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image data should still be present after the failed delete
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

        self.stop_servers()

    def test_property_protections_with_roles(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_roles
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image for role member with extra props
        # Raises 403 since user is not allowed to set 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have 'x_owner_foo'
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_owner_foo': 'o_s_bar',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

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
                                'spl_delete_prop': 'delete_bar',
                                'spl_delete_empty_prop': ''})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Attempt to replace properties
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            # Updating an empty property to verify bug #1332103.
            {'op': 'replace', 'path': '/spl_update_prop', 'value': ''},
            {'op': 'replace', 'path': '/spl_update_prop', 'value': 'u'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_update_prop' has update permission for spl_role
        # hence the value has changed
        self.assertEqual('u', image['spl_update_prop'])

        # Attempt to remove properties
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'spl_role'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/spl_delete_prop'},
            # Deleting an empty property to verify bug #1332103.
            {'op': 'remove', 'path': '/spl_delete_empty_prop'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_delete_prop' and 'spl_delete_empty_prop' have delete
        # permission for spl_role hence the property has been deleted
        self.assertNotIn('spl_delete_prop', image.keys())
        self.assertNotIn('spl_delete_empty_prop', image.keys())

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        self.stop_servers()

    def test_property_protections_with_policies(self):
        # Enable property protection
        self.api_server.property_protection_file = self.property_file_policies
        self.api_server.property_protection_rule_format = 'policies'
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image for role member with extra props
        # Raises 403 since user is not allowed to set 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'member'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

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
        self.assertEqual(http.CREATED, response.status_code)
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
            # Updating an empty property to verify bug #1332103.
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': ''},
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': 'r'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Attempt to read properties
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'random_role'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        image = jsonutils.loads(response.text)
        # 'random_role' is allowed read 'spl_default_policy'.
        self.assertEqual(image['spl_default_policy'], 'default_bar')
        # 'random_role' is forbidden to read 'spl_creator_policy'.
        self.assertNotIn('spl_creator_policy', image)

        # Attempt to replace and remove properties which are permitted
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = jsonutils.dumps([
            # Deleting an empty property to verify bug #1332103.
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': ''},
            {'op': 'remove', 'path': '/spl_creator_policy'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)

        # 'spl_creator_policy' has delete permission for admin
        # hence the value has been deleted
        self.assertNotIn('spl_creator_policy', image)

        # Attempt to read a property that is permitted
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'random_role'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual(image['spl_default_policy'], 'default_bar')

        # Image Deletion should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_admin': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)
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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_joe_soap': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Verify both admin and unknown role can read properties marked with
        # '@'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.FORBIDDEN, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code)

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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code, response.text)

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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code, response.text)

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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_admin': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)
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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'x_all_permitted_joe_soap': '1',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Verify both admin and unknown role can read properties marked with
        # '@'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('1', image['x_all_permitted_joe_soap'])
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.OK, response.status_code, response.text)
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
        self.assertEqual(http.FORBIDDEN, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code)

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
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('x_none_read', image.keys())
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'joe_soap'})
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code, response.text)

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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code, response.text)

        self.stop_servers()

    def test_tag_lifecycle(self):
        self.start_servers(**self.__dict__.copy())
        # Create an image with a tag - duplicate should be ignored
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'tags': ['sniff', 'sniff']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)
        image_id = jsonutils.loads(response.text)['id']

        # Image should show a list with a single tag
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff'], tags)

        # Delete all tags
        for tag in tags:
            path = self._url('/v2/images/%s/tags/%s' % (image_id, tag))
            response = requests.delete(path, headers=self._headers())
            self.assertEqual(http.NO_CONTENT, response.status_code)

        # Update image with too many tags via PUT
        # Configured limit is 10 tags
        for i in range(10):
            path = self._url('/v2/images/%s/tags/foo%i' % (image_id, i))
            response = requests.put(path, headers=self._headers())
            self.assertEqual(http.NO_CONTENT, response.status_code)

        # 11th tag should fail
        path = self._url('/v2/images/%s/tags/fail_me' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Make sure the 11th tag was not added
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.OK, response.status_code)

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
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Tags should not have changed since request was over limit
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Image should show the appropriate tags
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Attempt to tag the image with a duplicate should be ignored
        path = self._url('/v2/images/%s/tags/snozz' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Create another more complex tag
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.put(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Double-check that the tags container on the image is populated
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['gabe@example.com', 'sniff', 'snozz'],
                         sorted(tags))

        # Query images by single tag
        path = self._url('/v2/images?tag=sniff')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by multiple tags
        path = self._url('/v2/images?tag=sniff&tag=snozz')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and other attributes
        path = self._url('/v2/images?tag=sniff&status=queued')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and a nonexistent tag
        path = self._url('/v2/images?tag=sniff&tag=fake')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # The tag should be deletable
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # List of tags should reflect the deletion
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Deleting the same tag should return a 404
        path = self._url('/v2/images/%s/tags/gabe%%40example.com' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # The tags won't be able to query the images after deleting
        path = self._url('/v2/images?tag=gabe%%40example.com')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Try to add a tag that is too long
        big_tag = 'a' * 300
        path = self._url('/v2/images/%s/tags/%s' % (image_id, big_tag))
        response = requests.put(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Tags should not have changed since request was over limit
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        self.stop_servers()

    def test_images_container(self):
        # Image list should be empty and no next link should be present
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        first = jsonutils.loads(response.text)['first']
        self.assertEqual(0, len(images))
        self.assertNotIn('next', jsonutils.loads(response.text))
        self.assertEqual('/v2/images', first)

        # Create 7 images
        images = []
        fixtures = [
            {'name': 'image-3', 'type': 'kernel', 'ping': 'pong',
             'container_format': 'ami', 'disk_format': 'ami'},
            {'name': 'image-4', 'type': 'kernel', 'ping': 'pong',
             'container_format': 'bare', 'disk_format': 'ami'},
            {'name': 'image-1', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-3', 'type': 'ramdisk', 'ping': 'pong'},
            {'name': 'image-2', 'type': 'kernel', 'ping': 'ding'},
            {'name': 'image-3', 'type': 'kernel', 'ping': 'pong'},
            {'name': 'image-2,image-5', 'type': 'kernel', 'ping': 'pong'},
        ]
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        for fixture in fixtures:
            data = jsonutils.dumps(fixture)
            response = requests.post(path, headers=headers, data=data)
            self.assertEqual(http.CREATED, response.status_code)
            images.append(jsonutils.loads(response.text))

        # Image list should contain 7 images
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(7, len(body['images']))
        self.assertEqual('/v2/images', body['first'])
        self.assertNotIn('next', jsonutils.loads(response.text))

        # Image list filters by created_at time
        url_template = '/v2/images?created_at=lt:%s'
        path = self._url(url_template % images[0]['created_at'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['images']))
        self.assertEqual(url_template % images[0]['created_at'],
                         urllib.parse.unquote(body['first']))

        # Image list filters by updated_at time
        url_template = '/v2/images?updated_at=lt:%s'
        path = self._url(url_template % images[2]['updated_at'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(3, len(body['images']))
        self.assertEqual(url_template % images[2]['updated_at'],
                         urllib.parse.unquote(body['first']))

        # Image list filters by updated_at and created time with invalid value
        url_template = '/v2/images?%s=lt:invalid_value'
        for filter in ['updated_at', 'created_at']:
            path = self._url(url_template % filter)
            response = requests.get(path, headers=self._headers())
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by updated_at and created_at with invalid operator
        url_template = '/v2/images?%s=invalid_operator:2015-11-19T12:24:02Z'
        for filter in ['updated_at', 'created_at']:
            path = self._url(url_template % filter)
            response = requests.get(path, headers=self._headers())
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by non-'URL encoding' value
        path = self._url('/v2/images?name=%FF')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by name with in operator
        url_template = '/v2/images?name=in:%s'
        filter_value = 'image-1,image-2'
        path = self._url(url_template % filter_value)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(3, len(body['images']))

        # Image list filters by container_format with in operator
        url_template = '/v2/images?container_format=in:%s'
        filter_value = 'bare,ami'
        path = self._url(url_template % filter_value)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(2, len(body['images']))

        # Image list filters by disk_format with in operator
        url_template = '/v2/images?disk_format=in:%s'
        filter_value = 'bare,ami,iso'
        path = self._url(url_template % filter_value)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(2, len(body['images']))

        # Begin pagination after the first image
        template_url = ('/v2/images?limit=2&sort_dir=asc&sort_key=name'
                        '&marker=%s&type=kernel&ping=pong')
        path = self._url(template_url % images[2]['id'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[6]['id'], images[0]['id']], response_ids)

        # Continue pagination using next link from previous request
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[5]['id'], images[1]['id']], response_ids)

        # Continue pagination - expect no results
        path = self._url(body['next'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['images']))

        # Delete first image
        path = self._url('/v2/images/%s' % images[0]['id'])
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Ensure bad request for using a deleted image as marker
        path = self._url('/v2/images?marker=%s' % images[0]['id'])
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        self.stop_servers()

    def test_image_visibility_to_different_users(self):
        self.cleanup()
        self.api_server.deployment_flavor = 'fakeauth'

        kwargs = self.__dict__.copy()
        self.start_servers(**kwargs)

        owners = ['admin', 'tenant1', 'tenant2', 'none']
        visibilities = ['public', 'private', 'shared', 'community']

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
                self.assertEqual(http.CREATED, response.status_code)

        def list_images(tenant, role='', visibility=None):
            auth_token = 'user:%s:%s' % (tenant, role)
            headers = {'X-Auth-Token': auth_token}
            path = self._url('/v2/images')
            if visibility is not None:
                path += '?visibility=%s' % visibility
            response = requests.get(path, headers=headers)
            self.assertEqual(http.OK, response.status_code)
            return jsonutils.loads(response.text)['images']

        # 1. Known user sees public and their own images
        images = list_images('tenant1')
        self.assertEqual(7, len(images))
        for image in images:
            self.assertTrue(image['visibility'] == 'public'
                            or 'tenant1' in image['name'])

        # 2. Known user, visibility=public, sees all public images
        images = list_images('tenant1', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 3. Known user, visibility=private, sees only their private image
        images = list_images('tenant1', visibility='private')
        self.assertEqual(1, len(images))
        image = images[0]
        self.assertEqual('private', image['visibility'])
        self.assertIn('tenant1', image['name'])

        # 4. Known user, visibility=shared, sees only their shared image
        images = list_images('tenant1', visibility='shared')
        self.assertEqual(1, len(images))
        image = images[0]
        self.assertEqual('shared', image['visibility'])
        self.assertIn('tenant1', image['name'])

        # 5. Known user, visibility=community, sees all community images
        images = list_images('tenant1', visibility='community')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('community', image['visibility'])

        # 6. Unknown user sees only public images
        images = list_images('none')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 7. Unknown user, visibility=public, sees only public images
        images = list_images('none', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 8. Unknown user, visibility=private, sees no images
        images = list_images('none', visibility='private')
        self.assertEqual(0, len(images))

        # 9. Unknown user, visibility=shared, sees no images
        images = list_images('none', visibility='shared')
        self.assertEqual(0, len(images))

        # 10. Unknown user, visibility=community, sees only community images
        images = list_images('none', visibility='community')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('community', image['visibility'])

        # 11. Unknown admin sees all images except for community images
        images = list_images('none', role='admin')
        self.assertEqual(12, len(images))

        # 12. Unknown admin, visibility=public, shows only public images
        images = list_images('none', role='admin', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 13. Unknown admin, visibility=private, sees only private images
        images = list_images('none', role='admin', visibility='private')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('private', image['visibility'])

        # 14. Unknown admin, visibility=shared, sees only shared images
        images = list_images('none', role='admin', visibility='shared')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('shared', image['visibility'])

        # 15. Unknown admin, visibility=community, sees only community images
        images = list_images('none', role='admin', visibility='community')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('community', image['visibility'])

        # 16. Known admin sees all images, except community images owned by
        # others
        images = list_images('admin', role='admin')
        self.assertEqual(13, len(images))

        # 17. Known admin, visibility=public, sees all public images
        images = list_images('admin', role='admin', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 18. Known admin, visibility=private, sees all private images
        images = list_images('admin', role='admin', visibility='private')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('private', image['visibility'])

        # 19. Known admin, visibility=shared, sees all shared images
        images = list_images('admin', role='admin', visibility='shared')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('shared', image['visibility'])

        # 20. Known admin, visibility=community, sees all community images
        images = list_images('admin', role='admin', visibility='community')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('community', image['visibility'])

        self.stop_servers()

    def test_update_locations(self):
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())
        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])
        self.assertIsNone(image['size'])
        self.assertIsNone(image['virtual_size'])

        # Update locations for the queued image
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_port0
        data = jsonutils.dumps([{'op': 'replace', 'path': '/locations',
                                 'value': [{'url': url, 'metadata': {}}]
                                 }])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # The image size should be updated
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(10, image['size'])

    def test_update_locations_with_restricted_sources(self):
        self.api_server.show_multiple_locations = True
        self.start_servers(**self.__dict__.copy())
        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])
        self.assertIsNone(image['size'])
        self.assertIsNone(image['virtual_size'])

        # Update locations for the queued image
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = jsonutils.dumps([{'op': 'replace', 'path': '/locations',
                                 'value': [{'url': 'file:///foo_image',
                                            'metadata': {}}]
                                 }])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        data = jsonutils.dumps([{'op': 'replace', 'path': '/locations',
                                 'value': [{'url': 'swift+config:///foo_image',
                                            'metadata': {}}]
                                 }])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)


class TestImagesIPv6(functional.FunctionalTest):
    """Verify that API and REG servers running IPv6 can communicate"""

    def setUp(self):
        """
        First applying monkey patches of functions and methods which have
        IPv4 hardcoded.
        """
        # Setting up initial monkey patch (1)
        test_utils.get_unused_port_ipv4 = test_utils.get_unused_port
        test_utils.get_unused_port_and_socket_ipv4 = (
            test_utils.get_unused_port_and_socket)
        test_utils.get_unused_port = test_utils.get_unused_port_ipv6
        test_utils.get_unused_port_and_socket = (
            test_utils.get_unused_port_and_socket_ipv6)
        super(TestImagesIPv6, self).setUp()
        self.cleanup()
        # Setting up monkey patch (2), after object is ready...
        self.ping_server_ipv4 = self.ping_server
        self.ping_server = self.ping_server_ipv6
        self.include_scrubber = False

    def tearDown(self):
        # Cleaning up monkey patch (2).
        self.ping_server = self.ping_server_ipv4
        super(TestImagesIPv6, self).tearDown()
        # Cleaning up monkey patch (1).
        test_utils.get_unused_port = test_utils.get_unused_port_ipv4
        test_utils.get_unused_port_and_socket = (
            test_utils.get_unused_port_and_socket_ipv4)

    def _url(self, path):
        return "http://[::1]:%d%s" % (self.api_port, path)

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

    def test_image_list_ipv6(self):
        # Image list should be empty

        self.start_servers(**self.__dict__.copy())

        requests.get(self._url('/'), headers=self._headers())

        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))


class TestImageDirectURLVisibility(functional.FunctionalTest):

    def setUp(self):
        super(TestImageDirectURLVisibility, self).setUp()
        self.cleanup()
        self.include_scrubber = False
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

    def test_image_direct_url_visible(self):

        self.api_server.show_image_direct_url = True
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image direct_url should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('direct_url', image)

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image direct_url should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('direct_url', image)

        # Image direct_url should be visible to non-owner, non-admin user
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json',
                                 'X-Tenant-Id': TENANT2})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('direct_url', image)

        # Image direct_url should be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertIn('direct_url', image)

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
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image locations should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual([], image["locations"])

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image locations should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        loc = image['locations']
        self.assertGreater(len(loc), 0)
        loc = loc[0]
        self.assertIn('url', loc)
        self.assertIn('metadata', loc)

        self.stop_servers()

    def test_image_direct_url_not_visible(self):

        self.api_server.show_image_direct_url = False
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Upload some image data, setting the image location
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data='ZZZZZ')
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image direct_url should not be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('direct_url', image)

        # Image direct_url should not be visible in a list
        path = self._url('/v2/images')
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertNotIn('direct_url', image)

        self.stop_servers()


class TestImageLocationSelectionStrategy(functional.FunctionalTest):

    def setUp(self):
        super(TestImageLocationSelectionStrategy, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server.deployment_flavor = 'noauth'
        for i in range(3):
            ret = test_utils.start_http_server("foo_image_id%d" % i,
                                               "foo_image%d" % i)
            setattr(self, 'http_server%d' % i, ret[1])
            setattr(self, 'http_port%d' % i, ret[2])

    def tearDown(self):
        for i in range(3):
            httpd = getattr(self, 'http_server%d' % i, None)
            if httpd:
                httpd.shutdown()
                httpd.server_close()

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
        self.assertEqual(http.CREATED, response.status_code)

        # Get the image id
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Image locations should not be visible before location is set
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual([], image["locations"])

        # Update image locations via PATCH
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        values = [{'url': 'http://127.0.0.1:%s/foo_image' % self.http_port0,
                   'metadata': {}},
                  {'url': 'http://127.0.0.1:%s/foo_image' % self.http_port1,
                   'metadata': {}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code)

        # Image locations should be visible
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'Content-Type': 'application/json'})
        response = requests.get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual(values, image['locations'])
        self.assertIn('direct_url', image)
        self.assertEqual(values[0]['url'], image['direct_url'])

        self.stop_servers()


class TestImageMembers(functional.FunctionalTest):

    def setUp(self):
        super(TestImageMembers, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server.deployment_flavor = 'fakeauth'
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

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        owners = ['tenant1', 'tenant2', 'admin']
        visibilities = ['community', 'private', 'public', 'shared']
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
                self.assertEqual(http.CREATED, response.status_code)
                image_fixture.append(jsonutils.loads(response.text))

        # Image list should contain 6 images for tenant1
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(6, len(images))

        # Image list should contain 3 images for TENANT3
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Add Image member for tenant1-shared image
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        body = jsonutils.dumps({'member': TENANT3})
        response = requests.post(path, headers=get_auth_header('tenant1'),
                                 data=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertIn('created_at', image_member)
        self.assertIn('updated_at', image_member)
        self.assertEqual('pending', image_member['status'])

        # Image list should contain 3 images for TENANT3
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Image list should contain 0 shared images for TENANT3
        # because default is accepted
        path = self._url('/v2/images?visibility=shared')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 4 images for TENANT3 with status pending
        path = self._url('/v2/images?member_status=pending')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 4 images for TENANT3 with status all
        path = self._url('/v2/images?member_status=all')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 1 image for TENANT3 with status pending
        # and visibility shared
        path = self._url('/v2/images?member_status=pending&visibility=shared')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'tenant1-shared')

        # Image list should contain 0 image for TENANT3 with status rejected
        # and visibility shared
        path = self._url('/v2/images?member_status=rejected&visibility=shared')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility shared
        path = self._url('/v2/images?member_status=accepted&visibility=shared')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility private
        path = self._url('/v2/images?visibility=private')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image tenant2-shared's image members list should contain no members
        path = self._url('/v2/images/%s/members' % image_fixture[7]['id'])
        response = requests.get(path, headers=get_auth_header('tenant2'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Tenant 1, who is the owner cannot change status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_auth_header('tenant1'),
                                data=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Tenant 1, who is the owner can get status of its own image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual('pending', body['status'])
        self.assertEqual(image_fixture[3]['id'], body['image_id'])
        self.assertEqual(TENANT3, body['member_id'])

        # Tenant 3, who is the member can get status of its own status
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual('pending', body['status'])
        self.assertEqual(image_fixture[3]['id'], body['image_id'])
        self.assertEqual(TENANT3, body['member_id'])

        # Tenant 2, who not the owner cannot get status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header('tenant2'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Tenant 3 can change status of image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_auth_header(TENANT3),
                                data=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertEqual('accepted', image_member['status'])

        # Image list should contain 4 images for TENANT3 because status is
        # accepted
        path = self._url('/v2/images')
        response = requests.get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Tenant 3 invalid status change
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'invalid-status'})
        response = requests.put(path, headers=get_auth_header(TENANT3),
                                data=body)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Owner cannot change status of image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        body = jsonutils.dumps({'status': 'accepted'})
        response = requests.put(path, headers=get_auth_header('tenant1'),
                                data=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member for tenant2-shared image
        path = self._url('/v2/images/%s/members' % image_fixture[7]['id'])
        body = jsonutils.dumps({'member': TENANT4})
        response = requests.post(path, headers=get_auth_header('tenant2'),
                                 data=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[7]['id'], image_member['image_id'])
        self.assertEqual(TENANT4, image_member['member_id'])
        self.assertIn('created_at', image_member)
        self.assertIn('updated_at', image_member)

        # Add Image member to public image
        path = self._url('/v2/images/%s/members' % image_fixture[2]['id'])
        body = jsonutils.dumps({'member': TENANT2})
        response = requests.post(path, headers=get_auth_header('tenant1'),
                                 data=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member to private image
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        body = jsonutils.dumps({'member': TENANT2})
        response = requests.post(path, headers=get_auth_header('tenant1'),
                                 data=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member to community image
        path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
        body = jsonutils.dumps({'member': TENANT2})
        response = requests.post(path, headers=get_auth_header('tenant1'),
                                 data=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image tenant1-shared's members list should contain 1 member
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Admin can see any members
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1',
                                                              role='admin'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Image members not found for private image not owned by TENANT 1
        path = self._url('/v2/images/%s/members' % image_fixture[7]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image members forbidden for public image
        path = self._url('/v2/images/%s/members' % image_fixture[2]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image members forbidden for community image
        path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image members forbidden for private image
        path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Member Cannot delete Image membership
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[3]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Now the image has no members
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Adding 11 image members should fail since configured limit is 10
        path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
        for i in range(10):
            body = jsonutils.dumps({'member': str(uuid.uuid4())})
            response = requests.post(path, headers=get_auth_header('tenant1'),
                                     data=body)
            self.assertEqual(http.OK, response.status_code)

        body = jsonutils.dumps({'member': str(uuid.uuid4())})
        response = requests.post(path, headers=get_auth_header('tenant1'),
                                 data=body)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Get Image member should return not found for public image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[2]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Get Image member should return not found for community image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[0]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Get Image member should return not found for private image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Delete Image member should return forbidden for public image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[2]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member should return forbidden for community image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[0]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member should return forbidden for private image
        path = self._url('/v2/images/%s/members/%s' % (image_fixture[1]['id'],
                                                       TENANT3))
        response = requests.delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        self.stop_servers()


class TestQuotas(functional.FunctionalTest):

    def setUp(self):
        super(TestQuotas, self).setUp()
        self.cleanup()
        self.include_scrubber = False
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
        self.assertEqual(http.OK, response.status_code)
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
        self.assertEqual(http.CREATED, response.status_code)
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
        self.assertEqual(http.NO_CONTENT, response.status_code)

    def test_image_upload_under_quota(self):
        data = b'x' * (self.user_storage_quota - 1)
        self._upload_image_test(data, http.NO_CONTENT)

    def test_image_upload_exceed_quota(self):
        data = b'x' * (self.user_storage_quota + 1)
        self._upload_image_test(data, http.REQUEST_ENTITY_TOO_LARGE)

    def test_chunked_image_upload_under_quota(self):
        def data_gen():
            yield b'x' * (self.user_storage_quota - 1)

        self._upload_image_test(data_gen(), http.NO_CONTENT)

    def test_chunked_image_upload_exceed_quota(self):
        def data_gen():
            yield b'x' * (self.user_storage_quota + 1)

        self._upload_image_test(data_gen(), http.REQUEST_ENTITY_TOO_LARGE)


class TestImagesMultipleBackend(functional.MultipleBackendFunctionalTest):

    def setUp(self):
        super(TestImagesMultipleBackend, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server_multiple_backend.deployment_flavor = 'noauth'
        for i in range(3):
            ret = test_utils.start_http_server("foo_image_id%d" % i,
                                               "foo_image%d" % i)
            setattr(self, 'http_server%d' % i, ret[1])
            setattr(self, 'http_port%d' % i, ret[2])

    def tearDown(self):
        for i in range(3):
            httpd = getattr(self, 'http_server%d' % i, None)
            if httpd:
                httpd.shutdown()
                httpd.server_close()

        super(TestImagesMultipleBackend, self).tearDown()

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

    def test_image_import_using_glance_direct(self):
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # glance-direct should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("glance-direct", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'

        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Upload some image data to staging area
        image_data = b'QQQQQ'
        path = self._url('/v2/images/%s/stage' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='uploading')

        # Import image to store
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
        })
        data = jsonutils.dumps({'method': {
            'name': 'glance-direct'
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)
        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(len(image_data),
                         jsonutils.loads(response.text)['size'])

        # Ensure image is created in default backend
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_using_glance_direct_different_backend(self):
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # glance-direct should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("glance-direct", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Upload some image data to staging area
        image_data = b'GLANCE IS DEAD SEXY'
        path = self._url('/v2/images/%s/stage' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='uploading')

        # Import image to file2 store (other than default backend)
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
            'X-Image-Meta-Store': 'file2'
        })
        data = jsonutils.dumps({'method': {
            'name': 'glance-direct'
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)
        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(len(image_data),
                         jsonutils.loads(response.text)['size'])

        # Ensure image is created in different backend
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_using_web_download(self):
        self.config(node_staging_uri="file:///tmp/staging/")
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # web-download should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("web-download", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Import image to store
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps({'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=20,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()
        # Ensure image is created in default backend
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_using_web_download_different_backend(self):
        self.config(node_staging_uri="file:///tmp/staging/")
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # web-download should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("web-download", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')
        # Import image to store
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
            'X-Image-Meta-Store': 'file2'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps({'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=20,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in different backend
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_multi_stores(self):
        self.config(node_staging_uri="file:///tmp/staging/")
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # web-download should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("web-download", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')
        # Import image to multiple stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps(
            {'method': {'name': 'web-download', 'uri': image_data_uri},
             'stores': ['file1', 'file2']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in the two stores
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_copy_image_lifecycle(self):
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # copy-image should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("copy-image", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')
        # Import image to multiple stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps(
            {'method': {'name': 'web-download', 'uri': image_data_uri},
             'stores': ['file1']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in the one store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Copy newly created image to file2 and file3 stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        data = jsonutils.dumps(
            {'method': {'name': 'copy-image'},
             'stores': ['file2', 'file3']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is copied
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['file2', 'file3'],
                                    max_sec=40,
                                    delay_sec=0.2,
                                    start_delay_sec=1)

        # Ensure image is copied to the file2 and file3 store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])
        self.assertIn('file3', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_copy_image_revert_lifecycle(self):
        # Test if copying task fails in between then the rollback
        # should delete the data from only stores to which it is
        # copied and not from the existing stores.
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # copy-image should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("copy-image", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')
        # Import image to multiple stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps(
            {'method': {'name': 'web-download', 'uri': image_data_uri},
             'stores': ['file1']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in the one store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Copy newly created image to file2 and file3 stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # NOTE(abhishekk): Deleting file3 image directory to trigger the
        # failure, so that we can verify that revert call does not delete
        # the data from existing stores
        # NOTE(danms): Do this before we start the import, on a later store,
        # which will cause that store to fail after we have already completed
        # the first one.
        os.rmdir(self.test_dir + "/images_3")

        data = jsonutils.dumps(
            {'method': {'name': 'copy-image'},
             'stores': ['file2', 'file3']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        def poll_callback(image):
            # NOTE(danms): We need to wait for the specific
            # arrangement we're expecting, which is that file3 has
            # failed, nothing else is importing, and file2 has been
            # removed from stores by the revert.
            return not (image['os_glance_importing_to_stores'] == '' and
                        image['os_glance_failed_import'] == 'file3' and
                        image['stores'] == 'file1')

        func_utils.poll_entity(self._url('/v2/images/%s' % image_id),
                               self._headers(),
                               poll_callback)

        # Here we check that the failure of 'file3' caused 'file2' to
        # be removed from image['stores'], and that 'file3' is reported
        # as failed in the appropriate status list. Since the import
        # started with 'store1' being populated, that should remain,
        # but 'store2' should be reverted/removed.
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])
        self.assertNotIn('file2', jsonutils.loads(response.text)['stores'])
        self.assertNotIn('file3', jsonutils.loads(response.text)['stores'])
        fail_key = 'os_glance_failed_import'
        pend_key = 'os_glance_importing_to_stores'
        self.assertEqual('file3', jsonutils.loads(response.text)[fail_key])
        self.assertEqual('', jsonutils.loads(response.text)[pend_key])

        # Copy newly created image to file2 and file3 stores and
        # all_stores_must_succeed set to false.
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        data = jsonutils.dumps(
            {'method': {'name': 'copy-image'},
             'stores': ['file2', 'file3'],
             'all_stores_must_succeed': False})

        for i in range(0, 5):
            response = requests.post(path, headers=headers, data=data)
            if response.status_code != http.CONFLICT:
                break
            # We might race with the revert of the previous task and do not
            # really have a good way to make sure that it's done. In order
            # to make sure we tolerate the 409 possibility when import
            # locking is added, gracefully wait a few times before failing.
            time.sleep(1)

        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is copied
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['file2'],
                                    max_sec=10,
                                    delay_sec=0.2,
                                    start_delay_sec=1,
                                    failure_scenario=True)

        # Ensure data is not deleted from existing stores as well as
        # from the stores where it is copied successfully
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])
        self.assertNotIn('file3', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_import_multi_stores_specifying_all_stores(self):
        self.config(node_staging_uri="file:///tmp/staging/")
        self.start_servers(**self.__dict__.copy())

        # Image list should be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # web-download should be available in discovery response
        path = self._url('/v2/info/import')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        self.assertIn("web-download", discovery_calls)

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'type',
            u'min_ram',
            u'schema',
            u'disk_format',
            u'container_format',
            u'owner',
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': False,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')
        # Import image to multiple stores
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps(
            {'method': {'name': 'web-download', 'uri': image_data_uri},
             'all_stores': True})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in the two stores
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file3', jsonutils.loads(response.text)['stores'])
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Deleting image should work
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_lifecycle(self):
        # Image list should be empty
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki', 'abc': 'xyz',
                                'protected': True})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'
        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': True,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'foo': 'bar',
            'abc': 'xyz',
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        image_data = b'OpenStack Rules, Other Clouds Drool'
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # Ensure image is created in default backend
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual(image_data.decode('utf-8'), response.text)

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(len(image_data),
                         jsonutils.loads(response.text)['size'])

        # Unprotect image for deletion
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # And neither should its data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()

    def test_image_lifecycle_different_backend(self):
        # Image list should be empty
        self.start_servers(**self.__dict__.copy())
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # file1 and file2 should be available in discovery response
        available_stores = ['file1', 'file2', 'file3']
        path = self._url('/v2/info/stores')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        discovery_calls = jsonutils.loads(
            response.text)['stores']
        # os_glance_staging_store should not be available in discovery response
        for stores in discovery_calls:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertFalse(stores["id"].startswith("os_glance_"))

        # Create an image (with two deployer-defined properties)
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'foo': 'bar', 'disk_format': 'aki',
                                'container_format': 'aki', 'abc': 'xyz',
                                'protected': True})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Check 'OpenStack-image-store-ids' header present in response
        self.assertIn('OpenStack-image-store-ids', response.headers)
        for store in available_stores:
            self.assertIn(store, response.headers['OpenStack-image-store-ids'])

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
            u'checksum',
            u'size',
            u'virtual_size',
            u'os_hidden',
            u'os_hash_algo',
            u'os_hash_value'

        ])
        self.assertEqual(checked_keys, set(image.keys()))
        expected_image = {
            'status': 'queued',
            'name': 'image-1',
            'tags': [],
            'visibility': 'shared',
            'self': '/v2/images/%s' % image_id,
            'protected': True,
            'file': '/v2/images/%s/file' % image_id,
            'min_disk': 0,
            'foo': 'bar',
            'abc': 'xyz',
            'type': 'kernel',
            'min_ram': 0,
            'schema': '/v2/schemas/image',
        }
        for key, value in expected_image.items():
            self.assertEqual(value, image[key], key)

        # Image list should now have one entry
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Try to download data before its uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        image_data = b'just a passing glance'
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers({
            'Content-Type': 'application/octet-stream',
            'X-Image-Meta-Store': 'file2'
        })
        response = requests.put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        expect_c = six.text_type(md5(image_data,
                                     usedforsecurity=False).hexdigest())
        expect_h = six.text_type(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # Ensure image is created in different backend
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])

        # Try to download the data that was just uploaded
        path = self._url('/v2/images/%s/file' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual(image_data.decode('utf-8'), response.text)

        # Ensure the size is updated to reflect the data uploaded
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(len(image_data),
                         jsonutils.loads(response.text)['size'])

        # Unprotect image for deletion
        path = self._url('/v2/images/%s' % image_id)
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        data = jsonutils.dumps(doc)
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image
        path = self._url('/v2/images/%s' % image_id)
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # This image should be no longer be directly accessible
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # And neither should its data
        path = self._url('/v2/images/%s/file' % image_id)
        headers = self._headers()
        response = requests.get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now be empty
        path = self._url('/v2/images')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        self.stop_servers()


class TestMultiStoreImageMembers(functional.MultipleBackendFunctionalTest):

    def setUp(self):
        super(TestMultiStoreImageMembers, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server_multiple_backend.deployment_flavor = 'noauth'
        for i in range(3):
            ret = test_utils.start_http_server("foo_image_id%d" % i,
                                               "foo_image%d" % i)
            setattr(self, 'http_server%d' % i, ret[1])
            setattr(self, 'http_port%d' % i, ret[2])

    def tearDown(self):
        for i in range(3):
            httpd = getattr(self, 'http_server%d' % i, None)
            if httpd:
                httpd.shutdown()
                httpd.server_close()

        super(TestMultiStoreImageMembers, self).tearDown()

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

    def test_image_member_lifecycle_for_multiple_stores(self):
        self.start_servers(**self.__dict__.copy())

        try:
            def get_header(tenant, tenant_id=None, role=''):
                return self._headers(custom_headers=get_auth_header(
                    tenant, tenant_id, role))

            # Image list should be empty
            path = self._url('/v2/images')
            response = requests.get(path, headers=get_header('tenant1'))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(0, len(images))

            owners = ['tenant1', 'tenant2', 'admin']
            visibilities = ['community', 'private', 'public', 'shared']
            image_fixture = []
            for owner in owners:
                for visibility in visibilities:
                    path = self._url('/v2/images')
                    headers = self._headers(custom_headers={
                        'content-type': 'application/json',
                        'X-Auth-Token': 'createuser:%s:admin' % owner,
                    })
                    data = jsonutils.dumps({
                        'name': '%s-%s' % (owner, visibility),
                        'visibility': visibility,
                    })
                    response = requests.post(path, headers=headers, data=data)
                    self.assertEqual(http.CREATED, response.status_code)
                    image_fixture.append(jsonutils.loads(response.text))

            # Image list should contain 12 images for tenant1
            path = self._url('/v2/images')
            response = requests.get(path, headers=get_header('tenant1'))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(12, len(images))

            # Image list should contain 3 images for TENANT3
            path = self._url('/v2/images')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(3, len(images))

            # Add Image member for tenant1-shared image
            path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
            body = jsonutils.dumps({'member': TENANT3})
            response = requests.post(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.OK, response.status_code)
            image_member = jsonutils.loads(response.text)
            self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
            self.assertEqual(TENANT3, image_member['member_id'])
            self.assertIn('created_at', image_member)
            self.assertIn('updated_at', image_member)
            self.assertEqual('pending', image_member['status'])

            # Image list should contain 3 images for TENANT3
            path = self._url('/v2/images')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(3, len(images))

            # Image list should contain 0 shared images for TENANT3
            # because default is accepted
            path = self._url('/v2/images?visibility=shared')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(0, len(images))

            # Image list should contain 4 images for TENANT3 with status
            # pending
            path = self._url('/v2/images?member_status=pending')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(4, len(images))

            # Image list should contain 4 images for TENANT3 with status all
            path = self._url('/v2/images?member_status=all')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(4, len(images))

            # Image list should contain 1 image for TENANT3 with status pending
            # and visibility shared
            path = self._url(
                '/v2/images?member_status=pending&visibility=shared')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(1, len(images))
            self.assertEqual(images[0]['name'], 'tenant1-shared')

            # Image list should contain 0 image for TENANT3 with status
            # rejected and visibility shared
            path = self._url(
                '/v2/images?member_status=rejected&visibility=shared')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(0, len(images))

            # Image list should contain 0 image for TENANT3 with status
            # accepted and visibility shared
            path = self._url(
                '/v2/images?member_status=accepted&visibility=shared')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(0, len(images))

            # Image list should contain 0 image for TENANT3 with status
            # accepted and visibility private
            path = self._url('/v2/images?visibility=private')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(0, len(images))

            # Image tenant2-shared's image members list should contain
            # no members
            path = self._url('/v2/images/%s/members' % image_fixture[7]['id'])
            response = requests.get(path, headers=get_header('tenant2'))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual(0, len(body['members']))

            # Tenant 1, who is the owner cannot change status of image member
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            body = jsonutils.dumps({'status': 'accepted'})
            response = requests.put(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Tenant 1, who is the owner can get status of its own image member
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual('pending', body['status'])
            self.assertEqual(image_fixture[3]['id'], body['image_id'])
            self.assertEqual(TENANT3, body['member_id'])

            # Tenant 3, who is the member can get status of its own status
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual('pending', body['status'])
            self.assertEqual(image_fixture[3]['id'], body['image_id'])
            self.assertEqual(TENANT3, body['member_id'])

            # Tenant 2, who not the owner cannot get status of image member
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                'tenant2', tenant_id=TENANT2))
            self.assertEqual(http.NOT_FOUND, response.status_code)

            # Tenant 3 can change status of image member
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            body = jsonutils.dumps({'status': 'accepted'})
            response = requests.put(path, headers=get_header(
                TENANT3, tenant_id=TENANT3), data=body)
            self.assertEqual(http.OK, response.status_code)
            image_member = jsonutils.loads(response.text)
            self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
            self.assertEqual(TENANT3, image_member['member_id'])
            self.assertEqual('accepted', image_member['status'])

            # Image list should contain 4 images for TENANT3 because status is
            # accepted
            path = self._url('/v2/images')
            response = requests.get(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(4, len(images))

            # Tenant 3 invalid status change
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            body = jsonutils.dumps({'status': 'invalid-status'})
            response = requests.put(path, headers=get_header(
                TENANT3, tenant_id=TENANT3), data=body)
            self.assertEqual(http.BAD_REQUEST, response.status_code)

            # Owner cannot change status of image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            body = jsonutils.dumps({'status': 'accepted'})
            response = requests.put(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Add Image member for tenant2-shared image
            path = self._url('/v2/images/%s/members' % image_fixture[7]['id'])
            body = jsonutils.dumps({'member': TENANT4})
            response = requests.post(path, headers=get_header('tenant2'),
                                     data=body)
            self.assertEqual(http.OK, response.status_code)
            image_member = jsonutils.loads(response.text)
            self.assertEqual(image_fixture[7]['id'], image_member['image_id'])
            self.assertEqual(TENANT4, image_member['member_id'])
            self.assertIn('created_at', image_member)
            self.assertIn('updated_at', image_member)

            # Add Image member to public image
            path = self._url('/v2/images/%s/members' % image_fixture[2]['id'])
            body = jsonutils.dumps({'member': TENANT2})
            response = requests.post(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Add Image member to private image
            path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
            body = jsonutils.dumps({'member': TENANT2})
            response = requests.post(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Add Image member to community image
            path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
            body = jsonutils.dumps({'member': TENANT2})
            response = requests.post(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Image tenant1-shared's members list should contain 1 member
            path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual(1, len(body['members']))

            # Admin can see any members
            path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
            response = requests.get(path, headers=get_header('tenant1',
                                                             tenant_id=TENANT1,
                                                             role='admin'))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual(1, len(body['members']))

            # Image members forbidden for public image
            path = self._url('/v2/images/%s/members' % image_fixture[2]['id'])
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertIn("Only shared images have members", response.text)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Image members forbidden for community image
            path = self._url('/v2/images/%s/members' % image_fixture[0]['id'])
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertIn("Only shared images have members", response.text)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Image members forbidden for private image
            path = self._url('/v2/images/%s/members' % image_fixture[1]['id'])
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertIn("Only shared images have members", response.text)
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Image Member Cannot delete Image membership
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            response = requests.delete(path, headers=get_header(
                TENANT3, tenant_id=TENANT3))
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Delete Image member
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[3]['id'], TENANT3))
            response = requests.delete(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.NO_CONTENT, response.status_code)

            # Now the image has no members
            path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.OK, response.status_code)
            body = jsonutils.loads(response.text)
            self.assertEqual(0, len(body['members']))

            # Adding 11 image members should fail since configured limit is 10
            path = self._url('/v2/images/%s/members' % image_fixture[3]['id'])
            for i in range(10):
                body = jsonutils.dumps({'member': str(uuid.uuid4())})
                response = requests.post(path, headers=get_header(
                    'tenant1', tenant_id=TENANT1), data=body)
                self.assertEqual(http.OK, response.status_code)

            body = jsonutils.dumps({'member': str(uuid.uuid4())})
            response = requests.post(path, headers=get_header(
                'tenant1', tenant_id=TENANT1), data=body)
            self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE,
                             response.status_code)

            # Get Image member should return not found for public image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[2]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.NOT_FOUND, response.status_code)

            # Get Image member should return not found for community image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[0]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.NOT_FOUND, response.status_code)

            # Get Image member should return not found for private image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[1]['id'], TENANT3))
            response = requests.get(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.NOT_FOUND, response.status_code)

            # Delete Image member should return forbidden for public image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[2]['id'], TENANT3))
            response = requests.delete(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Delete Image member should return forbidden for community image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[0]['id'], TENANT3))
            response = requests.delete(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.FORBIDDEN, response.status_code)

            # Delete Image member should return forbidden for private image
            path = self._url('/v2/images/%s/members/%s' % (
                image_fixture[1]['id'], TENANT3))
            response = requests.delete(path, headers=get_header(
                'tenant1', tenant_id=TENANT1))
            self.assertEqual(http.FORBIDDEN, response.status_code)
        except requests.exceptions.ConnectionError as e:
            # NOTE(abhishekk): This test fails intermittently for py37
            # environment refer,
            # https://bugs.launchpad.net/glance/+bug/1873735
            self.skipTest("Remote connection closed abruptly: %s" % e.args[0])

        self.stop_servers()


class TestCopyImagePermissions(functional.MultipleBackendFunctionalTest):

    def setUp(self):
        super(TestCopyImagePermissions, self).setUp()
        self.cleanup()
        self.include_scrubber = False
        self.api_server_multiple_backend.deployment_flavor = 'noauth'

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

    def _create_and_import_image_data(self):
        # Create a public image
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json'})
        data = jsonutils.dumps({'name': 'image-1', 'type': 'kernel',
                                'visibility': 'public',
                                'disk_format': 'aki',
                                'container_format': 'aki'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.CREATED, response.status_code)

        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        thread, httpd, port = test_utils.start_standalone_http_server()

        image_data_uri = 'http://localhost:%s/' % port
        data = jsonutils.dumps(
            {'method': {'name': 'web-download', 'uri': image_data_uri},
             'stores': ['file1']})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = six.text_type(md5(r.content,
                                         usedforsecurity=False).hexdigest())
            expect_h = six.text_type(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        return image_id

    def _test_copy_public_image_as_non_admin(self):
        self.start_servers(**self.__dict__.copy())

        # Create a publicly-visible image as TENANT1
        image_id = self._create_and_import_image_data()

        # Ensure image is created in the one store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual('file1', jsonutils.loads(response.text)['stores'])

        # Copy newly created image to file2 store as TENANT2
        path = self._url('/v2/images/%s/import' % image_id)
        headers = self._headers({
            'content-type': 'application/json',
        })
        headers = get_auth_header(TENANT2, TENANT2,
                                  role='member', headers=headers)
        data = jsonutils.dumps(
            {'method': {'name': 'copy-image'},
             'stores': ['file2']})
        response = requests.post(path, headers=headers, data=data)
        return image_id, response

    def test_copy_public_image_as_non_admin(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted": "",
            "download_image": "",
            "add_member": "",
            "publicize_image": "",
            "copy_image": "role:admin",
        }

        self.set_policy_rules(rules)

        image_id, response = self._test_copy_public_image_as_non_admin()
        # Expect failure to copy another user's image
        self.assertEqual(http.FORBIDDEN, response.status_code)

    def test_copy_public_image_as_non_admin_permitted(self):
        rules = {
            "context_is_admin": "role:admin",
            "default": "",
            "add_image": "",
            "get_image": "",
            "modify_image": "",
            "upload_image": "",
            "get_image_location": "",
            "delete_image": "",
            "restricted": "",
            "download_image": "",
            "add_member": "",
            "publicize_image": "",
            "copy_image": "'public':%(visibility)s",
        }

        self.set_policy_rules(rules)

        image_id, response = self._test_copy_public_image_as_non_admin()
        # Expect success because image is public
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is copied
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['file2'],
                                    max_sec=40,
                                    delay_sec=0.2,
                                    start_delay_sec=1)

        # Ensure image is copied to the file2 and file3 store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file2', jsonutils.loads(response.text)['stores'])
