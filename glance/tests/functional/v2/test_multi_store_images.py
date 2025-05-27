# Copyright 2025 RedHat Inc.
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
import time

from oslo_config import cfg
from oslo_serialization import jsonutils

from glance.tests import functional
from glance.tests.functional import ft_utils as func_utils
from glance.tests.functional.v2 import test_images


CONF = cfg.CONF

TENANT1 = test_images.TENANT1
TENANT2 = test_images.TENANT2
TENANT3 = test_images.TENANT3
TENANT4 = test_images.TENANT4


class TestImagesMultipleBackend(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestImagesMultipleBackend, self).setUp()
        self.api_methods = test_images.ImageAPIHelper(
            self.api_get, self.api_post, self.api_put, self.api_delete)

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

    def _verify_available_stores(self, expected_stores):
        """Verify that the available stores do not contain the staging
        store and have valid IDs.

        This method checks the list of expected stores against the available
        stores and asserts that the staging store is not present.
        """
        path = '/v2/info/stores'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)

        discovery_stores = jsonutils.loads(response.text)['stores']

        for store in discovery_stores:
            self.assertIn('id', store)
            self.assertIn(store['id'], expected_stores)
            self.assertFalse(store['id'].startswith("os_glance_"))

    def test_image_import_using_glance_direct(self):
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # glance-direct should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method()

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Upload some image data to staging area
        image_data = b'ZZZZZ'
        self.api_methods.stage_image_data(image_id, data=image_data)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  size=len(image_data),
                                                  status='uploading')

        # Import image to store
        data = {
            'method': {
                'name': 'glance-direct'
            }
        }
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id, data=image_data)

        # Ensure the size is updated to reflect the data uploaded
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'])

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_import_using_glance_direct_different_backend(self):
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # glance-direct should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method()

        # store1 and store2 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(expected_stores=available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Upload some image data to staging area
        image_data = b'ZZZZZ'
        self.api_methods.stage_image_data(image_id, data=image_data)

        # Verify image is in uploading state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  size=len(image_data),
                                                  status='uploading')

        # Import image to store2 store (other than default backend)
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
            'X-Image-Meta-Store': 'store2'
        })
        data = {'method': {
            'name': 'glance-direct'
        }}
        self.api_methods.import_image(image_id, data=data,
                                      headers=headers)
        self.api_methods.verify_image_import_status(image_id, data=image_data)

        # Ensure the size is updated to reflect the data uploaded and
        # image is imported to store2
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store2'])

        # Deleting image should work
        self.api_methods.delete_image(image_id)

        # Image list should now be empty
        self.api_methods.verify_empty_image_list

    def test_image_import_using_web_download(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # web-download should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='web-download')

        # store1 and store2 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(expected_stores=available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }}
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # Ensure the size is updated to reflect the data imported and
        # image is imported to default backend
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'])

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_import_using_web_download_different_backend(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # web-download should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='web-download')

        # store1 and store2 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(expected_stores=available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }}
        # Import image to store
        # Import image to store
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin',
            'X-Image-Meta-Store': 'store2'
        })
        self.api_methods.import_image(image_id, data=data, headers=headers)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # Ensure the size is updated to reflect the data imported and
        # image is imported to default backend
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store2'])

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_import_multi_stores(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        # Image list should be empty
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # web-download should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='web-download')

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {
            'method': {
                'name': 'web-download',
                'uri': image_data_uri
            },
            'stores': ['store1', 'store2']
        }
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # kill the local http server
        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Ensure image is created in the two stores
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1', 'store2'])

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_copy_image_lifecycle(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()
        # Image list should be empty
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # copy-image should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='copy-image')

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }}
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # Ensure the size is updated to reflect the data imported and
        # image is imported to default backend
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'])

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Ensure image has one task associated with it
        path = '/v2/images/%s/tasks' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(1, len(tasks))
        for task in tasks:
            self.assertEqual(image_id, task['image_id'])
            user_id = response.request.headers.get(
                'X-User-Id')
            self.assertEqual(user_id, task['user_id'])
            self.assertEqual(self.api_methods.import_reqid, task['request_id'])

        # Copy newly created image to store2 and store3 stores
        path = '/v2/images/%s/import' % image_id
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        data = {
            'method': {'name': 'copy-image'},
            'stores': ['store2', 'store3']
        }
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code)
        copy_reqid = response.headers['X-Openstack-Request-Id']

        # Verify image is copied
        # NOTE(abhishekk): As import is a async call we need to provide
        # some timelap to complete the call.
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['store2', 'store3'],
                                    max_sec=40,
                                    delay_sec=0.2,
                                    start_delay_sec=1,
                                    api_get_method=self.api_get)

        # Ensure image is copied to the store2 and store3 store and available
        # in all 3 stores now
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1', 'store2', 'store3'])

        # Ensure image has two tasks associated with it
        path = '/v2/images/%s/tasks' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(2, len(tasks))
        expected_reqids = [copy_reqid, self.api_methods.import_reqid]
        for task in tasks:
            self.assertEqual(image_id, task['image_id'])
            user_id = response.request.headers.get(
                'X-User-Id')
            self.assertEqual(user_id, task['user_id'])
            self.assertEqual(expected_reqids.pop(), task['request_id'])

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_copy_image_revert_lifecycle(self):
        # Test if copying task fails in between then the rollback
        # should delete the data from only stores to which it is
        # copied and not from the existing stores.
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()
        # Image list should be empty
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # copy-image should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='copy-image')

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {'method': {
            'name': 'web-download',
            'uri': image_data_uri
        }}
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # Ensure the size is updated to reflect the data imported and
        # image is imported to default backend
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'])

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # NOTE(abhishekk): Deleting store3 image directory to trigger the
        # failure, so that we can verify that revert call does not delete
        # the data from existing stores
        # NOTE(danms): Do this before we start the import, on a later store,
        # which will cause that store to fail after we have already completed
        # the first one.
        os.rmdir(self.test_dir + "/store3")

        # Copy newly created image to store2 and store3 store
        path = '/v2/images/%s/import' % image_id
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })
        data = {
            'method': {'name': 'copy-image'},
            'stores': ['store2', 'store3']
        }
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.ACCEPTED, response.status_code)

        def poll_callback(image):
            # NOTE(danms): We need to wait for the specific
            # arrangement we're expecting, which is that file3 has
            # failed, nothing else is importing, and store2 has been
            # removed from stores by the revert.
            return not (image['os_glance_importing_to_stores'] == '' and
                        image['os_glance_failed_import'] == 'store3' and
                        image['stores'] == 'store1')

        func_utils.poll_entity('/v2/images/%s' % image_id,
                               self._headers(),
                               poll_callback,
                               api_get_method=self.api_get)

        # Here we check that the failure of 'store2' caused 'store2' to
        # be removed from image['stores'], and that 'store3' is reported
        # as failed in the appropriate status list. Since the import
        # started with 'store1' being populated, that should remain,
        # but 'store2' should be reverted/removed.
        response = self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'],
            rejected_stores=['store2', 'store3'])
        fail_key = 'os_glance_failed_import'
        pend_key = 'os_glance_importing_to_stores'
        self.assertEqual('store3', response[fail_key])
        self.assertEqual('', response[pend_key])

        # Copy newly created image to store2 and store3 stores and
        # all_stores_must_succeed set to false.
        headers = self._headers({
            'content-type': 'application/json',
            'X-Roles': 'admin'
        })

        data = {
            'method': {'name': 'copy-image'},
            'stores': ['store2', 'store3'],
            'all_stores_must_succeed': False
        }

        for i in range(0, 5):
            response = self.api_post(path, headers=headers, json=data)
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
        path = '/v2/images/%s' % image_id
        func_utils.wait_for_copying(request_path=path,
                                    request_headers=self._headers(),
                                    stores=['store2'],
                                    max_sec=10,
                                    delay_sec=0.2,
                                    start_delay_sec=1,
                                    failure_scenario=True,
                                    api_get_method=self.api_get)

        # Ensure data is not deleted from existing stores as well as
        # from the stores where it is copied successfully
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1', 'store2'],
            rejected_stores=['store3'])

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_import_multi_stores_specifying_all_stores(self):
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()
        # Image list should be empty
        self.start_server()

        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # copy-image should be available in discovery response
        self.api_methods.verify_discovery_includes_import_method(
            method='copy-image')

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Verify image is in queued state and checksum is None
        func_utils.verify_image_hashes_and_status(self, image_id,
                                                  status='queued')

        # Start http server locally
        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        data = {
            'method': {
                'name': 'web-download',
                'uri': image_data_uri,
                'all_stores': True
            },
            'all_stores': True
        }
        self.api_methods.import_image(image_id, data=data)
        self.api_methods.verify_image_import_status(image_id,
                                                    data=image_data_uri)

        # Ensure image is imported to all available stores
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1', 'store2', 'store3'])

        # kill the local http server
        self.api_methods.httpd.shutdown()
        self.api_methods.httpd.server_close()

        # Clean up: Delete the image and verify the list is empty
        self.api_methods.delete_image(image_id)
        self.api_methods.verify_empty_image_list()

    def test_image_lifecycle(self):
        self.start_server()
        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image (with two deployer-defined properties)
        additional_properties = {
            'protected': True,
            'foo': 'bar',
            'abc': 'xyz'
        }
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores,
            additional_properties=additional_properties)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Try to download data before its uploaded
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        image_data = b'OpenStack Rules, Other Clouds Drool'
        self.api_methods.upload_and_verify(image_id, image_data)

        # Ensure image is created in default backend
        self.api_methods.verify_image_stores(image_id,
                                             expected_stores=['store1'])

        # Try to download the data that was just uploaded
        expect_c = hashlib.md5(image_data, usedforsecurity=False).hexdigest()
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual(image_data.decode('utf-8'), response.text)

        # Ensure the size is updated to reflect the data uploaded
        self.api_methods.verify_image_size(
            image_id, expected_size=len(image_data))

        # Unprotect image for deletion
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

        # And neither should its data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now be empty
        self.api_methods.verify_empty_image_list

    def test_image_lifecycle_different_backend(self):
        self.start_server()
        # Image list should be empty
        self.api_methods.verify_empty_image_list()

        # store1, store2 and store3 should be available in discovery response
        available_stores = ['store1', 'store2', 'store3']
        self._verify_available_stores(available_stores)

        # Create an image (with two deployer-defined properties)
        additional_properties = {
            'protected': True,
            'foo': 'bar',
            'abc': 'xyz'
        }
        image_id = self.api_methods.create_and_verify_image(
            name='image-1', type='kernel',
            disk_format='aki', container_format='aki',
            verify_stores=True, available_stores=available_stores,
            additional_properties=additional_properties)

        # Image list should now have one entry
        self.api_methods.verify_image_list_contains(image_id,
                                                    expected_count=1)

        # Try to download data before its uploaded
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Upload some image data
        image_data = b'just a passing glance'
        headers = self._headers({
            'Content-Type': 'application/octet-stream',
            'X-Image-Meta-Store': 'store2'
        })
        self.api_methods.upload_and_verify(image_id, image_data,
                                           headers=headers)

        # Ensure image is created in default backend
        self.api_methods.verify_image_stores(image_id,
                                             expected_stores=['store2'])

        # Try to download the data that was just uploaded
        expect_c = hashlib.md5(image_data, usedforsecurity=False).hexdigest()
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        self.assertEqual(expect_c, response.headers['Content-MD5'])
        self.assertEqual(image_data.decode('utf-8'), response.text)

        # Ensure the size is updated to reflect the data uploaded
        self.api_methods.verify_image_size(
            image_id, expected_size=len(image_data))

        # Unprotect image for deletion
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        doc = [{'op': 'replace', 'path': '/protected', 'value': False}]
        response = self.api_patch(path, doc, headers=headers)
        self.assertEqual(http.OK, response.status_code, response.text)

        # Deletion should work. Deleting image
        self.api_methods.delete_image(image_id)

        # This image should be no longer be directly accessible
        self.api_methods.assert_image_not_found(image_id)

        # And neither should its data
        path = '/v2/images/%s/file' % image_id
        headers = self._headers()
        response = self.api_get(path, headers=headers)
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image list should now be empty
        self.api_methods.verify_empty_image_list
