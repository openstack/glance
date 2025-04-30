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
import http.client as http
import os
import subprocess
import tempfile
import time
from unittest import mock
import urllib
import uuid

import fixtures
import glance_store

from oslo_config import cfg
from oslo_limit import exception as ol_exc
from oslo_limit import limit
import oslo_policy.policy
from oslo_serialization import jsonutils
from oslo_utils import units
import requests

from glance.api import policy
from glance.common import wsgi
from glance.quota import keystone as ks_quota
from glance.tests import functional
from glance.tests.functional import ft_utils as func_utils
from glance.tests import utils as test_utils


CONF = cfg.CONF

TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


def get_auth_header(tenant, tenant_id=None,
                    role='reader,member', headers=None):
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


class ImageAPIHelper(test_utils.BaseTestCase):
    """A helper class for testing Image API endpoints.

    Provides methods to create, verify, stage, import, and delete images,
    as well as to check image listings and properties. Designed to facilitate
    automated testing of the image management API in OpenStack or similar
    environments.

    Attributes:
        api_get (callable): Function to perform HTTP GET requests.
        api_post (callable): Function to perform HTTP POST requests.
        api_put (callable): Function to perform HTTP PUT requests.
        api_delete (callable): Function to perform HTTP DELETE requests.
        image_location_header (str or None): Stores the 'Location' header of
        created images.
        """

    def __init__(self, api_get, api_post, api_put, api_delete):
        self.api_get = api_get
        self.api_post = api_post
        self.api_put = api_put
        self.api_delete = api_delete
        self.image_location_header = None

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def assert_image_not_found(self, image_id):
        path = f'/v2/images/{image_id}'
        response = self.api_get(path, headers=self._headers())
        assert http.NOT_FOUND == response.status_code

    def verify_empty_image_list(self):
        path = '/v2/images'
        response = self.api_get(path, headers=self._headers())
        assert http.OK == response.status_code
        images = jsonutils.loads(response.text)['images']
        first = jsonutils.loads(response.text)['first']
        assert len(images) == 0
        self.assertNotIn('next', jsonutils.loads(response.text))
        self.assertEqual('/v2/images', first)

    def verify_discovery_includes_import_method(self, method='glance-direct'):
        path = '/v2/info/import'
        response = self.api_get(path, headers=self._headers())
        assert http.OK == response.status_code
        discovery_calls = jsonutils.loads(
            response.text)['import-methods']['value']
        assert method in discovery_calls

    def create_and_verify_image(self, name, type=None, disk_format=None,
                                container_format=None,
                                additional_properties=None,
                                show_locations=False, hidden=False,
                                headers=None):
        additional_properties = additional_properties or {}
        path = '/v2/images'
        if not headers:
            headers = self._headers({'content-type': 'application/json'})

        data = {
            'name': name,
            'os_hidden': hidden,
            'protected': False
        }

        if type is not None:
            data['type'] = type
        if disk_format is not None:
            data['disk_format'] = disk_format
        if container_format is not None:
            data['container_format'] = container_format

        if additional_properties:
            data.update(additional_properties)

        response = self.api_post(path, headers=headers, json=data)
        if not self.image_location_header:
            self.image_location_header = response.headers.get('Location')

        assert http.CREATED == response.status_code

        image = jsonutils.loads(response.text)
        image_id = image['id']

        self.verify_image_details(
            image, image_id, expected_name=name,
            additional_properties=additional_properties,
            show_locations=show_locations,
            hidden=hidden,
            type=type)

        return image_id

    def verify_image_details(self, image, image_id, expected_name,
                             additional_properties={},
                             show_locations=False,
                             hidden=False,
                             type=None):
        expected_keys = {
            'status', 'name', 'tags', 'created_at', 'updated_at',
            'visibility', 'self', 'protected', 'os_hidden', 'id',
            'file', 'min_disk', 'min_ram', 'schema',
            'disk_format', 'container_format', 'owner',
            'checksum', 'os_hash_algo', 'os_hash_value',
            'size', 'virtual_size'
        }
        if type is not None:
            expected_keys.add('type')
        if additional_properties:
            expected_keys.update(additional_properties.keys())
        if show_locations:
            expected_keys.add('locations')

        assert expected_keys == set(image.keys())
        expected_image = {
            'status': 'queued', 'name': expected_name, 'tags': [],
            'visibility': 'shared', 'self': f'/v2/images/{image_id}',
            'protected': False, 'file': f'/v2/images/{image_id}/file',
            'min_disk': 0, 'min_ram': 0,
            'schema': '/v2/schemas/image', 'os_hidden': hidden,
            'size': None, 'virtual_size': None
        }
        if type is not None:
            expected_image['type'] = type
        if additional_properties:
            expected_image.update(additional_properties)

        for key, value in expected_image.items():
            # NOTE(abhishekk): if key is tags then  remove duplicate elements
            if key == 'tags':
                unique_tags = []
                [unique_tags.append(
                    tag) for tag in value if tag not in unique_tags]
                assert unique_tags == image[key], key
            else:
                assert value == image[key], key

    def verify_image_list_contains(self, image_id, image2_id=None,
                                   expected_count=1, path='/v2/images'):
        response = self.api_get(path, headers=self._headers())
        assert http.OK == response.status_code
        images = jsonutils.loads(response.text)['images']
        assert expected_count == len(images)
        if image2_id:
            assert image2_id == images[0]['id']
            assert image_id == images[1]['id']
        else:
            assert image_id == images[0]['id']

    def stage_image_data(self, image_id, data):
        path = f'/v2/images/{image_id}/stage'
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = self.api_put(path, headers=headers, data=data)
        assert http.NO_CONTENT == response.status_code

    def verify_image_list_hidden_filter(
            self, expected_ids=None, expected_count=0,
            os_hidden='false', expect_error=False):
        path = f'/v2/images?os_hidden={os_hidden}'
        response = self.api_get(path, headers=self._headers())

        if expect_error:
            self.assertEqual(http.BAD_REQUEST, response.status_code)
        else:
            self.assertEqual(http.OK, response.status_code)
            images = jsonutils.loads(response.text)['images']
            self.assertEqual(expected_count, len(images))
            if expected_ids:
                for image_id in expected_ids:
                    self.assertIn(image_id, [img['id'] for img in images])

    def import_image(self, image_id, data=None):
        path = f'/v2/images/{image_id}/import'
        headers = self._headers(
            {'content-type': 'application/json', 'X-Roles': 'admin'})
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

    def verify_image_import_status(self, image_id, data=None):
        path = f'/v2/images/{image_id}'
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active', max_sec=10, delay_sec=0.2)

        if not isinstance(data, bytes) and data.startswith(
                'http://localhost'):
            with requests.get(data) as r:
                expect_c = str(
                    hashlib.md5(r.content, usedforsecurity=False).hexdigest())
                expect_h = str(hashlib.sha512(r.content).hexdigest())
                size = len(r.content.decode('utf-8'))
        else:
            expect_c = str(hashlib.md5(
                data, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(data).hexdigest())
            size = len(data)

        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=size,
                                                  status='active')

    def verify_image_size(self, image_id, expected_size):
        path = f'/v2/images/{image_id}'
        response = self.api_get(path, headers=self._headers())
        assert http.OK == response.status_code
        assert expected_size == jsonutils.loads(response.text)['size']

    def delete_image(self, image_id, failure=False, headers=None):
        if not headers:
            headers = self._headers()
        path = f'/v2/images/{image_id}'
        response = self.api_delete(path, headers=headers)
        if failure:
            self.assertTrue(response.status_code == http.NOT_FOUND or
                            response.status_code == http.FORBIDDEN,
                            f"Unexpected status code: {response.status_code}")
        else:
            self.assertEqual(http.NO_CONTENT, response.status_code)

    def start_http_server_and_get_uri(self):
        thread, self.httpd, port = test_utils.start_standalone_http_server()
        return f'http://localhost:{port}/'

    def upload_and_verify(self, image_id, image_data):
        """Uploads image data to the specified image ID and verifies hashes."""
        path = f'/v2/images/{image_id}/file'
        headers = self._headers({'Content-Type': 'application/octet-stream'})

        # Upload the image data
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Calculate expected hashes
        expect_c = hashlib.md5(image_data, usedforsecurity=False).hexdigest()
        expect_h = hashlib.sha512(image_data).hexdigest()

        # Verify the image hashes and status
        func_utils.verify_image_hashes_and_status(
            self,
            image_id,
            expect_c,
            expect_h,
            size=len(image_data),
            status='active'
        )

    def create_qcow(self, size):
        # Create a temporary file and get its path
        fd, fn = tempfile.mkstemp(
            prefix='glance-unittest-images-', suffix='.qcow2')
        # Close the file descriptor; qemu-img will create/overwrite the file
        os.close(fd)
        # Create the qcow2 image using qemu-img
        subprocess.check_output(
            'qemu-img create -f qcow2 %s %i' % (fn, size),
            shell=True)
        return fn


