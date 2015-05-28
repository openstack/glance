# Copyright 2014 OpenStack Foundation
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

import mock
from six.moves import urllib

from glance.common import exception
from glance.common.scripts import utils as script_utils
import glance.tests.utils as test_utils


class TestScriptsUtils(test_utils.BaseTestCase):
    def setUp(self):
        super(TestScriptsUtils, self).setUp()

    def test_get_task(self):
        task = mock.ANY
        task_repo = mock.Mock(return_value=task)
        task_id = mock.ANY
        self.assertEqual(task, script_utils.get_task(task_repo, task_id))

    def test_unpack_task_input(self):
        task_input = {"import_from": "foo",
                      "import_from_format": "bar",
                      "image_properties": "baz"}
        task = mock.Mock(task_input=task_input)
        self.assertEqual(task_input,
                         script_utils.unpack_task_input(task))

    def test_unpack_task_input_error(self):
        task_input1 = {"import_from_format": "bar", "image_properties": "baz"}
        task_input2 = {"import_from": "foo", "image_properties": "baz"}
        task_input3 = {"import_from": "foo", "import_from_format": "bar"}
        task1 = mock.Mock(task_input=task_input1)
        task2 = mock.Mock(task_input=task_input2)
        task3 = mock.Mock(task_input=task_input3)
        self.assertRaises(exception.Invalid,
                          script_utils.unpack_task_input, task1)
        self.assertRaises(exception.Invalid,
                          script_utils.unpack_task_input, task2)
        self.assertRaises(exception.Invalid,
                          script_utils.unpack_task_input, task3)

    def test_set_base_image_properties(self):
        properties = {}
        script_utils.set_base_image_properties(properties)
        self.assertIn('disk_format', properties)
        self.assertIn('container_format', properties)
        self.assertEqual('qcow2', properties['disk_format'])
        self.assertEqual('bare', properties['container_format'])

    def test_set_base_image_properties_none(self):
        properties = None
        script_utils.set_base_image_properties(properties)
        self.assertIsNone(properties)

    def test_set_base_image_properties_not_empty(self):
        properties = {'disk_format': 'vmdk', 'container_format': 'bare'}
        script_utils.set_base_image_properties(properties)
        self.assertIn('disk_format', properties)
        self.assertIn('container_format', properties)
        self.assertEqual('vmdk', properties.get('disk_format'))
        self.assertEqual('bare', properties.get('container_format'))

    def test_validate_location_http(self):
        location = 'http://example.com'
        self.assertEqual(location,
                         script_utils.validate_location_uri(location))

    def test_validate_location_https(self):
        location = 'https://example.com'
        self.assertEqual(location,
                         script_utils.validate_location_uri(location))

    def test_validate_location_none_error(self):
        self.assertRaises(exception.BadStoreUri,
                          script_utils.validate_location_uri, '')

    def test_validate_location_file_location_error(self):
        self.assertRaises(StandardError, script_utils.validate_location_uri,
                          "file:///tmp")
        self.assertRaises(StandardError, script_utils.validate_location_uri,
                          "filesystem:///tmp")

    def test_validate_location_unsupported_error(self):
        location = 'swift'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'swift+http'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'swift+https'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'swift+config'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'vsphere'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'sheepdog://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 's3+https://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'rbd://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'gridfs://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'cinder://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

    def test_get_image_data_http(self):
        uri = "http://example.com"
        response = urllib.request.urlopen(uri)
        expected = response.read()
        self.assertEqual(expected,
                         script_utils.get_image_data_iter(uri).read())

    def test_get_image_data_https(self):
        uri = "https://example.com"
        response = urllib.request.urlopen(uri)
        expected = response.read()
        self.assertEqual(expected,
                         script_utils.get_image_data_iter(uri).read())

    def test_get_image_data_http_error(self):
        uri = "http:/example.com"
        self.assertRaises(urllib.error.URLError,
                          script_utils.get_image_data_iter,
                          uri)
