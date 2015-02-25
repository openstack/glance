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

import json
import mock
import os
import StringIO

import glance_store
from oslo_concurrency import processutils
from oslo_config import cfg

from glance.async.flows import convert
from glance.async import taskflow_executor
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
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
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

    def test_convert_success(self):
        image_convert = convert._Convert(self.task.task_id,
                                         self.task_type,
                                         self.img_repo)

        self.task_repo.get.return_value = self.task
        image_id = mock.sentinel.image_id
        image = mock.MagicMock(image_id=image_id, virtual_size=None)
        self.img_repo.get.return_value = image

        with mock.patch.object(processutils, 'execute') as exc_mock:
            exc_mock.return_value = ("", None)
            image_convert.execute(image, '/test/path.raw')

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

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = StringIO.StringIO("TEST_IMAGE")

            with mock.patch.object(processutils, 'execute') as exc_mock:
                result = json.dumps({
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
                })

                # NOTE(flaper87): First result for the conversion step and
                # the second one for the introspection one. The later *must*
                # come after the former. If not, the current builtin flow
                # process will be unsound.
                # Follow-up work will fix this by having a better way to handle
                # task's dependencies and activation.
                exc_mock.side_effect = [("", None), (result, None)]
                executor.begin_processing(self.task.task_id)
                image_path = os.path.join(self.test_dir, image.image_id)
                tmp_image_path = "%s.tasks_import" % image_path
                self.assertFalse(os.path.exists(tmp_image_path))
                self.assertTrue(os.path.exists(image_path))
                self.assertEqual('qcow2', image.disk_format)
                self.assertEqual(10737418240, image.virtual_size)
