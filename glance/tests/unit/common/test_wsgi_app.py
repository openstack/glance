# -*- coding: utf-8 -*-
# Copyright 2020, Red Hat, Inc.
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

from glance.api import common
from glance.common import wsgi_app
from glance.tests import utils as test_utils


class TestWsgiAppInit(test_utils.BaseTestCase):
    @mock.patch('glance.common.config.load_paste_app')
    @mock.patch('glance.async_.set_threadpool_model')
    @mock.patch('glance.common.wsgi_app._get_config_files')
    def test_wsgi_init_sets_thread_settings(self, mock_config_files,
                                            mock_set_model,
                                            mock_load):
        mock_config_files.return_value = []
        self.config(task_pool_threads=123, group='wsgi')
        common.DEFAULT_POOL_SIZE = 1024
        wsgi_app.init_app()
        # Make sure we declared the system threadpool model as native
        mock_set_model.assert_called_once_with('native')
        # Make sure we set the default pool size
        self.assertEqual(123, common.DEFAULT_POOL_SIZE)
        mock_load.assert_called_once_with('glance-api')
