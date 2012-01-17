# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

import json
import os
import shutil
import unittest

import stubout

from glance.tests import stubs
from glance.tests import utils as test_utils


class IsolatedUnitTest(unittest.TestCase):

    """
    Unit test case that establishes a mock environment within
    a testing directory (in isolation)
    """

    def setUp(self):
        self.test_id, self.test_dir = test_utils.get_isolated_test_env()
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs, self.test_dir)
        policy_file = self._copy_data_file('policy.json', self.test_dir)
        options = {'sql_connection': 'sqlite://',
                   'verbose': False,
                   'debug': False,
                   'default_store': 'filesystem',
                   'filesystem_store_datadir': os.path.join(self.test_dir),
                   'policy_file': policy_file}

        self.conf = test_utils.TestConfigOpts(options)

    def _copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def set_policy_rules(self, rules):
        fap = open(self.conf.policy_file, 'w')
        fap.write(json.dumps(rules))
        fap.close()

    def tearDown(self):
        self.stubs.UnsetAll()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
