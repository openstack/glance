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

import glance.common.scripts as scripts
from glance.common.scripts.image_import import main as image_import
import glance.tests.utils as test_utils


class TestScripts(test_utils.BaseTestCase):

    def setUp(self):
        super(TestScripts, self).setUp()

    def test_run_task(self):
        task_id = mock.ANY
        task_type = 'import'
        context = mock.ANY
        task_repo = mock.ANY
        image_repo = mock.ANY
        image_factory = mock.ANY

        with mock.patch.object(image_import, 'run') as mock_run:
            scripts.run_task(task_id, task_type, context, task_repo,
                             image_repo, image_factory)

        mock_run.assert_called_once_with(task_id, context, task_repo,
                                         image_repo, image_factory)
