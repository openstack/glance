# Copyright 2012 Red Hat, Inc
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

"""Functional test cases for sqlite-specific logic"""


import os

from glance.tests import functional
from glance.tests.utils import depends_on_exe
from glance.tests.utils import execute
from glance.tests.utils import skip_if_disabled


class TestSqlite(functional.SynchronousAPIBase):
    """Functional tests for sqlite-specific logic"""

    @depends_on_exe('sqlite3')
    @skip_if_disabled
    def test_big_int_mapping(self):
        """Ensure BigInteger not mapped to BIGINT, but to INTEGER"""
        self.start_server()

        db_file = os.path.join(self.test_dir, 'test.db')
        self.assertTrue(os.path.exists(db_file))

        for (table, field) in [
            ('images', 'size'),
            ('images', 'virtual_size'),
            ('node_reference', 'node_reference_id'),
            ('cached_images', 'id'),
            ('cached_images', 'node_reference_id'),
        ]:
            sql = f"SELECT type FROM pragma_table_info('{table}')"
            sql = f"{sql} WHERE name='{field}'"
            cmd = f'sqlite3 {db_file} "{sql}"'
            exitcode, out, _ = execute(cmd, raise_error=True)
            self.assertEqual(exitcode, 0)
            self.assertEqual(out.decode().strip(), 'INTEGER')