class TestImagesSingleStore(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestImagesSingleStore, self).setUp(single_store=True)
        self.api_methods = ImageAPIHelper(self.api_get, self.api_post,
                                          self.api_put, self.api_delete)
        self.http_servers = []
        self.http_ports = []
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

        for i in range(3):
            server_info = test_utils.start_http_server(
                f"foo_image_id{i}", f"foo_image{i}")
            self.http_servers.append(server_info[1])
            self.http_ports.append(server_info[2])

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImagesSingleStore, self).start_server()

    def tearDown(self) -> None:
        for server in self.http_servers:
            if server:
                server.shutdown()
                server.server_close()
        super().tearDown()

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_image_import_using_glance_direct(self):
        self.start_server()

        # Initial checks: Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Check if glance-direct is available
        self.api_methods.verify_discovery_includes_import_method()

        # Create an image and verify its details
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki')

        # Confirm image list contains one image
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Upload image data
        self.api_methods.stage_image_data(image_id, data=b'ZZZZZ')

        # Import the image and verify its status and hashes
        data = {
            'method': {
                'name': 'glance-direct'
            }
        }
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id, data=b'ZZZZZ')

        # Ensure size is updated accordingly
        self.api_methods.verify_image_size(image_id, expected_size=5)

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_import_using_web_download(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        # Initial checks: Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Check if web-download is available
        self.api_methods.verify_discovery_includes_import_method(
            method='web-download')

        # Create an image and verify its details
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki')

        # Confirm image list contains one image
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and hashes are None
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  status='queued')

        # Import image to store
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }}
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    @mock.patch('glance.location._check_image_location', new=lambda *a: 0)
    @mock.patch('glance.location.ImageRepoProxy._set_acls', new=lambda *a: 0)
    def test_image_lifecycle(self):
        # Image list should be empty
        self.config(show_multiple_locations=True)
        self.config(image_property_quota=10)
        self.config(image_location_quota=2)
        self.start_server()

        # Initial checks: Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Create an image (with two deployer-defined properties)
        additional_properties = {
            'foo': 'bar',
            'abc': 'xyz',
            'protected': True
        }
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            additional_properties=additional_properties,
            show_locations=True
        )

        # Confirm image list contains one image
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Create another image (with two deployer-defined properties)
        additional_properties = {
            'bar': 'foo',
            'xyz': 'abc',
        }
        image2_id = self.api_methods.create_and_verify_image(
            name='image-2', type='kernel',
            disk_format='aki', container_format='aki',
            additional_properties=additional_properties,
            show_locations=True
        )

        # Image list should now have two entries
        self.api_methods.verify_image_list_contains(image_id,
                                                    image2_id=image2_id,
                                                    expected_count=2)

        # Image list should list only image-2 as image-1 doesn't contain the
        # property 'bar'
        path = '/v2/images?bar=foo'
        self.api_methods.verify_image_list_contains(image2_id, path=path)

        # Image list should list only image-1 as image-2 doesn't contain the
        # property 'foo'
        path = '/v2/images?foo=bar'
        self.api_methods.verify_image_list_contains(image_id, path=path)

        # The "changes-since" filter shouldn't work on glance v2
        path = '/v2/images?changes-since=20001007T10:10:10'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        path = '/v2/images?changes-since=aaa'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list should list only image-1 based on the filter
        # 'protected=true'
        path = '/v2/images?protected=true'
        self.api_methods.verify_image_list_contains(image_id, path=path)

        # Image list should list only image-2 based on the filter
        # 'protected=false'
        path = '/v2/images?protected=false'
        self.api_methods.verify_image_list_contains(image2_id, path=path)

        # Image list should return 400 based on the filter
        # 'protected=False'
        path = '/v2/images?protected=False'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list should list only image-1 based on the filter
        # 'foo=bar&abc=xyz'
        path = '/v2/images?foo=bar&abc=xyz'
        self.api_methods.verify_image_list_contains(image_id, path=path)

        # Image list should list only image-2 based on the filter
        # 'bar=foo&xyz=abc'
        path = '/v2/images?bar=foo&xyz=abc'
        self.api_methods.verify_image_list_contains(image2_id, path=path)

        # Image list should not list anything as the filter 'foo=baz&abc=xyz'
        # is not satisfied by either images
        path = '/v2/images?foo=baz&abc=xyz'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Get the image using the returned Location header
        response = self.api_get(self.api_methods.image_location_header,
                                headers=self._headers())
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
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        url = ('file://')
        changes = {
            'op': 'add',
            'path': '/locations/-',
            'value': {
                'url': url,
                'metadata': {}
            }
        }

        response = self.api_patch(path, changes, headers=headers)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        # The image should be mutable, including adding and removing properties
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = [
            {'op': 'replace', 'path': '/name', 'value': 'image-2'},
            {'op': 'replace', 'path': '/disk_format', 'value': 'vhd'},
            {'op': 'replace', 'path': '/container_format', 'value': 'ami'},
            {'op': 'replace', 'path': '/foo', 'value': 'baz'},
            {'op': 'add', 'path': '/ping', 'value': 'pong'},
            {'op': 'replace', 'path': '/protected', 'value': True},
            {'op': 'remove', 'path': '/type'},
        ]
        response = self.api_patch(path, data, headers=headers)
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
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        changes = []
        for i in range(11):
            changes.append({'op': 'add',
                            'path': '/ping%i' % i,
                            'value': 'pong'})

        response = self.api_patch(path, changes, headers=headers)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code,
                         response.text)

        # Adding 3 image locations should fail since configured limit is 2
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        changes = []
        for i in self.http_ports:
            url = 'http://127.0.0.1:%s/foo_image' % i
            changes.append({'op': 'add', 'path': '/locations/-',
                            'value': {'url': url, 'metadata': {}},
                            })

        response = self.api_patch(path, changes, headers=headers)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code,
                         response.text)

        # Ensure the v2.0 json-patch content type is accepted
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type})
        data = [{'op': 'add', 'path': '/ding', 'value': 'dong'}]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertEqual('dong', image['ding'])

        # Updates should persist across requests
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(image_id, image['id'])
        self.assertEqual('image-2', image['name'])
        self.assertEqual('baz', image['foo'])
        self.assertEqual('pong', image['ping'])
        self.assertTrue(image['protected'])
        self.assertNotIn('type', image, response.text)

        # Try to download data before its uploaded
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ZZZZZ'
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        expect_c = str(
            hashlib.md5(image_data, usedforsecurity=False).hexdigest())
        expect_h = str(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self, image_id, expect_c,
                                                  expect_h, 'active',
                                                  size=len(image_data))

        # `disk_format` and `container_format` cannot
        # be replaced when the image is active.
        immutable_paths = ['/disk_format', '/container_format']
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        path = '/v2/images/%s' % image_id
        for immutable_path in immutable_paths:
            data = [
                {'op': 'replace', 'path': immutable_path, 'value': 'ari'},
            ]
            response = self.api_patch(path, data, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        # Try to download the data that was just uploaded
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual('ZZZZZ', response.text)

        # Uploading duplicate data should be rejected with a 409. The
        # original data should remain untouched.
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = self.api_put(path, headers=headers, data=b'XXX')
        self.assertEqual(http.CONFLICT, response.status_code)
        func_utils.verify_image_hashes_and_status(self, image_id, expect_c,
                                                  expect_h, 'active',
                                                  size=len(image_data))

        # Ensure the size is updated to reflect the data uploaded
        self.api_methods.verify_image_size(image_id, expected_size=5)

        # Should be able to deactivate image
        path = '/v2/images/%s/actions/deactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Change the image to public so TENANT2 can see it
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.0-json-patch'
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'admin'})
        data = [{"op": "replace", "path": "/visibility", "value": "public"}]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Tenant2 should get Forbidden when deactivating the public image
        path = '/v2/images/%s/actions/deactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers(
            {'X-Tenant-Id': TENANT2}))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Tenant2 should get Forbidden when reactivating the public image
        path = '/v2/images/%s/actions/reactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers(
            {'X-Tenant-Id': TENANT2}))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Deactivating a deactivated image succeeds (no-op)
        path = '/v2/images/%s/actions/deactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Can't download a deactivated image
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Deactivated image should still be in a listing
        self.api_methods.verify_image_list_contains(
            image_id, image2_id=image2_id, expected_count=2)

        # Should be able to reactivate a deactivated image
        path = '/v2/images/%s/actions/reactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Reactivating an active image succeeds (no-op)
        path = '/v2/images/%s/actions/reactivate' % image_id
        response = self.api_post(path, data={}, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Deletion should not work on protected images
        self.api_methods.delete_image(image_id, failure=True)

        # Unprotect image for deletion
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image-1
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # And neither should its data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now contain just image-2
        self.api_methods.verify_image_list_contains(
            image2_id, expected_count=1)

        # Deleting image-2 should work
        self.api_methods.delete_image(image2_id)

        # Image list should now be empty
        self.api_methods.verify_empty_image_list()

        # Define the endpoint and headers
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        # List of invalid test cases (data, expected status)
        invalid_cases = [
            ('true', http.BAD_REQUEST),
            ('"hello"', http.BAD_REQUEST),
            ('123', http.BAD_REQUEST),
        ]
        for data, expected_status in invalid_cases:
            # Send POST request with invalid data
            response = self.api_post(path, headers=headers, json=data)
            # Assert that the response status code matches the expected status
            self.assertEqual(expected_status, response.status_code)

    def test_image_upload_qcow_virtual_size_calculation(self):
        self.start_server()

        # Create an image
        headers = self._headers({'Content-Type': 'application/json'})
        data = {'name': 'myqcow', 'disk_format': 'qcow2',
                'container_format': 'bare'}
        response = self.api_post('/v2/images',
                                 headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code,
                         'Failed to create: %s' % response.text)
        image = jsonutils.loads(response.text)

        # Upload a qcow
        fn = self.api_methods.create_qcow(128 * units.Mi)
        raw_size = os.path.getsize(fn)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = self.api_put('/v2/images/%s/file' % image['id'],
                                headers=headers,
                                data=open(fn, 'rb').read())
        os.remove(fn)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Check the image attributes
        response = self.api_get('/v2/images/%s' % image['id'],
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(128 * units.Mi, image['virtual_size'])
        self.assertEqual(raw_size, image['size'])

    def test_image_import_qcow_virtual_size_calculation(self):
        self.start_server()

        # Create an image
        headers = self._headers({'Content-Type': 'application/json'})
        data = {'name': 'myqcow', 'disk_format': 'qcow2',
                'container_format': 'bare'}
        response = self.api_post('/v2/images',
                                 headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code,
                         'Failed to create: %s' % response.text)
        image = jsonutils.loads(response.text)

        # Stage a qcow
        fn = self.api_methods.create_qcow(128 * units.Mi)
        raw_size = os.path.getsize(fn)
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = self.api_put('/v2/images/%s/stage' % image['id'],
                                headers=headers,
                                data=open(fn, 'rb').read())
        os.remove(fn)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image['id'],
                                                  status='uploading',
                                                  size=raw_size)

        # Import the image and verify its status and hashes
        import_data = {
            'method': {
                'name': 'glance-direct'
            }
        }
        self.api_methods.import_image(image['id'], data=import_data)
        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = '/v2/images/%s' % image['id']
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)

        # Check the image attributes
        response = self.api_get('/v2/images/%s' % image['id'],
                                headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(128 * units.Mi, image['virtual_size'])
        self.assertEqual(raw_size, image['size'])

    def test_hidden_images(self):
        self.config(show_multiple_locations=True)
        self.start_server()
        # Initial checks: Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Create and verify image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            show_locations=True
        )

        # Confirm image list contains one image
        self.api_methods.verify_image_list_contains(image_id, expected_count=1)

        # Create another image with hidden true
        image2_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            show_locations=True, hidden=True
        )

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(
            image_id, expected_count=1)

        # Verify the image list for the filter 'hidden=false'
        self.api_methods.verify_image_list_hidden_filter(
            expected_ids=[image_id], os_hidden='false', expected_count=1)

        # Verify the image list for the filter 'hidden=true'
        self.api_methods.verify_image_list_hidden_filter(
            expected_ids=[image2_id], os_hidden='true', expected_count=1)

        # Check for invalid input with 'hidden=abcd'
        self.api_methods.verify_image_list_hidden_filter(
            expected_count=0, os_hidden='abcd', expect_error=True)

        # Image-1 data upload
        self.api_methods.upload_and_verify(image_id, b'ZZZZZ')

        # Image-2 data upload
        self.api_methods.upload_and_verify(image2_id, b'WWWWW')

        # Hide image-1
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = [
            {'op': 'replace', 'path': '/os_hidden', 'value': True},
        ]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertTrue(image['os_hidden'])

        # Image list should now have 0 entries
        path = '/v2/images'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should show image-1, and image-2 based
        # on the filter 'hidden=true'
        self.api_methods.verify_image_list_hidden_filter(
            expected_ids=[image_id, image2_id], os_hidden='true',
            expected_count=2)

        # Un-Hide image-1
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = [
            {'op': 'replace', 'path': '/os_hidden', 'value': False},
        ]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(response.text)
        self.assertFalse(image['os_hidden'])

        # Image list should now have 1 entry
        self.api_methods.verify_image_list_contains(
            image_id, expected_count=1)

        # Deleting image-1 should work
        self.api_methods.delete_image(image_id)

        # Deleting image-2 should work
        self.api_methods.delete_image(image2_id)

        # Image list should now be empty
        self.api_methods.verify_empty_image_list()

    @mock.patch('glance.location._check_image_location', new=lambda *a: 0)
    @mock.patch('glance.location.ImageRepoProxy._set_acls', new=lambda *a: 0)
    def test_update_readonly_prop(self):
        self.start_server()
        # Create an image (with two deployer-defined properties)
        image_id = self.api_methods.create_and_verify_image(
            name='image-1')

        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})

        props = ['/id', '/file', '/location', '/schema', '/self']

        for prop in props:
            doc = [{'op': 'replace',
                    'path': prop,
                    'value': 'value1'}]
            response = self.api_patch(path, doc, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        for prop in props:
            doc = [{'op': 'remove',
                    'path': prop,
                    'value': 'value1'}]
            response = self.api_patch(path, doc, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

        for prop in props:
            doc = [{'op': 'add',
                    'path': prop,
                    'value': 'value1'}]
            response = self.api_patch(path, doc, headers=headers)
            self.assertEqual(http.FORBIDDEN, response.status_code)

    def test_methods_that_dont_accept_illegal_bodies(self):
        self.start_server()

        # Initial checks: Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Test all the schemas
        schema_urls = [
            '/v2/schemas/images',
            '/v2/schemas/image',
            '/v2/schemas/members',
            '/v2/schemas/member',
        ]
        for value in schema_urls:
            response = self.api_get(value, headers=self._headers(),
                                    json=["body"])
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Create image for use with tests
        image_id = self.api_methods.create_and_verify_image(
            name='image-1')

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
            path = link % image_id
            response = getattr(
                self, f"api_{method}")(path, headers=self._headers(),
                                       json=["body"])

            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # DELETE /images/imgid without legal json
        path = '/v2/images/%s' % image_id
        data = '{"hello"]'
        response = self.api_delete(path, headers=self._headers(), json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # POST /images/imgid/members
        path = '/v2/images/%s/members' % image_id
        data = {'member': TENANT3}
        response = self.api_post(path, headers=self._headers(), json=data)
        self.assertEqual(http.OK, response.status_code)

        # GET /images/imgid/members/memid
        path = '/v2/images/%s/members/%s' % (image_id, TENANT3)
        data = ["body"]
        response = self.api_get(path, headers=self._headers(), json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # DELETE /images/imgid/members/memid
        path = '/v2/images/%s/members/%s' % (image_id, TENANT3)
        data = ["body"]
        response = self.api_delete(path, headers=self._headers(), json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

    def test_download_random_access_w_range_request(self):
        """
        Test partial download 'Range' requests for images (random image access)
        """
        self.start_server()
        # Create an image (with two deployer-defined properties)
        additional_properties = {
            'foo': 'bar',
            'abc': 'xyz'
        }
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            additional_properties=additional_properties
        )

        # Upload data to image
        image_data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self.api_methods.upload_and_verify(image_id, image_data)

        # test for success on satisfiable Range request.
        range_ = 'bytes=3-10'
        headers = self._headers({'Range': range_})
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.PARTIAL_CONTENT, response.status_code)
        self.assertEqual('DEFGHIJK', response.text)

        # test for failure on unsatisfiable Range request.
        range_ = 'bytes=10-5'
        headers = self._headers({'Range': range_})
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE,
                         response.status_code)

    def test_download_random_access_w_content_range(self):
        """
        Even though Content-Range is incorrect on requests, we support it
        for backward compatibility with clients written for pre-Pike Glance.
        The following test is for 'Content-Range' requests, which we have
        to ensure that we prevent regression.
        """
        self.start_server()
        # Create another image (with two deployer-defined properties)
        additional_properties = {
            'foo': 'bar',
            'abc': 'xyz'
        }
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            additional_properties=additional_properties
        )

        # Upload data to image
        image_data = b'Z' * 15
        self.api_methods.upload_and_verify(image_id, image_data)

        result_body = ''
        for x in range(15):
            # NOTE(flaper87): Read just 1 byte. Content-Range is
            # 0-indexed and it specifies the first byte to read
            # and the last byte to read.
            content_range = 'bytes %s-%s/15' % (x, x)
            headers = self._headers({'Content-Range': content_range})
            path = '/v2/images/%s/file' % image_id
            response = self.api_get(path, headers=headers)
            self.assertEqual(http.PARTIAL_CONTENT, response.status_code)
            result_body += response.text

        self.assertEqual(result_body, image_data.decode('utf-8'))

        # test for failure on unsatisfiable request for ContentRange.
        content_range = 'bytes 3-16/15'
        headers = self._headers({'Content-Range': content_range})
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE,
                         response.status_code)

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
        self.start_server()

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki'
        )

        # Upload data to image
        image_data = b'Z' * 5
        self.api_methods.upload_and_verify(image_id, image_data)

        # Get an image should fail
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Deletion should work
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

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
        self.start_server()

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki'
        )

        # Upload data to image
        image_data = b'Z' * 5
        self.api_methods.upload_and_verify(image_id, image_data)

        # Get an image should fail
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream',
                                 'X-Roles': '_member_'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Deletion should work
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

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
        self.start_server()

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki'
        )

        # Upload data to image
        image_data = b'Z' * 5
        self.api_methods.upload_and_verify(image_id, image_data)

        # Get an image should be allowed
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream',
                                 'X-Roles': 'reader,member'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Image Deletion should work
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

    def test_download_image_raises_service_unavailable(self):
        """Test image download returns HTTPServiceUnavailable."""
        self.config(show_multiple_locations=True)
        self.start_server()

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            show_locations=True
        )

        # Update image locations via PATCH
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        thread, httpd, http_port = test_utils.start_http_server(image_id,
                                                                "image-1")
        values = [{'url': 'http://127.0.0.1:%s/image-1' % http_port,
                   'metadata': {'idx': '0'}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Download an image should work
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Stop http server used to update image location
        httpd.shutdown()
        httpd.server_close()

        # Download an image should raise HTTPServiceUnavailable
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.SERVICE_UNAVAILABLE, response.status_code)

        # Image Deletion should work
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers['content-type'] = media_type
        del headers['X-Roles']
        data = [
            {'op': 'replace', 'path': '/name', 'value': 'new-name'},
        ]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code)

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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers['content-type'] = media_type
        del headers['X-Roles']
        data = [
            {'op': 'replace', 'path': '/name', 'value': 'new-name'},
        ]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        # Get the image's members resource
        path = '/v2/images/%s/members' % image_id
        body = {'member': TENANT3}
        del headers['X-Roles']
        response = self.api_post(path, headers=headers, json=body)
        self.assertEqual(http.OK, response.status_code)

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
        self.start_server()

        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        headers['X-Tenant-Id'] = TENANT2
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

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
        self.start_server()

        # Create an image
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        # Replace the admin role with reader and member
        headers['X-Roles'] = 'reader,member'

        # Can retrieve the image as TENANT1
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Can retrieve the image's members as TENANT1
        path = '/v2/images/%s/members' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        headers['X-Tenant-Id'] = TENANT2
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        path = '/v2/images/%s' % image_id
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT1,
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        response = self.api_patch(path, doc, headers=headers)
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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        path = '/v2/images/%s' % image_id
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT1,
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'community'}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)

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
        self.start_server()

        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin', 'X-Tenant-Id': TENANT1})
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers
        )

        # Delete image should work
        self.api_methods.delete_image(image_id)

    def test_list_show_ok_when_get_location_allowed_for_admins(self):
        self.config(show_image_direct_url=True)
        self.config(show_multiple_locations=True)
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
        self.start_server()

        # Create an image
        headers = self._headers({'content-type': 'application/json',
                                 'X-Tenant-Id': TENANT1})
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki',
            headers=headers,
            show_locations=True
        )

        # Can retrieve the image as TENANT1
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Can list images as TENANT1
        path = '/v2/images'
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

    def test_image_size_cap(self):
        self.config(image_size_cap=128)
        self.start_server()
        # create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='aki', container_format='aki'
        )

        # try to populate it with oversized data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})

        class StreamSim(object):
            # Using a one-shot iterator to force chunked transfer in the PUT
            # request
            def __init__(self, size):
                self.size = size

            def __iter__(self):
                yield b'Z' * self.size

        response = self.api_put(path, headers=headers,
                                body_file=StreamSim(129))
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # hashlib.md5('Z'*129).hexdigest()
        #     == '76522d28cb4418f12704dfa7acd6e7ee'
        # If the image has this checksum, it means that the whole stream was
        # accepted and written to the store, which should not be the case.
        path = '/v2/images/%s' % image_id
        headers = self._headers({'content-type': 'application/json'})
        response = self.api_get(path, headers=headers)
        image_checksum = jsonutils.loads(response.text).get('checksum')
        self.assertNotEqual(image_checksum, '76522d28cb4418f12704dfa7acd6e7ee')

    def test_permissions(self):
        self.start_server()
        # Create an image that belongs to TENANT1
        # create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1',
            disk_format='raw', container_format='bare'
        )

        # Upload some image data
        self.api_methods.upload_and_verify(image_id, b'ZZZZZ')

        # TENANT1 should see the image in their list
        self.api_methods.verify_image_list_contains(image_id, expected_count=1)

        # TENANT1 should be able to access the image directly
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)

        # TENANT2 should not see the image in their list
        path = '/v2/images'
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # TENANT2 should not be able to access the image directly
        path = '/v2/images/%s' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT2})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # TENANT2 should not be able to modify the image, either
        path = '/v2/images/%s' % image_id
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT2,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # TENANT2 should not be able to delete the image, either
        headers = self._headers({'X-Tenant-Id': TENANT2})
        self.api_methods.delete_image(image_id, headers=headers, failure=True)

        # Publicize the image as an admin of TENANT1
        path = '/v2/images/%s' % image_id
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Roles': 'admin',
        })
        doc = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # TENANT3 should now see the image in their list
        path = '/v2/images'
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(image_id, images[0]['id'])

        # TENANT3 should also be able to access the image directly
        path = '/v2/images/%s' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT3})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # TENANT3 still should not be able to modify the image
        path = '/v2/images/%s' % image_id
        headers = self._headers({
            'Content-Type': 'application/openstack-images-v2.1-json-patch',
            'X-Tenant-Id': TENANT3,
        })
        doc = [{'op': 'replace', 'path': '/name', 'value': 'image-2'}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # TENANT3 should not be able to delete the image, either
        headers = self._headers({'X-Tenant-Id': TENANT3})
        self.api_methods.delete_image(image_id, headers=headers, failure=True)

        # Image data should still be present after the failed delete
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(response.text, 'ZZZZZ')

    def test_tag_lifecycle(self):
        self.config(image_tag_quota=10)
        self.start_server()
        # Create an image with a tag - duplicate should be ignored
        additional_properties = {
            'tags': ['sniff', 'sniff']
        }
        image_id = self.api_methods.create_and_verify_image(
            'image-1', additional_properties=additional_properties
        )

        # Image should show a list with a single tag
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff'], tags)

        # Delete all tags
        for tag in tags:
            path = '/v2/images/%s/tags/%s' % (image_id, tag)
            response = self.api_delete(path, headers=self._headers())
            self.assertEqual(http.NO_CONTENT, response.status_code)

        # Update image with too many tags via PUT
        # Configured limit is 10 tags
        for i in range(10):
            path = '/v2/images/%s/tags/foo%i' % (image_id, i)
            response = self.api_put(path, headers=self._headers())
            self.assertEqual(http.NO_CONTENT, response.status_code)

        # 11th tag should fail
        path = '/v2/images/%s/tags/fail_me' % image_id
        response = self.api_put(path, headers=self._headers())
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Make sure the 11th tag was not added
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(10, len(tags))

        # Update image tags via PATCH
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [
            {
                'op': 'replace',
                'path': '/tags',
                'value': ['foo'],
            },
        ]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Update image with too many tags via PATCH
        # Configured limit is 10 tags
        path = '/v2/images/%s' % image_id
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
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Tags should not have changed since request was over limit
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['foo'], tags)

        # Update image with duplicate tag - it should be ignored
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [
            {
                'op': 'replace',
                'path': '/tags',
                'value': ['sniff', 'snozz', 'snozz'],
            },
        ]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Image should show the appropriate tags
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Attempt to tag the image with a duplicate should be ignored
        path = '/v2/images/%s/tags/snozz' % image_id
        response = self.api_put(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Create another more complex tag
        path = '/v2/images/%s/tags/gabe%%40example.com' % image_id
        response = self.api_put(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Double-check that the tags container on the image is populated
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['gabe@example.com', 'sniff', 'snozz'],
                         sorted(tags))

        # Query images by single tag
        path = '/v2/images?tag=sniff'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by multiple tags
        path = '/v2/images?tag=sniff&tag=snozz'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and other attributes
        path = '/v2/images?tag=sniff&status=queued'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual('image-1', images[0]['name'])

        # Query images by tag and a nonexistent tag
        path = '/v2/images?tag=sniff&tag=fake'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # The tag should be deletable
        path = '/v2/images/%s/tags/gabe%%40example.com' % image_id
        response = self.api_delete(path, headers=self._headers())
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # List of tags should reflect the deletion
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        # Deleting the same tag should return a 404
        path = '/v2/images/%s/tags/gabe%%40example.com' % image_id
        response = self.api_delete(path, headers=self._headers())
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # The tags won't be able to query the images after deleting
        path = '/v2/images?tag=gabe%%40example.com'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Try to add a tag that is too long
        big_tag = 'a' * 300
        path = '/v2/images/%s/tags/%s' % (image_id, big_tag)
        response = self.api_put(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Tags should not have changed since request was over limit
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tags = jsonutils.loads(response.text)['tags']
        self.assertEqual(['sniff', 'snozz'], sorted(tags))

        self.api_methods.delete_image(image_id)

    def test_images_container(self):
        self.start_server()
        # Image list should be empty and no next link should be present
        self.api_methods.verify_empty_image_list()

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
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        for fixture in fixtures:
            response = self.api_post(path, headers=headers, json=fixture)
            self.assertEqual(http.CREATED, response.status_code)
            images.append(jsonutils.loads(response.text))

        # Image list should contain 7 images
        path = '/v2/images'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(7, len(body['images']))
        self.assertEqual('/v2/images', body['first'])
        self.assertNotIn('next', jsonutils.loads(response.text))

        # Image list filters by created_at time
        url_template = '/v2/images?created_at=lt:%s'
        path = url_template % images[0]['created_at']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['images']))
        self.assertEqual(url_template % images[0]['created_at'],
                         urllib.parse.unquote(body['first']))

        # Image list filters by updated_at time
        url_template = '/v2/images?updated_at=lt:%s'
        path = url_template % images[2]['updated_at']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(3, len(body['images']))
        self.assertEqual(url_template % images[2]['updated_at'],
                         urllib.parse.unquote(body['first']))

        # Image list filters by updated_at and created time with invalid value
        url_template = '/v2/images?%s=lt:invalid_value'
        for filter in ['updated_at', 'created_at']:
            path = url_template % filter
            response = self.api_get(path, headers=self._headers())
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by updated_at and created_at with invalid operator
        url_template = '/v2/images?%s=invalid_operator:2015-11-19T12:24:02Z'
        for filter in ['updated_at', 'created_at']:
            path = url_template % filter
            response = self.api_get(path, headers=self._headers())
            self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by non-'URL encoding' value
        path = '/v2/images?name=%FF'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Image list filters by name with in operator
        url_template = '/v2/images?name=in:%s'
        filter_value = 'image-1,image-2'
        path = url_template % filter_value
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(3, len(body['images']))

        # Image list filters by container_format with in operator
        url_template = '/v2/images?container_format=in:%s'
        filter_value = 'bare,ami'
        path = url_template % filter_value
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(2, len(body['images']))

        # Image list filters by disk_format with in operator
        url_template = '/v2/images?disk_format=in:%s'
        filter_value = 'bare,ami,iso'
        path = url_template % filter_value
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertGreaterEqual(2, len(body['images']))

        # Begin pagination after the first image
        template_url = ('/v2/images?limit=2&sort_dir=asc&sort_key=name'
                        '&marker=%s&type=kernel&ping=pong')
        path = template_url % images[2]['id']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[6]['id'], images[0]['id']], response_ids)

        # Continue pagination using next link from previous request
        path = body['next']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(2, len(body['images']))
        response_ids = [image['id'] for image in body['images']]
        self.assertEqual([images[5]['id'], images[1]['id']], response_ids)

        # Continue pagination - expect no results
        path = body['next']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['images']))

        # Delete first image
        self.api_methods.delete_image(images[0]['id'])

        # Ensure bad request for using a deleted image as marker
        path = '/v2/images?marker=%s' % images[0]['id']
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.BAD_REQUEST, response.status_code)

    def test_update_locations(self):
        self.config(show_multiple_locations=True)
        self.start_server()
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            show_locations=True
        )

        # Update locations for the queued image
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        data = [{
            'op': 'replace',
            'path': '/locations',
            'value': [{
                'url': url,
                'metadata': {}
            }]
        }]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # The image size should be updated
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(10, image['size'])

    def test_update_locations_with_restricted_sources(self):
        self.config(show_multiple_locations=True)
        self.start_server()
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            show_locations=True
        )

        # Update locations for the queued image
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        data = [{
            'op': 'replace',
            'path': '/locations',
            'value': [{
                'url': 'file:///foo_image',
                'metadata': {}
            }]
        }]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        data = [{
            'op': 'replace',
            'path': '/locations',
            'value': [{
                'url': 'swift+config:///foo_image',
                'metadata': {}
            }]
        }]
        response = self.api_patch(path, data, headers=headers)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

    def test_add_location_with_do_secure_hash_true_negative(self):
        # Create an image
        self.start_server()
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        # Add Location with non image owner
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT2})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]

        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.NOT_FOUND, response.status_code, response.text)

        # Add location with invalid validation_data
        # Invalid os_hash_value
        validation_data = {
            'os_hash_algo': "sha512",
            'os_hash_value': "dbc9e0f80d131e64b94913a7b40bb5"
        }
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code,
                         response.text)

        # Add location with invalid validation_data (without os_hash_algo)
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        with requests.get(url) as r:
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        validation_data = {'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        # Add location with invalid validation_data &
        # (invalid hash_algo)
        validation_data = {
            'os_hash_algo': 'sha123',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        # Add location with invalid validation_data
        # (mismatch hash_value with hash algo)
        with requests.get(url) as r:
            expect_h = str(hashlib.sha256(r.content).hexdigest())

        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

    def test_add_location_with_do_secure_hash_true(self):
        self.start_server()

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        # Add location with os_hash_algo other than sha512
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha256(r.content).hexdigest())
        validation_data = {
            'os_hash_algo': 'sha256',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1)
        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=headers)
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

        # Add location with valid validation data
        # os_hash_algo value sha512
        # Create an image 2
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]

        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)

        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=self._headers())
        output = jsonutils.loads(resp.text)
        self.assertEqual('queued', output['status'])
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1)
        # Show Image
        resp = self.api_get(path, headers=self._headers())
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

        # Add Location with valid URL and do_secure_hash = True
        # without validation_data
        # Create an image 3
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1)
        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=headers)
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

    def test_add_location_with_do_secure_hash_false(self):
        self.config(do_secure_hash=False)
        self.start_server()

        # Add Location with valid URL and do_secure_hash = False
        # with validation_data
        # Create an image 1
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        with requests.get(url) as r:
            expect_h = str(hashlib.sha512(r.content).hexdigest())

        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)

        path = '/v2/images/%s' % image_id
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=2,
                                   delay_sec=0.2,
                                   start_delay_sec=1)

        # Add Location with valid URL and do_secure_hash = False
        # without validation_data
        # Create an image 2
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[0]
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)

        path = '/v2/images/%s' % image_id
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=2,
                                   delay_sec=0.3,
                                   start_delay_sec=1)

    def test_get_location(self):
        self.start_server()
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        # Get locations of `queued` image
        headers = self._headers({'X-Roles': 'service'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, len(jsonutils.loads(response.text)))

        # Get location of invalid image
        fake_image_id = str(uuid.uuid4())
        path = '/v2/images/%s/locations' % fake_image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code, response.text)

        # Add Location with valid URL and image owner
        path = '/v2/images/%s/locations' % image_id
        url = 'http://127.0.0.1:%s/foo_image' % self.http_ports[1]
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(202, response.status_code, response.text)

        path = '/v2/images/%s' % image_id
        headers = self._headers({'content-type': 'application/json'})
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=10,
                                   delay_sec=0.2,
                                   start_delay_sec=1)

        # Get Locations not allowed for any other user
        headers = self._headers({'X-Roles': 'admin,member'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Get Locations allowed only for service user
        headers = self._headers({'X-Roles': 'service'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code, response.text)

    def test_get_location_with_data_upload(self):
        self.start_server()
        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki'
        )

        # Upload some image data
        image_data = b'ZZZZZ'
        self.api_methods.upload_and_verify(image_id, image_data)

        # Get Locations not allowed for any other user
        headers = self._headers({'X-Roles': 'admin,member'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Get Locations allowed only for service user
        headers = self._headers({'X-Roles': 'service'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code, response.text)
        output = jsonutils.loads(response.text)
        self.assertTrue(output[0]['url'])


class TestImages(functional.FunctionalTest):

    def setUp(self):
        super(TestImages, self).setUp()
        self.cleanup()
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

        super(TestImages, self).tearDown()

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

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
                                 'X-Roles': 'reader,member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'reader,member'})
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
                                 'X-Roles': 'reader,member,spl_role'})
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
                                 'X-Roles': 'reader,member,spl_role'})
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
                                 'X-Roles': 'reader,member,spl_role'})
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
                                 'X-Roles': 'reader,member,spl_role'})
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
                                 'X-Roles': 'reader,member,spl_role'})
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
        rules = {
            "glance_creator": "role:admin or role:spl_role"
        }
        self.set_policy_rules(rules)
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
                                 'X-Roles': 'reader,member'})
        data = jsonutils.dumps({'name': 'image-1', 'foo': 'bar',
                                'disk_format': 'aki',
                                'container_format': 'aki',
                                'x_owner_foo': 'o_s_bar'})
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Create an image for role member without 'foo'
        path = self._url('/v2/images')
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'reader,member'})
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
                                 'X-Roles': 'reader,member,spl_role, admin'})
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
                                 'X-Roles': 'reader,member,spl_role'})
        data = jsonutils.dumps([
            {'op': 'replace', 'path': '/spl_creator_policy', 'value': 'z'},
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Attempt to read properties
        path = self._url('/v2/images/%s' % image_id)
        headers = self._headers({'content-type': media_type,
                                 'X-Roles': 'reader,random_role'})
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
                                 'X-Roles': 'reader,random_role'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
        data = jsonutils.dumps([
            {'op': 'replace',
             'path': '/x_none_update', 'value': '3'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        # FIXME(danms): This was expecting CONFLICT, but ... should it
        # not be the same as the admin case above?
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

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
                                 'X-Roles': 'reader,member,joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        # FIXME(danms): This was expecting CONFLICT, but ... should it
        # not be the same as the admin case above?
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
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
                                 'X-Roles': 'reader,member,joe_soap'})
        data = jsonutils.dumps([
            {'op': 'remove', 'path': '/x_none_delete'}
        ])
        response = requests.patch(path, headers=headers, data=data)
        self.assertEqual(http.CONFLICT, response.status_code, response.text)

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
        images = list_images('tenant1', role='reader')
        self.assertEqual(7, len(images))
        for image in images:
            self.assertTrue(image['visibility'] == 'public'
                            or 'tenant1' in image['name'])

        # 2. Known user, visibility=public, sees all public images
        images = list_images('tenant1', role='reader', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 3. Known user, visibility=private, sees only their private image
        images = list_images('tenant1', role='reader', visibility='private')
        self.assertEqual(1, len(images))
        image = images[0]
        self.assertEqual('private', image['visibility'])
        self.assertIn('tenant1', image['name'])

        # 4. Known user, visibility=shared, sees only their shared image
        images = list_images('tenant1', role='reader', visibility='shared')
        self.assertEqual(1, len(images))
        image = images[0]
        self.assertEqual('shared', image['visibility'])
        self.assertIn('tenant1', image['name'])

        # 5. Known user, visibility=community, sees all community images
        images = list_images('tenant1', role='reader', visibility='community')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('community', image['visibility'])

        # 6. Unknown user sees only public images
        images = list_images('none', role='reader')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 7. Unknown user, visibility=public, sees only public images
        images = list_images('none', role='reader', visibility='public')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertEqual('public', image['visibility'])

        # 8. Unknown user, visibility=private, sees no images
        images = list_images('none', role='reader', visibility='private')
        self.assertEqual(0, len(images))

        # 9. Unknown user, visibility=shared, sees no images
        images = list_images('none', role='reader', visibility='shared')
        self.assertEqual(0, len(images))

        # 10. Unknown user, visibility=community, sees only community images
        images = list_images('none', role='reader', visibility='community')
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

    def tearDown(self):
        # Cleaning up monkey patch (2).
        self.ping_server = self.ping_server_ipv4
        super(TestImagesIPv6, self).tearDown()
        # Cleaning up monkey patch (1).
        test_utils.get_unused_port = test_utils.get_unused_port_ipv4
        test_utils.get_unused_port_and_socket = (
            test_utils.get_unused_port_and_socket_ipv4)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_image_list_ipv6(self):
        # Image list should be empty

        self.api_server.deployment_flavor = "caching"
        self.start_servers(**self.__dict__.copy())

        url = f'http://[::1]:{self.api_port}'
        path = '/'
        requests.get(url + path, headers=self._headers())

        path = '/v2/images'
        response = requests.get(url + path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))


class TestImageDirectURLVisibility(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestImageDirectURLVisibility, self).setUp(single_store=True)
        self.api_methods = ImageAPIHelper(self.api_get, self.api_post,
                                          self.api_put, self.api_delete)
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super().start_server()

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_image_direct_url_visible(self):
        self.config(show_image_direct_url=True)
        self.set_policy_rules({
            'get_images': '',
            'get_image': '',
            'add_image': '',
            'upload_image': '',
            'publicize_image': '',
        })
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Create an image
        additional_properties = {
            'visibility': 'public',
            'foo': 'bar'
        }
        headers = self._headers({'content-type': 'application/json',
                                 'X-Roles': 'admin'})
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            type='kernel',
            additional_properties=additional_properties,
            headers=headers
        )

        # Image direct_url should not be visible before location is set
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('direct_url', image)

        # Upload some image data, setting the image location
        self.api_methods.upload_and_verify(image_id, b'ZZZZZ')

        # Image direct_url should be visible
        path = '/v2/images/%s' % image_id
        response = self.api_get(path)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('direct_url', image)

        # Image direct_url should be visible to non-owner, non-admin user
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json',
                                 'X-Tenant-Id': TENANT2})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('direct_url', image)

        # Image direct_url should be visible in a list
        path = '/v2/images'
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertIn('direct_url', image)

    def test_image_multiple_location_url_visible(self):
        self.config(show_multiple_locations=True)
        self.start_server()

        # Create an image
        additional_properties = {
            'foo': 'bar'
        }
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            type='kernel',
            additional_properties=additional_properties,
            show_locations=True
        )

        # Image locations should not be visible before location is set
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual([], image["locations"])

        # Upload some image data, setting the image location
        self.api_methods.upload_and_verify(image_id, b'ZZZZZ')

        # Image locations should be visible
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        loc = image['locations']
        self.assertGreater(len(loc), 0)
        loc = loc[0]
        self.assertIn('url', loc)
        self.assertIn('metadata', loc)

    def test_image_direct_url_not_visible(self):
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # Create an image
        additional_properties = {
            'foo': 'bar'
        }
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            type='kernel',
            additional_properties=additional_properties
        )

        # Upload some image data, setting the image location
        self.api_methods.upload_and_verify(image_id, b'ZZZZZ')

        # Image direct_url should not be visible
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertNotIn('direct_url', image)

        # Image direct_url should not be visible in a list
        path = '/v2/images'
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)['images'][0]
        self.assertNotIn('direct_url', image)


