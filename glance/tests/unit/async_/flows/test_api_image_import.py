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

from unittest import mock

from glance_store import exceptions as store_exceptions
from oslo_config import cfg

import glance.async_.flows.api_image_import as import_flow
from glance.common.exception import ImportTaskError
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


class TestImportToStoreTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImportToStoreTask, self).setUp()
        self.gateway = gateway.Gateway()
        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)
        self.img_factory = self.gateway.get_image_factory(self.context)

    def test_raises_when_image_deleted(self):
        img_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  img_repo, "http://url",
                                                  IMAGE_ID1, "store1", False,
                                                  True)
        image = self.img_factory.new_image(image_id=UUID1)
        image.status = "deleted"
        img_repo.get.return_value = image
        self.assertRaises(ImportTaskError, image_import.execute)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_remove_store_from_property(self, mock_import):
        img_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  img_repo, "http://url",
                                                  IMAGE_ID1, "store1", True,
                                                  True)
        extra_properties = {"os_glance_importing_to_stores": "store1,store2"}
        image = self.img_factory.new_image(image_id=UUID1,
                                           extra_properties=extra_properties)
        img_repo.get.return_value = image
        image_import.execute()
        self.assertEqual(
            image.extra_properties['os_glance_importing_to_stores'], "store2")

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_raises_when_all_stores_must_succeed(self, mock_import):
        img_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  img_repo, "http://url",
                                                  IMAGE_ID1, "store1", True,
                                                  True)
        image = self.img_factory.new_image(image_id=UUID1)
        img_repo.get.return_value = image
        mock_import.set_image_data.side_effect = \
            cursive_exception.SignatureVerificationError(
                "Signature verification failed")
        self.assertRaises(cursive_exception.SignatureVerificationError,
                          image_import.execute)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_doesnt_raise_when_not_all_stores_must_succeed(self, mock_import):
        img_repo = mock.MagicMock()
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  img_repo, "http://url",
                                                  IMAGE_ID1, "store1", False,
                                                  True)
        image = self.img_factory.new_image(image_id=UUID1)
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


class TestVerifyImageStateTask(test_utils.BaseTestCase):
    def test_verify_active_status(self):
        fake_img = mock.MagicMock(status='active')
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value = fake_img

        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             mock_repo, IMAGE_ID1,
                                             'anything!')

        task.execute()

        fake_img.status = 'importing'
        self.assertRaises(import_flow._NoStoresSucceeded,
                          task.execute)

    def test_revert_copy_status_unchanged(self):
        fake_img = mock.MagicMock(status='active')
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value = fake_img
        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             mock_repo, IMAGE_ID1,
                                             'copy-image')
        task.revert(mock.sentinel.result)

        # If we are doing copy-image, no state update should be made
        mock_repo.save_image.assert_not_called()

    def test_reverts_state_nocopy(self):
        fake_img = mock.MagicMock(status='importing')
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value = fake_img
        task = import_flow._VerifyImageState(TASK_ID1, TASK_TYPE,
                                             mock_repo, IMAGE_ID1,
                                             'glance-direct')
        task.revert(mock.sentinel.result)

        # Except for copy-image, image state should revert to queued
        mock_repo.save_image.assert_called_once()
