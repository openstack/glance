# Copyright 2022 Red Hat, Inc.
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
import urllib.error

from glance_store._drivers import filesystem
from oslo_config import cfg
from oslo_utils.fixture import uuidsentinel

from glance.async_.flows._internal_plugins import glance_download
from glance.async_.flows import api_image_import
import glance.common.exception
import glance.context
from glance import domain
import glance.tests.utils as test_utils

CONF = cfg.CONF


TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestGlanceDownloadTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestGlanceDownloadTask, self).setUp()

        self.config(node_staging_uri='/tmp/staging')
        self.image_repo = mock.MagicMock()
        self.image_id = mock.MagicMock()
        self.uri = mock.MagicMock()
        self.task_factory = domain.TaskFactory()
        self.context = glance.context.RequestContext(tenant=TENANT1,
                                                     auth_token='token')
        task_input = {
            "import_req": {
                'method': {
                    'name': 'glance-download',
                    'glance_image_id': uuidsentinel.remote_image,
                    'glance_region': 'RegionTwo',
                    'glance_service_interface': 'public',
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

    @mock.patch.object(filesystem.Store, 'add')
    @mock.patch('glance.async_.utils.get_glance_endpoint')
    def test_glance_download(self, mock_gge, mock_add):
        mock_gge.return_value = 'https://other.cloud.foo/image'
        glance_download_task = glance_download._DownloadGlanceImage(
            self.context, self.task.task_id, self.task_type,
            self.action_wrapper, ['foo'],
            'RegionTwo', uuidsentinel.remote_image, 'public')
        with mock.patch('urllib.request') as mock_request:
            mock_add.return_value = ["path", 12345]
            self.assertEqual(glance_download_task.execute(12345), "path")
            mock_add.assert_called_once_with(
                self.image_id,
                mock_request.urlopen.return_value, 0)
            mock_request.Request.assert_called_once_with(
                'https://other.cloud.foo/image/v2/images/%s/file' % (
                    uuidsentinel.remote_image),
                headers={'X-Auth-Token': self.context.auth_token})
        mock_gge.assert_called_once_with(self.context, 'RegionTwo', 'public')

    @mock.patch.object(filesystem.Store, 'add')
    @mock.patch('glance.async_.utils.get_glance_endpoint')
    def test_glance_download_failed(self, mock_gge, mock_add):
        mock_gge.return_value = 'https://other.cloud.foo/image'
        glance_download_task = glance_download._DownloadGlanceImage(
            self.context, self.task.task_id, self.task_type,
            self.action_wrapper, ['foo'],
            'RegionTwo', uuidsentinel.remote_image, 'public')
        with mock.patch('urllib.request') as mock_request:
            mock_request.urlopen.side_effect = urllib.error.HTTPError(
                '/file', 400, 'Test Fail', {}, None)
            self.assertRaises(urllib.error.HTTPError,
                              glance_download_task.execute,
                              12345)
            mock_add.assert_not_called()
            mock_request.Request.assert_called_once_with(
                'https://other.cloud.foo/image/v2/images/%s/file' % (
                    uuidsentinel.remote_image),
                headers={'X-Auth-Token': self.context.auth_token})
        mock_gge.assert_called_once_with(self.context, 'RegionTwo', 'public')

    @mock.patch('urllib.request')
    @mock.patch('glance.async_.utils.get_glance_endpoint')
    def test_glance_download_no_glance_endpoint(self, mock_gge, mock_request):
        mock_gge.side_effect = glance.common.exception.GlanceEndpointNotFound(
            region='RegionTwo',
            interface='public')
        glance_download_task = glance_download._DownloadGlanceImage(
            self.context, self.task.task_id, self.task_type,
            self.action_wrapper, ['foo'],
            'RegionTwo', uuidsentinel.remote_image, 'public')
        self.assertRaises(glance.common.exception.GlanceEndpointNotFound,
                          glance_download_task.execute, 12345)
        mock_request.assert_not_called()

    @mock.patch.object(filesystem.Store, 'add')
    @mock.patch('glance.async_.utils.get_glance_endpoint')
    def test_glance_download_size_mismatch(self, mock_gge, mock_add):
        mock_gge.return_value = 'https://other.cloud.foo/image'
        glance_download_task = glance_download._DownloadGlanceImage(
            self.context, self.task.task_id, self.task_type,
            self.action_wrapper, ['foo'],
            'RegionTwo', uuidsentinel.remote_image, 'public')
        with mock.patch('urllib.request') as mock_request:
            mock_add.return_value = ["path", 1]
            self.assertRaises(glance.common.exception.ImportTaskError,
                              glance_download_task.execute, 12345)
            mock_add.assert_called_once_with(
                self.image_id,
                mock_request.urlopen.return_value, 0)
            mock_request.Request.assert_called_once_with(
                'https://other.cloud.foo/image/v2/images/%s/file' % (
                    uuidsentinel.remote_image),
                headers={'X-Auth-Token': self.context.auth_token})
        mock_gge.assert_called_once_with(self.context, 'RegionTwo', 'public')

    @mock.patch('urllib.request')
    @mock.patch('glance.common.utils.validate_import_uri')
    @mock.patch('glance.async_.utils.get_glance_endpoint')
    def test_glance_download_wrong_download_url(self, mock_gge, mock_validate,
                                                mock_request):
        mock_validate.return_value = False
        mock_gge.return_value = 'https://other.cloud.foo/image'
        glance_download_task = glance_download._DownloadGlanceImage(
            self.context, self.task.task_id, self.task_type,
            self.action_wrapper, ['foo'],
            'RegionTwo', uuidsentinel.remote_image, 'public')
        self.assertRaises(glance.common.exception.ImportTaskError,
                          glance_download_task.execute, 12345)
        mock_request.assert_not_called()
        mock_validate.assert_called_once_with(
            'https://other.cloud.foo/image/v2/images/%s/file' % (
                uuidsentinel.remote_image))
