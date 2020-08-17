# Copyright 2018 Verizon Wireless
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

import sys
from unittest import mock

from glance_store import exceptions as store_exceptions
from oslo_config import cfg
from oslo_utils import units
import taskflow

import glance.async_.flows.api_image_import as import_flow
from glance.common import exception
from glance.common.scripts.image_import import main as image_import
from glance import context
from glance import gateway
import glance.tests.utils as test_utils

from cursive import exception as cursive_exception

CONF = cfg.CONF

TASK_TYPE = 'api_image_import'
TASK_ID1 = 'dbbe7231-020f-4311-87e1-5aaa6da56c02'
IMAGE_ID1 = '41f5b3b0-f54c-4cef-bd45-ce3e376a142f'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestApiImageImportTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestApiImageImportTask, self).setUp()

        self.wd_task_input = {
            "import_req": {
                "method": {
                    "name": "web-download",
                    "uri": "http://example.com/image.browncow"
                }
            }
        }

        self.gd_task_input = {
            "import_req": {
                "method": {
                    "name": "glance-direct"
                }
            }
        }

        self.mock_task_repo = mock.MagicMock()
        self.mock_image_repo = mock.MagicMock()
        self.mock_image_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}

    @mock.patch('glance.async_.flows.api_image_import._VerifyStaging.__init__')
    @mock.patch('taskflow.patterns.linear_flow.Flow.add')
    @mock.patch('taskflow.patterns.linear_flow.__init__')
    def _pass_uri(self, mock_lf_init, mock_flow_add, mock_VS_init,
                  uri, file_uri, import_req):
        flow_kwargs = {"task_id": TASK_ID1,
                       "task_type": TASK_TYPE,
                       "task_repo": self.mock_task_repo,
                       "image_repo": self.mock_image_repo,
                       "image_id": IMAGE_ID1,
                       "import_req": import_req}

        mock_lf_init.return_value = None
        mock_VS_init.return_value = None

        self.config(node_staging_uri=uri)
        import_flow.get_flow(**flow_kwargs)
        mock_VS_init.assert_called_with(TASK_ID1, TASK_TYPE,
                                        self.mock_task_repo,
                                        file_uri)

    def test_get_flow_handles_node_uri_with_ending_slash(self):
        test_uri = 'file:///some/where/'
        expected_uri = '{0}{1}'.format(test_uri, IMAGE_ID1)
        self._pass_uri(uri=test_uri, file_uri=expected_uri,
                       import_req=self.gd_task_input['import_req'])
        self._pass_uri(uri=test_uri, file_uri=expected_uri,
                       import_req=self.wd_task_input['import_req'])

    def test_get_flow_handles_node_uri_without_ending_slash(self):
        test_uri = 'file:///some/where'
        expected_uri = '{0}/{1}'.format(test_uri, IMAGE_ID1)
        self._pass_uri(uri=test_uri, file_uri=expected_uri,
                       import_req=self.wd_task_input['import_req'])
        self._pass_uri(uri=test_uri, file_uri=expected_uri,
                       import_req=self.gd_task_input['import_req'])


