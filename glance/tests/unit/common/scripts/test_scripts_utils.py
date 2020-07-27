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

from unittest import mock

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
        self.assertRaises(exception.BadStoreUri,
                          script_utils.validate_location_uri, "file:///tmp")
        self.assertRaises(exception.BadStoreUri,
                          script_utils.validate_location_uri,
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

        location = 'rbd://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)

        location = 'cinder://'
        self.assertRaises(urllib.error.URLError,
                          script_utils.validate_location_uri, location)


class TestCallbackIterator(test_utils.BaseTestCase):
    def test_iterator_iterates(self):
        # Include a zero-length generation to make sure we don't trigger
        # the callback when nothing new has happened.
        items = ['1', '2', '', '3']
        callback = mock.MagicMock()
        cb_iter = script_utils.CallbackIterator(iter(items), callback)
        iter_items = list(cb_iter)
        callback.assert_has_calls([mock.call(1, 1),
                                   mock.call(1, 2),
                                   mock.call(1, 3)])
        self.assertEqual(items, iter_items)

        # Make sure we don't call the callback on close if we
        # have processed all the data
        callback.reset_mock()
        cb_iter.close()
        callback.assert_not_called()

    @mock.patch('oslo_utils.timeutils.StopWatch')
    def test_iterator_iterates_granularly(self, mock_sw):
        items = ['1', '2', '3']
        callback = mock.MagicMock()
        mock_sw.return_value.expired.side_effect = [False, True, False]
        cb_iter = script_utils.CallbackIterator(iter(items), callback,
                                                min_interval=30)
        iter_items = list(cb_iter)
        self.assertEqual(items, iter_items)
        # The timer only fired once, but we should still expect the final
        # chunk to be emitted.
        callback.assert_has_calls([mock.call(2, 2),
                                   mock.call(1, 3)])

        mock_sw.assert_called_once_with(30)
        mock_sw.return_value.start.assert_called_once_with()
        mock_sw.return_value.restart.assert_called_once_with()

        # Make sure we don't call the callback on close if we
        # have processed all the data
        callback.reset_mock()
        cb_iter.close()
        callback.assert_not_called()

    def test_proxy_close(self):
        callback = mock.MagicMock()
        source = mock.MagicMock()
        del source.close
        # NOTE(danms): This will generate AttributeError if it
        # tries to call close after the del above.
        script_utils.CallbackIterator(source, callback).close()

        source = mock.MagicMock()
        source.close.return_value = 'foo'
        script_utils.CallbackIterator(source, callback).close()
        source.close.assert_called_once_with()

        # We didn't process any data, so no callback should be expected
        callback.assert_not_called()

    @mock.patch('oslo_utils.timeutils.StopWatch')
    def test_proxy_read(self, mock_sw):
        items = ['1', '2', '3']
        source = mock.MagicMock()
        source.read.side_effect = items
        callback = mock.MagicMock()
        mock_sw.return_value.expired.side_effect = [False, True, False]
        cb_iter = script_utils.CallbackIterator(source, callback,
                                                min_interval=30)
        results = [cb_iter.read(1) for i in range(len(items))]
        self.assertEqual(items, results)
        # The timer only fired once while reading, so we only expect
        # one callback.
        callback.assert_has_calls([mock.call(2, 2)])
        cb_iter.close()
        # If we close with residue since the last callback, we should
        # call the callback with that.
        callback.assert_has_calls([mock.call(2, 2),
                                   mock.call(1, 3)])
