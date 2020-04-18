# Copyright 2016 OpenStack Foundation.
# Copyright 2016 NTT Data.
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

from oslo_db import exception as db_exception

from glance.cmd import manage
from glance import context
from glance.db.sqlalchemy import api as db_api
import glance.tests.utils as test_utils

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'


class DBCommandsTestCase(test_utils.BaseTestCase):
    def setUp(self):
        super(DBCommandsTestCase, self).setUp()
        self.commands = manage.DbCommands()
        self.context = context.RequestContext(
            user=USER1, tenant=TENANT1)

    @mock.patch.object(db_api, 'purge_deleted_rows')
    @mock.patch.object(context, 'get_admin_context')
    def test_purge_command(self, mock_context, mock_db_purge):
        mock_context.return_value = self.context
        self.commands.purge(0, 100)
        mock_db_purge.assert_called_once_with(self.context, 0, 100)

    def test_purge_command_negative_rows(self):
        exit = self.assertRaises(SystemExit, self.commands.purge, 1, -1)
        self.assertEqual("Minimal rows limit is 1.", exit.code)

    def test_purge_invalid_age_in_days(self):
        age_in_days = 'abcd'
        ex = self.assertRaises(SystemExit, self.commands.purge, age_in_days)
        expected = ("Invalid int value for age_in_days: "
                    "%(age_in_days)s") % {'age_in_days': age_in_days}
        self.assertEqual(expected, ex.code)

    def test_purge_negative_age_in_days(self):
        ex = self.assertRaises(SystemExit, self.commands.purge, '-1')
        self.assertEqual("Must supply a non-negative value for age.", ex.code)

    def test_purge_invalid_max_rows(self):
        max_rows = 'abcd'
        ex = self.assertRaises(SystemExit, self.commands.purge, 1, max_rows)
        expected = ("Invalid int value for max_rows: "
                    "%(max_rows)s") % {'max_rows': max_rows}
        self.assertEqual(expected, ex.code)

    @mock.patch.object(db_api, 'purge_deleted_rows')
    @mock.patch.object(context, 'get_admin_context')
    def test_purge_max_rows(self, mock_context, mock_db_purge):
        mock_context.return_value = self.context
        value = (2 ** 31) - 1
        self.commands.purge(age_in_days=1, max_rows=value)
        mock_db_purge.assert_called_once_with(self.context, 1, value)

    def test_purge_command_exceeded_maximum_rows(self):
        # value(2 ** 31) is greater than max_rows(2147483647) by 1.
        value = 2 ** 31
        ex = self.assertRaises(SystemExit, self.commands.purge, age_in_days=1,
                               max_rows=value)
        expected = "'max_rows' value out of range, must not exceed 2147483647."
        self.assertEqual(expected, ex.code)

    @mock.patch('glance.db.sqlalchemy.api.purge_deleted_rows')
    def test_purge_command_fk_constraint_failure(self, purge_deleted_rows):
        purge_deleted_rows.side_effect = db_exception.DBReferenceError(
            'fake_table', 'fake_constraint', 'fake_key', 'fake_key_table')
        exit = self.assertRaises(SystemExit, self.commands.purge, 10, 100)
        self.assertEqual("Purge command failed, check glance-manage logs"
                         " for more details.", exit.code)
