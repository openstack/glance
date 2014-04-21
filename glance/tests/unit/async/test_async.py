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


import mock

import glance.async
import glance.tests.utils as test_utils


class TestTaskExecutor(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTaskExecutor, self).setUp()
        self.context = mock.Mock()
        self.task_repo = mock.Mock()
        self.image_repo = mock.Mock()
        self.image_factory = mock.Mock()
        self.executor = glance.async.TaskExecutor(self.context,
                                                  self.task_repo,
                                                  self.image_repo,
                                                  self.image_factory)

    def test_begin_processing(self):
        # setup
        task_id = mock.ANY
        task_type = mock.ANY
        task = mock.Mock()

        with mock.patch.object(
                glance.async.TaskExecutor,
                '_run') as mock_run:
            self.task_repo.get.return_value = task
            self.executor.begin_processing(task_id)

        # assert the call
        mock_run.assert_called_once_with(task_id, task_type)
