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

import optparse

import mock
from six.moves import StringIO

from glance.cmd import cache_manage
from glance.common import exception
import glance.common.utils
import glance.image_cache.client
from glance.tests import utils as test_utils


@mock.patch('sys.stdout', mock.Mock())
class TestGlanceCmdManage(test_utils.BaseTestCase):

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_cached_images')
    @mock.patch.object(glance.common.utils.PrettyTable, 'make_row')
    def test_list_cached_images(self, mock_row_create, mock_images):
        """
        Verify that list_cached() method correctly processes images with all
        filled data and images with not filled 'last_accessed' field.
        """

        mock_images.return_value = [
            {'last_accessed': float(0),
             'last_modified': float(1378985797.124511),
             'image_id': '1', 'size': '128', 'hits': '1'},
            {'last_accessed': float(1378985797.124511),
             'last_modified': float(1378985797.124511),
             'image_id': '2', 'size': '255', 'hits': '2'}]
        cache_manage.list_cached(mock.Mock(), '')

        self.assertEqual(len(mock_images.return_value),
                         mock_row_create.call_count)

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_cached_images')
    def test_list_cached_images_empty(self, mock_images):
        """
        Verify that list_cached() method handles a case when no images are
        cached without errors.
        """

        mock_images.return_value = []
        self.assertEqual(cache_manage.SUCCESS,
                         cache_manage.list_cached(mock.Mock(), ''))

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_queued_images')
    @mock.patch.object(glance.common.utils.PrettyTable, 'make_row')
    def test_list_queued_images(self, mock_row_create, mock_images):
        """Verify that list_queued() method correctly processes images."""

        mock_images.return_value = [
            {'image_id': '1'}, {'image_id': '2'}]
        cache_manage.list_queued(mock.Mock(), '')

        self.assertEqual(len(mock_images.return_value),
                         mock_row_create.call_count)

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_queued_images')
    def test_list_queued_images_empty(self, mock_images):
        """
        Verify that list_queued() method handles a case when no images were
        queued without errors.
        """

        mock_images.return_value = []

        self.assertEqual(cache_manage.SUCCESS,
                         cache_manage.list_queued(mock.Mock(), ''))

    def test_queue_image_without_index(self):
        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.queue_image(mock.Mock(), []))

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_queue_image_not_forced_not_confirmed(self,
                                                  mock_client, mock_confirm):
        # options.forced set to False and queue confirmation set to False.

        mock_confirm.return_value = False
        mock_options = mock.Mock()
        mock_options.force = False
        self.assertEqual(cache_manage.SUCCESS,
                         cache_manage.queue_image(mock_options, ['img_id']))
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_queue_image_not_forced_confirmed(self, mock_client, mock_confirm):
        # options.forced set to False and queue confirmation set to True.

        mock_confirm.return_value = True
        mock_options = mock.Mock()
        mock_options.force = False
        mock_options.verbose = True  # to cover additional condition and line
        manager = mock.MagicMock()
        manager.attach_mock(mock_client, 'mock_client')

        self.assertEqual(cache_manage.SUCCESS,
                         cache_manage.queue_image(mock_options, ['img_id']))
        self.assertTrue(mock_client.called)
        self.assertIn(
            mock.call.mock_client().queue_image_for_caching('img_id'),
            manager.mock_calls)

    def test_delete_cached_image_without_index(self):
        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.delete_cached_image(mock.Mock(), []))

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_image_not_forced_not_confirmed(self,
                                                          mock_client,
                                                          mock_confirm):
        # options.forced set to False and delete confirmation set to False.

        mock_confirm.return_value = False
        mock_options = mock.Mock()
        mock_options.force = False
        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_cached_image(mock_options, ['img_id']))
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_image_not_forced_confirmed(self, mock_client,
                                                      mock_confirm):
        # options.forced set to False and delete confirmation set to True.

        mock_confirm.return_value = True
        mock_options = mock.Mock()
        mock_options.force = False
        mock_options.verbose = True  # to cover additional condition and line
        manager = mock.MagicMock()
        manager.attach_mock(mock_client, 'mock_client')

        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_cached_image(mock_options, ['img_id']))

        self.assertIn(
            mock.call.mock_client().delete_cached_image('img_id'),
            manager.mock_calls)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_images_not_forced_not_confirmed(self,
                                                           mock_client,
                                                           mock_confirm):
        # options.forced set to False and delete confirmation set to False.

        mock_confirm.return_value = False
        mock_options = mock.Mock()
        mock_options.force = False
        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_all_cached_images(mock_options, None))
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_images_not_forced_confirmed(self, mock_client,
                                                       mock_confirm):
        # options.forced set to False and delete confirmation set to True.

        mock_confirm.return_value = True
        mock_options = mock.Mock()
        mock_options.force = False
        mock_options.verbose = True  # to cover additional condition and line
        manager = mock.MagicMock()
        manager.attach_mock(mock_client, 'mock_client')

        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_all_cached_images(mock_options, None))
        self.assertTrue(mock_client.called)
        self.assertIn(
            mock.call.mock_client().delete_all_cached_images(),
            manager.mock_calls)

    def test_delete_queued_image_without_index(self):
        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.delete_queued_image(mock.Mock(), []))

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_image_not_forced_not_confirmed(self,
                                                          mock_client,
                                                          mock_confirm):
        # options.forced set to False and delete confirmation set to False.

        mock_confirm.return_value = False
        mock_options = mock.Mock()
        mock_options.force = False
        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_queued_image(mock_options, ['img_id']))
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_image_not_forced_confirmed(self, mock_client,
                                                      mock_confirm):
        # options.forced set to False and delete confirmation set to True.

        mock_confirm.return_value = True
        mock_options = mock.Mock()
        mock_options.force = False
        mock_options.verbose = True  # to cover additional condition and line
        manager = mock.MagicMock()
        manager.attach_mock(mock_client, 'mock_client')

        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_queued_image(mock_options, ['img_id']))
        self.assertTrue(mock_client.called)
        self.assertIn(
            mock.call.mock_client().delete_queued_image('img_id'),
            manager.mock_calls)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_images_not_forced_not_confirmed(self,
                                                           mock_client,
                                                           mock_confirm):
        # options.forced set to False and delete confirmation set to False.

        mock_confirm.return_value = False
        mock_options = mock.Mock()
        mock_options.force = False
        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_all_queued_images(mock_options, None))
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_images_not_forced_confirmed(self, mock_client,
                                                       mock_confirm):
        # options.forced set to False and delete confirmation set to True.
        mock_confirm.return_value = True
        mock_options = mock.Mock()
        mock_options.force = False
        mock_options.verbose = True  # to cover additional condition and line
        manager = mock.MagicMock()
        manager.attach_mock(mock_client, 'mock_client')

        self.assertEqual(
            cache_manage.SUCCESS,
            cache_manage.delete_all_queued_images(mock_options, None))
        self.assertTrue(mock_client.called)
        self.assertIn(
            mock.call.mock_client().delete_all_queued_images(),
            manager.mock_calls)

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_not_found(self, mock_function):
        mock_function.side_effect = exception.NotFound()

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(mock.Mock(), None))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_forbidden(self, mock_function):
        mock_function.side_effect = exception.Forbidden()

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(mock.Mock(), None))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_unhandled(self, mock_function):
        mock_function.side_effect = exception.Duplicate()
        my_mock = mock.Mock()
        my_mock.debug = False

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(my_mock, None))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_unhandled_debug_mode(self, mock_function):
        mock_function.side_effect = exception.Duplicate()
        my_mock = mock.Mock()
        my_mock.debug = True

        self.assertRaises(exception.Duplicate,
                          cache_manage.list_cached, my_mock, None)

    def test_cache_manage_env(self):
        def_value = 'sometext12345678900987654321'
        self.assertNotEqual(def_value,
                            cache_manage.env('PATH', default=def_value))

    def test_cache_manage_env_default(self):
        def_value = 'sometext12345678900987654321'
        self.assertEqual(def_value,
                         cache_manage.env('TMPVALUE1234567890',
                                          default=def_value))

    def test_create_option(self):
        oparser = optparse.OptionParser()
        cache_manage.create_options(oparser)
        self.assertTrue(len(oparser.option_list) > 0)

    @mock.patch.object(glance.cmd.cache_manage, 'lookup_command')
    def test_parse_options_no_parameters(self, mock_lookup):
        with mock.patch('sys.stdout', new_callable=StringIO):
            oparser = optparse.OptionParser()
            cache_manage.create_options(oparser)

            result = self.assertRaises(SystemExit, cache_manage.parse_options,
                                       oparser, [])
            self.assertEqual(0, result.code)
            self.assertFalse(mock_lookup.called)

    @mock.patch.object(optparse.OptionParser, 'print_usage')
    def test_parse_options_no_arguments(self, mock_printout):
        oparser = optparse.OptionParser()
        cache_manage.create_options(oparser)

        result = self.assertRaises(SystemExit, cache_manage.parse_options,
                                   oparser, ['-p', '1212'])
        self.assertEqual(0, result.code)
        self.assertTrue(mock_printout.called)

    @mock.patch.object(glance.cmd.cache_manage, 'lookup_command')
    def test_parse_options_retrieve_command(self, mock_lookup):
        mock_lookup.return_value = True
        oparser = optparse.OptionParser()
        cache_manage.create_options(oparser)
        (options, command, args) = cache_manage.parse_options(oparser,
                                                              ['-p', '1212',
                                                               'list-cached'])

        self.assertTrue(command)

    def test_lookup_command_unsupported_command(self):
        self.assertRaises(SystemExit, cache_manage.lookup_command, mock.Mock(),
                          'unsupported_command')

    def test_lookup_command_supported_command(self):
        command = cache_manage.lookup_command(mock.Mock(), 'list-cached')
        self.assertEqual(cache_manage.list_cached, command)