class TestImageLock(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageLock, self).setUp()
        self.img_repo = mock.MagicMock()

    @mock.patch('glance.async_.flows.api_image_import.LOG')
    def test_execute_confirms_lock(self, mock_log):
        self.img_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(self.img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        imagelock = import_flow._ImageLock(TASK_ID1, TASK_TYPE, wrapper)
        imagelock.execute()
        mock_log.debug.assert_called_once_with('Image %(image)s import task '
                                               '%(task)s lock confirmed',
                                               {'image': IMAGE_ID1,
                                                'task': TASK_ID1})

    @mock.patch('glance.async_.flows.api_image_import.LOG')
    def test_execute_confirms_lock_not_held(self, mock_log):
        wrapper = import_flow.ImportActionWrapper(self.img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        imagelock = import_flow._ImageLock(TASK_ID1, TASK_TYPE, wrapper)
        self.assertRaises(exception.TaskAbortedError,
                          imagelock.execute)

    @mock.patch('glance.async_.flows.api_image_import.LOG')
    def test_revert_drops_lock(self, mock_log):
        wrapper = import_flow.ImportActionWrapper(self.img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        imagelock = import_flow._ImageLock(TASK_ID1, TASK_TYPE, wrapper)
        with mock.patch.object(wrapper, 'drop_lock_for_task') as mock_drop:
            imagelock.revert(None)
            mock_drop.assert_called_once_with()
        mock_log.debug.assert_called_once_with('Image %(image)s import task '
                                               '%(task)s dropped its lock '
                                               'after failure',
                                               {'image': IMAGE_ID1,
                                                'task': TASK_ID1})

    @mock.patch('glance.async_.flows.api_image_import.LOG')
    def test_revert_drops_lock_missing(self, mock_log):
        wrapper = import_flow.ImportActionWrapper(self.img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        imagelock = import_flow._ImageLock(TASK_ID1, TASK_TYPE, wrapper)
        with mock.patch.object(wrapper, 'drop_lock_for_task') as mock_drop:
            mock_drop.side_effect = exception.NotFound()
            imagelock.revert(None)
        mock_log.warning.assert_called_once_with('Image %(image)s import task '
                                                 '%(task)s lost its lock '
                                                 'during execution!',
                                                 {'image': IMAGE_ID1,
                                                  'task': TASK_ID1})


class TestImportToStoreTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportToStoreTask, self).setUp()
        self.gateway = gateway.Gateway()
        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)
        self.img_factory = self.gateway.get_image_factory(self.context)

    def test_execute(self):
        wrapper = mock.MagicMock()
        action = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper.__enter__.return_value = action
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        # Assert file_path is honored
        with mock.patch.object(image_import, '_execute') as mock_execute:
            image_import.execute(mock.sentinel.path)
            mock_execute.assert_called_once_with(action, mock.sentinel.path)

        # Assert file_path is optional
        with mock.patch.object(image_import, '_execute') as mock_execute:
            image_import.execute()
            mock_execute.assert_called_once_with(action, None)

    def test_execute_body_with_store(self):
        image = mock.MagicMock()
        img_repo = mock.MagicMock()
        img_repo.get.return_value = image
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        action = mock.MagicMock()
        image_import._execute(action, mock.sentinel.path)
        action.set_image_data.assert_called_once_with(
            mock.sentinel.path,
            TASK_ID1, backend='store1',
            set_active=True,
            callback=image_import._status_callback)
        action.remove_importing_stores(['store1'])

    def test_execute_body_with_store_no_path(self):
        image = mock.MagicMock()
        img_repo = mock.MagicMock()
        img_repo.get.return_value = image
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        action = mock.MagicMock()
        image_import._execute(action, None)
        action.set_image_data.assert_called_once_with(
            'http://url',
            TASK_ID1, backend='store1',
            set_active=True,
            callback=image_import._status_callback)
        action.remove_importing_stores(['store1'])

    def test_execute_body_without_store(self):
        image = mock.MagicMock()
        img_repo = mock.MagicMock()
        img_repo.get.return_value = image
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  None, False,
                                                  True)
        action = mock.MagicMock()
        image_import._execute(action, mock.sentinel.path)
        action.set_image_data.assert_called_once_with(
            mock.sentinel.path,
            TASK_ID1, backend=None,
            set_active=True,
            callback=image_import._status_callback)
        action.remove_importing_stores.assert_not_called()

    @mock.patch('glance.async_.flows.api_image_import.LOG.debug')
    @mock.patch('oslo_utils.timeutils.now')
    def test_status_callback_limits_rate(self, mock_now, mock_log):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        task_repo.get.return_value.status = 'processing'
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  None, False,
                                                  True)

        expected_calls = []
        log_call = mock.call('Image import %(image_id)s copied %(copied)i MiB',
                             {'image_id': IMAGE_ID1,
                              'copied': 0})
        action = mock.MagicMock(image_id=IMAGE_ID1)

        mock_now.return_value = 1000
        image_import._status_callback(action, 32, 32)
        # First call will emit immediately because we only ran __init__
        # which sets the last status to zero
        expected_calls.append(log_call)
        mock_log.assert_has_calls(expected_calls)

        image_import._status_callback(action, 32, 64)
        # Second call will not emit any other logs because no time
        # has passed
        mock_log.assert_has_calls(expected_calls)

        mock_now.return_value += 190
        image_import._status_callback(action, 32, 96)
        # Third call will not emit any other logs because not enough
        # time has passed
        mock_log.assert_has_calls(expected_calls)

        mock_now.return_value += 300
        image_import._status_callback(action, 32, 128)
        # Fourth call will emit because we crossed five minutes
        expected_calls.append(log_call)
        mock_log.assert_has_calls(expected_calls)

        mock_now.return_value += 150
        image_import._status_callback(action, 32, 128)
        # Fifth call will not emit any other logs because not enough
        # time has passed
        mock_log.assert_has_calls(expected_calls)

        mock_now.return_value += 3600
        image_import._status_callback(action, 32, 128)
        # Sixth call will emit because we crossed five minutes
        expected_calls.append(log_call)
        mock_log.assert_has_calls(expected_calls)

    def test_raises_when_image_deleted(self):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        image = self.img_factory.new_image(image_id=UUID1)
        image.status = "deleted"
        img_repo.get.return_value = image
        self.assertRaises(exception.ImportTaskError, image_import.execute)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_remove_store_from_property(self, mock_import):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", True,
                                                  True)
        extra_properties = {"os_glance_importing_to_stores": "store1,store2",
                            "os_glance_import_task": TASK_ID1}
        image = self.img_factory.new_image(image_id=UUID1,
                                           extra_properties=extra_properties)
        img_repo.get.return_value = image
        image_import.execute()
        self.assertEqual(
            image.extra_properties['os_glance_importing_to_stores'], "store2")

    def test_revert_updates_status_keys(self):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", True,
                                                  True)
        extra_properties = {"os_glance_importing_to_stores": "store1,store2",
                            "os_glance_import_task": TASK_ID1}
        image = self.img_factory.new_image(image_id=UUID1,
                                           extra_properties=extra_properties)
        img_repo.get.return_value = image

        fail_key = 'os_glance_failed_import'
        pend_key = 'os_glance_importing_to_stores'

        image_import.revert(None)
        self.assertEqual('store2', image.extra_properties[pend_key])

        try:
            raise Exception('foo')
        except Exception:
            fake_exc_info = sys.exc_info()

        extra_properties = {"os_glance_importing_to_stores": "store1,store2"}
        image_import.revert(taskflow.types.failure.Failure(fake_exc_info))
        self.assertEqual('store2', image.extra_properties[pend_key])
        self.assertEqual('store1', image.extra_properties[fail_key])

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_raises_when_all_stores_must_succeed(self, mock_import):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", True,
                                                  True)
        extra_properties = {'os_glance_import_task': TASK_ID1}
        image = self.img_factory.new_image(image_id=UUID1,
                                           extra_properties=extra_properties)
        img_repo.get.return_value = image
        mock_import.set_image_data.side_effect = \
            cursive_exception.SignatureVerificationError(
                "Signature verification failed")
        self.assertRaises(cursive_exception.SignatureVerificationError,
                          image_import.execute)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_doesnt_raise_when_not_all_stores_must_succeed(self, mock_import):
        img_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, wrapper,
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        extra_properties = {'os_glance_import_task': TASK_ID1}
        image = self.img_factory.new_image(image_id=UUID1,
                                           extra_properties=extra_properties)
        img_repo.get.return_value = image
        mock_import.set_image_data.side_effect = \
            cursive_exception.SignatureVerificationError(
                "Signature verification failed")
        try:
            image_import.execute()
            self.assertEqual(image.extra_properties['os_glance_failed_import'],
                             "store1")
        except cursive_exception.SignatureVerificationError:
            self.fail("Exception shouldn't be raised")

    @mock.patch('glance.common.scripts.utils.get_task')
    def test_status_callback_updates_task_message(self, mock_get):
        task_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, mock.MagicMock(),
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        task = mock.MagicMock()
        task.status = 'processing'
        mock_get.return_value = task
        action = mock.MagicMock()
        image_import._status_callback(action, 128, 256 * units.Mi)
        mock_get.assert_called_once_with(task_repo, TASK_ID1)
        task_repo.save.assert_called_once_with(task)
        self.assertEqual(_('Copied %i MiB' % 256), task.message)

    @mock.patch('glance.common.scripts.utils.get_task')
    def test_status_aborts_missing_task(self, mock_get):
        task_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, mock.MagicMock(),
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        mock_get.return_value = None
        action = mock.MagicMock()
        self.assertRaises(exception.TaskNotFound,
                          image_import._status_callback,
                          action, 128, 256 * units.Mi)
        mock_get.assert_called_once_with(task_repo, TASK_ID1)
        task_repo.save.assert_not_called()

    @mock.patch('glance.common.scripts.utils.get_task')
    def test_status_aborts_invalid_task_state(self, mock_get):
        task_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  task_repo, mock.MagicMock(),
                                                  "http://url",
                                                  "store1", False,
                                                  True)
        task = mock.MagicMock()
        task.status = 'failed'
        mock_get.return_value = task
        action = mock.MagicMock()
        self.assertRaises(exception.TaskAbortedError,
                          image_import._status_callback,
                          action, 128, 256 * units.Mi)
        mock_get.assert_called_once_with(task_repo, TASK_ID1)
        task_repo.save.assert_not_called()


