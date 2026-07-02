# Copyright 2026 OpenStack Foundation
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

"""Functional tests for parallel multi-store interoperable image import."""

import hashlib
import http.client as http
import os
import subprocess
import tempfile
import time
from unittest import mock

from oslo_serialization import jsonutils
from oslo_utils import units

from glance import context
import glance.db as db_api
from glance.tests import functional
from glance.tests.functional import ft_utils as func_utils
from glance.tests.functional.v2 import test_images
from glance.tests.unit import utils as unit_test_utils

TENANT1 = test_images.TENANT1
AVAILABLE_STORES = ['store1', 'store2', 'store3']
IMAGE_DATA = b'PARALLEL_FUNCTIONAL_IMPORT_DATA'
SIGNATURE_PATCH = (
    'glance.async_.flows.parallel_api_image_import.'
    'signature_utils.get_verifier')
SIGNATURE_PROPS = {
    'img_signature_certificate_uuid': 'UUID',
    'img_signature_hash_method': 'METHOD',
    'img_signature_key_type': 'TYPE',
}


class TestParallelStoreImport(functional.SynchronousAPIBase):
    """Exercise parallel_api_image_import via the import API."""

    def setUp(self):
        super(TestParallelStoreImport, self).setUp()
        self.api_methods = test_images.ImageAPIHelper(
            self.api_get, self.api_post, self.api_put, self.api_delete)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _enable_parallel_import(self, max_parallel_stores=3):
        # Register image_import_opts (includes max_parallel_stores).
        from glance.async_.flows import api_image_import  # noqa: F401
        self.config(max_parallel_stores=max_parallel_stores,
                    group='image_import_opts')
        self.config(allowed_ports=[], group='import_filtering_opts')

    def _enable_image_conversion(self, output_format='raw'):
        from glance.async_.flows.plugins import image_conversion  # noqa: F401
        self.config(image_import_plugins=['image_conversion'],
                    group='image_import_opts')
        self.config(output_format=output_format, group='image_conversion')

    def _create_staged_image(self):
        image_id = self.api_methods.create_and_verify_image(
            name='parallel-import-image',
            type='kernel',
            disk_format='aki',
            container_format='aki',
            verify_stores=True,
            available_stores=AVAILABLE_STORES)
        self.api_methods.stage_image_data(image_id, data=IMAGE_DATA)
        func_utils.verify_image_hashes_and_status(
            self, image_id, size=len(IMAGE_DATA), status='uploading')
        return image_id

    def _create_staged_raw_image(self, size_bytes=units.Mi):
        """Stage a small valid raw image for image_conversion tests."""
        fd, fn = tempfile.mkstemp(suffix='.raw')
        os.close(fd)
        try:
            subprocess.check_output(
                ['qemu-img', 'create', '-f', 'raw', fn, str(size_bytes)],
                stderr=subprocess.STDOUT)
            with open(fn, 'rb') as image_file:
                image_data = image_file.read()
        finally:
            os.remove(fn)

        image_id = self.api_methods.create_and_verify_image(
            name='parallel-import-raw',
            type='kernel',
            disk_format='raw',
            container_format='bare',
            verify_stores=True,
            available_stores=AVAILABLE_STORES)
        self.api_methods.stage_image_data(image_id, data=image_data)
        func_utils.verify_image_hashes_and_status(
            self, image_id, size=len(image_data), status='uploading')
        return image_id

    def _import_glance_direct(self, image_id, stores, all_stores_must_succeed):
        data = {
            'method': {'name': 'glance-direct'},
            'stores': stores,
            'all_stores_must_succeed': all_stores_must_succeed,
        }
        self.api_methods.import_image(
            image_id, data=data,
            headers=self._headers({'content-type': 'application/json'}))

    def _import_web_download(self, image_id, uri, stores,
                             all_stores_must_succeed=True):
        data = {
            'method': {
                'name': 'web-download',
                'uri': uri,
            },
            'stores': stores,
            'all_stores_must_succeed': all_stores_must_succeed,
        }
        self.api_methods.import_image(
            image_id, data=data,
            headers=self._headers({'content-type': 'application/json'}))

    def _break_store(self, store):
        """Remove a backend datadir so writes to that store fail."""
        store_path = self._store_dir(store)
        if os.path.isdir(store_path):
            os.rmdir(store_path)

    def _store_has_image_data(self, store):
        store_path = self._store_dir(store)
        if not os.path.isdir(store_path):
            return False
        for _root, _dirs, files in os.walk(store_path):
            if files:
                return True
        return False

    def _wait_for_import_task_success(self, image_id, max_sec=40,
                                      delay_sec=0.2, start_delay_sec=1):
        start_time = time.time()
        done_time = start_time + max_sec
        if start_delay_sec:
            time.sleep(start_delay_sec)

        while time.time() <= done_time:
            try:
                task = self._get_latest_task(image_id)
                if task['status'] == 'success':
                    return task
                if task['status'] == 'failure':
                    self.fail('Import unexpectedly failed')
            except (KeyError, IndexError):
                pass
            time.sleep(delay_sec)

        task = self._get_latest_task(image_id)
        self.assertEqual('success', task['status'])
        return task

    def _wait_for_task_failure(self, image_id, max_sec=40, delay_sec=0.2,
                               start_delay_sec=1):
        start_time = time.time()
        done_time = start_time + max_sec
        if start_delay_sec:
            time.sleep(start_delay_sec)

        while time.time() <= done_time:
            try:
                task = self._get_latest_task(image_id)
                if task['status'] == 'failure':
                    return task
                if task['status'] == 'success':
                    self.fail('Import unexpectedly succeeded')
            except (KeyError, IndexError):
                pass
            time.sleep(delay_sec)

        task = self._get_latest_task(image_id)
        self.assertEqual('failure', task['status'])
        return task

    def _get_image(self, image_id):
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        return jsonutils.loads(response.text)

    def _set_image_db_attributes(self, image_id, **values):
        """Set readonly API fields in the DB (functional tests only)."""
        admin_context = context.get_admin_context()
        db_api.get_api()._FACADE = None
        db_api.get_api().image_update(admin_context, image_id, values)

    def _signature_properties(self, signature_value='VALID'):
        props = dict(SIGNATURE_PROPS)
        props['img_signature'] = signature_value
        return props

    def _create_staged_bare_raw_image(self, size_bytes=units.Mi):
        """Stage a valid bare/raw image (exercises InspectWrapper path)."""
        fd, fn = tempfile.mkstemp(suffix='.raw')
        os.close(fd)
        try:
            subprocess.check_output(
                ['qemu-img', 'create', '-f', 'raw', fn, str(size_bytes)],
                stderr=subprocess.STDOUT)
            with open(fn, 'rb') as image_file:
                image_data = image_file.read()
        finally:
            os.remove(fn)

        image_id = self.api_methods.create_and_verify_image(
            name='parallel-import-bare-raw',
            type='kernel',
            disk_format='raw',
            container_format='bare',
            verify_stores=True,
            available_stores=AVAILABLE_STORES)
        self.api_methods.stage_image_data(image_id, data=image_data)
        func_utils.verify_image_hashes_and_status(
            self, image_id, size=len(image_data), status='uploading')
        return image_id, image_data

    def _create_staged_image_with_checksum(self, checksum):
        image_id = self._create_staged_image()
        self._set_image_db_attributes(image_id, checksum=checksum)
        return image_id

    def test_parallel_glance_direct_imports_all_stores(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self._create_staged_image()
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)
        self.api_methods.verify_image_import_status(image_id, data=IMAGE_DATA)
        self.api_methods.verify_image_stores(
            image_id, expected_stores=AVAILABLE_STORES)

        for store in AVAILABLE_STORES:
            self.assertTrue(
                self._store_has_image_data(store),
                'Expected image data on store %s' % store)

        self.api_methods.delete_image(image_id)

    def test_parallel_glance_direct_two_stores_bounded_workers(self):
        self._enable_parallel_import(max_parallel_stores=2)
        self.start_server()

        image_id = self._create_staged_image()
        stores = ['store1', 'store2']
        self._import_glance_direct(
            image_id, stores, all_stores_must_succeed=True)
        self.api_methods.verify_image_import_status(image_id, data=IMAGE_DATA)
        self.api_methods.verify_image_stores(
            image_id, expected_stores=stores)

        self.api_methods.delete_image(image_id)

    def test_parallel_web_download_multi_store(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self.api_methods.create_and_verify_image(
            name='parallel-web-download',
            type='kernel',
            disk_format='aki',
            container_format='aki',
            verify_stores=True,
            available_stores=AVAILABLE_STORES)
        func_utils.verify_image_hashes_and_status(
            self, image_id, status='queued')

        image_data_uri = self.api_methods.start_http_server_and_get_uri()
        try:
            self._import_web_download(
                image_id, image_data_uri, ['store1', 'store2'],
                all_stores_must_succeed=True)
            self.api_methods.verify_image_import_status(
                image_id, data=image_data_uri)
            self.api_methods.verify_image_stores(
                image_id, expected_stores=['store1', 'store2'])
        finally:
            self.api_methods.httpd.shutdown()
            self.api_methods.httpd.server_close()

        self.api_methods.delete_image(image_id)

    def test_multi_store_serial_when_max_parallel_stores_is_one(self):
        self._enable_parallel_import(max_parallel_stores=1)
        self.start_server()

        image_id = self._create_staged_image()
        self._import_glance_direct(
            image_id, ['store1', 'store2'], all_stores_must_succeed=True)
        self.api_methods.verify_image_import_status(image_id, data=IMAGE_DATA)
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1', 'store2'])

        self.api_methods.delete_image(image_id)

    def test_parallel_single_store_uses_serial_path(self):
        """One target store never selects the parallel import flow."""
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self._create_staged_image()
        self._import_glance_direct(
            image_id, ['store1'], all_stores_must_succeed=True)
        self.api_methods.verify_image_import_status(image_id, data=IMAGE_DATA)
        self.api_methods.verify_image_stores(
            image_id, expected_stores=['store1'])

        self.api_methods.delete_image(image_id)

    def test_parallel_all_stores_must_succeed_failure(self):
        """Fatal parallel failure without import plugins (default config)."""
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self._create_staged_image()
        self._break_store('store3')
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_task_failure(image_id)
        image = self._get_image(image_id)
        # No image_conversion plugin: revert does not reset status to queued.
        self.assertEqual('importing', image['status'])
        self.assertIsNone(image.get('checksum'))
        # No store should be published on the image after a fatal import.
        self.assertEqual('', image.get('stores', ''))

        self.api_methods.delete_image(image_id)

    def test_parallel_all_stores_must_succeed_failure_with_image_conversion(
            self):
        """Fatal parallel failure with image_conversion (devstack parity)."""
        self._enable_parallel_import(max_parallel_stores=3)
        self._enable_image_conversion()
        self.start_server()

        image_id = self._create_staged_raw_image()
        self._break_store('store3')
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_task_failure(image_id)
        image = self._get_image(image_id)
        self.assertEqual('queued', image['status'])
        self.assertIsNone(image.get('checksum'))
        self.assertEqual('', image.get('stores', ''))
        self.assertEqual('', image.get('os_glance_importing_to_stores', ''))
        failed = set(image.get('os_glance_failed_import', '').split(','))
        self.assertEqual(set(AVAILABLE_STORES), failed)

        for store in AVAILABLE_STORES:
            self.assertFalse(
                self._store_has_image_data(store),
                'Expected no image data on store %s after fatal failure' %
                store)

        self.api_methods.delete_image(image_id)

    def test_parallel_partial_success_not_all_must(self):
        self._enable_parallel_import(max_parallel_stores=2)
        self.start_server()

        image_id = self._create_staged_image()
        self._break_store('store2')
        self._import_glance_direct(
            image_id, ['store1', 'store2'], all_stores_must_succeed=False)

        self._wait_for_import_task_success(image_id)
        self.api_methods.verify_image_import_status(image_id, data=IMAGE_DATA)
        image = self.api_methods.verify_image_stores(
            image_id,
            expected_stores=['store1'],
            rejected_stores=['store2'])
        self.assertEqual('store2', image['os_glance_failed_import'])
        self.assertEqual('', image['os_glance_importing_to_stores'])
        self.assertTrue(self._store_has_image_data('store1'))
        self.assertFalse(self._store_has_image_data('store2'))

        self.api_methods.delete_image(image_id)

    def test_parallel_bare_raw_multi_store_success(self):
        """Bare/raw staged data uses the same upload pipeline as set_data."""
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id, image_data = self._create_staged_bare_raw_image()
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)
        self._wait_for_import_task_success(image_id)
        self.api_methods.verify_image_import_status(image_id, data=image_data)
        self.api_methods.verify_image_stores(
            image_id, expected_stores=AVAILABLE_STORES)

        for store in AVAILABLE_STORES:
            self.assertTrue(self._store_has_image_data(store))

        self.api_methods.delete_image(image_id)

    def test_parallel_signed_import_success(self):
        """Signed images verify once on staging before parallel store copy."""
        with mock.patch(SIGNATURE_PATCH,
                        side_effect=unit_test_utils.fake_get_verifier):
            self._enable_parallel_import(max_parallel_stores=3)
            self.start_server()

            image_id = self.api_methods.create_and_verify_image(
                name='parallel-import-signed',
                type='kernel',
                disk_format='aki',
                container_format='aki',
                additional_properties=self._signature_properties('VALID'),
                verify_stores=True,
                available_stores=AVAILABLE_STORES)
            self.api_methods.stage_image_data(image_id, data=IMAGE_DATA)
            func_utils.verify_image_hashes_and_status(
                self, image_id, size=len(IMAGE_DATA), status='uploading')

            self._import_glance_direct(
                image_id, AVAILABLE_STORES, all_stores_must_succeed=True)
            self._wait_for_import_task_success(image_id)
            self.api_methods.verify_image_import_status(
                image_id, data=IMAGE_DATA)
            self.api_methods.verify_image_stores(
                image_id, expected_stores=AVAILABLE_STORES)

            self.api_methods.delete_image(image_id)

    def test_parallel_signed_import_invalid_signature_fails(self):
        with mock.patch(SIGNATURE_PATCH,
                        side_effect=unit_test_utils.fake_get_verifier):
            self._enable_parallel_import(max_parallel_stores=3)
            self.start_server()

            image_id = self.api_methods.create_and_verify_image(
                name='parallel-import-signed-bad',
                type='kernel',
                disk_format='aki',
                container_format='aki',
                additional_properties=self._signature_properties('INVALID'),
                verify_stores=True,
                available_stores=AVAILABLE_STORES)
            self.api_methods.stage_image_data(image_id, data=IMAGE_DATA)
            func_utils.verify_image_hashes_and_status(
                self, image_id, size=len(IMAGE_DATA), status='uploading')

            self._import_glance_direct(
                image_id, AVAILABLE_STORES, all_stores_must_succeed=True)
            self._wait_for_task_failure(image_id)

            image = self._get_image(image_id)
            self.assertEqual('queued', image['status'])
            self.assertEqual('', image.get('stores', ''))
            failed = set(image.get('os_glance_failed_import', '').split(','))
            self.assertEqual(set(AVAILABLE_STORES), failed)
            for store in AVAILABLE_STORES:
                self.assertFalse(self._store_has_image_data(store))

            self.api_methods.delete_image(image_id)

    def test_parallel_staged_size_mismatch_fails(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self._create_staged_image()
        # size is readonly via API; staging sets the real byte count.
        self._set_image_db_attributes(
            image_id, size=len(IMAGE_DATA) + 1000)
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_task_failure(image_id)
        image = self._get_image(image_id)
        self.assertEqual('importing', image['status'])
        self.assertEqual('', image.get('stores', ''))

        self.api_methods.delete_image(image_id)

    def test_parallel_checksum_mismatch_fails(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        wrong_checksum = '0' * 32
        image_id = self._create_staged_image_with_checksum(wrong_checksum)
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_task_failure(image_id)
        image = self._get_image(image_id)
        self.assertEqual('importing', image['status'])
        self.assertEqual('', image.get('stores', ''))

        self.api_methods.delete_image(image_id)

    def test_parallel_checksum_match_success(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        checksum = hashlib.md5(IMAGE_DATA, usedforsecurity=False).hexdigest()
        image_id = self._create_staged_image_with_checksum(checksum)
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_import_task_success(image_id)
        image = self._get_image(image_id)
        self.assertEqual(checksum, image['checksum'])
        self.api_methods.verify_image_stores(
            image_id, expected_stores=AVAILABLE_STORES)

        self.api_methods.delete_image(image_id)

    def test_parallel_all_target_stores_fail(self):
        self._enable_parallel_import(max_parallel_stores=3)
        self.start_server()

        image_id = self._create_staged_image()
        for store in AVAILABLE_STORES:
            self._break_store(store)
        self._import_glance_direct(
            image_id, AVAILABLE_STORES, all_stores_must_succeed=True)

        self._wait_for_task_failure(image_id)
        image = self._get_image(image_id)
        self.assertEqual('importing', image['status'])
        for store in AVAILABLE_STORES:
            self.assertFalse(self._store_has_image_data(store))

        self.api_methods.delete_image(image_id)
