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

import mock

from glance_store._drivers import filesystem
from glance_store import backend
from oslo_config import cfg

import glance.async.flows._internal_plugins.web_download as web_download
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
            mock_iter.return_value = b"dddd"
            web_download_task.execute()
            mock_add.assert_called_once_with(self.image_id, b"dddd", 0)

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
