# Copyright 2026 OpenStack Foundation
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

import threading
from unittest import mock

from oslo_config import cfg

from glance.async_.flows import parallel_api_image_import as pstores
from glance.common import exception
import glance.tests.utils as test_utils

CONF = cfg.CONF

_UPLOAD_RESULT = {
    'store': 'a',
    'url': 'file:///a',
    'metadata': {'store': 'a'},
    'size': 10,
    'checksum': 'c',
    'os_hash_value': 'h',
}


class TestParallelImportHelpers(test_utils.BaseTestCase):

    def test_pending_placeholder_url(self):
        self.assertTrue(
            pstores._placeholder_location_url('img', 'fs').startswith(
                'pending://parallel-import/'))
        self.assertTrue(
            pstores._placeholder_location_url('img', None).endswith('/_'))

    def test_location_metadata(self):
        self.assertEqual({}, pstores._location_metadata({}))
        self.assertEqual({}, pstores._location_metadata({'metadata': None}))
        self.assertEqual(
            {'k': 'v'}, pstores._location_metadata({'metadata': {'k': 'v'}}))
        self.assertEqual({}, pstores._location_metadata({'metadata': 'bad'}))

    def test_should_use_parallel_disabled_by_default(self):
        self.config(enabled_backends={'a': 'file', 'b': 'file'})
        self.assertFalse(pstores.should_use_parallel_store_import(
            'glance-direct', ['a', 'b']))

    def test_should_use_parallel_when_configured(self):
        self.config(enabled_backends={'a': 'file', 'b': 'file'})
        self.config(max_parallel_stores=2, group='image_import_opts')
        self.assertTrue(pstores.should_use_parallel_store_import(
            'web-download', ['a', 'b']))
        self.assertTrue(pstores.should_use_parallel_store_import(
            'glance-download', ['a', 'b']))
        self.assertFalse(pstores.should_use_parallel_store_import(
            'copy-image', ['a', 'b']))
        self.assertFalse(pstores.should_use_parallel_store_import(
            'web-download', ['a']))
        self.assertFalse(pstores.should_use_parallel_store_import(
            'web-download', []))

    def test_should_use_parallel_requires_enabled_backends(self):
        self.config(max_parallel_stores=3, group='image_import_opts')
        self.assertFalse(pstores.should_use_parallel_store_import(
            'glance-direct', ['a', 'b']))

    def test_is_parallel_in_progress_db_location(self):
        marker = {
            pstores.LOC_META_IMPORT_TAG: pstores.LOC_META_IMPORT_TAG_VALUE,
        }
        self.assertTrue(pstores._is_in_progress_import_location({
            'status': 'pending', 'metadata': marker}))
        self.assertTrue(pstores._is_in_progress_import_location({
            'status': 'uploading', 'metadata': marker}))
        self.assertFalse(pstores._is_in_progress_import_location({
            'status': 'active', 'metadata': marker}))
        self.assertFalse(pstores._is_in_progress_import_location({
            'status': 'pending', 'metadata': {}}))
        self.assertFalse(pstores._is_in_progress_import_location({
            'status': 'pending',
            'metadata': {pstores.LOC_META_IMPORT_TAG: 'other'},
        }))


class TestAddParallelStoreImportTasks(test_utils.BaseTestCase):

    def test_adds_tasks_to_flow(self):
        mock_flow = mock.MagicMock()
        mock_wrapper = mock.MagicMock()
        mock_wrapper.image_id = 'img-1'
        pstores.add_parallel_store_import_tasks(
            mock_flow, 'task-1', 'api_image_import', mock.MagicMock(),
            mock_wrapper, 'file:///staged', ['a', 'b'], True,
            'glance-direct', mock.MagicMock(), mock.MagicMock())
        self.assertEqual(2, mock_flow.add.call_count)
        verify_task = mock_flow.add.call_args_list[0][0][0]
        import_task = mock_flow.add.call_args_list[1][0][0]
        self.assertIsInstance(verify_task,
                              pstores._VerifyStagedImageSignatureTask)
        self.assertIsInstance(import_task, pstores._ParallelStoreImportTask)


def _mock_image(image_id='img', size=None, checksum=None,
                container_format='aki', disk_format='aki',
                extra_properties=None):
    image = mock.MagicMock()
    image.image_id = image_id
    image.size = size
    image.checksum = checksum
    image.os_hash_value = None
    image.container_format = container_format
    image.disk_format = disk_format
    image.extra_properties = extra_properties or {}
    return image


