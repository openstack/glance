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
import os
from unittest import mock

import glance.async_.flows.plugins.image_decompression as image_decompression
from glance import gateway
import glance.tests.utils as test_utils

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestDecompressImageTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestDecompressImageTask, self).setUp()

        self.context = mock.MagicMock()
        self.img_repo = mock.MagicMock()
        self.image_id = UUID1
        self.task_id = 'fake-task-id'
        self.task_type = 'api_image_import'

        self.gateway = gateway.Gateway()
        self.img_factory = self.gateway.get_image_factory(self.context)
        self.image = self.img_factory.new_image(image_id=self.image_id,
                                                disk_format='raw',
                                                container_format='bare')
        self.image.size = 1000  # Initial compressed size
        self.img_repo.get.return_value = self.image

    def _create_gzip_file(self, content, filename='test.gz'):
        """Create a gzipped file with the given content."""
        filepath = os.path.join(self.test_dir, filename)
        with gzip.open(filepath, 'wb') as f:
            f.write(content)
        return filepath

    def test_decompress_gzip_updates_image_size(self):
        """Test that image size is updated after successful GZIP
        decompression.
        """
        # Create a gzipped file
        original_content = b'x' * 10000  # 10KB uncompressed
        compressed_file = self._create_gzip_file(original_content, 'test.gz')

        # Get compressed size
        compressed_size = os.path.getsize(compressed_file)

        # Create decompression task
        decompress_task = image_decompression._DecompressImage(
            self.context, self.task_id, self.task_type,
            self.img_repo, self.image_id)

        # Execute decompression
        file_path = 'file://%s' % compressed_file
        result = decompress_task.execute(file_path)

        # Verify the image size was updated to decompressed size
        self.assertEqual(10000, self.image.size)
        # Verify image_repo.save was called
        self.img_repo.save.assert_called_once_with(self.image)
        # Verify the result is the file path
        self.assertEqual(file_path, result)
        # Verify the file was replaced by checking the size changed.
        self.assertNotEqual(compressed_size, os.path.getsize(compressed_file))
        self.assertEqual(10000, os.path.getsize(compressed_file))

    def test_decompress_no_compression_detected(self):
        """Test that image size is not updated when no compression
        is detected.
        """
        # Create a non-compressed file
        uncompressed_file = os.path.join(self.test_dir, 'test.raw')
        with open(uncompressed_file, 'wb') as f:
            f.write(b'x' * 5000)

        decompress_task = image_decompression._DecompressImage(
            self.context, self.task_id, self.task_type,
            self.img_repo, self.image_id)

        file_path = 'file://%s' % uncompressed_file
        result = decompress_task.execute(file_path)

        # Verify image size was NOT updated (no compression detected)
        self.assertEqual(1000, self.image.size)
        # Verify image_repo.save was NOT called
        self.img_repo.save.assert_not_called()
        # Verify the result is the file path
        self.assertEqual(file_path, result)

    def test_decompress_skips_when_container_format_compressed(self):
        """Test that decompression is skipped when container_format
        is 'compressed'.
        """
        # Create a gzipped file
        original_content = b'x' * 10000
        compressed_file = self._create_gzip_file(original_content, 'test.gz')

        # Set container_format to 'compressed'
        self.image.container_format = 'compressed'

        decompress_task = image_decompression._DecompressImage(
            self.context, self.task_id, self.task_type,
            self.img_repo, self.image_id)

        file_path = 'file://%s' % compressed_file
        result = decompress_task.execute(file_path)

        # Verify image size was NOT updated
        self.assertEqual(1000, self.image.size)
        # Verify image_repo.save was NOT called
        self.img_repo.save.assert_not_called()
        # Verify the result is the file path
        self.assertEqual(file_path, result)

    @mock.patch('glance.async_.flows.plugins.image_decompression.LOG')
    def test_decompress_logs_size_update(self, mock_log):
        """Test that size update is logged."""
        # Create a gzipped file
        original_content = b'x' * 5000
        compressed_file = self._create_gzip_file(original_content, 'test.gz')

        decompress_task = image_decompression._DecompressImage(
            self.context, self.task_id, self.task_type,
            self.img_repo, self.image_id)

        file_path = 'file://%s' % compressed_file
        result = decompress_task.execute(file_path)

        # Verify the result is the file path
        self.assertEqual(file_path, result)
        # Verify logging was called
        mock_log.info.assert_called()
        # Check that the log message contains the expected information
        log_calls = [str(call) for call in mock_log.info.call_args_list]
        size_update_logged = any(
            'Updated image' in str(call) and
            'size to' in str(call) and
            'after decompression' in str(call)
            for call in log_calls)
        self.assertTrue(size_update_logged,
                        "Size update log message not found")

    def test_decompress_handles_missing_file(self):
        """Test that decompression raises FileNotFoundError for missing
        file.
        """
        missing_file = os.path.join(self.test_dir, 'nonexistent.gz')

        decompress_task = image_decompression._DecompressImage(
            self.context, self.task_id, self.task_type,
            self.img_repo, self.image_id)

        file_path = 'file://%s' % missing_file
        # The code doesn't check for file existence, so it will raise
        # FileNotFoundError when trying to open the file
        self.assertRaises(FileNotFoundError,
                          decompress_task.execute,
                          file_path)

        # Verify image size was NOT updated
        self.assertEqual(1000, self.image.size)
        # Verify image_repo.save was NOT called
        self.img_repo.save.assert_not_called()

    def test_get_flow_returns_flow_with_decompress_task(self):
        """Test that get_flow returns a flow with the decompress task."""
        kwargs = {
            'context': self.context,
            'task_id': self.task_id,
            'task_type': self.task_type,
            'image_repo': self.img_repo,
            'image_id': self.image_id
        }

        flow = image_decompression.get_flow(**kwargs)

        # Verify flow is created
        self.assertIsNotNone(flow)
        # Verify flow is a taskflow Flow object
        from taskflow.patterns import linear_flow as lf
        self.assertIsInstance(flow, lf.Flow)
        # Verify flow has tasks (check via iterating)
        tasks = list(flow)
        self.assertEqual(1, len(tasks))
        task = tasks[0]
        self.assertIsInstance(task, image_decompression._DecompressImage)
        self.assertEqual(self.image_id, task.image_id)
        self.assertEqual(self.task_id, task.task_id)
        self.assertEqual(self.task_type, task.task_type)
