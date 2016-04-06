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

import mock

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
        self.commands.purge(1, 100)
        mock_db_purge.assert_called_once_with(self.context, 1, 100)

    def test_purge_command_negative_rows(self):
        exit = self.assertRaises(SystemExit, self.commands.purge, 1, -1)
        self.assertEqual("Minimal rows limit is 1.", exit.code)

    def test_purge_invalid_age_in_days(self):
        age_in_days = 'abcd'
        ex = self.assertRaises(SystemExit, self.commands.purge, age_in_days)
        expected = ("Invalid int value for age_in_days: "
                    "%(age_in_days)s") % {'age_in_days': age_in_days}
        self.assertEqual(expected, ex.code)

    def test_purge_invalid_max_rows(self):
        max_rows = 'abcd'
        ex = self.assertRaises(SystemExit, self.commands.purge, 1, max_rows)
        expected = ("Invalid int value for max_rows: "
                    "%(max_rows)s") % {'max_rows': max_rows}
        self.assertEqual(expected, ex.code)