class TestDeleteFromFS(test_utils.BaseTestCase):
    def test_delete_with_backends_deletes(self):
        task = import_flow._DeleteFromFS(TASK_ID1, TASK_TYPE)
        self.config(enabled_backends='file:foo')
        with mock.patch.object(import_flow.store_api, 'delete') as mock_del:
            task.execute(mock.sentinel.path)
            mock_del.assert_called_once_with(
                mock.sentinel.path,
                'os_glance_staging_store')

    def test_delete_with_backends_delete_fails(self):
        self.config(enabled_backends='file:foo')
        task = import_flow._DeleteFromFS(TASK_ID1, TASK_TYPE)
        with mock.patch.object(import_flow.store_api, 'delete') as mock_del:
            mock_del.side_effect = store_exceptions.NotFound(image=IMAGE_ID1,
                                                             message='Testing')
            # If we didn't swallow this we would explode here
            task.execute(mock.sentinel.path)
            mock_del.assert_called_once_with(
                mock.sentinel.path,
                'os_glance_staging_store')

            # Raise something unexpected and make sure it bubbles up
            mock_del.side_effect = RuntimeError
            self.assertRaises(RuntimeError,
                              task.execute, mock.sentinel.path)

    @mock.patch('os.path.exists')
    @mock.patch('os.unlink')
    def test_delete_without_backends_exists(self, mock_unlink, mock_exists):
        mock_exists.return_value = True
        task = import_flow._DeleteFromFS(TASK_ID1, TASK_TYPE)
        task.execute('1234567foo')
        # FIXME(danms): I have no idea why the code arbitrarily snips
        # the first seven characters from the path. Need a comment or
        # *something*.
        mock_unlink.assert_called_once_with('foo')

        mock_unlink.reset_mock()
        mock_unlink.side_effect = OSError(123, 'failed')
        # Make sure we swallow the OSError and don't explode
        task.execute('1234567foo')

    @mock.patch('os.path.exists')
    @mock.patch('os.unlink')
    def test_delete_without_backends_missing(self, mock_unlink, mock_exists):
        mock_exists.return_value = False
        task = import_flow._DeleteFromFS(TASK_ID1, TASK_TYPE)
        task.execute('foo')
        mock_unlink.assert_not_called()


class TestImportCopyImageTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportCopyImageTask, self).setUp()

        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_init_copy_flow_as_non_owner(self, mock_import):
        img_repo = mock.MagicMock()
        admin_repo = mock.MagicMock()

        fake_req = {"method": {"name": "copy-image"},
                    "backend": ['cheap']}

        fake_img = mock.MagicMock()
        fake_img.id = IMAGE_ID1
        fake_img.status = 'active'
        fake_img.extra_properties = {'os_glance_import_task': TASK_ID1}
        admin_repo.get.return_value = fake_img

        import_flow.get_flow(task_id=TASK_ID1,
                             task_type=TASK_TYPE,
                             task_repo=mock.MagicMock(),
                             image_repo=img_repo,
                             admin_repo=admin_repo,
                             image_id=IMAGE_ID1,
                             import_req=fake_req,
                             backend=['cheap'])

        # Assert that we saved the image with the admin repo instead of the
        # user-context one at the end of get_flow() when we initialize the
        # parameters.
        admin_repo.save.assert_called_once_with(fake_img, 'active')
        img_repo.save.assert_not_called()


class TestVerifyImageStateTask(test_utils.BaseTestCase):
    def test_verify_active_status(self):
        fake_img = mock.MagicMock(status='active',
                                  extra_properties={
                                      'os_glance_import_task': TASK_ID1})
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value = fake_img
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)

        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             wrapper, 'anything!')

        task.execute()

        fake_img.status = 'importing'
        self.assertRaises(import_flow._NoStoresSucceeded,
                          task.execute)

    def test_revert_copy_status_unchanged(self):
        wrapper = mock.MagicMock()
        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             wrapper, 'copy-image')
        task.revert(mock.sentinel.result)

        # If we are doing copy-image, no state update should be made
        wrapper.__enter__.return_value.set_image_status.assert_not_called()

    def test_reverts_state_nocopy(self):
        wrapper = mock.MagicMock()
        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             wrapper, 'glance-direct')
        task.revert(mock.sentinel.result)

        # Except for copy-image, image state should revert to queued
        action = wrapper.__enter__.return_value
        action.set_image_status.assert_called_once_with('queued')


