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
import urllib

import glance.common.exception as exception
from glance.common.scripts.image_import import main as image_import_script
from glance.common.scripts import utils
from glance.common import store_utils

import glance.tests.utils as test_utils


class TestImageImport(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageImport, self).setUp()

    def test_run(self):
        with mock.patch.object(image_import_script,
                               '_execute') as mock_execute:
            task_id = mock.ANY
            context = mock.ANY
            task_repo = mock.ANY
            image_repo = mock.ANY
            image_factory = mock.ANY
            image_import_script.run(task_id, context, task_repo, image_repo,
                                    image_factory)

        mock_execute.assert_called_once_with(task_id, task_repo, image_repo,
                                             image_factory)

    def test_import_image(self):
        image_id = mock.ANY
        image = mock.Mock(image_id=image_id)
        image_repo = mock.Mock()
        image_repo.get.return_value = image
        image_factory = mock.ANY
        task_input = mock.Mock(image_properties=mock.ANY)
        uri = mock.ANY
        with mock.patch.object(image_import_script,
                               'create_image') as mock_create_image:
            with mock.patch.object(image_import_script,
                                   'set_image_data') as mock_set_img_data:
                mock_create_image.return_value = image
                self.assertEqual(
                    image_id,
                    image_import_script.import_image(image_repo, image_factory,
                                                     task_input, None, uri))
                # Check image is in saving state before image_repo.save called
                self.assertEqual('saving', image.status)
                self.assertTrue(image_repo.save.called)
                mock_set_img_data.assert_called_once_with(image, uri, None)
                self.assertTrue(image_repo.get.called)
                self.assertTrue(image_repo.save.called)

    def test_create_image(self):
        image = mock.ANY
        image_repo = mock.Mock()
        image_factory = mock.Mock()
        image_factory.new_image.return_value = image

        # Note: include some base properties to ensure no error while
        # attempting to verify them
        image_properties = {'disk_format': 'foo',
                            'id': 'bar'}

        self.assertEqual(image,
                         image_import_script.create_image(image_repo,
                                                          image_factory,
                                                          image_properties,
                                                          None))

    @mock.patch.object(utils, 'get_image_data_iter')
    def test_set_image_data_http(self, mock_image_iter):
        uri = 'http://www.example.com'
        image = mock.Mock()
        mock_image_iter.return_value = test_utils.FakeHTTPResponse()
        self.assertIsNone(image_import_script.set_image_data(image,
                                                             uri,
                                                             None))

    def test_set_image_data_http_error(self):
        uri = 'blahhttp://www.example.com'
        image = mock.Mock()
        self.assertRaises(urllib.error.URLError,
                          image_import_script.set_image_data, image, uri, None)

    @mock.patch.object(image_import_script, 'create_image')
    @mock.patch.object(image_import_script, 'set_image_data')
    @mock.patch.object(store_utils, 'delete_image_location_from_backend')
    def test_import_image_failed_with_expired_token(
            self, mock_delete_data, mock_set_img_data, mock_create_image):
        image_id = mock.ANY
        locations = ['location']
        image = mock.Mock(image_id=image_id, locations=locations)
        image_repo = mock.Mock()
        image_repo.get.side_effect = [image, exception.NotAuthenticated]
        image_factory = mock.ANY
        task_input = mock.Mock(image_properties=mock.ANY)
        uri = mock.ANY

        mock_create_image.return_value = image
        self.assertRaises(exception.NotAuthenticated,
                          image_import_script.import_image,
                          image_repo, image_factory,
                          task_input, None, uri)
        self.assertEqual(1, mock_set_img_data.call_count)
        mock_delete_data.assert_called_once_with(
            mock_create_image().context, image_id, 'location')

    @mock.patch('oslo_utils.timeutils.StopWatch')
    @mock.patch('glance.common.scripts.utils.get_image_data_iter')
    def test_set_image_data_with_callback(self, mock_gidi, mock_sw):
        data = [b'0' * 60, b'0' * 50, b'0' * 10, b'0' * 150]
        result_data = []
        mock_gidi.return_value = iter(data)
        mock_sw.return_value.expired.side_effect = [False, True, False,
                                                    False]
        image = mock.MagicMock()
        callback = mock.MagicMock()

        def fake_set_data(data_iter, **kwargs):
            for chunk in data_iter:
                result_data.append(chunk)

        image.set_data.side_effect = fake_set_data
        image_import_script.set_image_data(image, 'http://fake', None,
                                           callback=callback)

        mock_gidi.assert_called_once_with('http://fake')
        self.assertEqual(data, result_data)
        # Since we only fired the timer once, only two calls expected
        # for the four reads we did, including the final obligatory one
        callback.assert_has_calls([mock.call(110, 110),
                                   mock.call(160, 270)])
