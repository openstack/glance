# Copyright (c) 2017 RedHat, Inc.
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

from unittest import mock

import glance.api.v2.discovery
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class TestInfoControllers(test_utils.BaseTestCase):

    def setUp(self):
        super(TestInfoControllers, self).setUp()
        self.controller = glance.api.v2.discovery.InfoController()

    def test_get_import_info_with_empty_method_list(self):
        """When methods list is empty, should still return import methods"""
        self.config(enabled_import_methods=[])
        req = unit_test_utils.get_fake_request()
        output = self.controller.get_image_import(req)
        self.assertIn('import-methods', output)
        self.assertEqual([], output['import-methods']['value'])

    def test_get_import_info(self):
        """Testing defaults, not all possible values"""
        default_import_methods = ['glance-direct', 'web-download',
                                  'copy-image']

        req = unit_test_utils.get_fake_request()
        output = self.controller.get_image_import(req)
        self.assertIn('import-methods', output)
        self.assertEqual(default_import_methods,
                         output['import-methods']['value'])

    def test_get_import_info_detail(self):
        controller = glance.api.v2.discovery.InfoController(
            policy_enforcer=mock.Mock())
        self.config(image_import_plugins=['inject_image_metadata',
                                          'image_conversion',
                                          'image_decompression'],
                    group='image_import_opts')
        self.config(ignore_user_roles=['admin'],
                    group='inject_metadata_properties')
        self.config(inject={'os_distro': 'fedora'},
                    group='inject_metadata_properties')
        self.config(output_format='qcow2', group='image_conversion')

        req = unit_test_utils.get_fake_request(is_admin=True, roles=['admin'])
        output = controller.get_image_import_detail(req)

        self.assertEqual(['glance-direct', 'web-download', 'copy-image'],
                         output['import-methods']['value'])
        self.assertEqual(
            [
                {
                    'name': 'inject_image_metadata',
                    'properties': {
                        'ignore_user_roles': ['admin'],
                        'inject': {'os_distro': 'fedora'}
                    }
                },
                {
                    'name': 'image_conversion',
                    'properties': {'output_format': 'qcow2'}
                },
                {
                    'name': 'image_decompression',
                    'properties': {}
                }
            ],
            output['plugins'])
