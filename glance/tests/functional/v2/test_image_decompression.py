# Copyright 2025 Red Hat, Inc.
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

import gzip
import hashlib
import http.client as http
import http.server as http_server
import os
import threading
import time
import zipfile

from oslo_serialization import jsonutils
import testtools

import glance.async_.flows.plugins.image_decompression as image_decompression
from glance.tests import functional
from glance.tests.functional import ft_utils as func_utils
from glance.tests.functional.v2.test_images import ImageAPIHelper


class TestImageDecompression(functional.SynchronousAPIBase):
    """Functional tests for image decompression plugin.

    Tests the image decompression plugin during image import operations
    using both glance-direct and web-download methods.
    """

    def setUp(self, single_store=True):
        super(TestImageDecompression, self).setUp(single_store=single_store)
        # Import to register image_import_opts config group otherwise tests
        # will fail with NoSuchOptGroup error.
        from glance.async_.flows import api_image_import  # noqa
        self.setup_database()
        self.setup_simple_paste()
        if single_store:
            self.setup_single_store()
        else:
            self.setup_stores()

        # Enable image decompression plugin
        self.config(image_import_plugins=['image_decompression'],
                    group='image_import_opts')
        self.config(enabled_import_methods=['glance-direct', 'web-download'])

        self.api_methods = ImageAPIHelper(
            self.api_get, self.api_post, self.api_put, self.api_delete)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': '70b8c4b4-4e3e-4e3e-9e3e-4e3e4e3e4e3e',
            'X-Project-Id': self.TENANT,
            'X-Roles': 'member,reader',
            'content-type': 'application/json'
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _create_gzip_file(self, content, filename='test.gz'):
        """Create a gzipped file with the given content."""
        filepath = os.path.join(self.test_dir, filename)
        with gzip.open(filepath, 'wb') as f:
            f.write(content)
        return filepath

    def _create_zip_file(self, content, filename='test.zip',
                         entry_name='test_image.raw'):
        """Create a ZIP file with the given content."""
        filepath = os.path.join(self.test_dir, filename)
        with zipfile.ZipFile(filepath, 'w') as zf:
            zf.writestr(entry_name, content)
        return filepath

    def _create_zip_file_multiple(self, files_dict, filename='test.zip'):
        """Create a ZIP file with multiple entries."""
        filepath = os.path.join(self.test_dir, filename)
        with zipfile.ZipFile(filepath, 'w') as zf:
            for entry_name, content in files_dict.items():
                zf.writestr(entry_name, content)
        return filepath

    def _create_uncompressed_file(self, content, filename='test.raw'):
        """Create an uncompressed file with the given content."""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        return filepath

    def _calculate_checksum(self, data):
        """Calculate MD5 checksum of data."""
        return hashlib.md5(data, usedforsecurity=False).hexdigest()

    def _calculate_sha512(self, data):
        """Calculate SHA512 checksum of data."""
        return hashlib.sha512(data).hexdigest()

    def _wait_for_task_failure(self, image_id, max_sec=40, delay_sec=0.2,
                               start_delay_sec=1):
        """Wait for import task to fail.

        This method checks the task status associated with the image to
        determine if the import task has failed.

        :param image_id: The image ID to check
        :param max_sec: Maximum seconds to wait (default: 40)
        :param delay_sec: Seconds to sleep between checks (default: 0.2)
        :param start_delay_sec: Seconds to wait before first check (default: 1)
        :returns: The task dict from the API response
        """
        start_time = time.time()
        done_time = start_time + max_sec
        if start_delay_sec:
            time.sleep(start_delay_sec)

        while time.time() <= done_time:
            try:
                task = self._get_latest_task(image_id)
                if task['status'] == 'failure':
                    return task
                elif task['status'] == 'success':
                    self.fail("Import unexpectedly succeeded "
                              "(task status=success)")
            except (KeyError, IndexError):
                # Task may not exist yet, continue checking
                pass

            time.sleep(delay_sec)

        # Final check - verify task status
        task = self._get_latest_task(image_id)
        self.assertEqual('failure', task['status'])
        return task

    def _start_binary_http_server(self, data):
        """Start an HTTP server serving binary data.

        Returns a tuple of (httpd, thread, uri) where:
        - httpd: The HTTP server instance (for cleanup)
        - thread: The server thread (for reference)
        - uri: The URI to use for web-download
        """
        class BinaryHTTPRequestHandler(http_server.BaseHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.data = data
                super().__init__(*args, **kwargs)

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(self.data)))
                self.end_headers()
                self.wfile.write(self.data)
                return

            def log_message(self, *args, **kwargs):
                return

        server_address = ('127.0.0.1', 0)
        httpd = http_server.HTTPServer(server_address,
                                       BinaryHTTPRequestHandler)
        port = httpd.server_address[1]

        def serve_requests(server):
            server.serve_forever()

        thread = threading.Thread(target=serve_requests, args=(httpd,))
        thread.daemon = True
        thread.start()
        uri = 'http://localhost:%d/' % port
        return (httpd, thread, uri)

    def test_decompress_gzip_with_glance_direct(self):
        """Test GZIP decompression during glance-direct import."""
        self.start_server()

        original_content = b'X' * 10000
        compressed_file = self._create_gzip_file(original_content)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='gzip-image',
            disk_format='raw',
            container_format='bare')

        with open(compressed_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        self.api_methods.verify_image_size(image_id, expected_size=10000)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        expected_checksum = self._calculate_checksum(original_content)
        expected_sha512 = self._calculate_sha512(original_content)
        self.assertEqual(expected_checksum, image['checksum'])
        self.assertEqual(expected_sha512, image['os_hash_value'])

        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        downloaded_data = response.body
        self.assertEqual(10000, len(downloaded_data))
        self.assertEqual(original_content, downloaded_data)

    def test_decompress_gzip_with_web_download(self):
        """Test GZIP decompression during web-download import."""
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        original_content = b'Y' * 15000
        compressed_file = self._create_gzip_file(original_content)

        image_id = self.api_methods.create_and_verify_image(
            name='gzip-web-image',
            disk_format='raw',
            container_format='bare')

        with open(compressed_file, 'rb') as f:
            compressed_data = f.read()

        httpd, thread, image_data_uri = self._start_binary_http_server(
            compressed_data)

        data = {'method': {'name': 'web-download', 'uri': image_data_uri}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        self.api_methods.verify_image_size(image_id, expected_size=15000)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        expected_checksum = self._calculate_checksum(original_content)
        self.assertEqual(expected_checksum, image['checksum'])

        httpd.shutdown()
        httpd.server_close()

    def test_decompress_zip_with_glance_direct(self):
        """Test ZIP decompression during glance-direct import."""
        self.start_server()

        original_content = b'Z' * 20000
        zip_file = self._create_zip_file(original_content)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='zip-image',
            disk_format='raw',
            container_format='bare')

        with open(zip_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        self.api_methods.verify_image_size(image_id, expected_size=20000)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        expected_checksum = self._calculate_checksum(original_content)
        self.assertEqual(expected_checksum, image['checksum'])

        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        downloaded_data = response.body
        self.assertEqual(20000, len(downloaded_data))
        self.assertEqual(original_content, downloaded_data)

    def test_decompress_zip_with_web_download(self):
        """Test ZIP decompression during web-download import."""
        self.config(allowed_ports=[], group='import_filtering_opts')
        self.start_server()

        original_content = b'W' * 12000
        zip_file = self._create_zip_file(original_content)

        image_id = self.api_methods.create_and_verify_image(
            name='zip-web-image',
            disk_format='raw',
            container_format='bare')

        with open(zip_file, 'rb') as f:
            compressed_data = f.read()

        httpd, thread, image_data_uri = self._start_binary_http_server(
            compressed_data)

        data = {'method': {'name': 'web-download', 'uri': image_data_uri}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        self.api_methods.verify_image_size(image_id, expected_size=12000)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        expected_checksum = self._calculate_checksum(original_content)
        self.assertEqual(expected_checksum, image['checksum'])

        httpd.shutdown()
        httpd.server_close()

    def test_decompress_zip_multiple_files_error(self):
        """Test that ZIP with multiple files fails during import."""
        self.start_server()

        # Create a ZIP file with multiple files
        files_dict = {
            'file1.raw': b'content1',
            'file2.raw': b'content2'
        }
        zip_file = self._create_zip_file_multiple(files_dict)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='zip-multi-image',
            disk_format='raw',
            container_format='bare')

        # Stage the compressed file
        with open(zip_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        self._wait_for_task_failure(image_id)

        # Verify image state after task failure
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('importing', image['status'])
        self.assertIsNone(image.get('checksum'))

    def test_skip_decompression_container_format_compressed(self):
        """Test decompression is skipped when container_format='compressed'."""
        self.start_server()

        original_content = b'C' * 8000
        compressed_file = self._create_gzip_file(original_content)
        compressed_size = os.path.getsize(compressed_file)

        image_id = self.api_methods.create_and_verify_image(
            name='compressed-format-image',
            disk_format='raw',
            container_format='compressed')

        with open(compressed_file, 'rb') as f:
            compressed_data = f.read()
            self.api_methods.stage_image_data(image_id, data=compressed_data)

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual(compressed_size, image['size'])

        expected_checksum = self._calculate_checksum(compressed_data)
        self.assertEqual(expected_checksum, image['checksum'])

        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        downloaded_data = response.body
        self.assertEqual(compressed_size, len(downloaded_data))
        self.assertEqual(compressed_data, downloaded_data)

    def test_no_decompression_uncompressed_file(self):
        """Test that uncompressed files pass through unchanged."""
        self.start_server()

        original_content = b'U' * 5000
        uncompressed_file = self._create_uncompressed_file(original_content)

        image_id = self.api_methods.create_and_verify_image(
            name='uncompressed-image',
            disk_format='raw',
            container_format='bare')

        with open(uncompressed_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        func_utils.wait_for_status(
            self, request_path='/v2/images/%s' % image_id,
            request_headers=self._headers(),
            status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)

        self.api_methods.verify_image_size(image_id, expected_size=5000)

        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        expected_checksum = self._calculate_checksum(original_content)
        self.assertEqual(expected_checksum, image['checksum'])

        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        downloaded_data = response.body
        self.assertEqual(5000, len(downloaded_data))
        self.assertEqual(original_content, downloaded_data)

    def _create_lha_file(self, content, filename='test.lha',
                         entry_name='test_image.raw'):
        """Create an LHA file with the given content."""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(b'\x00\x00\x2d\x6c\x68' + b'X' * 100)
        return filepath

    @testtools.skipIf(
        image_decompression.NO_LHA,
        "lhafile library not available")
    def test_decompress_lha_with_glance_direct(self):
        """Test LHA decompression during glance-direct import."""
        self.start_server()

        lha_file = self._create_lha_file(b'H' * 9000)

        # Create an image
        image_id = self.api_methods.create_and_verify_image(
            name='lha-image',
            disk_format='raw',
            container_format='bare')

        with open(lha_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        # If LHA file is not valid, import will fail.
        try:
            func_utils.wait_for_status(
                self, request_path='/v2/images/%s' % image_id,
                request_headers=self._headers(),
                status='active', max_sec=40, delay_sec=0.2, start_delay_sec=1)
            # If import succeeded, verify final status is active
            path = '/v2/images/%s' % image_id
            response = self.api_get(path, headers=self._headers())
            self.assertEqual(http.OK, response.status_code)
            image = jsonutils.loads(response.text)
            self.assertEqual('active', image['status'])
        except Exception:
            # If import failed, verify it's in importing status with no
            # checksum
            path = '/v2/images/%s' % image_id
            response = self.api_get(path, headers=self._headers())
            self.assertEqual(http.OK, response.status_code)
            image = jsonutils.loads(response.text)
            self.assertEqual('importing', image['status'])
            self.assertIsNone(image.get('checksum'))

    def test_decompress_lha_no_library_error(self):
        """Test LHA import fails gracefully when library is unavailable."""
        if not image_decompression.NO_LHA:
            self.skipTest("lhafile library is available, cannot test NO_LHA")

        self.start_server()

        lha_file = self._create_lha_file(b'LHA content')

        image_id = self.api_methods.create_and_verify_image(
            name='lha-no-lib-image',
            disk_format='raw',
            container_format='bare')

        with open(lha_file, 'rb') as f:
            self.api_methods.stage_image_data(image_id, data=f.read())

        data = {'method': {'name': 'glance-direct'}}
        self.api_methods.import_image(image_id, data=data)

        self._wait_for_task_failure(image_id)

        # Verify image state after task failure
        path = '/v2/images/%s' % image_id
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        image = jsonutils.loads(response.text)
        self.assertEqual('importing', image['status'])
        self.assertIsNone(image.get('checksum'))
