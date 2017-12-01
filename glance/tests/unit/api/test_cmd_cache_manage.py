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

import argparse
import sys

import mock
import prettytable

from glance.cmd import cache_manage
from glance.common import exception
import glance.common.utils
import glance.image_cache.client
from glance.tests import utils as test_utils


@mock.patch('sys.stdout', mock.Mock())
class TestGlanceCmdManage(test_utils.BaseTestCase):

    def _run_command(self, cmd_args, return_code=None):
        """Runs the cache-manage command.

        :param cmd_args: The command line arguments.
        :param return_code: The expected return code of the command.
        """
        testargs = ['cache_manage']
        testargs.extend(cmd_args)
        with mock.patch.object(sys, 'exit') as mock_exit:
            with mock.patch.object(sys, 'argv', testargs):
                try:
                    cache_manage.main()
                except Exception:
                    # See if we expected this failure
                    if return_code is None:
                        raise

            if return_code is not None:
                mock_exit.called_with(return_code)

    @mock.patch.object(argparse.ArgumentParser, 'print_help')
    def test_help(self, mock_print_help):
        self._run_command(['help'])
        self.assertEqual(1, mock_print_help.call_count)

    @mock.patch.object(cache_manage, 'lookup_command')
    def test_help_with_command(self, mock_lookup_command):
        mock_lookup_command.return_value = cache_manage.print_help
        self._run_command(['help', 'list-cached'])
        mock_lookup_command.assert_any_call('help')
        mock_lookup_command.assert_any_call('list-cached')

    def test_help_with_redundant_command(self):
        self._run_command(['help', 'list-cached', '1'], cache_manage.FAILURE)

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_cached_images')
    @mock.patch.object(prettytable.PrettyTable, 'add_row')
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
        self._run_command(['list-cached'], cache_manage.SUCCESS)
        self.assertEqual(len(mock_images.return_value),
                         mock_row_create.call_count)

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_cached_images')
    def test_list_cached_images_empty(self, mock_images):
        """
        Verify that list_cached() method handles a case when no images are
        cached without errors.
        """
        self._run_command(['list-cached'], cache_manage.SUCCESS)

    @mock.patch.object(glance.image_cache.client.CacheClient,
                       'get_queued_images')
    @mock.patch.object(prettytable.PrettyTable, 'add_row')
    def test_list_queued_images(self, mock_row_create, mock_images):
        """Verify that list_queued() method correctly processes images."""

        mock_images.return_value = [
            {'image_id': '1'}, {'image_id': '2'}]
        # cache_manage.list_queued(mock.Mock())
        self._run_command(['list-queued'], cache_manage.SUCCESS)
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
        self._run_command(['list-queued'], cache_manage.SUCCESS)

    def test_queue_image_without_index(self):
        self._run_command(['queue-image'], cache_manage.FAILURE)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_queue_image_not_forced_not_confirmed(self,
                                                  mock_client, mock_confirm):
        # --force not set and queue confirmation return False.
        mock_confirm.return_value = False
        self._run_command(['queue-image', 'fakeimageid'], cache_manage.SUCCESS)
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_queue_image_not_forced_confirmed(self, mock_get_client,
                                              mock_confirm):
        # --force not set and confirmation return True.
        mock_confirm.return_value = True
        mock_client = mock.MagicMock()
        mock_get_client.return_value = mock_client

        # verbose to cover additional condition and line
        self._run_command(['queue-image', 'fakeimageid', '-v'],
                          cache_manage.SUCCESS)

        self.assertTrue(mock_get_client.called)
        mock_client.queue_image_for_caching.assert_called_with('fakeimageid')

    def test_delete_cached_image_without_index(self):
        self._run_command(['delete-cached-image'], cache_manage.FAILURE)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_image_not_forced_not_confirmed(self,
                                                          mock_client,
                                                          mock_confirm):
        # --force not set and confirmation return False.
        mock_confirm.return_value = False
        self._run_command(['delete-cached-image', 'fakeimageid'],
                          cache_manage.SUCCESS)
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_image_not_forced_confirmed(self, mock_get_client,
                                                      mock_confirm):
        # --force not set and confirmation return True.
        mock_confirm.return_value = True
        mock_client = mock.MagicMock()
        mock_get_client.return_value = mock_client

        # verbose to cover additional condition and line
        self._run_command(['delete-cached-image', 'fakeimageid', '-v'],
                          cache_manage.SUCCESS)

        self.assertTrue(mock_get_client.called)
        mock_client.delete_cached_image.assert_called_with('fakeimageid')

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_images_not_forced_not_confirmed(self,
                                                           mock_client,
                                                           mock_confirm):
        # --force not set and confirmation return False.
        mock_confirm.return_value = False
        self._run_command(['delete-all-cached-images'], cache_manage.SUCCESS)
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_cached_images_not_forced_confirmed(self, mock_get_client,
                                                       mock_confirm):
        # --force not set and confirmation return True.
        mock_confirm.return_value = True
        mock_client = mock.MagicMock()
        mock_get_client.return_value = mock_client

        # verbose to cover additional condition and line
        self._run_command(['delete-all-cached-images', '-v'],
                          cache_manage.SUCCESS)

        self.assertTrue(mock_get_client.called)
        mock_client.delete_all_cached_images.assert_called()

    def test_delete_queued_image_without_index(self):
        self._run_command(['delete-queued-image'], cache_manage.FAILURE)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_image_not_forced_not_confirmed(self,
                                                          mock_client,
                                                          mock_confirm):
        # --force not set and confirmation set to False.
        mock_confirm.return_value = False
        self._run_command(['delete-queued-image', 'img_id'],
                          cache_manage.SUCCESS)
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_image_not_forced_confirmed(self, mock_get_client,
                                                      mock_confirm):
        # --force not set and confirmation set to True.
        mock_confirm.return_value = True
        mock_client = mock.MagicMock()
        mock_get_client.return_value = mock_client

        self._run_command(['delete-queued-image', 'img_id', '-v'],
                          cache_manage.SUCCESS)

        self.assertTrue(mock_get_client.called)
        mock_client.delete_queued_image.assert_called_with('img_id')

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_images_not_forced_not_confirmed(self,
                                                           mock_client,
                                                           mock_confirm):
        # --force not set and confirmation set to False.
        mock_confirm.return_value = False
        self._run_command(['delete-all-queued-images'],
                          cache_manage.SUCCESS)
        self.assertFalse(mock_client.called)

    @mock.patch.object(glance.cmd.cache_manage, 'user_confirm')
    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_delete_queued_images_not_forced_confirmed(self, mock_get_client,
                                                       mock_confirm):
        # --force not set and confirmation set to True.
        mock_confirm.return_value = True
        mock_client = mock.MagicMock()
        mock_get_client.return_value = mock_client

        self._run_command(['delete-all-queued-images', '-v'],
                          cache_manage.SUCCESS)

        self.assertTrue(mock_get_client.called)
        mock_client.delete_all_queued_images.assert_called()

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_not_found(self, mock_function):
        mock_function.side_effect = exception.NotFound()

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(mock.Mock()))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_forbidden(self, mock_function):
        mock_function.side_effect = exception.Forbidden()

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(mock.Mock()))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_unhandled(self, mock_function):
        mock_function.side_effect = exception.Duplicate()
        my_mock = mock.Mock()
        my_mock.debug = False

        self.assertEqual(cache_manage.FAILURE,
                         cache_manage.list_cached(my_mock))

    @mock.patch.object(glance.cmd.cache_manage, 'get_client')
    def test_catch_error_unhandled_debug_mode(self, mock_function):
        mock_function.side_effect = exception.Duplicate()
        my_mock = mock.Mock()
        my_mock.debug = True

        self.assertRaises(exception.Duplicate,
                          cache_manage.list_cached, my_mock)

    def test_cache_manage_env(self):
        def_value = 'sometext12345678900987654321'
        self.assertNotEqual(def_value,
                            cache_manage.env('PATH', default=def_value))

    def test_cache_manage_env_default(self):
        def_value = 'sometext12345678900987654321'
        self.assertEqual(def_value,
                         cache_manage.env('TMPVALUE1234567890',
                                          default=def_value))

    def test_lookup_command_unsupported_command(self):
        self._run_command(['unsupported_command'], cache_manage.FAILURE)