class TestVerifyStagedImageSignature(test_utils.BaseTestCase):

    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_create_upload_verifier')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_skips_when_image_is_unsigned(
            self, mock_script, mock_create_verifier):
        mock_create_verifier.return_value = None
        pstores._verify_staged_image_signature(
            mock.MagicMock(), {}, 'file:///staged', 'img-1')
        mock_script.get_image_data_iter.assert_not_called()

    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_create_upload_verifier')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_verifies_staged_data_once(
            self, mock_script, mock_create_verifier):
        mock_verifier = mock.MagicMock()
        mock_create_verifier.return_value = mock_verifier
        mock_script.get_image_data_iter.return_value = (iter([b'data']), 4)

        pstores._verify_staged_image_signature(
            mock.MagicMock(), {'signed': True}, 'file:///staged', 'img-1')

        mock_verifier.update.assert_called_once_with(b'data')
        mock_verifier.verify.assert_called_once_with()

    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_create_upload_verifier')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_invalid_signature_raises(
            self, mock_script, mock_create_verifier):
        from cryptography import exceptions as crypto_exception
        from cursive import exception as cursive_exception

        mock_verifier = mock.MagicMock()
        mock_verifier.verify.side_effect = crypto_exception.InvalidSignature()
        mock_create_verifier.return_value = mock_verifier
        mock_script.get_image_data_iter.return_value = (iter([b'data']), 4)

        self.assertRaises(
            cursive_exception.SignatureVerificationError,
            pstores._verify_staged_image_signature,
            mock.MagicMock(), {'signed': True}, 'file:///staged', 'img-1')

    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_verify_staged_image_signature')
    def test_task_loads_image_and_verifies_staged_uri(self, mock_verify):
        mock_repo = mock.MagicMock()
        mock_repo.get.return_value = _mock_image(extra_properties={'k': 'v'})
        mock_wrapper = mock.MagicMock()
        task = pstores._VerifyStagedImageSignatureTask(
            'task-1', 'api_image_import', mock.MagicMock(), mock_repo,
            mock_wrapper, 'file:///staged', 'img-1', ['a', 'b'])
        task.execute(file_path='file:///override')

        mock_repo.get.assert_called_once_with('img-1')
        mock_verify.assert_called_once_with(
            task.context, {'k': 'v'}, 'file:///override', 'img-1')

    def test_revert_on_failure_resets_image_and_deletes_staging(self):
        import taskflow.types.failure as tf_failure

        mock_wrapper = mock.MagicMock()
        mock_wrapper.__enter__ = mock.MagicMock(return_value=mock_wrapper)
        mock_wrapper.__exit__ = mock.MagicMock(return_value=False)
        mock_action = mock.MagicMock()
        mock_wrapper.__enter__.return_value = mock_action

        task = pstores._VerifyStagedImageSignatureTask(
            'task-1', 'api_image_import', mock.MagicMock(), mock.MagicMock(),
            mock_wrapper, 'file:///staging/img-1', 'img-1', ['a', 'b'])
        fail_result = tf_failure.Failure.from_exception(
            RuntimeError('signature failed'))

        with mock.patch.object(
                pstores, '_delete_staged_import_file') as mock_del:
            task.revert(fail_result, file_path='file:///staging/img-1')

        mock_action.set_image_attribute.assert_called_once_with(
            status='queued')
        mock_action.remove_importing_stores.assert_called_once_with(['a', 'b'])
        mock_action.add_failed_stores.assert_called_once_with(['a', 'b'])
        mock_del.assert_called_once_with('file:///staging/img-1')

    def test_revert_skipped_when_task_succeeded(self):
        mock_wrapper = mock.MagicMock()
        task = pstores._VerifyStagedImageSignatureTask(
            'task-1', 'api_image_import', mock.MagicMock(), mock.MagicMock(),
            mock_wrapper, 'file:///staged', 'img-1', ['a'])

        with mock.patch.object(
                pstores, '_delete_staged_import_file') as mock_del:
            task.revert(None)

        mock_wrapper.__enter__.assert_not_called()
        mock_del.assert_not_called()


