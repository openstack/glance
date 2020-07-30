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
        self.base_flow = ['ConfigureStaging', 'ImportToStore',
                          'DeleteFromFS', 'VerifyImageState',
                          'CompleteTask']
        self.import_plugins = ['Convert_Image',
                               'Decompress_Image',
                               'InjectMetadataProperties']

    def _get_flow(self, import_req=None):
        inputs = {
            'task_id': mock.MagicMock(),
            'task_type': mock.MagicMock(),
            'task_repo': mock.MagicMock(),
            'image_repo': mock.MagicMock(),
            'image_id': mock.MagicMock(),
            'import_req': import_req or mock.MagicMock()
        }
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
        # assert flow has 5 tasks
        self.assertEqual(5, len(flow_comp))
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
        # assert flow has 6 tasks
        self.assertEqual(6, len(flow_comp))
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
        # assert flow has 6 tasks
        self.assertEqual(6, len(flow_comp))
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
        # assert flow has 8 tasks (base_flow + plugins)
        self.assertEqual(8, len(flow_comp))
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
        # assert flow has 6 tasks
        self.assertEqual(6, len(flow_comp))
        for c in self.base_flow:
            self.assertIn(c, flow_comp)
        self.assertIn('CopyImage', flow_comp)
