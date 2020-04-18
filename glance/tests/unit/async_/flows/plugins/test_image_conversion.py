# Copyright 2018 RedHat, Inc.
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

import json
import os
from unittest import mock

import glance_store
from oslo_concurrency import processutils
from oslo_config import cfg

import glance.async_.flows.plugins.image_conversion as image_conversion
from glance.common import utils
from glance import domain
from glance import gateway
import glance.tests.utils as test_utils

CONF = cfg.CONF


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestConvertImageTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestConvertImageTask, self).setUp()

        glance_store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")
        self.config(output_format='qcow2',
                    group='image_conversion')
        glance_store.create_stores(CONF)

        self.work_dir = os.path.join(self.test_dir, 'work_dir')
        utils.safe_mkdirs(self.work_dir)
        self.config(work_dir=self.work_dir, group='task')

        self.context = mock.MagicMock()
        self.img_repo = mock.MagicMock()
        self.task_repo = mock.MagicMock()
        self.image_id = UUID1

        self.gateway = gateway.Gateway()
        self.task_factory = domain.TaskFactory()
        self.img_factory = self.gateway.get_image_factory(self.context)
        self.image = self.img_factory.new_image(image_id=self.image_id,
                                                disk_format='raw',
                                                container_format='bare')

        task_input = {
            "import_from": "http://cloud.foo/image.raw",
            "import_from_format": "raw",
            "image_properties": {'disk_format': 'raw',
                                 'container_format': 'bare'}
        }

        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

    @mock.patch.object(os, 'remove')
    def test_image_convert_success(self, mock_os_remove):
        mock_os_remove.return_value = None
        image_convert = image_conversion._ConvertImage(self.context,
                                                       self.task.task_id,
                                                       self.task_type,
                                                       self.img_repo,
                                                       self.image_id)

        self.task_repo.get.return_value = self.task
        image = mock.MagicMock(image_id=self.image_id, virtual_size=None,
                               disk_format='qcow2')
        self.img_repo.get.return_value = image

        with mock.patch.object(processutils, 'execute') as exc_mock:
            exc_mock.return_value = ("", None)
            with mock.patch.object(json, 'loads') as jloads_mock:
                jloads_mock.return_value = {'format': 'raw'}
                image_convert.execute('file:///test/path.raw')

                # NOTE(hemanthm): Asserting that the source format is passed
                # to qemu-utis to avoid inferring the image format. This
                # shields us from an attack vector described at
                # https://bugs.launchpad.net/glance/+bug/1449062/comments/72
                self.assertIn('-f', exc_mock.call_args[0])
                self.assertEqual("qcow2", image.disk_format)

    @mock.patch.object(os, 'remove')
    def test_image_convert_revert_success(self, mock_os_remove):
        mock_os_remove.return_value = None
        image_convert = image_conversion._ConvertImage(self.context,
                                                       self.task.task_id,
                                                       self.task_type,
                                                       self.img_repo,
                                                       self.image_id)

        self.task_repo.get.return_value = self.task

        with mock.patch.object(processutils, 'execute') as exc_mock:
            exc_mock.return_value = ("", None)
            with mock.patch.object(os.path, 'exists') as os_exists_mock:
                os_exists_mock.return_value = True
                image_convert.revert(result=mock.MagicMock())
                self.assertEqual(1, mock_os_remove.call_count)