class TestUploadToStore(test_utils.BaseTestCase):

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_success(self, mock_script, mock_store_api, mock_sutils):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        mock_store_api.add_with_multihash.return_value = (
            'loc', 99, 'cs', 'hash', {'store': 'x'})
        mock_sutils.get_updated_store_location.return_value = [
            {'url': 'file:///x', 'metadata': {'store': 'x'}}]
        abort = threading.Event()

        out = pstores._import_staged_data_to_store(
            mock.MagicMock(), _mock_image(), 'file:///staged', 'x', 'sha512',
            mock.MagicMock(), 'task-1', abort)

        self.assertEqual(99, out['size'])
        self.assertEqual('cs', out['checksum'])
        self.assertTrue(mock_iter.close.called)
        mock_store_api.add_with_multihash.assert_called_once()
        self.assertNotIn(
            'verifier', mock_store_api.add_with_multihash.call_args.kwargs)

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_rejects_invalid_image_format(
            self, mock_script, mock_store_api, mock_sutils):
        from oslo_utils.imageutils import format_inspector

        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        mock_store_api.add_with_multihash.side_effect = (
            format_inspector.ImageFormatError('bad format'))
        abort = threading.Event()

        self.assertRaises(
            exception.InvalidImageData,
            pstores._import_staged_data_to_store,
            mock.MagicMock(), _mock_image(container_format='bare'),
            'file:///staged', 'x', 'sha512', mock.MagicMock(), 'task-1',
            abort)

    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_create_upload_verifier')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_does_not_verify_signature_per_store(
            self, mock_script, mock_store_api, mock_sutils,
            mock_create_verifier):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        mock_store_api.add_with_multihash.return_value = (
            'loc', 99, 'cs', 'hash', {'store': 'x'})
        mock_sutils.get_updated_store_location.return_value = [
            {'url': 'file:///x', 'metadata': {'store': 'x'}}]
        abort = threading.Event()

        pstores._import_staged_data_to_store(
            mock.MagicMock(),
            _mock_image(extra_properties={'img_signature': 'x'}),
            'file:///staged', 'x', 'sha512', mock.MagicMock(), 'task-1', abort)

        mock_create_verifier.assert_not_called()

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_rejects_checksum_metadata_mismatch(
            self, mock_script, mock_store_api, mock_sutils):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        mock_store_api.add_with_multihash.return_value = (
            'loc', 99, 'wrong', 'hash', {'store': 'x'})
        mock_sutils.get_updated_store_location.return_value = [
            {'url': 'file:///x', 'metadata': {'store': 'x'}}]
        abort = threading.Event()

        self.assertRaises(
            exception.UploadException,
            pstores._import_staged_data_to_store,
            mock.MagicMock(), _mock_image(checksum='expected'),
            'file:///staged', 'x', 'sha512', mock.MagicMock(), 'task-1', abort)

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_rejects_staged_size_mismatch(
            self, mock_script, mock_store_api, mock_sutils):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        abort = threading.Event()
        image = _mock_image(size=50)

        self.assertRaises(
            exception.ImportTaskError,
            pstores._import_staged_data_to_store,
            mock.MagicMock(), image, 'file:///staged', 'x', 'sha512',
            mock.MagicMock(), 'task-1', abort)
        mock_store_api.add_with_multihash.assert_not_called()

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_aborts_when_abort_event_set(self, mock_script, mock_store,
                                                mock_sutils):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        abort = threading.Event()
        abort.set()

        def fake_callback_iter(data, callback, min_interval=60):
            callback(1, 1)
            return data

        mock_script.CallbackIterator.side_effect = fake_callback_iter
        mock_sutils.get_updated_store_location.return_value = [
            {'url': 'u', 'metadata': {}}]

        self.assertRaises(
            exception.TaskAbortedError,
            pstores._import_staged_data_to_store,
            mock.MagicMock(), _mock_image(), 'file:///staged', 'x', 'sha512',
            mock.MagicMock(), 'task-1', abort)

    @mock.patch('glance.async_.flows.parallel_api_image_import.store_utils')
    @mock.patch('glance.async_.flows.parallel_api_image_import.store_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.script_utils')
    def test_upload_aborts_when_task_not_processing(
            self, mock_script, mock_store, mock_sutils):
        mock_iter = mock.MagicMock()
        mock_script.get_image_data_iter.return_value = (mock_iter, 99)
        mock_task_repo = mock.MagicMock()
        mock_task_repo.get.return_value = mock.MagicMock(status='failure')

        def fake_callback_iter(data, callback, min_interval=60):
            callback(1, 1)
            return data

        mock_script.CallbackIterator.side_effect = fake_callback_iter
        abort = threading.Event()

        self.assertRaises(
            exception.TaskAbortedError,
            pstores._import_staged_data_to_store,
            mock.MagicMock(), _mock_image(), 'file:///staged', 'x', 'sha512',
            mock_task_repo, 'task-1', abort)


class TestParallelMultiStoreImportTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestParallelMultiStoreImportTask, self).setUp()
        self.image_id = '41f5b3b0-f54c-4cef-bd45-ce3e376a142f'
        self.task_id = 'dbbe7231-020f-4311-87e1-5aaa6da56c02'
        self.mock_task_repo = mock.MagicMock()
        self.mock_image_repo = mock.MagicMock()
        self.mock_image = self.mock_image_repo.get.return_value
        self.mock_image.image_id = self.image_id
        self.mock_image.os_hash_algo = 'sha512'
        self.mock_action_wrapper = mock.MagicMock()
        self.mock_action_wrapper.image_id = self.image_id
        self.mock_action = mock.MagicMock()
        self.mock_action._image = mock.MagicMock()
        self.mock_action._image.locations = []
        self.mock_action_wrapper.__enter__ = mock.MagicMock(
            return_value=self.mock_action)
        self.mock_action_wrapper.__exit__ = mock.MagicMock(return_value=False)

    def _pending_row(self, loc_id, store, status='pending'):
        return {
            'id': loc_id,
            'url': pstores._placeholder_location_url(self.image_id, store),
            'metadata': {
                'store': store,
                pstores.LOC_META_IMPORT_TAG: pstores.LOC_META_IMPORT_TAG_VALUE,
            },
            'status': status,
        }

    def _task(self, stores, all_must=True):
        return pstores._ParallelStoreImportTask(
            self.task_id, 'api_image_import', self.mock_task_repo,
            self.mock_action_wrapper, 'file:///tmp/staged', stores,
            all_must, 'glance-direct', mock.MagicMock(), self.mock_image_repo)

    def _ok(self, store, checksum='c', size=10):
        return {
            'store': store,
            'url': 'file:///%s' % store,
            'metadata': {'store': store},
            'size': size,
            'checksum': checksum,
            'os_hash_value': 'h',
        }

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_all_stores_success(self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(101, 'a'),
                self._pending_row(102, 'b'),
            ],
        }
        mock_upload.side_effect = [
            self._ok('a'), self._ok('b'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        task = self._task(['a', 'b'])
        task.execute()

        self.assertEqual(2, mock_upload.call_count)
        pending_adds = [
            c[0][2] for c in mock_db.image_location_add.call_args_list
            if c[0][2].get('status') == 'pending']
        self.assertEqual(2, len(pending_adds))
        self.assertEqual(4, mock_db.image_location_update.call_count)
        self.mock_action.set_image_attribute.assert_called_with(
            status='active', size=10)
        self.mock_action.remove_importing_stores.assert_called_with(['a', 'b'])

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_uses_file_path_override(self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [self._pending_row(1, 'a')],
        }
        mock_upload.return_value = self._ok('a')
        self.config(max_parallel_stores=1, group='image_import_opts')

        self._task(['a']).execute(file_path='file:///other')

        mock_upload.assert_called_once()
        self.assertEqual('file:///other', mock_upload.call_args[0][2])

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_fatal_all_stores_must_succeed(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(201, 'a'),
                self._pending_row(202, 'b'),
            ],
        }
        mock_upload.side_effect = [
            self._ok('a'),
            exception.ImportTaskError('fail'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        task = self._task(['a', 'b'], all_must=True)
        with mock.patch.object(
                task, '_delete_uploaded_backend_data') as mock_del:
            self.assertRaises(exception.ImportTaskError, task.execute)
            mock_del.assert_called()
        mock_db.image_location_delete.assert_called()

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_all_stores_fail(self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(301, 'a'),
                self._pending_row(302, 'b'),
            ],
        }
        mock_upload.side_effect = [
            exception.ImportTaskError('fail-a'),
            exception.ImportTaskError('fail-b'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        task = self._task(['a', 'b'], all_must=True)
        self.assertRaises(exception.ImportTaskError, task.execute)
        self.mock_action.set_image_attribute.assert_not_called()

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_partial_success_not_all_must(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(401, 'a'),
                self._pending_row(402, 'b'),
            ],
        }
        mock_upload.side_effect = [
            self._ok('a'),
            exception.ImportTaskError('fail'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        self._task(['a', 'b'], all_must=False).execute()

        mock_db.image_update.assert_called_with(
            mock.ANY, self.image_id,
            {'status': 'active', 'size': 10, 'checksum': 'c',
             'os_hash_value': 'h', 'os_hash_algo': 'sha512'},
            from_state='importing')
        active_kw_calls = [
            c for c in self.mock_action.set_image_attribute.call_args_list
            if c[1] == {'status': 'active', 'size': 10}]
        self.assertEqual(0, len(active_kw_calls))
        self.mock_action.add_failed_stores.assert_called()
        self.assertGreaterEqual(mock_db.image_get.call_count, 2)

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_partial_success_merges_pending_rows(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        pending_a = self._pending_row(501, 'a')
        pending_b = self._pending_row(502, 'b', status='uploading')
        mock_db.image_get.side_effect = [
            {'locations': [pending_a, self._pending_row(502, 'b')]},
            {'locations': [pending_a, pending_b]},
            {'locations': [pending_a, pending_b]},
        ]
        mock_upload.side_effect = [
            self._ok('a'),
            exception.ImportTaskError('fail-b'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        task = self._task(['a', 'b'], all_must=False)
        task.execute()

        merged = self.mock_action._image.locations
        self.assertEqual(2, len(merged))
        self.assertEqual({501, 502}, {loc['id'] for loc in merged})

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_three_stores_bounded_workers(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(1, 'a'),
                self._pending_row(2, 'b'),
                self._pending_row(3, 'c'),
            ],
        }
        mock_upload.side_effect = [
            self._ok('a'), self._ok('b'), self._ok('c'),
        ]
        self.config(max_parallel_stores=2, group='image_import_opts')

        self._task(['a', 'b', 'c']).execute()
        self.assertEqual(3, mock_upload.call_count)

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_missing_pending_id_uses_location_add(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {'locations': []}
        mock_upload.return_value = self._ok('a')
        self.config(max_parallel_stores=1, group='image_import_opts')

        self._task(['a']).execute()

        active_adds = [
            c[0][2] for c in mock_db.image_location_add.call_args_list
            if c[0][2].get('status') == 'active']
        self.assertEqual(1, len(active_adds))

    @mock.patch('glance.async_.flows.parallel_api_image_import.db_api')
    @mock.patch('glance.async_.flows.parallel_api_image_import.'
                '_import_staged_data_to_store')
    def test_execute_both_succeed_not_all_must_activates_once(
            self, mock_upload, mock_db_mod):
        mock_db = mock_db_mod.get_api.return_value
        mock_db.image_get.return_value = {
            'locations': [
                self._pending_row(701, 'a'),
                self._pending_row(702, 'b'),
            ],
        }
        mock_upload.side_effect = [self._ok('a'), self._ok('b')]
        self.config(max_parallel_stores=2, group='image_import_opts')

        self._task(['a', 'b'], all_must=False).execute()

        active_updates = [
            c for c in mock_db.image_update.call_args_list
            if c[0][2].get('status') == 'active']
        self.assertEqual(1, len(active_updates))
        active_kw_calls = [
            c for c in self.mock_action.set_image_attribute.call_args_list
            if c[1] == {'status': 'active', 'size': 10}]
        self.assertEqual(0, len(active_kw_calls))

    def test_delete_pending_swallows_delete_errors(self):
        mock_db = mock.MagicMock()
        mock_db.image_location_delete.side_effect = Exception('db err')
        task = self._task(['a'])
        task._delete_location_rows(mock_db, self.image_id, [9])

    def test_sync_locations_from_db_merges_all_rows(self):
        mock_db = mock.MagicMock()
        mock_db.image_get.return_value = {
            'locations': [
                {'id': 1, 'url': 'u', 'metadata': {}, 'status': 'pending'},
                self._pending_row(2, 'b'),
            ],
        }
        task = self._task(['b'])
        task._sync_locations_from_db(
            mock_db, self.image_id, self.mock_action)
        self.assertEqual(2, len(self.mock_action._image.locations))

    @mock.patch('glance.common.store_utils.delete_image_location_from_backend')
    def test_revert_deletes_successful_writes(self, mock_delete):
        task = self._task(['a'])
        task._completed_imports = [self._ok('a'), self._ok('b')]
        task.revert(result=None)
        self.assertEqual(2, mock_delete.call_count)

    @mock.patch('glance.common.store_utils.delete_image_location_from_backend')
    def test_delete_backend_object_logs_on_failure(self, mock_delete):
        mock_delete.side_effect = Exception('delete failed')
        task = self._task(['a'])
        with mock.patch.object(pstores, 'LOG') as mock_log:
            task._delete_uploaded_backend_data(self._ok('a'))
        self.assertTrue(mock_log.exception.called)
