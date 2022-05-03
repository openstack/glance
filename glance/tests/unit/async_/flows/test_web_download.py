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

from unittest import mock

from glance_store._drivers import filesystem
from oslo_config import cfg

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
        self.image_repo = mock.MagicMock()
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
        self.web_download_task = web_download._WebDownload(
            self.task.task_id, self.task_type, self.uri, self.action_wrapper,
            ['foo'])
        self.image_repo.get.return_value = mock.MagicMock(
            extra_properties={'os_glance_import_task': self.task_id})

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_add.return_value = ["path", 4]
            mock_iter.return_value.headers = {}
            self.assertEqual(self.web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_with_content_length(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': '4'}
            mock_add.return_value = ["path", 4]
            self.assertEqual(self.web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_with_invalid_content_length(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': "not_valid"}
            mock_add.return_value = ["path", 4]
            self.assertEqual(self.web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_fails_when_data_size_different(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_iter.return_value.headers = {'content-length': '4'}
            mock_add.return_value = ["path", 3]
            self.assertRaises(
                glance.common.exception.ImportTaskError,
                self.web_download_task.execute)

    def test_web_download_failed(self):
        with mock.patch.object(script_utils,
                               "get_image_data_iter") as mock_iter:
            mock_iter.side_effect = glance.common.exception.NotFound
            self.assertRaises(glance.common.exception.NotFound,
                              self.web_download_task.execute)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_check_content_length(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_add.return_value = ["path", 4]
            mock_iter.return_value.headers = {'content-length': '4'}
            self.assertEqual(self.web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_invalid_content_length(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_add.return_value = ["path", 4]
            mock_iter.return_value.headers = {'content-length': 'not_valid'}
            self.assertEqual(self.web_download_task.execute(), "path")
            mock_add.assert_called_once_with(self.image_id,
                                             mock_iter.return_value, 0)

    @mock.patch.object(filesystem.Store, 'add')
    def test_web_download_wrong_content_length(self, mock_add):
        with mock.patch.object(script_utils,
                               'get_image_data_iter') as mock_iter:
            mock_add.return_value = ["path", 2]
            mock_iter.return_value.headers = {'content-length': '4'}
            self.assertRaises(glance.common.exception.ImportTaskError,
                              self.web_download_task.execute)
