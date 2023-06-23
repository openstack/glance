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
        available_stores = ['cheap', 'fast', 'readonly_store', 'fast-cinder',
                            'fast-rbd', 'reliable']
        req = unit_test_utils.get_fake_request()
        output = self.controller.get_stores(req)
        self.assertIn('stores', output)
        for stores in output['stores']:
            self.assertIn('id', stores)
            self.assertNotIn('weight', stores)
            self.assertIn(stores['id'], available_stores)

    def test_get_stores_read_only_store(self):
        available_stores = ['cheap', 'fast', 'readonly_store', 'fast-cinder',
                            'fast-rbd', 'reliable']
        req = unit_test_utils.get_fake_request()
        output = self.controller.get_stores(req)
        self.assertIn('stores', output)
        for stores in output['stores']:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            if stores['id'] == 'readonly_store':
                self.assertTrue(stores['read-only'])
            else:
                self.assertIsNone(stores.get('read-only'))

    def test_get_stores_reserved_stores_excluded(self):
        enabled_backends = {
            'fast': 'file',
            'cheap': 'file'
        }
        self.config(enabled_backends=enabled_backends)
        req = unit_test_utils.get_fake_request()
        output = self.controller.get_stores(req)
        self.assertIn('stores', output)
        self.assertEqual(2, len(output['stores']))
        for stores in output["stores"]:
            self.assertFalse(stores["id"].startswith("os_glance_"))

    def test_get_stores_detail(self):
        available_stores = ['cheap', 'fast', 'readonly_store', 'fast-cinder',
                            'fast-rbd', 'reliable']
        available_store_type = ['file', 'file', 'http', 'cinder', 'rbd',
                                'swift']
        req = unit_test_utils.get_fake_request(roles=['admin'])
        output = self.controller.get_stores_detail(req)
        self.assertEqual(len(CONF.enabled_backends), len(output['stores']))
        self.assertIn('stores', output)
        for stores in output['stores']:
            self.assertIn('id', stores)
            self.assertIn(stores['id'], available_stores)
            self.assertIn(stores['type'], available_store_type)
            self.assertIsNotNone(stores['properties'])

    def test_get_stores_detail_properties(self):
        store_attributes = {'rbd': ['chunk_size', 'pool', 'thin_provisioning'],
                            'file': ['data_dir', 'chunk_size',
                                     'thin_provisioning'],
                            'cinder': ['volume_type', 'use_multipath'],
                            'swift': ['container',
                                      'large_object_size',
                                      'large_object_chunk_size'],
                            'http': []}
        req = unit_test_utils.get_fake_request(roles=['admin'])
        output = self.controller.get_stores_detail(req)
        self.assertEqual(len(CONF.enabled_backends), len(output['stores']))
        self.assertIn('stores', output)
        for store in output['stores']:
            actual_attribute = list(store['properties'].keys())
            expected_attribute = store_attributes[store['type']]
            self.assertEqual(actual_attribute, expected_attribute)

    def test_get_stores_detail_with_store_weight(self):
        self.config(weight=100, group='fast')
        self.config(weight=200, group='cheap')
        self.config(weight=300, group='fast-rbd')
        self.config(weight=400, group='fast-cinder')
        self.config(weight=500, group='reliable')

        req = unit_test_utils.get_fake_request(roles=['admin'])
        output = self.controller.get_stores_detail(req)
        self.assertEqual(len(CONF.enabled_backends), len(output['stores']))
        self.assertIn('stores', output)
        for store in output['stores']:
            self.assertIn('weight', store)

    def test_get_stores_detail_non_admin(self):
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.get_stores_detail,
                          req)
