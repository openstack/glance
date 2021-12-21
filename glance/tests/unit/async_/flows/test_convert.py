# Copyright 2015 Red Hat, Inc.
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

import io
import json
import os
from unittest import mock

import glance_store
from oslo_concurrency import processutils
from oslo_config import cfg

from glance.async_.flows import convert
from glance.async_ import taskflow_executor
from glance.common.scripts import utils as script_utils
from glance.common import utils
from glance import domain
from glance import gateway
import glance.tests.utils as test_utils

CONF = cfg.CONF

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestImportTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportTask, self).setUp()
        self.work_dir = os.path.join(self.test_dir, 'work_dir')
        utils.safe_mkdirs(self.work_dir)
        self.config(work_dir=self.work_dir, group='task')

        self.context = mock.MagicMock()
        self.img_repo = mock.MagicMock()
        self.task_repo = mock.MagicMock()

        self.gateway = gateway.Gateway()
        self.task_factory = domain.TaskFactory()
        self.img_factory = self.gateway.get_image_factory(self.context)
        self.image = self.img_factory.new_image(image_id=UUID1,
                                                disk_format='raw',
                                                container_format='bare')

        task_input = {
            "import_from": "http://cloud.foo/image.raw",
            "import_from_format": "raw",
            "image_properties": {'disk_format': 'qcow2',
                                 'container_format': 'bare'}
        }
        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        request_id = 'fake_request_id'
        user_id = 'fake_user'
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               UUID1, user_id, request_id,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

        glance_store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        self.config(conversion_format='qcow2',
                    group='taskflow_executor')
        glance_store.create_stores(CONF)

    @mock.patch.object(os, 'unlink')
    def test_convert_success(self, mock_unlink):
        image_convert = convert._Convert(self.task.task_id,
                                         self.task_type,
                                         self.img_repo)

        self.task_repo.get.return_value = self.task
        image_id = mock.sentinel.image_id
        image = mock.MagicMock(image_id=image_id, virtual_size=None)
        self.img_repo.get.return_value = image

        with mock.patch.object(processutils, 'execute') as exc_mock:
            exc_mock.return_value = ("", None)
            with mock.patch.object(os, 'rename') as rm_mock:
                rm_mock.return_value = None
                image_convert.execute(image, 'file:///test/path.raw')

                # NOTE(hemanthm): Asserting that the source format is passed
                # to qemu-utis to avoid inferring the image format. This
                # shields us from an attack vector described at
                # https://bugs.launchpad.net/glance/+bug/1449062/comments/72
                self.assertIn('-f', exc_mock.call_args[0])

    def test_convert_revert_success(self):
        image_convert = convert._Convert(self.task.task_id,
                                         self.task_type,
                                         self.img_repo)

        self.task_repo.get.return_value = self.task
        image_id = mock.sentinel.image_id
        image = mock.MagicMock(image_id=image_id, virtual_size=None)
        self.img_repo.get.return_value = image

        with mock.patch.object(processutils, 'execute') as exc_mock:
            exc_mock.return_value = ("", None)
            with mock.patch.object(os, 'remove') as rmtree_mock:
                rmtree_mock.return_value = None
                image_convert.revert(image, 'file:///tmp/test')

    def test_import_flow_with_convert_and_introspect(self):
        self.config(engine_mode='serial',
                    group='taskflow_executor')

        image = self.img_factory.new_image(image_id=UUID1,
                                           disk_format='raw',
                                           container_format='bare')

        img_factory = mock.MagicMock()

        executor = taskflow_executor.TaskExecutor(
            self.context,
            self.task_repo,
            self.img_repo,
            img_factory)

        self.task_repo.get.return_value = self.task

        def create_image(*args, **kwargs):
            kwargs['image_id'] = UUID1
            return self.img_factory.new_image(*args, **kwargs)

        self.img_repo.get.return_value = image
        img_factory.new_image.side_effect = create_image

        image_path = os.path.join(self.work_dir, image.image_id)

        def fake_execute(*args, **kwargs):
            if 'info' in args:
                # NOTE(flaper87): Make sure the file actually
                # exists. Extra check to verify previous tasks did
                # what they were supposed to do.
                assert os.path.exists(args[3].split("file://")[-1])

                return (json.dumps({
                    "virtual-size": 10737418240,
                    "filename": "/tmp/image.qcow2",
                    "cluster-size": 65536,
                    "format": "qcow2",
                    "actual-size": 373030912,
                    "format-specific": {
                        "type": "qcow2",
                        "data": {
                            "compat": "0.10"
                        }
                    },
                    "dirty-flag": False
                }), None)

            open("%s.converted" % image_path, 'a').close()
            return ("", None)

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = io.BytesIO(b"TEST_IMAGE")

            with mock.patch.object(processutils, 'execute') as exc_mock:
                exc_mock.side_effect = fake_execute
                executor.begin_processing(self.task.task_id)

                # NOTE(flaper87): DeleteFromFS should've deleted this
                # file. Make sure it doesn't exist.
                self.assertFalse(os.path.exists(image_path))

                # NOTE(flaper87): Workdir should be empty after all
                # the tasks have been executed.
                self.assertEqual([], os.listdir(self.work_dir))
                self.assertEqual('qcow2', image.disk_format)
                self.assertEqual(10737418240, image.virtual_size)

                # NOTE(hemanthm): Asserting that the source format is passed
                # to qemu-utis to avoid inferring the image format when
                # converting. This shields us from an attack vector described
                # at https://bugs.launchpad.net/glance/+bug/1449062/comments/72
                #
                # A total of three calls will be made to 'execute': 'info',
                # 'convert' and 'info' towards introspection, conversion and
                # OVF packaging respectively. We care about the 'convert' call
                # here, hence we fetch the 2nd set of args from the args list.
                convert_call_args, _ = exc_mock.call_args_list[1]
                self.assertIn('-f', convert_call_args)
