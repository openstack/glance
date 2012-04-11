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

import glance.api.v2.schemas
import glance.tests.unit.utils as test_utils


class TestSchemasController(unittest.TestCase):

    def setUp(self):
        super(TestSchemasController, self).setUp()
        self.controller = glance.api.v2.schemas.SchemasController({})

    def test_index(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req)
        expected = {'links': [
            {'rel': 'image', 'href': '/schemas/image'},
            {'rel': 'access', 'href': '/schemas/image/access'},
        ]}
        self.assertEqual(expected, output)

    def test_image(self):
        req = test_utils.FakeRequest()
        output = self.controller.image(req)
        self.assertEqual(glance.api.v2.schemas.IMAGE_SCHEMA, output)

    def test_access(self):
        req = test_utils.FakeRequest()
        output = self.controller.access(req)
        self.assertEqual(glance.api.v2.schemas.ACCESS_SCHEMA, output)