class TestImportActionWrapper(test_utils.BaseTestCase):
    def test_wrapper_success(self):
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)
        with wrapper as action:
            self.assertIsInstance(action, import_flow._ImportActions)
        mock_repo.get.assert_has_calls([mock.call(IMAGE_ID1),
                                        mock.call(IMAGE_ID1)])
        mock_repo.save.assert_called_once_with(
            mock_repo.get.return_value,
            mock_repo.get.return_value.status)

    def test_wrapper_failure(self):
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)

        class SpecificError(Exception):
            pass

        try:
            with wrapper:
                raise SpecificError('some failure')
        except SpecificError:
            # NOTE(danms): Make sure we only caught the test exception
            # and aren't hiding anything else
            pass

        mock_repo.get.assert_called_once_with(IMAGE_ID1)
        mock_repo.save.assert_not_called()

    @mock.patch.object(import_flow, 'LOG')
    def test_wrapper_logs_status(self, mock_log):
        mock_repo = mock.MagicMock()
        mock_image = mock_repo.get.return_value
        mock_image.extra_properties = {'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)

        mock_image.status = 'foo'
        with wrapper as action:
            action.set_image_status('bar')

        mock_log.debug.assert_called_once_with(
            'Image %(image_id)s status changing from '
            '%(old_status)s to %(new_status)s',
            {'image_id': IMAGE_ID1,
             'old_status': 'foo',
             'new_status': 'bar'})
        self.assertEqual('bar', mock_image.status)

    def test_image_id_property(self):
        mock_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)
        self.assertEqual(IMAGE_ID1, wrapper.image_id)

    def test_drop_lock_for_task(self):
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)
        wrapper.drop_lock_for_task()
        mock_repo.delete_property_atomic.assert_called_once_with(
            mock_repo.get.return_value, 'os_glance_import_task', TASK_ID1)

    def test_assert_task_lock(self):
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value.extra_properties = {
            'os_glance_import_task': TASK_ID1}
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)
        wrapper.assert_task_lock()

        # Try again with a different task ID and it should fail
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  'foo')
        self.assertRaises(exception.TaskAbortedError,
                          wrapper.assert_task_lock)

    def _grab_image(self, wrapper):
        with wrapper:
            pass

    @mock.patch.object(import_flow, 'LOG')
    def test_check_task_lock(self, mock_log):
        mock_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1,
                                                  TASK_ID1)
        image = mock.MagicMock(image_id=IMAGE_ID1)
        image.extra_properties = {'os_glance_import_task': TASK_ID1}
        mock_repo.get.return_value = image
        self._grab_image(wrapper)
        mock_log.error.assert_not_called()

        image.extra_properties['os_glance_import_task'] = 'somethingelse'
        self.assertRaises(exception.TaskAbortedError,
                          self._grab_image, wrapper)
        mock_log.error.assert_called_once_with(
            'Image %(image)s import task %(task)s attempted to take action on '
            'image, but other task %(other)s holds the lock; Aborting.',
            {'image': image.image_id,
             'task': TASK_ID1,
             'other': 'somethingelse'})


