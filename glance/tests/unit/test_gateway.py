# Copyright 2020 Red Hat, Inc.
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

from glance import gateway
import glance.tests.utils as test_utils


class TestGateway(test_utils.BaseTestCase):
    def setUp(self):
        super(TestGateway, self).setUp()
        self.gateway = gateway.Gateway()
        self.context = mock.sentinel.context

    @mock.patch('glance.domain.TaskExecutorFactory')
    def test_get_task_executor_factory(self, mock_factory):
        @mock.patch.object(self.gateway, 'get_task_repo')
        @mock.patch.object(self.gateway, 'get_repo')
        @mock.patch.object(self.gateway, 'get_image_factory')
        def _test(mock_gif, mock_gr, mock_gtr):
            self.gateway.get_task_executor_factory(self.context)
            mock_gtr.assert_called_once_with(self.context)
            mock_gr.assert_called_once_with(self.context)
            mock_gif.assert_called_once_with(self.context)
            mock_factory.assert_called_once_with(
                mock_gtr.return_value,
                mock_gr.return_value,
                mock_gif.return_value,
                admin_repo=None)

        _test()

    @mock.patch('glance.domain.TaskExecutorFactory')
    def test_get_task_executor_factory_with_admin(self, mock_factory):
        @mock.patch.object(self.gateway, 'get_task_repo')
        @mock.patch.object(self.gateway, 'get_repo')
        @mock.patch.object(self.gateway, 'get_image_factory')
        def _test(mock_gif, mock_gr, mock_gtr):
            mock_gr.side_effect = [mock.sentinel.image_repo,
                                   mock.sentinel.admin_repo]
            self.gateway.get_task_executor_factory(
                self.context,
                admin_context=mock.sentinel.admin_context)
            mock_gtr.assert_called_once_with(self.context)
            mock_gr.assert_has_calls([
                mock.call(self.context),
                mock.call(mock.sentinel.admin_context),
            ])
            mock_gif.assert_called_once_with(self.context)
            mock_factory.assert_called_once_with(
                mock_gtr.return_value,
                mock.sentinel.image_repo,
                mock_gif.return_value,
                admin_repo=mock.sentinel.admin_repo)

        _test()
