# Copyright (c) 2018-2019 RedHat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from oslo_config import cfg
import webob.exc

import glance.api.v2.discovery
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils


CONF = cfg.CONF


class TestInfoControllers(base.MultiStoreClearingUnitTest):
    def setUp(self):
        super(TestInfoControllers, self).setUp()
        self.controller = glance.api.v2.discovery.InfoController()

    def tearDown(self):
        super(TestInfoControllers, self).tearDown()

    def test_get_stores_with_enabled_backends_empty(self):
        self.config(enabled_backends={})
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get_stores,
                          req)

    def test_get_stores(self):
        available_stores = ['ceph1', 'file1']
        req = unit_test_utils.get_fake_request()
        output = self.controller.get_stores(req)
        self.assertIn('stores', output)
        for stores in output['stores']:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