class TestImportActions(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImportActions, self).setUp()
        self.image = mock.MagicMock()
        self.image.image_id = IMAGE_ID1
        self.image.status = 'active'
        self.image.extra_properties = {'speed': '88mph'}
        self.image.checksum = mock.sentinel.checksum
        self.image.os_hash_algo = mock.sentinel.hash_algo
        self.image.os_hash_value = mock.sentinel.hash_value
        self.image.size = mock.sentinel.size
        self.actions = import_flow._ImportActions(self.image)

    def test_image_property_proxies(self):
        self.assertEqual(IMAGE_ID1, self.actions.image_id)
        self.assertEqual('active', self.actions.image_status)

    def test_merge_store_list(self):
        # Addition with no existing property works
        self.actions.merge_store_list('stores', ['foo', 'bar'])
        self.assertEqual({'speed': '88mph',
                          'stores': 'bar,foo'},
                         self.image.extra_properties)

        # Addition adds to the list
        self.actions.merge_store_list('stores', ['baz'])
        self.assertEqual('bar,baz,foo', self.image.extra_properties['stores'])

        # Removal preserves the rest
        self.actions.merge_store_list('stores', ['foo'], subtract=True)
        self.assertEqual('bar,baz', self.image.extra_properties['stores'])

        # Duplicates aren't duplicated
        self.actions.merge_store_list('stores', ['bar'])
        self.assertEqual('bar,baz', self.image.extra_properties['stores'])

        # Removing the last store leaves the key empty but present
        self.actions.merge_store_list('stores', ['baz', 'bar'], subtract=True)
        self.assertEqual('', self.image.extra_properties['stores'])

        # Make sure we ignore falsey stores
        self.actions.merge_store_list('stores', ['', None])
        self.assertEqual('', self.image.extra_properties['stores'])

    @mock.patch.object(import_flow, 'LOG')
    def test_merge_store_logs_info(self, mock_log):
        # Removal from non-present key logs debug, but does not fail
        self.actions.merge_store_list('stores', ['foo,bar'], subtract=True)
        mock_log.debug.assert_has_calls([
            mock.call(
                'Stores %(stores)s not in %(key)s for image %(image_id)s',
                {'image_id': IMAGE_ID1,
                 'key': 'stores',
                 'stores': 'foo,bar'}),
            mock.call(
                'Image %(image_id)s %(key)s=%(stores)s',
                {'image_id': IMAGE_ID1,
                 'key': 'stores',
                 'stores': ''}),
        ])

        mock_log.debug.reset_mock()

        self.actions.merge_store_list('stores', ['foo'])
        self.assertEqual('foo', self.image.extra_properties['stores'])

        mock_log.debug.reset_mock()

        # Removal from a list where store is not present logs debug,
        # but does not fail
        self.actions.merge_store_list('stores', ['bar'], subtract=True)
        self.assertEqual('foo', self.image.extra_properties['stores'])
        mock_log.debug.assert_has_calls([
            mock.call(
                'Stores %(stores)s not in %(key)s for image %(image_id)s',
                {'image_id': IMAGE_ID1,
                 'key': 'stores',
                 'stores': 'bar'}),
            mock.call(
                'Image %(image_id)s %(key)s=%(stores)s',
                {'image_id': IMAGE_ID1,
                 'key': 'stores',
                 'stores': 'foo'}),
        ])

    def test_store_list_helpers(self):
        self.actions.add_importing_stores(['foo', 'bar', 'baz'])
        self.actions.remove_importing_stores(['bar'])
        self.actions.add_failed_stores(['foo', 'bar'])
        self.actions.remove_failed_stores(['foo'])
        self.assertEqual({'speed': '88mph',
                          'os_glance_importing_to_stores': 'baz,foo',
                          'os_glance_failed_import': 'bar'},
                         self.image.extra_properties)

    @mock.patch.object(image_import, 'set_image_data')
    def test_set_image_data(self, mock_sid):
        self.assertEqual(mock_sid.return_value,
                         self.actions.set_image_data(
                             mock.sentinel.uri, mock.sentinel.task_id,
                             mock.sentinel.backend, mock.sentinel.set_active))
        mock_sid.assert_called_once_with(
            self.image, mock.sentinel.uri, mock.sentinel.task_id,
            backend=mock.sentinel.backend, set_active=mock.sentinel.set_active,
            callback=None)

    @mock.patch.object(image_import, 'set_image_data')
    def test_set_image_data_with_callback(self, mock_sid):
        def fake_set_image_data(image, uri, task_id, backend=None,
                                set_active=False,
                                callback=None):
            callback(mock.sentinel.chunk, mock.sentinel.total)

        mock_sid.side_effect = fake_set_image_data

        callback = mock.MagicMock()
        self.actions.set_image_data(mock.sentinel.uri, mock.sentinel.task_id,
                                    mock.sentinel.backend,
                                    mock.sentinel.set_active,
                                    callback=callback)

        # Make sure our callback was triggered through the functools.partial
        # to include the original params and the action wrapper
        callback.assert_called_once_with(self.actions,
                                         mock.sentinel.chunk,
                                         mock.sentinel.total)

    def test_remove_location_for_store(self):
        self.image.locations = [
            {},
            {'metadata': {}},
            {'metadata': {'store': 'foo'}},
            {'metadata': {'store': 'bar'}},
        ]

        self.actions.remove_location_for_store('foo')
        self.assertEqual([{}, {'metadata': {}},
                          {'metadata': {'store': 'bar'}}],
                         self.image.locations)

        # Add a second definition for bar and make sure only one is removed
        self.image.locations.append({'metadata': {'store': 'bar'}})
        self.actions.remove_location_for_store('bar')
        self.assertEqual([{}, {'metadata': {}},
                          {'metadata': {'store': 'bar'}}],
                         self.image.locations)

    def test_remove_location_for_store_last_location(self):
        self.image.locations = [{'metadata': {'store': 'foo'}}]
        self.actions.remove_location_for_store('foo')
        self.assertEqual([], self.image.locations)
        self.assertIsNone(self.image.checksum)
        self.assertIsNone(self.image.os_hash_algo)
        self.assertIsNone(self.image.os_hash_value)
        self.assertIsNone(self.image.size)

    @mock.patch.object(import_flow, 'LOG')
    def test_remove_location_for_store_pop_failures(self, mock_log):
        class TestList(list):
            def pop(self):
                pass

        self.image.locations = TestList([{'metadata': {'store': 'foo'}}])
        with mock.patch.object(self.image.locations, 'pop',
                               new_callable=mock.PropertyMock) as mock_pop:

            mock_pop.side_effect = store_exceptions.NotFound(image='image')
            self.actions.remove_location_for_store('foo')
            mock_log.warning.assert_called_once_with(
                _('Error deleting from store foo when reverting.'))
            mock_log.warning.reset_mock()

            mock_pop.side_effect = store_exceptions.Forbidden()
            self.actions.remove_location_for_store('foo')
            mock_log.warning.assert_called_once_with(
                _('Error deleting from store foo when reverting.'))
            mock_log.warning.reset_mock()

            mock_pop.side_effect = Exception
            self.actions.remove_location_for_store('foo')
            mock_log.warning.assert_called_once_with(
                _('Unexpected exception when deleting from store foo.'))
            mock_log.warning.reset_mock()


