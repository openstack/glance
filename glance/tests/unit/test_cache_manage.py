# Copyright 2020 Red Hat Inc.
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
import sys
from unittest import mock

import fixtures

from glance.cmd import cache_manage
from glance.image_cache import client as cache_client
from glance.tests import utils as test_utils


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class TestCacheManage(test_utils.BaseTestCase):

    def setUp(self):
        super(TestCacheManage, self).setUp()

    def _main_test_helper(self, argv, result=cache_manage.SUCCESS):
        self.useFixture(fixtures.MonkeyPatch('sys.argv', argv))
        with mock.patch.object(cache_client, 'get_client'):
            with mock.patch.object(sys, 'exit') as mock_exit:
                cache_manage.main()
            mock_exit.assert_called_once_with(result)

    def test_list_cached_images(self):
        self._main_test_helper(['glance.cmd.cache_manage', 'list-cached'])

    def test_list_queued_images(self):
        self._main_test_helper(['glance.cmd.cache_manage', 'list-queued'])

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_queue_image(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'queue-image', UUID1])
        self.assertEqual(1, mock_user_confirm.call_count)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_queue_image_invalid_image_id(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage', 'queue-image',
                                'fake_id'],
                               result=cache_manage.FAILURE)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_queued_image(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-queued-image', UUID1])
        self.assertEqual(1, mock_user_confirm.call_count)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_queued_image_invalid_image_id(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-queued-image',
                                'fake_id'],
                               result=cache_manage.FAILURE)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_cached_image(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-cached-image', UUID1])
        self.assertEqual(1, mock_user_confirm.call_count)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_cached_image_invalid_image_id(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-cached-image',
                                'fake_id'],
                               result=cache_manage.FAILURE)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_all_queued_image(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-all-queued-images'])
        self.assertEqual(1, mock_user_confirm.call_count)

    @mock.patch.object(cache_manage, 'user_confirm')
    def test_delete_all_cached_image(self, mock_user_confirm):
        self._main_test_helper(['glance.cmd.cache_manage',
                                'delete-all-cached-images'])
        self.assertEqual(1, mock_user_confirm.call_count)
