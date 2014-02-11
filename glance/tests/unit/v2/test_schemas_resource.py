# Copyright 2012 OpenStack Foundation.
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

import glance.api.v2.schemas
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class TestSchemasController(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSchemasController, self).setUp()
        self.controller = glance.api.v2.schemas.Controller()

    def test_image(self):
        req = unit_test_utils.get_fake_request()
        output = self.controller.image(req)
        self.assertEqual(output['name'], 'image')
        expected = set(['status', 'name', 'tags', 'checksum', 'created_at',
                        'disk_format', 'updated_at', 'visibility', 'self',
                        'file', 'container_format', 'schema', 'id', 'size',
                        'direct_url', 'min_ram', 'min_disk', 'protected',
                        'locations', 'owner', 'virtual_size'])
        self.assertEqual(set(output['properties'].keys()), expected)

    def test_images(self):
        req = unit_test_utils.get_fake_request()
        output = self.controller.images(req)
        self.assertEqual(output['name'], 'images')
        expected = set(['images', 'schema', 'first', 'next'])
        self.assertEqual(set(output['properties'].keys()), expected)
        expected = set(['{schema}', '{first}', '{next}'])
        actual = set([link['href'] for link in output['links']])
        self.assertEqual(actual, expected)
