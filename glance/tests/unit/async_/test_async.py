# Copyright 2014 OpenStack Foundation
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

import futurist
import glance_store as store
from oslo_config import cfg
from taskflow.patterns import linear_flow

import glance.async_
from glance.async_.flows import api_image_import
import glance.tests.utils as test_utils

CONF = cfg.CONF


class TestTaskExecutor(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTaskExecutor, self).setUp()
        self.context = mock.Mock()
        self.task_repo = mock.Mock()
        self.image_repo = mock.Mock()
        self.image_factory = mock.Mock()
        self.executor = glance.async_.TaskExecutor(self.context,
                                                   self.task_repo,
                                                   self.image_repo,
                                                   self.image_factory)

    def test_begin_processing(self):
        # setup
        task_id = mock.ANY
        task_type = mock.ANY
        task = mock.Mock()

        with mock.patch.object(
                glance.async_.TaskExecutor,
                '_run') as mock_run:
            self.task_repo.get.return_value = task
            self.executor.begin_processing(task_id)

        # assert the call
        mock_run.assert_called_once_with(task_id, task_type)

    def test_with_admin_repo(self):
        admin_repo = mock.MagicMock()
        executor = glance.async_.TaskExecutor(self.context,
                                              self.task_repo,
                                              self.image_repo,
                                              self.image_factory,
                                              admin_repo=admin_repo)
        self.assertEqual(admin_repo, executor.admin_repo)


