# vim: tabstop=4 shiftwidth=4 softtabstop=4

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


from glance.tests import functional
from glance.tests.utils import execute


class TestSqlite(functional.FunctionalTest):
    """Functional tests for sqlite-specific logic"""

    @functional.runs_sql
    def test_big_int_mapping(self):
        """Ensure BigInteger not mapped to BIGINT"""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        cmd = "sqlite3 tests.sqlite '.schema'"
        exitcode, out, err = execute(cmd, raise_error=True)

        self.assertFalse('BIGINT' in out)

        self.stop_servers()
