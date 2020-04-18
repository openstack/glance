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