class TestImportTaskFlow(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportTaskFlow, self).setUp()
        store.register_opts(CONF)
        self.config(default_store='file',
                    stores=['file', 'http'],
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")
        self.config(enabled_import_methods=[
            'glance-direct', 'web-download', 'copy-image'])
        self.config(node_staging_uri='file:///tmp/staging')
        store.create_stores(CONF)
        self.base_flow = ['ImageLock', 'ConfigureStaging', 'ImportToStore',
                          'DeleteFromFS', 'VerifyImageState',
                          'CompleteTask']
        self.import_plugins = ['Convert_Image',
                               'Decompress_Image',
                               'InjectMetadataProperties']

    def _get_flow(self, import_req=None):
        inputs = {
            'task_id': mock.sentinel.task_id,
            'task_type': mock.MagicMock(),
            'task_repo': mock.MagicMock(),
            'image_repo': mock.MagicMock(),
            'image_id': mock.MagicMock(),
            'import_req': import_req or mock.MagicMock(),
            'context': mock.MagicMock(),
        }
        inputs['image_repo'].get.return_value = mock.MagicMock(
            extra_properties={'os_glance_import_task': mock.sentinel.task_id})
        flow = api_image_import.get_flow(**inputs)
        return flow

    def _get_flow_tasks(self, flow):
        flow_comp = []
        for c, p in flow.iter_nodes():
            if isinstance(c, linear_flow.Flow):
                flow_comp += self._get_flow_tasks(c)
            else:
                name = str(c).split('-')
                if len(name) > 1:
                    flow_comp.append(name[1])
        return flow_comp

    def test_get_default_flow(self):
        # This test will ensure that without import plugins
        # and without internal plugins flow builds with the
        # base_flow components
        flow = self._get_flow()

        flow_comp = self._get_flow_tasks(flow)
        # assert flow has all the tasks
        self.assertEqual(len(self.base_flow), len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)

    def test_get_flow_web_download_enabled(self):
        # This test will ensure that without import plugins
        # and with web-download plugin flow builds with
        # base_flow components and '_WebDownload'
        import_req = {
            'method': {
                'name': 'web-download',
                'uri': 'http://cloud.foo/image.qcow2'
            }
        }

        flow = self._get_flow(import_req=import_req)

        flow_comp = self._get_flow_tasks(flow)
        # assert flow has all the tasks
        self.assertEqual(len(self.base_flow) + 1, len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)
        self.assertIn('WebDownload', flow_comp)

    @mock.patch.object(store, 'get_store_from_store_identifier')
    def test_get_flow_copy_image_enabled(self, mock_store):
        # This test will ensure that without import plugins
        # and with copy-image plugin flow builds with
        # base_flow components and '_CopyImage'
        import_req = {
            'method': {
                'name': 'copy-image',
                'stores': ['fake-store']
            }
        }

        mock_store.return_value = mock.Mock()
        flow = self._get_flow(import_req=import_req)

        flow_comp = self._get_flow_tasks(flow)
        # assert flow has all the tasks
        self.assertEqual(len(self.base_flow) + 1, len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)
        self.assertIn('CopyImage', flow_comp)

    def test_get_flow_with_all_plugins_enabled(self):
        # This test will ensure that flow includes import plugins
        # and base flow
        self.config(image_import_plugins=['image_conversion',
                                          'image_decompression',
                                          'inject_image_metadata'],
                    group='image_import_opts')

        flow = self._get_flow()

        flow_comp = self._get_flow_tasks(flow)
        # assert flow has all the tasks (base_flow + plugins)
        plugins = CONF.image_import_opts.image_import_plugins
        self.assertEqual(len(self.base_flow) + len(plugins), len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)
        for c in self.import_plugins:
            self.assertIn(c, flow_comp)

    @mock.patch.object(store, 'get_store_from_store_identifier')
    def test_get_flow_copy_image_not_includes_import_plugins(
            self, mock_store):
        # This test will ensure that flow does not includes import
        # plugins as import method is copy image
        self.config(image_import_plugins=['image_conversion',
                                          'image_decompression',
                                          'inject_image_metadata'],
                    group='image_import_opts')

        mock_store.return_value = mock.Mock()
        import_req = {
            'method': {
                'name': 'copy-image',
                'stores': ['fake-store']
            }
        }

        flow = self._get_flow(import_req=import_req)

        flow_comp = self._get_flow_tasks(flow)
        # assert flow has all the tasks (just base and conversion)
        self.assertEqual(len(self.base_flow) + 1, len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)
        self.assertIn('CopyImage', flow_comp)


@mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
class TestSystemThreadPoolModel(test_utils.BaseTestCase):
    def test_eventlet_model(self):
        model_cls = glance.async_.EventletThreadPoolModel
        self.assertEqual(futurist.GreenThreadPoolExecutor,
                         model_cls.get_threadpool_executor_class())

    def test_native_model(self):
        model_cls = glance.async_.NativeThreadPoolModel
        self.assertEqual(futurist.ThreadPoolExecutor,
                         model_cls.get_threadpool_executor_class())

    @mock.patch('glance.async_.ThreadPoolModel.get_threadpool_executor_class')
    def test_base_model_spawn(self, mock_gte):
        pool_cls = mock.MagicMock()
        pool_cls.configure_mock(__name__='fake')
        mock_gte.return_value = pool_cls

        model = glance.async_.ThreadPoolModel()
        result = model.spawn(print, 'foo', bar='baz')

        pool = pool_cls.return_value

        # Make sure the default size was passed to the executor
        pool_cls.assert_called_once_with(1)

        # Make sure we submitted the function to the executor
        pool.submit.assert_called_once_with(print, 'foo', bar='baz')

        # This isn't used anywhere, but make sure we get the future
        self.assertEqual(pool.submit.return_value, result)

    def test_model_map(self):
        model = glance.async_.EventletThreadPoolModel()
        results = model.map(lambda s: s.upper(), ['a', 'b', 'c'])
        self.assertEqual(['A', 'B', 'C'], list(results))

    @mock.patch('glance.async_.ThreadPoolModel.get_threadpool_executor_class')
    def test_base_model_init_with_size(self, mock_gte):
        mock_gte.return_value.__name__ = 'TestModel'
        with mock.patch.object(glance.async_, 'LOG') as mock_log:
            glance.async_.ThreadPoolModel(123)
            mock_log.debug.assert_called_once_with(
                'Creating threadpool model %r with size %i',
                'TestModel', 123)
        mock_gte.return_value.assert_called_once_with(123)

    def test_set_threadpool_model_native(self):
        glance.async_.set_threadpool_model('native')
        self.assertEqual(glance.async_.NativeThreadPoolModel,
                         glance.async_._THREADPOOL_MODEL)

    def test_set_threadpool_model_eventlet(self):
        glance.async_.set_threadpool_model('eventlet')
        self.assertEqual(glance.async_.EventletThreadPoolModel,
                         glance.async_._THREADPOOL_MODEL)

    def test_set_threadpool_model_unknown(self):
        # Unknown threadpool models are not tolerated
        self.assertRaises(RuntimeError,
                          glance.async_.set_threadpool_model,
                          'danthread9000')

    def test_set_threadpool_model_again(self):
        # Setting the model to the same thing is fine
        glance.async_.set_threadpool_model('native')
        glance.async_.set_threadpool_model('native')

    def test_set_threadpool_model_different(self):
        glance.async_.set_threadpool_model('native')
        # The model cannot be switched at runtime
        self.assertRaises(RuntimeError,
                          glance.async_.set_threadpool_model,
                          'eventlet')

    def test_set_threadpool_model_log(self):
        with mock.patch.object(glance.async_, 'LOG') as mock_log:
            glance.async_.set_threadpool_model('eventlet')
            mock_log.info.assert_called_once_with(
                'Threadpool model set to %r', 'EventletThreadPoolModel')

    def test_get_threadpool_model(self):
        glance.async_.set_threadpool_model('native')
        self.assertEqual(glance.async_.NativeThreadPoolModel,
                         glance.async_.get_threadpool_model())

    def test_get_threadpool_model_unset(self):
        # If the model is not set, we get an AssertionError
        self.assertRaises(AssertionError,
                          glance.async_.get_threadpool_model)