@mock.patch('glance.common.scripts.utils.get_task')
class TestCompleteTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestCompleteTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.wrapper = mock.MagicMock(image_id=IMAGE_ID1)

    def test_execute(self, mock_get_task):
        complete = import_flow._CompleteTask(TASK_ID1, TASK_TYPE,
                                             self.task_repo, self.wrapper)
        mock_get_task.return_value = self.task
        complete.execute()
        mock_get_task.assert_called_once_with(self.task_repo,
                                              TASK_ID1)
        self.task.succeed.assert_called_once_with({'image_id': IMAGE_ID1})
        self.task_repo.save.assert_called_once_with(self.task)
        self.wrapper.drop_lock_for_task.assert_called_once_with()

    def test_execute_no_task(self, mock_get_task):
        mock_get_task.return_value = None
        complete = import_flow._CompleteTask(TASK_ID1, TASK_TYPE,
                                             self.task_repo, self.wrapper)
        complete.execute()
        self.task_repo.save.assert_not_called()
        self.wrapper.drop_lock_for_task.assert_called_once_with()

    def test_execute_succeed_fails(self, mock_get_task):
        mock_get_task.return_value = self.task
        self.task.succeed.side_effect = Exception('testing')
        complete = import_flow._CompleteTask(TASK_ID1, TASK_TYPE,
                                             self.task_repo, self.wrapper)
        complete.execute()
        self.task.fail.assert_called_once_with(
            _('Error: <class \'Exception\'>: testing'))
        self.task_repo.save.assert_called_once_with(self.task)
        self.wrapper.drop_lock_for_task.assert_called_once_with()

    def test_execute_drop_lock_fails(self, mock_get_task):
        mock_get_task.return_value = self.task
        self.wrapper.drop_lock_for_task.side_effect = exception.NotFound()
        complete = import_flow._CompleteTask(TASK_ID1, TASK_TYPE,
                                             self.task_repo, self.wrapper)
        with mock.patch('glance.async_.flows.api_image_import.LOG') as m_log:
            complete.execute()
            m_log.error.assert_called_once_with('Image %(image)s import task '
                                                '%(task)s did not hold the '
                                                'lock upon completion!',
                                                {'image': IMAGE_ID1,
                                                 'task': TASK_ID1})
        self.task.succeed.assert_called_once_with({'image_id': IMAGE_ID1})
