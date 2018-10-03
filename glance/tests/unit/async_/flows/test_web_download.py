# Copyright 2018 Red Hat, Inc.
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

from glance_store._drivers import filesystem
from glance_store import backend
from oslo_config import cfg
from taskflow.types import failure

from glance.async_.flows._internal_plugins import web_download
from glance.async_.flows import api_image_import
import glance.common.exception
import glance.common.scripts.utils as script_utils
from glance import domain
import glance.tests.utils as test_utils

CONF = cfg.CONF


TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestWebDownloadTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestWebDownloadTask, self).setUp()

        self.config(node_staging_uri='/tmp/staging')
        self.task_repo = mock.MagicMock()
        self.image_id = mock.MagicMock()
        self.uri = mock.MagicMock()
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
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download(self, mock_add):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_add.return_value = ["path", 4]
            mock_iter.return_value.headers = {}
            self.assertEqual(web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_with_content_length(self, mock_add):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': '4'}
            mock_add.return_value = ["path", 4]
            self.assertEqual(web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_with_invalid_content_length(self, mock_add):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': "not_valid"}
            mock_add.return_value = ["path", 4]
            self.assertEqual(web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_fails_when_data_size_different(self, mock_add):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': '4'}
            mock_add.return_value = ["path", 3]
            self.assertRaises(
                glance.common.exception.ImportTaskError,
                web_download_task.execute)

    def test_web_download_node_staging_uri_is_none(self):
        self.config(node_staging_uri=None)
        self.assertRaises(glance.common.exception.BadTaskConfiguration,
                          web_download._WebDownload, self.task.task_id,
                          self.task_type, self.task_repo, self.image_id,
                          self.uri)

    @mock.patch.object(cfg.ConfigOpts, "set_override")
    def test_web_download_node_store_initialization_failed(self,
                                                           mock_override):
        with mock.patch.object(backend, '_load_store') as mock_load_store:
            mock_load_store.return_value = None
            self.assertRaises(glance.common.exception.BadTaskConfiguration,
                              web_download._WebDownload, self.task.task_id,
                              self.task_type, self.task_repo, self.image_id,
                              self.uri)
            mock_override.assert_called()

    def test_web_download_failed(self):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               "get_image_data_iter") as mock_iter:
            mock_iter.side_effect = glance.common.exception.NotFound
            self.assertRaises(glance.common.exception.NotFound,
                              web_download_task.execute)

    def test_web_download_delete_staging_image_not_exist(self):
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
    def test_web_download_delete_staging_image_failed(self, mock_exists):
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
    def test_web_download_delete_staging_image_succeed(self, mock_exists):
        mock_exists.return_value = True
        staging_path = "file:///tmp/staging/temp-image"
        delete_from_fs_task = api_image_import._DeleteFromFS(
            self.task.task_id, self.task_type)
        with mock.patch.object(os, "unlink") as mock_unlik:
            delete_from_fs_task.execute(staging_path)
            self.assertEqual(1, mock_exists.call_count)
            self.assertEqual(1, mock_unlik.call_count)

    @mock.patch.object(filesystem.Store, 'add')
    @mock.patch("glance.async_.flows._internal_plugins.web_download.store_api")
    def test_web_download_revert_with_failure(self, mock_store_api,
                                              mock_add):
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': '4'}
            mock_add.return_value = "/path/to_downloaded_data", 3
            self.assertRaises(
                glance.common.exception.ImportTaskError,
                web_download_task.execute)

        web_download_task.revert(None)
        mock_store_api.delete_from_backend.assert_called_once_with(
            "/path/to_downloaded_data")

    @mock.patch("glance.async_.flows._internal_plugins.web_download.store_api")
    def test_web_download_revert_without_failure_multi_store(self,
                                                             mock_store_api):
        enabled_backends = {
            'fast': 'file',
            'cheap': 'file'
        }
        self.config(enabled_backends=enabled_backends)
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        web_download_task._path = "/path/to_downloaded_data"
        web_download_task.revert("/path/to_downloaded_data")
        mock_store_api.delete.assert_called_once_with(
            "/path/to_downloaded_data", None)

    @mock.patch("glance.async_.flows._internal_plugins.web_download.store_api")
    def test_web_download_revert_with_failure_without_path(self,
                                                           mock_store_api):
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        web_download_task.revert(result)
        mock_store_api.delete_from_backend.assert_not_called()

    @mock.patch("glance.async_.flows._internal_plugins.web_download.store_api")
    def test_web_download_revert_with_failure_with_path(self, mock_store_api):
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        web_download_task._path = "/path/to_downloaded_data"
        web_download_task.revert(result)
        mock_store_api.delete_from_backend.assert_called_once_with(
            "/path/to_downloaded_data")

    @mock.patch("glance.async_.flows._internal_plugins.web_download.store_api")
    def test_web_download_delete_fails_on_revert(self, mock_store_api):
        result = failure.Failure.from_exception(
            glance.common.exception.ImportTaskError())
        mock_store_api.delete_from_backend.side_effect = Exception
        web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.task_repo,
            self.image_id, self.uri)
        web_download_task._path = "/path/to_downloaded_data"
        # this will verify that revert does not break because of failure
        # while deleting data in staging area
        web_download_task.revert(result)