class TestImageLocationSelectionStrategy(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestImageLocationSelectionStrategy, self).setUp(
            single_store=True)
        self.api_methods = ImageAPIHelper(self.api_get, self.api_post,
                                          self.api_put, self.api_delete)
        self.http_servers = []
        self.http_ports = []

        for i in range(3):
            server_info = test_utils.start_http_server(
                f"foo_image_id{i}", f"foo_image{i}")
            self.http_servers.append(server_info[1])
            self.http_ports.append(server_info[2])

    def tearDown(self) -> None:
        for server in self.http_servers:
            if server:
                server.shutdown()
                server.server_close()
        super().tearDown()

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_image_locations_with_order_strategy(self):
        self.config(show_image_direct_url=True)
        self.config(show_multiple_locations=True)
        self.config(image_location_quota=10)

        self.start_server()

        # Create an image
        additional_properties = {
            'foo': 'bar'
        }
        image_id = self.api_methods.create_and_verify_image(
            'image-1', disk_format='aki', container_format='aki',
            type='kernel',
            additional_properties=additional_properties,
            show_locations=True
        )

        # Image locations should not be visible before location is set
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual([], image["locations"])

        # Update image locations via PATCH
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        values = [{'url': 'http://127.0.0.1:%s/foo_image' % self.http_ports[0],
                   'metadata': {}},
                  {'url': 'http://127.0.0.1:%s/foo_image' % self.http_ports[1],
                   'metadata': {}}]
        doc = [{'op': 'replace',
                'path': '/locations',
                'value': values}]

        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code)

        # Image locations should be visible
        path = '/v2/images/%s' % image_id
        headers = self._headers({'Content-Type': 'application/json'})
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertIn('locations', image)
        self.assertEqual(values, image['locations'])
        self.assertIn('direct_url', image)
        self.assertEqual(values[0]['url'], image['direct_url'])


