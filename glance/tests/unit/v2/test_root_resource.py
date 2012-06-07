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

import glance.api.v2.root
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class TestRootController(test_utils.BaseTestCase):

    def setUp(self):
        super(TestRootController, self).setUp()
        self.controller = glance.api.v2.root.RootController()

    def test_index(self):
        req = unit_test_utils.get_fake_request()
        output = self.controller.index(req)
        expected = {
            'links': [
                {'rel': 'schemas', 'href': '/v2/schemas'},
                {'rel': 'images', 'href': '/v2/images'},
            ],
        }
        self.assertEqual(expected, output)
