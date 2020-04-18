# Copyright 2018 NTT DATA, Inc.
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

import glance_store
from oslo_config import cfg

import glance.async_.flows.plugins.inject_image_metadata as inject_metadata
from glance.common import utils
from glance import domain
from glance import gateway
from glance.tests.unit import utils as test_unit_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestInjectImageMetadataTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestInjectImageMetadataTask, self).setUp()

        glance_store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")
        glance_store.create_stores(CONF)

        self.work_dir = os.path.join(self.test_dir, 'work_dir')
        utils.safe_mkdirs(self.work_dir)
        self.config(work_dir=self.work_dir, group='task')

        self.context = mock.MagicMock()
        self.img_repo = mock.MagicMock()
        self.task_repo = mock.MagicMock()
        self.image_id = mock.MagicMock()

        self.gateway = gateway.Gateway()
        self.task_factory = domain.TaskFactory()
        self.img_factory = self.gateway.get_image_factory(self.context)
        self.image = self.img_factory.new_image(image_id=UUID1,
                                                disk_format='qcow2',
                                                container_format='bare')

        task_input = {
            "import_from": "http://cloud.foo/image.qcow2",
            "import_from_format": "qcow2",
            "image_properties": {'disk_format': 'qcow2',
                                 'container_format': 'bare'}
        }
        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

    def test_inject_image_metadata_using_non_admin_user(self):
        context = test_unit_utils.get_fake_context(roles='member')
        inject_image_metadata = inject_metadata._InjectMetadataProperties(
            context, self.task.task_id, self.task_type, self.img_repo,
            self.image_id)

        self.config(inject={"test": "abc"},
                    group='inject_metadata_properties')

        with mock.patch.object(self.img_repo, 'get') as get_mock:
            image = mock.MagicMock(image_id=self.image_id,
                                   extra_properties={"test": "abc"})
            get_mock.return_value = image

            with mock.patch.object(self.img_repo, 'save') as save_mock:
                inject_image_metadata.execute()
                get_mock.assert_called_once_with(self.image_id)
                save_mock.assert_called_once_with(image)
                self.assertEqual({"test": "abc"}, image.extra_properties)

    def test_inject_image_metadata_using_admin_user(self):
        context = test_unit_utils.get_fake_context(roles='admin')
        inject_image_metadata = inject_metadata._InjectMetadataProperties(
            context, self.task.task_id, self.task_type, self.img_repo,
            self.image_id)

        self.config(inject={"test": "abc"},
                    group='inject_metadata_properties')

        inject_image_metadata.execute()

        with mock.patch.object(self.img_repo, 'get') as get_mock:
            get_mock.assert_not_called()

        with mock.patch.object(self.img_repo, 'save') as save_mock:
            save_mock.assert_not_called()

    def test_inject_image_metadata_empty(self):
        context = test_unit_utils.get_fake_context(roles='member')
        inject_image_metadata = inject_metadata._InjectMetadataProperties(
            context, self.task.task_id, self.task_type, self.img_repo,
            self.image_id)

        self.config(inject={}, group='inject_metadata_properties')

        inject_image_metadata.execute()

        with mock.patch.object(self.img_repo, 'get') as get_mock:
            get_mock.assert_not_called()

        with mock.patch.object(self.img_repo, 'save') as save_mock:
            save_mock.assert_not_called()
