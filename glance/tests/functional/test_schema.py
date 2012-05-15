# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the 'License'); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import unittest

import glance.schema
import glance.tests.utils


class TestSchemaAPI(unittest.TestCase):

    def setUp(self):
        conf = glance.tests.utils.TestConfigOpts()
        self.schema_api = glance.schema.API(conf)

    def test_load_image_schema(self):
        output = self.schema_api.get_schema('image')
        self.assertEqual('image', output['name'])
        expected_keys = set([
            'id',
            'name',
            'visibility',
            'created_at',
            'updated_at',
            'tags',
        ])
        self.assertEqual(expected_keys, set(output['properties'].keys()))

    def test_load_access_schema(self):
        output = self.schema_api.get_schema('access')
        self.assertEqual('access', output['name'])
        expected_keys = ['tenant_id', 'can_share']
        self.assertEqual(expected_keys, output['properties'].keys())
