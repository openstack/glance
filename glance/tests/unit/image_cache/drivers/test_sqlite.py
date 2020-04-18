# Copyright (c) 2017 Huawei Technologies Co., Ltd.
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

"""
Tests for the sqlite image_cache driver.
"""

import os
from unittest import mock

import ddt

from glance.image_cache.drivers import sqlite
from glance.tests import utils


@ddt.ddt
class TestSqlite(utils.BaseTestCase):

    @ddt.data(True, False)
    def test_delete_cached_file(self, throw_not_exists):

        with mock.patch.object(os, 'unlink') as mock_unlink:
            if throw_not_exists:
                mock_unlink.side_effect = OSError((2, 'File not found'))

        # Should not raise an exception in all cases
        sqlite.delete_cached_file('/tmp/dummy_file')