class TestQuotas(functional.FunctionalTest):

    def setUp(self):
        super(TestQuotas, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.user_storage_quota = 100
        self.start_servers(**self.__dict__.copy())

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
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

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'

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
                                                  size=len(image_data),
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)
        expect_c = str(
            hashlib.md5(image_data, usedforsecurity=False).hexdigest())
        expect_h = str(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(image_data),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
                                                  size=len(image_data),
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=15,
                                   delay_sec=0.2)
        expect_c = str(
            hashlib.md5(image_data, usedforsecurity=False).hexdigest())
        expect_h = str(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(image_data),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=20,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=20,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        import_reqid = response.headers['X-Openstack-Request-Id']

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = self._url('/v2/images/%s' % image_id)
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
                                                  status='active')

        # kill the local http server
        httpd.shutdown()
        httpd.server_close()

        # Ensure image is created in the one store
        path = self._url('/v2/images/%s' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('file1', jsonutils.loads(response.text)['stores'])

        # Ensure image has one task associated with it
        path = self._url('/v2/images/%s/tasks' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(1, len(tasks))
        for task in tasks:
            self.assertEqual(image_id, task['image_id'])
            user_id = response.request.headers.get(
                'X-User-Id')
            self.assertEqual(user_id, task['user_id'])
            self.assertEqual(import_reqid, task['request_id'])

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
        copy_reqid = response.headers['X-Openstack-Request-Id']

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

        # Ensure image has two tasks associated with it
        path = self._url('/v2/images/%s/tasks' % image_id)
        response = requests.get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(2, len(tasks))
        expected_reqids = [copy_reqid, import_reqid]
        for task in tasks:
            self.assertEqual(image_id, task['image_id'])
            user_id = response.request.headers.get(
                'X-User-Id')
            self.assertEqual(user_id, task['user_id'])
            self.assertEqual(expected_reqids.pop(), task['request_id'])

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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'foo',
            'abc',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'
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

        expect_c = str(
            hashlib.md5(image_data, usedforsecurity=False).hexdigest())
        expect_h = str(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(image_data),
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
            'status',
            'name',
            'tags',
            'created_at',
            'updated_at',
            'visibility',
            'self',
            'protected',
            'id',
            'file',
            'min_disk',
            'foo',
            'abc',
            'type',
            'min_ram',
            'schema',
            'disk_format',
            'container_format',
            'owner',
            'checksum',
            'size',
            'virtual_size',
            'os_hidden',
            'os_hash_algo',
            'os_hash_value'

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

        expect_c = str(
            hashlib.md5(image_data, usedforsecurity=False).hexdigest())
        expect_h = str(hashlib.sha512(image_data).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(image_data),
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


class TestCopyImagePermissions(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestCopyImagePermissions, self).setUp()
        self.api_methods = ImageAPIHelper(self.api_get, self.api_post,
                                          self.api_put, self.api_delete)
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super().start_server()

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _create_and_import_image_data(self):
        # Create a public image
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'type': 'kernel',
                'visibility': 'public',
                'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        image = jsonutils.loads(response.text)
        image_id = image['id']

        path = '/v2/images/%s/import' % image_id
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {'name': 'web-download', 'uri': image_data_uri},
                'stores': ['store1']}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        # Verify image is in active state and checksum is set
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=self._headers(),
                                   status='active',
                                   max_sec=40,
                                   delay_sec=0.2,
                                   start_delay_sec=1)
        with requests.get(image_data_uri) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        func_utils.verify_image_hashes_and_status(self,
                                                  image_id,
                                                  checksum=expect_c,
                                                  os_hash_value=expect_h,
                                                  size=len(r.content),
                                                  status='active')

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        return image_id

    def _test_copy_public_image_as_non_admin(self):
        self.start_server()

        # Create a publicly-visible image as TENANT1
        image_id = self._create_and_import_image_data()

        # Ensure image is created in the one store
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual('store1', jsonutils.loads(response.text)['stores'])

        # Copy newly created image to store2 store as TENANT2
        path = '/v2/images/%s/import' % image_id
        headers = self._headers({
            'content-type': 'application/json',
        })
        headers = get_auth_header(TENANT2, TENANT2,
                                  role='reader,member', headers=headers)
        data = {'method': {'name': 'copy-image'}, 'stores': ['store2']}
        response = self.api_post(path, headers=headers, json=data)
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
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['store2'],
                                    max_sec=40,
                                    delay_sec=0.2,
                                    start_delay_sec=1,
                                    api_get_method=self.api_get)

        # Ensure image is copied to the file2 and file3 store
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertIn('store2', jsonutils.loads(response.text)['stores'])


class TestImportProxy(functional.SynchronousAPIBase):
    """Test the image import proxy-to-stage-worker behavior.

    This is done as a SynchronousAPIBase test with one mock for a couple of
    reasons:

    1. The main functional tests can't handle a call with a token
       inside because of their paste config. Even if they did, they would
       not be able to validate it.
    2. The main functional tests don't support multiple API workers with
       separate config and making them work that way is non-trivial.

    Functional tests are fairly synthetic and fixing or hacking over
    the above push us only further so. Using theh Synchronous API
    method is vastly easier, easier to verify, and tests the
    integration across the API calls, which is what is important.
    """

    def setUp(self):
        super(TestImportProxy, self).setUp()
        # Emulate a keystoneauth1 client for service-to-service communication
        self.ksa_client = self.useFixture(
            fixtures.MockPatch('glance.context.get_ksa_client')).mock

    def test_import_proxy(self):
        resp = requests.Response()
        resp.status_code = 202
        resp.headers['x-openstack-request-id'] = 'req-remote'
        self.ksa_client.return_value.post.return_value = resp

        # Stage it on worker1
        self.config(worker_self_reference_url='http://worker1')
        self.start_server(set_worker_url=False)
        image_id = self._create_and_stage()

        # Make sure we can't see the stage host key
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertIn('container_format', image)
        self.assertNotIn('os_glance_stage_host', image)

        # Import call goes to worker2
        self.config(worker_self_reference_url='http://worker2')
        self.start_server(set_worker_url=False)
        r = self._import_direct(image_id, ['store1'])

        # Assert that it was proxied back to worker1
        self.assertEqual(202, r.status_code)
        self.assertEqual('req-remote', r.headers['x-openstack-request-id'])
        self.ksa_client.return_value.post.assert_called_once_with(
            'http://worker1/v2/images/%s/import' % image_id,
            timeout=60,
            json={'method': {'name': 'glance-direct'},
                  'stores': ['store1'],
                  'all_stores': False})

    def test_import_proxy_fail_on_remote(self):
        resp = requests.Response()
        resp.url = '/v2'
        resp.status_code = 409
        resp.reason = 'Something Failed (tm)'
        self.ksa_client.return_value.post.return_value = resp
        self.ksa_client.return_value.delete.return_value = resp

        # Stage it on worker1
        self.config(worker_self_reference_url='http://worker1')
        self.start_server(set_worker_url=False)
        image_id = self._create_and_stage()

        # Import call goes to worker2
        self.config(worker_self_reference_url='http://worker2')
        self.start_server(set_worker_url=False)
        r = self._import_direct(image_id, ['store1'])

        # Make sure we see the relevant details from worker1
        self.assertEqual(409, r.status_code)
        self.assertEqual('409 Something Failed (tm)', r.status)

        # For a 40x, we should get the same on delete
        r = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(409, r.status_code)
        self.assertEqual('409 Something Failed (tm)', r.status)

    def _test_import_proxy_fail_requests(self, error, status):
        self.ksa_client.return_value.post.side_effect = error
        self.ksa_client.return_value.delete.side_effect = error

        # Stage it on worker1
        self.config(worker_self_reference_url='http://worker1')
        self.start_server(set_worker_url=False)
        image_id = self._create_and_stage()

        # Import call goes to worker2
        self.config(worker_self_reference_url='http://worker2')
        self.start_server(set_worker_url=False)
        r = self._import_direct(image_id, ['store1'])
        self.assertEqual(status, r.status)
        self.assertIn(b'Stage host is unavailable', r.body)

        # Make sure we can still delete it
        r = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(204, r.status_code)
        r = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual(404, r.status_code)

    def test_import_proxy_connection_refused(self):
        self._test_import_proxy_fail_requests(
            requests.exceptions.ConnectionError(),
            '504 Gateway Timeout')

    def test_import_proxy_connection_timeout(self):
        self._test_import_proxy_fail_requests(
            requests.exceptions.ConnectTimeout(),
            '504 Gateway Timeout')

    def test_import_proxy_connection_unknown_error(self):
        self._test_import_proxy_fail_requests(
            requests.exceptions.RequestException(),
            '502 Bad Gateway')


def get_enforcer_class(limits):
    class FakeEnforcer:
        def __init__(self, callback):
            self._callback = callback

        def enforce(self, project_id, values):
            for name, delta in values.items():
                current = self._callback(project_id, values.keys())
                if current.get(name) + delta > limits.get(name, 0):
                    raise ol_exc.ProjectOverLimit(
                        project_id=project_id,
                        over_limit_info_list=[ol_exc.OverLimitInfo(
                            name, limits.get(name), current.get(name), delta)])

        def calculate_usage(self, project_id, names):
            return {
                name: limit.ProjectUsage(
                    limits.get(name, 0),
                    self._callback(project_id, [name])[name])
                for name in names}

    return FakeEnforcer


class TestKeystoneQuotas(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestKeystoneQuotas, self).setUp()
        self.config(endpoint_id='ENDPOINT_ID', group='oslo_limit')
        self.config(use_keystone_limits=True)
        self.config(filesystem_store_datadir='/tmp/foo',
                    group='os_glance_tasks_store')

        self.enforcer_mock = self.useFixture(
            fixtures.MockPatchObject(ks_quota, 'limit')).mock

    def set_limit(self, limits):
        self.enforcer_mock.Enforcer = get_enforcer_class(limits)

    def test_upload(self):
        # Set a quota of 5MiB
        self.set_limit({'image_size_total': 5,
                        'image_count_total': 10,
                        'image_count_uploading': 10})
        self.start_server()

        # First upload of 3MiB is good
        image_id = self._create_and_upload(
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Second upload of 3MiB is allowed to complete, but leaves us
        # over-quota
        self._create_and_upload(
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Third upload of any size fails because we are now over quota
        self._create_and_upload(expected_code=413)

        # Delete one image, which should put us under quota
        self.api_delete('/v2/images/%s' % image_id)

        # Upload should now succeed
        self._create_and_upload()

    def test_import(self):
        # Set a quota of 5MiB
        self.set_limit({'image_size_total': 5,
                        'image_count_total': 10,
                        'image_count_uploading': 10})
        self.start_server()

        # First upload of 3MiB is good
        image_id = self._create_and_upload(
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Second upload of 3MiB is allowed to complete, but leaves us
        # over-quota
        self._create_and_upload(data_iter=test_utils.FakeData(3 * units.Mi))

        # Attempt to import of any size fails because we are now over quota
        self._create_and_import(stores=['store1'], expected_code=413)

        # Delete one image, which should put us under quota
        self.api_delete('/v2/images/%s' % image_id)

        # Import should now succeed
        self._create_and_import(stores=['store1'])

    def test_import_would_go_over(self):
        # Set a quota limit of 5MiB
        self.set_limit({'image_size_total': 5,
                        'image_count_total': 10,
                        'image_count_uploading': 10})
        self.start_server()

        # First upload of 3MiB is good
        image_id = self._create_and_upload(
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Stage a 3MiB image for later import
        import_id = self._create_and_stage(
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Import should fail the task because it would put us over our
        # 5MiB quota
        self._import_direct(import_id, ['store1'])
        image = self._wait_for_import(import_id)
        task = self._get_latest_task(import_id)
        self.assertEqual('failure', task['status'])
        self.assertIn(('image_size_total is over limit of 5 due to '
                       'current usage 3 and delta 3'), task['message'])

        # Delete the first image to make space
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(204, resp.status_code)

        # Stage a 3MiB image for later import (this must be done
        # because a failed import cannot go back to 'uploading' status)
        import_id = self._create_and_stage(
            data_iter=test_utils.FakeData(3 * units.Mi))
        # Make sure the import is possible now
        resp = self._import_direct(import_id, ['store1'])
        self.assertEqual(202, resp.status_code)
        image = self._wait_for_import(import_id)
        self.assertEqual('active', image['status'])
        task = self._get_latest_task(import_id)
        self.assertEqual('success', task['status'])

    def test_copy(self):
        # Set a size quota of 5MiB, with more staging quota than we need.
        self.set_limit({'image_size_total': 5,
                        'image_count_total': 10,
                        'image_stage_total': 15,
                        'image_count_uploading': 10})
        self.start_server()

        # First import of 3MiB is good
        image_id = self._create_and_import(
            stores=['store1'],
            data_iter=test_utils.FakeData(3 * units.Mi))

        # Second copy is allowed to complete, but leaves us us at
        # 6MiB of total usage, over quota
        req = self._import_copy(image_id, ['store2'])
        self.assertEqual(202, req.status_code)
        self._wait_for_import(image_id)
        self.assertEqual('success', self._get_latest_task(image_id)['status'])

        # Third copy should fail because we're over total size quota.
        req = self._import_copy(image_id, ['store3'])
        self.assertEqual(413, req.status_code)

        # Set our size quota to have enough space, but restrict our
        # staging quota to below the required size to stage the image
        # before copy. This request should succeed, but the copy task
        # should fail the staging quota check.
        self.set_limit({'image_size_total': 15,
                        'image_count_total': 10,
                        'image_stage_total': 5,
                        'image_count_uploading': 10})
        req = self._import_copy(image_id, ['store3'])
        self.assertEqual(202, req.status_code)
        self._wait_for_import(image_id)
        self.assertEqual('failure', self._get_latest_task(image_id)['status'])

        # If we increase our stage quota, we should now be able to copy.
        self.set_limit({'image_size_total': 15,
                        'image_count_total': 10,
                        'image_stage_total': 10,
                        'image_count_uploading': 10})
        req = self._import_copy(image_id, ['store3'])
        self.assertEqual(202, req.status_code)
        self._wait_for_import(image_id)
        self.assertEqual('success', self._get_latest_task(image_id)['status'])

    def test_stage(self):
        # Set a quota of 5MiB
        self.set_limit({'image_size_total': 15,
                        'image_stage_total': 5,
                        'image_count_total': 10,
                        'image_count_uploading': 10})
        self.start_server()

        # Stage 6MiB, which is allowed to complete, but leaves us over
        # quota
        image_id = self._create_and_stage(
            data_iter=test_utils.FakeData(6 * units.Mi))

        # Second stage fails because we are out of quota
        self._create_and_stage(expected_code=413)

        # Make sure that a web-download fails to actually run.
        image_id2 = self._create().json['id']
        req = self._import_web_download(image_id2, ['store1'],
                                        'http://example.com/foo.img')
        self.assertEqual(202, req.status_code)
        self._wait_for_import(image_id2)
        task = self._get_latest_task(image_id2)
        self.assertEqual('failure', task['status'])
        self.assertIn('image_stage_total is over limit', task['message'])

        # Finish importing one of the images, which should put us under quota
        # for staging
        req = self._import_direct(image_id, ['store1'])
        self.assertEqual(202, req.status_code)
        self._wait_for_import(image_id)

        # Stage should now succeed because we have freed up quota
        self._create_and_stage(
            data_iter=test_utils.FakeData(6 * units.Mi))

    def test_create(self):
        # Set a quota of 2 images
        self.set_limit({'image_size_total': 15,
                        'image_count_total': 2,
                        'image_count_uploading': 10})
        self.start_server()

        # Create one image
        image_id = self._create().json['id']

        # Create a second. This leaves us *at* quota
        self._create()

        # Attempt to create a third is rejected as OverLimit
        resp = self._create()
        self.assertEqual(413, resp.status_code)

        # Delete one image, which should put us under quota
        self.api_delete('/v2/images/%s' % image_id)

        # Now we can create that third image
        self._create()

    def test_uploading_methods(self):
        self.set_limit({'image_size_total': 100,
                        'image_stage_total': 100,
                        'image_count_total': 100,
                        'image_count_uploading': 1})
        self.start_server()

        # Create and stage one image. We are now at quota for count_uploading.
        image_id = self._create_and_stage()

        # Make sure we can not stage any more images.
        self._create_and_stage(expected_code=413)

        # Make sure we can not upload any more images.
        self._create_and_upload(expected_code=413)

        # Finish importing one of the images, which should put us under quota
        # for count_uploading.
        resp = self._import_direct(image_id, ['store1'])
        self.assertEqual(202, resp.status_code)
        self.assertEqual('active', self._wait_for_import(image_id)['status'])

        # Make sure we can upload now.
        self._create_and_upload()

        # Stage another, which should put us at quota for count_uploading.
        image_id2 = self._create_and_stage()

        # Start a copy. The request should succeed (because async) but
        # the task should ultimately fail because we are over quota.
        # NOTE(danms): It would be nice to try to do another copy or
        # upload while this is running, but since the task is fully
        # async and the copy happens quickly, we can't really time it
        # to avoid an unstable test (without some mocking).
        resp = self._import_copy(image_id, ['store2'])
        self.assertEqual(202, resp.status_code)
        self._wait_for_import(image_id)
        task = self._get_latest_task(image_id)
        self.assertEqual('failure', task['status'])
        self.assertIn('Resource image_count_uploading is over limit',
                      task['message'])

        # Finish the staged import.
        self._import_direct(image_id2, ['store1'])
        self.assertEqual(202, resp.status_code)
        self._wait_for_import(image_id2)

        # Make sure we can upload again after the import finishes.
        self._create_and_upload()

        # Re-try the copy that should now succeed and wait for it to
        # finish.
        resp = self._import_copy(image_id, ['store2'])
        self.assertEqual(202, resp.status_code)
        self._wait_for_import(image_id)
        task = self._get_latest_task(image_id)
        self.assertEqual('success', task['status'])

        # Make sure we can still upload.
        self._create_and_upload()

        # Make sure we can still import.
        self._create_and_import(stores=['store1'])


class TestStoreWeight(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestStoreWeight, self).setUp()

    def test_store_weight_combinations(self):
        self.start_server()
        # Import image in all available stores
        image_id = self._create_and_import(stores=['store1', 'store2',
                                                   'store3'])
        # make sure as weight is default, we will get locations based
        # on insertion order
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual("store1,store2,store3", image['stores'])

        # give highest weight to store2 then store3 and then store1
        self.config(weight=200, group='store2')
        self.config(weight=100, group='store3')
        self.config(weight=50, group='store1')
        self.start_server()
        # make sure as per store weight locations will be sorted
        # as store2,store3,store1
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual("store2,store3,store1", image['stores'])

        # give highest weight to store3 then store1 and then store2
        self.config(weight=20, group='store2')
        self.config(weight=100, group='store3')
        self.config(weight=50, group='store1')
        self.start_server()
        # make sure as per store weight locations will be sorted
        # as store3,store1,store2
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual("store3,store1,store2", image['stores'])


class TestMultipleBackendsLocationApi(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestMultipleBackendsLocationApi, self).setUp()
        self.start_server()
        for i in range(3):
            ret = test_utils.start_http_server("foo_image_id%d" % i,
                                               "foo_image%d" % i)
            setattr(self, 'http_server%d' % i, ret[1])
            setattr(self, 'http_port%d' % i, ret[2])

    def setup_stores(self):
        pass

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _setup_multiple_stores(self):
        self.ksa_client = self.useFixture(
            fixtures.MockPatch('glance.context.get_ksa_client')).mock
        self.config(enabled_backends={'store1': 'http', 'store2': 'http'})
        glance_store.register_store_opts(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)

        self.config(default_backend='store1',
                    group='glance_store')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')
        self.config(filesystem_store_datadir='/tmp/foo',
                    group='os_glance_tasks_store')

        glance_store.create_multi_stores(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        glance_store.verify_store()

    def test_add_location_with_do_secure_hash_false(self):
        self.config(do_secure_hash=False)
        self._setup_multiple_stores()

        # Add Location with valid URL and do_secure_hash = False
        # with validation_data
        # Create an image 1
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])
        self.assertIsNone(image['size'])
        self.assertIsNone(image['virtual_size'])

        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0
        with requests.get(url) as r:
            expect_h = str(hashlib.sha512(r.content).hexdigest())

        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url,
                'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=5,
                                   delay_sec=0.2,
                                   start_delay_sec=1,
                                   multistore=True)

        # Add Location with valid URL and do_secure_hash = False
        # without validation_data
        # Create an image 2
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])
        self.assertIsNone(image['size'])
        self.assertIsNone(image['virtual_size'])

        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=5,
                                   delay_sec=0.2,
                                   start_delay_sec=1, multistore=True)

    def test_add_location_with_do_secure_hash_true_negative(self):
        self._setup_multiple_stores()

        # Create an image
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])

        # Add Location with non image owner
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT2})
        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0

        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.NOT_FOUND, response.status_code, response.text)

        # Add location with invalid validation_data
        # Invalid os_hash_value
        validation_data = {
            'os_hash_algo': "sha512",
            'os_hash_value': "dbc9e0f80d131e64b94913a7b40bb5"
        }
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code,
                         response.text)

        # Add location with invalid validation_data (without os_hash_algo)
        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0
        with requests.get(url) as r:
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        validation_data = {'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        # Add location with invalid validation_data &
        # (invalid hash_algo)
        validation_data = {
            'os_hash_algo': 'sha123',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

        # Add location with invalid validation_data
        # (mismatch hash_value with hash algo)
        with requests.get(url) as r:
            expect_h = str(hashlib.sha256(r.content).hexdigest())

        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.BAD_REQUEST, response.status_code, response.text)

    def test_add_location_with_do_secure_hash_true(self):
        self._setup_multiple_stores()

        # Create an image
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])

        # Add location with os_hash_algo other than sha512
        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0
        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha256(r.content).hexdigest())
        validation_data = {
            'os_hash_algo': 'sha256',
            'os_hash_value': expect_h}
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1,
                                                      multistore=True)
        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=self._headers())
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

        # Add location with valid validation data
        # os_hash_algo value sha512
        # Create an image 3
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])

        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/store2/foo_image' % self.http_port0

        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        validation_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': expect_h}
        headers = self._headers({'X-Tenant-Id': TENANT1})
        data = {'url': url, 'validation_data': validation_data}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)

        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=self._headers())
        output = jsonutils.loads(resp.text)
        self.assertEqual('queued', output['status'])
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1,
                                                      multistore=True)
        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=self._headers())
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

        # Add Location with valid URL and do_secure_hash = True
        # without validation_data
        # Create an image 4
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])

        path = '/v2/images/%s/locations' % image_id
        headers = self._headers({'X-Tenant-Id': TENANT1})
        url = 'http://127.0.0.1:%s/store2/foo_image' % self.http_port0
        with requests.get(url) as r:
            expect_c = str(
                hashlib.md5(r.content, usedforsecurity=False).hexdigest())
            expect_h = str(hashlib.sha512(r.content).hexdigest())
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code, response.text)
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_image_checksum_and_status(self, image_id,
                                                      status='active',
                                                      max_sec=10,
                                                      delay_sec=0.2,
                                                      start_delay_sec=1,
                                                      multistore=True)
        # Show Image
        path = '/v2/images/%s' % image_id
        resp = self.api_get(path, headers=self._headers())
        image = jsonutils.loads(resp.text)
        self.assertEqual(expect_c, image['checksum'])
        self.assertEqual(expect_h, image['os_hash_value'])

    def test_get_location(self):
        self._setup_multiple_stores()

        # Create an image
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned image entity should have a generated id and status
        image = jsonutils.loads(response.text)
        image_id = image['id']
        self.assertEqual('queued', image['status'])

        # Get location of `queued` image
        headers = self._headers({'X-Roles': 'service'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, len(jsonutils.loads(response.text)))

        # Get location of invalid image
        image_id = str(uuid.uuid4())
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code, response.text)

        # Add Location with valid URL and image owner
        image_id = image['id']
        path = '/v2/images/%s/locations' % image_id
        url = 'http://127.0.0.1:%s/store1/foo_image' % self.http_port0
        data = {'url': url}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(202, response.status_code, response.text)
        path = '/v2/images/%s' % image_id
        headers = self._headers({'content-type': 'application/json'})
        func_utils.wait_for_status(self, request_path=path,
                                   request_headers=headers,
                                   status='active',
                                   max_sec=10,
                                   delay_sec=0.2,
                                   start_delay_sec=1, multistore=True)

        # Get Locations not allowed for any other user
        headers = self._headers({'X-Roles': 'admin,member'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.FORBIDDEN, response.status_code, response.text)

        # Get Locations allowed only for service user
        headers = self._headers({'X-Roles': 'service'})
        path = '/v2/images/%s/locations' % image_id
        response = self.api_get(path, headers=headers)
        self.assertEqual(200, response.status_code, response.text)
        output = jsonutils.loads(response.text)
        self.assertEqual(url, output[0]['url'])
