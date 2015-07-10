# Copyright 2015 OpenStack Foundation
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

import glance_store
from oslo_config import cfg
from taskflow import engines

from glance.async import taskflow_executor
from glance import domain
import glance.tests.utils as test_utils


CONF = cfg.CONF
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestTaskExecutor(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTaskExecutor, self).setUp()

        glance_store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")
        glance_store.create_stores(CONF)

        self.config(engine_mode='serial',
                    group='taskflow_executor')

        self.context = mock.Mock()
        self.task_repo = mock.Mock()
        self.image_repo = mock.Mock()
        self.image_factory = mock.Mock()

        task_input = {
            "import_from": "http://cloud.foo/image.qcow2",
            "import_from_format": "qcow2",
            "image_properties": {'disk_format': 'qcow2',
                                 'container_format': 'bare'}
        }
        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        self.task_factory = domain.TaskFactory()
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

        self.executor = taskflow_executor.TaskExecutor(
            self.context,
            self.task_repo,
            self.image_repo,
            self.image_factory)

    def test_begin_processing(self):
        with mock.patch.object(engines, 'load') as load_mock:
            engine = mock.Mock()
            load_mock.return_value = engine
            self.task_repo.get.return_value = self.task
            self.executor.begin_processing(self.task.task_id)

        # assert the call
        self.assertEqual(1, load_mock.call_count)
        self.assertEqual(1, engine.run.call_count)

    def test_task_fail(self):
        with mock.patch.object(engines, 'load') as load_mock:
            engine = mock.Mock()
            load_mock.return_value = engine
            engine.run.side_effect = RuntimeError
            self.task_repo.get.return_value = self.task
            self.assertRaises(RuntimeError, self.executor.begin_processing,
                              self.task.task_id)
        self.assertEqual('failure', self.task.status)
        self.task_repo.save.assert_called_with(self.task)
