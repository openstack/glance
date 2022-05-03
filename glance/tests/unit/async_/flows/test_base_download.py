# Copyright 2022 OVHCloud
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
from unittest import mock

from glance_store import backend
from oslo_config import cfg
from taskflow.types import failure

from glance.async_.flows import api_image_import
import glance.common.exception
from glance import domain
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF


TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestBaseDownloadTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestBaseDownloadTask, self).setUp()

        self.config(node_staging_uri='/tmp/staging')
        self.image_repo = mock.MagicMock()
        self.image_id = mock.MagicMock()
        self.uri = mock.MagicMock()
        self.plugin_name = 'FakeBaseDownload'
        self.task_factory = domain.TaskFactory()

        task_input = {
            "import_req": {
                'method': {
                    'name': 'web_download',
                    'uri': 'http://cloud.foo/image.qcow2'
                }
            }
        }
        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        request_id = 'fake_request_id'
        user_id = 'fake_user'
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               self.image_id, user_id,
                                               request_id,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

        self.task_id = self.task.task_id
        self.action_wrapper = api_image_import.ImportActionWrapper(
            self.image_repo, self.image_id, self.task_id)
        self.image_repo.get.return_value = mock.MagicMock(
            extra_properties={'os_glance_import_task': self.task_id})
        self.base_download_task = unit_test_utils.FakeBaseDownloadPlugin(
            self.task.task_id, self.task_type, self.action_wrapper,
            ['foo'], self.plugin_name)
        self.base_download_task._path = "/path/to_downloaded_data"

    def test_base_download_node_staging_uri_is_none(self):
        self.config(node_staging_uri=None)
        self.assertRaises(glance.common.exception.BadTaskConfiguration,
                          unit_test_utils.FakeBaseDownloadPlugin,
                          self.task.task_id, self.task_type, self.uri,
                          self.action_wrapper, ['foo'])

    @mock.patch.object(cfg.ConfigOpts, "set_override")
    def test_base_download_node_store_initialization_failed(
            self, mock_override):
        with mock.patch.object(backend, '_load_store') as mock_load_store:
            mock_load_store.return_value = None
            self.assertRaises(glance.common.exception.BadTaskConfiguration,
                              unit_test_utils.FakeBaseDownloadPlugin,
                              self.task.task_id, self.task_type, self.uri,
                              self.action_wrapper, ['foo'])
            mock_override.assert_called()

    def test_base_download_delete_staging_image_not_exist(self):
        staging_path = "file:///tmp/staging/temp-image"
        delete_from_fs_task = api_image_import._DeleteFromFS(
            self.task.task_id, self.task_type)
        with mock.patch.object(os.path, "exists") as mock_exists:
            mock_exists.return_value = False
            with mock.patch.object(os, "unlink") as mock_unlik:
                delete_from_fs_task.execute(staging_path)

                self.assertEqual(1, mock_exists.call_count)
                self.assertEqual(0, mock_unlik.call_count)

    @mock.patch.object(os.path, "exists")
    def test_base_download_delete_staging_image_failed(self, mock_exists):
        mock_exists.return_value = True
        staging_path = "file:///tmp/staging/temp-image"
        delete_from_fs_task = api_image_import._DeleteFromFS(
            self.task.task_id, self.task_type)
        with mock.patch.object(os, "unlink") as mock_unlink:
            try:
                delete_from_fs_task.execute(staging_path)
            except OSError:
                self.assertEqual(1, mock_unlink.call_count)

            self.assertEqual(1, mock_exists.call_count)

    @mock.patch.object(os.path, "exists")
    def test_base_download_delete_staging_image_succeed(self, mock_exists):
        mock_exists.return_value = True
        staging_path = "file:///tmp/staging/temp-image"
        delete_from_fs_task = api_image_import._DeleteFromFS(
            self.task.task_id, self.task_type)
        with mock.patch.object(os, "unlink") as mock_unlik:
            delete_from_fs_task.execute(staging_path)
            self.assertEqual(1, mock_exists.call_count)
            self.assertEqual(1, mock_unlik.call_count)

    @mock.patch(
        "glance.async_.flows._internal_plugins.base_download.store_api")
    def test_base_download_revert_with_failure(self, mock_store_api):
        image = self.image_repo.get.return_value
        image.extra_properties['os_glance_importing_to_stores'] = 'foo'
        image.extra_properties['os_glance_failed_import'] = ''

        self.base_download_task.execute = mock.MagicMock(
            side_effect=glance.common.exception.ImportTaskError)
        self.base_download_task.revert(None)
        mock_store_api.delete_from_backend.assert_called_once_with(
            "/path/to_downloaded_data")
        self.assertEqual(1, self.image_repo.save.call_count)
        self.assertEqual(
            '', image.extra_properties['os_glance_importing_to_stores'])
        self.assertEqual(
            'foo', image.extra_properties['os_glance_failed_import'])

    @mock.patch(
        "glance.async_.flows._internal_plugins.base_download.store_api")
    def test_base_download_revert_without_failure_multi_store(self,
                                                              mock_store_api):
        enabled_backends = {
            'fast': 'file',
            'cheap': 'file'
        }
        self.config(enabled_backends=enabled_backends)

        self.base_download_task.revert("/path/to_downloaded_data")
        mock_store_api.delete.assert_called_once_with(
            "/path/to_downloaded_data", None)

    @mock.patch(
        "glance.async_.flows._internal_plugins.base_download.store_api")
    def test_base_download_revert_with_failure_without_path(self,
                                                            mock_store_api):
        image = self.image_repo.get.return_value
        image.status = 'importing'
        image.extra_properties['os_glance_importing_to_stores'] = 'foo'
        image.extra_properties['os_glance_failed_import'] = ''
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())

        self.base_download_task._path = None
        self.base_download_task.revert(result)
        mock_store_api.delete_from_backend.assert_not_called()

        # NOTE(danms): Since we told revert that we were the problem,
        # we should have updated the image status and moved the stores
        # to the failed list.
        self.image_repo.save.assert_called_once_with(image, 'importing')
        self.assertEqual('queued', image.status)
        self.assertEqual(
            '', image.extra_properties['os_glance_importing_to_stores'])
        self.assertEqual(
            'foo', image.extra_properties['os_glance_failed_import'])

    @mock.patch(
        "glance.async_.flows._internal_plugins.base_download.store_api")
    def test_base_download_revert_with_failure_with_path(self, mock_store_api):
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())

        self.base_download_task.revert(result)
        mock_store_api.delete_from_backend.assert_called_once_with(
            "/path/to_downloaded_data")

    @mock.patch(
        "glance.async_.flows._internal_plugins.base_download.store_api")
    def test_base_download_delete_fails_on_revert(self, mock_store_api):
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())
        mock_store_api.delete_from_backend.side_effect = Exception

        # this will verify that revert does not break because of failure
        # while deleting data in staging area
        self.base_download_task.revert(result)
