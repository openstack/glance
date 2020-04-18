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
import os
from unittest import mock

import glance_store
from oslo_concurrency import processutils as putils
from oslo_config import cfg
import six
from six.moves import urllib
from taskflow import task
from taskflow.types import failure

import glance.async_.flows.base_import as import_flow
from glance.async_ import taskflow_executor
from glance.async_ import utils as async_utils
from glance.common.scripts.image_import import main as image_import
from glance.common.scripts import utils as script_utils
from glance.common import utils
from glance import context
from glance import domain
from glance import gateway
import glance.tests.utils as test_utils

CONF = cfg.CONF

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class _ErrorTask(task.Task):

    def execute(self):
        raise RuntimeError()


class TestImportTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportTask, self).setUp()

        glance_store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")
        glance_store.create_stores(CONF)

        self.work_dir = os.path.join(self.test_dir, 'work_dir')
        utils.safe_mkdirs(self.work_dir)
        self.config(work_dir=self.work_dir, group='task')

        self.context = context.RequestContext(
            user_id=TENANT1, project_id=TENANT1, overwrite=False
        )
        self.img_repo = mock.MagicMock()
        self.task_repo = mock.MagicMock()

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

    def _assert_qemu_process_limits(self, exec_mock):
        # NOTE(hemanthm): Assert that process limits are being applied
        # on "qemu-img info" calls. See bug #1449062 for more details.
        kw_args = exec_mock.call_args[1]
        self.assertIn('prlimit', kw_args)
        self.assertEqual(async_utils.QEMU_IMG_PROC_LIMITS,
                         kw_args.get('prlimit'))

    def test_import_flow(self):
        self.config(engine_mode='serial',
                    group='taskflow_executor')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = six.BytesIO(b"TEST_IMAGE")

            with mock.patch.object(putils, 'trycmd') as tmock:
                tmock.return_value = (json.dumps({
                    'format': 'qcow2',
                }), None)

                executor.begin_processing(self.task.task_id)
                image_path = os.path.join(self.test_dir, self.image.image_id)
                tmp_image_path = os.path.join(self.work_dir,
                                              "%s.tasks_import" % image_path)

                self.assertFalse(os.path.exists(tmp_image_path))
                self.assertTrue(os.path.exists(image_path))
                self.assertEqual(1, len(list(self.image.locations)))
                self.assertEqual("file://%s%s%s" % (self.test_dir, os.sep,
                                                    self.image.image_id),
                                 self.image.locations[0]['url'])

                self._assert_qemu_process_limits(tmock)

    def test_import_flow_missing_work_dir(self):
        self.config(engine_mode='serial', group='taskflow_executor')
        self.config(work_dir=None, group='task')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = six.BytesIO(b"TEST_IMAGE")

            with mock.patch.object(import_flow._ImportToFS, 'execute') as emk:
                executor.begin_processing(self.task.task_id)
                self.assertFalse(emk.called)

                image_path = os.path.join(self.test_dir, self.image.image_id)
                tmp_image_path = os.path.join(self.work_dir,
                                              "%s.tasks_import" % image_path)
                self.assertFalse(os.path.exists(tmp_image_path))
                self.assertTrue(os.path.exists(image_path))

    def test_import_flow_revert_import_to_fs(self):
        self.config(engine_mode='serial', group='taskflow_executor')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.side_effect = RuntimeError

            with mock.patch.object(import_flow._ImportToFS, 'revert') as rmock:
                self.assertRaises(RuntimeError,
                                  executor.begin_processing, self.task.task_id)
                self.assertTrue(rmock.called)
                self.assertIsInstance(rmock.call_args[1]['result'],
                                      failure.Failure)

                image_path = os.path.join(self.test_dir, self.image.image_id)
                tmp_image_path = os.path.join(self.work_dir,
                                              "%s.tasks_import" % image_path)
                self.assertFalse(os.path.exists(tmp_image_path))
                # Note(sabari): The image should not have been uploaded to
                # the store as the flow failed before ImportToStore Task.
                self.assertFalse(os.path.exists(image_path))

    def test_import_flow_backed_file_import_to_fs(self):
        self.config(engine_mode='serial', group='taskflow_executor')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = six.BytesIO(b"TEST_IMAGE")

            with mock.patch.object(putils, 'trycmd') as tmock:
                tmock.return_value = (json.dumps({
                    'backing-filename': '/etc/password'
                }), None)

                with mock.patch.object(import_flow._ImportToFS,
                                       'revert') as rmock:
                    self.assertRaises(RuntimeError,
                                      executor.begin_processing,
                                      self.task.task_id)
                    self.assertTrue(rmock.called)
                    self.assertIsInstance(rmock.call_args[1]['result'],
                                          failure.Failure)
                    self._assert_qemu_process_limits(tmock)

                    image_path = os.path.join(self.test_dir,
                                              self.image.image_id)

                    fname = "%s.tasks_import" % image_path
                    tmp_image_path = os.path.join(self.work_dir, fname)

                    self.assertFalse(os.path.exists(tmp_image_path))
                    # Note(sabari): The image should not have been uploaded to
                    # the store as the flow failed before ImportToStore Task.
                    self.assertFalse(os.path.exists(image_path))

    def test_import_flow_revert(self):
        self.config(engine_mode='serial',
                    group='taskflow_executor')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            dmock.return_value = six.BytesIO(b"TEST_IMAGE")

            with mock.patch.object(putils, 'trycmd') as tmock:
                tmock.return_value = (json.dumps({
                    'format': 'qcow2',
                }), None)

                with mock.patch.object(import_flow,
                                       "_get_import_flows") as imock:
                    imock.return_value = (x for x in [_ErrorTask()])
                    self.assertRaises(RuntimeError,
                                      executor.begin_processing,
                                      self.task.task_id)

                    self._assert_qemu_process_limits(tmock)

                    image_path = os.path.join(self.test_dir,
                                              self.image.image_id)
                    tmp_image_path = os.path.join(self.work_dir,
                                                  ("%s.tasks_import" %
                                                   image_path))
                    self.assertFalse(os.path.exists(tmp_image_path))

                    # NOTE(flaper87): Eventually, we want this to be assertTrue
                    # The current issue is there's no way to tell taskflow to
                    # continue on failures. That is, revert the subflow but
                    # keep executing the parent flow. Under
                    # discussion/development.
                    self.assertFalse(os.path.exists(image_path))

    def test_import_flow_no_import_flows(self):
        self.config(engine_mode='serial',
                    group='taskflow_executor')

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

        self.img_repo.get.return_value = self.image
        img_factory.new_image.side_effect = create_image

        with mock.patch.object(urllib.request, 'urlopen') as umock:
            content = b"TEST_IMAGE"
            umock.return_value = six.BytesIO(content)

            with mock.patch.object(import_flow, "_get_import_flows") as imock:
                imock.return_value = (x for x in [])
                executor.begin_processing(self.task.task_id)
                image_path = os.path.join(self.test_dir, self.image.image_id)
                tmp_image_path = os.path.join(self.work_dir,
                                              "%s.tasks_import" % image_path)
                self.assertFalse(os.path.exists(tmp_image_path))
                self.assertTrue(os.path.exists(image_path))
                self.assertEqual(1, umock.call_count)

                with open(image_path, 'rb') as ifile:
                    self.assertEqual(content, ifile.read())

    def test_create_image(self):
        image_create = import_flow._CreateImage(self.task.task_id,
                                                self.task_type,
                                                self.task_repo,
                                                self.img_repo,
                                                self.img_factory)

        self.task_repo.get.return_value = self.task
        with mock.patch.object(image_import, 'create_image') as ci_mock:
            ci_mock.return_value = mock.Mock()
            image_create.execute()

            ci_mock.assert_called_once_with(self.img_repo,
                                            self.img_factory,
                                            {'container_format': 'bare',
                                             'disk_format': 'qcow2'},
                                            self.task.task_id)

    def test_save_image(self):
        save_image = import_flow._SaveImage(self.task.task_id,
                                            self.task_type,
                                            self.img_repo)

        with mock.patch.object(self.img_repo, 'get') as get_mock:
            image_id = mock.sentinel.image_id
            image = mock.MagicMock(image_id=image_id, status='saving')
            get_mock.return_value = image

            with mock.patch.object(self.img_repo, 'save') as save_mock:
                save_image.execute(image.image_id)
                get_mock.assert_called_once_with(image_id)
                save_mock.assert_called_once_with(image)
                self.assertEqual('active', image.status)

    def test_import_to_fs(self):
        import_fs = import_flow._ImportToFS(self.task.task_id,
                                            self.task_type,
                                            self.task_repo,
                                            'http://example.com/image.qcow2')

        with mock.patch.object(script_utils, 'get_image_data_iter') as dmock:
            content = b"test"
            dmock.return_value = [content]

            with mock.patch.object(putils, 'trycmd') as tmock:
                tmock.return_value = (json.dumps({
                    'format': 'qcow2',
                }), None)

                image_id = UUID1
                path = import_fs.execute(image_id)
                reader, size = glance_store.get_from_backend(path)
                self.assertEqual(4, size)
                self.assertEqual(content, b"".join(reader))

                image_path = os.path.join(self.work_dir, image_id)
                tmp_image_path = os.path.join(self.work_dir, image_path)
                self.assertTrue(os.path.exists(tmp_image_path))
                self._assert_qemu_process_limits(tmock)

    def test_delete_from_fs(self):
        delete_fs = import_flow._DeleteFromFS(self.task.task_id,
                                              self.task_type)

        data = [b"test"]

        store = glance_store.get_store_from_scheme('file')
        path = glance_store.store_add_to_backend(mock.sentinel.image_id, data,
                                                 mock.sentinel.image_size,
                                                 store, context=None)[0]

        path_wo_scheme = path.split("file://")[1]
        self.assertTrue(os.path.exists(path_wo_scheme))
        delete_fs.execute(path)
        self.assertFalse(os.path.exists(path_wo_scheme))

    def test_complete_task(self):
        complete_task = import_flow._CompleteTask(self.task.task_id,
                                                  self.task_type,
                                                  self.task_repo)

        image_id = mock.sentinel.image_id
        image = mock.MagicMock(image_id=image_id)

        self.task_repo.get.return_value = self.task
        with mock.patch.object(self.task, 'succeed') as succeed:
            complete_task.execute(image.image_id)
            succeed.assert_called_once_with({'image_id': image_id})
