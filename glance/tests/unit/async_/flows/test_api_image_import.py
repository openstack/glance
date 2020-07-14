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
from glance.common.scripts.image_import import main as image_import
from glance import context
from glance import gateway
import glance.tests.utils as test_utils
from glance_store import exceptions as store_exceptions

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
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  wrapper, "http://url",
                                                  "store1", False,
                                                  True)
        image = self.img_factory.new_image(image_id=UUID1)
        image.status = "deleted"
        img_repo.get.return_value = image
        self.assertRaises(ImportTaskError, image_import.execute)

    @mock.patch("glance.async_.flows.api_image_import.image_import")
    def test_remove_store_from_property(self, mock_import):
        img_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  wrapper, "http://url",
                                                  "store1", True,
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
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  wrapper, "http://url",
                                                  "store1", True,
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
        wrapper = import_flow.ImportActionWrapper(img_repo, IMAGE_ID1)
        image_import = import_flow._ImportToStore(TASK_ID1, TASK_TYPE,
                                                  wrapper, "http://url",
                                                  "store1", False,
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
        fake_img.extra_properties = {}
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


class TestImportActionWrapper(test_utils.BaseTestCase):
    def test_wrapper_success(self):
        mock_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1)
        with wrapper as action:
            self.assertIsInstance(action, import_flow._ImportActions)
        mock_repo.get.assert_called_once_with(IMAGE_ID1)
        mock_repo.save.assert_called_once_with(
            mock_repo.get.return_value,
            mock_repo.get.return_value.status)

    def test_wrapper_failure(self):
        mock_repo = mock.MagicMock()
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1)

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
        wrapper = import_flow.ImportActionWrapper(mock_repo, IMAGE_ID1)

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
            backend=mock.sentinel.backend, set_active=mock.sentinel.set_active)

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
