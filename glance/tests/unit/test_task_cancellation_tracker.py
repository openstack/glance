# Copyright 2025 RedHat Inc.
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
import os
from unittest import mock

from oslo_concurrency import lockutils

from glance.common import exception
from glance import task_cancellation_tracker as tracker
from glance.tests.unit import base


class TestTaskCancellationTracker(base.MultiStoreClearingUnitTest):
    def setUp(self):
        super(TestTaskCancellationTracker, self).setUp()

    def test_get_data_dir(self):
        self.assertEqual(tracker.get_data_dir(), self.test_dir)

    def test_path_for_op(self):
        op_id = '123'
        expected = os.path.join(self.test_dir, "%s%s" % (
            "running-task-", op_id))
        self.assertEqual(tracker.path_for_op(op_id), expected)

    def test_register_and_is_canceled(self):
        op_id = 'op1'
        tracker.register_operation(op_id)
        self.assertFalse(tracker.is_canceled(op_id))
        # File should exist but be zero-length
        path = tracker.path_for_op(op_id)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 0)

    def test_signal_finished(self):
        op_id = 'op2'
        tracker.register_operation(op_id)
        tracker.signal_finished(op_id)
        self.assertFalse(os.path.exists(tracker.path_for_op(op_id)))

    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch.object(lockutils, 'external_lock')
    @mock.patch('os.path.exists', side_effect=[True, False])
    @mock.patch('time.sleep')
    def test_cancel_operation_immediate_cancel(
            self, mock_sleep, mock_exists, mock_external_lock, mock_open):
        op_id = 'op3'
        tracker.register_operation(op_id)
        tracker.cancel_operation(op_id)
        self.assertTrue(mock_external_lock.called)
        self.assertTrue(mock_open.called)
        mock_sleep.assert_not_called()
        mock_exists.assert_any_call(tracker.path_for_op(op_id))

    def test_register_operation_already_exists(self):
        op_id = 'op4'
        tracker.register_operation(op_id)
        self.assertRaises(RuntimeError, tracker.register_operation, op_id)

    def test_signal_finished_file_not_found(self):
        op_id = 'op5'
        # Should not raise
        tracker.signal_finished(op_id)

    @mock.patch('os.path.exists')
    @mock.patch('time.sleep', return_value=None)
    def test_cancel_operation_timeout(self, mock_sleep, mock_exists):
        mock_exists.return_value = True
        op_id = 'op6'
        self.assertRaises(
            exception.ServerError, tracker.cancel_operation, op_id)
        self.assertTrue(mock_sleep.called)

    @mock.patch('time.sleep', return_value=None)
    def test_cancel_operation_eventually_cancels(self, mock_sleep):
        op_id = 'op7'
        tracker.register_operation(op_id)

        def side_effect(path):
            # After 3 calls, simulate file removal
            if mock_sleep.call_count >= 3:
                return False
            return True

        with mock.patch('os.path.exists', side_effect=side_effect):
            with mock.patch('os.path.getsize', return_value=1):
                tracker.cancel_operation(op_id)
        self.assertEqual(mock_sleep.call_count, 3)

    @mock.patch('os.path.exists')
    def test_cancel_operation_not_registered(self, mock_exists):
        mock_exists.return_value = False
        op_id = 'op8'
        self.assertFalse(tracker.is_canceled(op_id))
        self.assertRaises(
            exception.ServerError, tracker.cancel_operation, op_id)
