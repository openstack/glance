# Copyright 2024 RedHat Inc.
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

import hashlib
import io
from unittest import mock

import glance_store as store
from oslo_config import cfg
from oslo_utils import units

import glance.async_.flows.location_import as import_flow
from glance.common import exception
from glance import context
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


CONF = cfg.CONF

BASE_URI = unit_test_utils.BASE_URI

TASK_TYPE = 'location_import'
TASK_ID1 = 'dbbe7231-020f-4311-87e1-5aaa6da56c02'
IMAGE_ID1 = '41f5b3b0-f54c-4cef-bd45-ce3e376a142f'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestCalculateHashTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestCalculateHashTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.hash_task_input = {
            'image_id': IMAGE_ID1,
        }
        self.image_repo = mock.MagicMock()
        self.image = self.image_repo.get.return_value
        self.image.image_id = IMAGE_ID1
        self.image.disk_format = 'raw'
        self.image.container_format = 'bare'
        self.config(do_secure_hash=True)
        self.config(http_retries='3')
        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)

    def test_execute_calculate_hash(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        hashing_algo = CONF.hashing_algorithm

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo)
        hash_calculation.execute()
        self.assertIsNotNone(self.image.checksum)
        self.assertIsNotNone(self.image.os_hash_algo)
        self.assertIsNotNone(self.image.os_hash_value)
        self.assertEqual('active', self.image.status)

    def test_hash_calculation_retry_count(self):
        hashing_algo = CONF.hashing_algorithm
        self.image.checksum = None
        self.image.os_hash_value = None
        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo,
                                                      status='importing')

        self.image.get_data.side_effect = IOError
        self.config(http_retries='10')
        expected_msg = ("Hash calculation failed for image .* data")
        self.assertRaisesRegex(import_flow._HashCalculationFailed,
                               expected_msg,
                               hash_calculation.execute)
        self.assertEqual(CONF.http_retries, self.image.get_data.call_count)
        self.assertEqual(CONF.hashing_algorithm, self.image.os_hash_algo)
        self.assertIsNone(self.image.checksum)
        self.assertIsNone(self.image.os_hash_value)

        hash_calculation.revert(None)
        self.assertIsNone(self.image.os_hash_algo)

    def test_execute_hash_calculation_fails_without_validation_data(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        self.hash_task_input.update(loc_url=self.loc_url)
        self.image.checksum = None
        self.image.os_hash_value = None

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)

        # Since Image is mocked here, self.image.locations will not be
        # set hence setting it here to check that it's not popped out
        # even after CalculateHash failure
        self.image.locations = ['%s/fake_location_1' % (BASE_URI)]
        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

        hashing_algo = CONF.hashing_algorithm
        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo)

        self.image.get_data.side_effect = IOError
        with mock.patch.object(import_flow.LOG, 'debug') as mock_debug:
            hash_calculation.execute()
            debug_logs = mock_debug.call_args_list
            self.assertIn(("[%i/%i] Hash calculation failed due to %s",
                           1, 3, ''), debug_logs[0])
            self.assertEqual(CONF.hashing_algorithm, self.image.os_hash_algo)
            self.assertIsNone(self.image.checksum)
            self.assertIsNone(self.image.os_hash_value)
            self.assertEqual('active', self.image.status)
            self.assertEqual(1, len(self.image.locations))

        hash_calculation.revert(None)
        self.assertIsNone(self.image.os_hash_algo)
        self.assertEqual('active', self.image.status)
        self.assertEqual(1, len(self.image.locations))

        # Hash Calculation failed when image is 'active'.
        # exception will not be raised instead there will be warning log
        self.image.get_data.side_effect = IOError
        with mock.patch.object(import_flow.LOG, 'warning') as mock_warn:
            hash_calculation.execute()
            msg = ("Hash calculation failed for image %s data" % IMAGE_ID1)
            mock_warn.assert_called_once_with(msg)
            self.assertEqual(CONF.hashing_algorithm, self.image.os_hash_algo)
            self.assertIsNone(self.image.checksum)
            self.assertIsNone(self.image.os_hash_value)
            self.assertEqual('active', self.image.status)
            self.assertEqual(1, len(self.image.locations))

        hash_calculation.revert(None)
        self.assertIsNone(self.image.os_hash_algo)
        self.assertEqual('active', self.image.status)
        self.assertEqual(1, len(self.image.locations))

    def test_execute_hash_calculation_fails_for_store_other_that_http(self):
        self.loc_url = "cinder://image/fake_location"
        self.hash_task_input.update(loc_url=self.loc_url)
        self.image.status = 'queued'
        self.image.checksum = None
        self.image.os_hash_value = None

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)

        # Since Image is mocked here, self.image.locations will not be
        # set hence setting it here to check that it's not popped out
        # even after CalculateHash failure
        self.image.locations = [{'url': 'cinder://image/fake_location'}]

        hashing_algo = CONF.hashing_algorithm
        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo,
                                                      status='importing')

        self.image.get_data.side_effect = IOError
        expected_msg = ("Hash calculation failed for image .* data")
        self.assertRaisesRegex(import_flow._HashCalculationFailed,
                               expected_msg,
                               hash_calculation.execute)
        self.assertEqual(CONF.hashing_algorithm, self.image.os_hash_algo)
        self.assertIsNone(self.image.checksum)
        self.assertIsNone(self.image.os_hash_value)
        self.assertEqual('importing', self.image.status)
        self.assertEqual(1, len(self.image.locations))

        hash_calculation.revert(None)
        self.assertIsNone(self.image.os_hash_algo)
        self.assertEqual('queued', self.image.status)
        self.assertEqual(0, len(self.image.locations))

    def test_execute_hash_calculation_fails_if_image_data_deleted(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        self.hash_task_input.update(loc_url=self.loc_url)
        self.image.checksum = None
        self.image.os_hash_value = None

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

        hashing_algo = CONF.hashing_algorithm
        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo)
        self.image.get_data.side_effect = store.exceptions.NotFound
        hash_calculation.execute()
        # Check if Image delete and image_repo.delete has been called
        # if exception raised
        self.image.delete.assert_called_once()
        self.image_repo.remove.assert_called_once_with(self.image)


class TestVerifyValidationDataTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestVerifyValidationDataTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.val_data_task_input = {
            'image_id': IMAGE_ID1,
        }
        self.image_repo = mock.MagicMock()
        self.image = self.image_repo.get.return_value
        self.image.image_id = IMAGE_ID1
        self.image.disk_format = 'raw'
        self.image.container_format = 'bare'
        self.config(do_secure_hash=True)

    def test_execute_with_valid_validation_data(self):
        url = '%s/fake_location_1' % BASE_URI
        self.image.status = 'queued'
        self.image.locations = {"url": url, "metadata": {"store": "foo"}}
        expected_size = 4 * units.Ki
        expected_data = b"*" * expected_size
        self.image.get_data.return_value = io.BytesIO(expected_data)
        hash_value = hashlib.sha512(expected_data).hexdigest()
        hashing_algo = CONF.hashing_algorithm
        self.image.checksum = None
        self.image.os_hash_value = None
        val_data = {
            'os_hash_algo': hashing_algo,
            'os_hash_value': hash_value
        }
        self.val_data_task_input.update(val_data=val_data)

        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo,
                                                      status='importing')
        hash_calculation.execute()

        self.image.os_hash_algo = val_data.get("os_hash_algo",
                                               hashing_algo)

        verify_validation_data = import_flow._VerifyValidationData(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, val_data)

        verify_validation_data.execute()
        self.assertEqual('sha512', self.image.os_hash_algo)
        self.assertEqual(hash_value, self.image.os_hash_value)
        self.assertEqual('importing', self.image.status)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

    def test_execute_with_os_hash_value_other_than_512(self):
        url = '%s/fake_location_1' % BASE_URI
        self.image.status = 'queued'
        self.image.locations = {"url": url, "metadata": {"store": "foo"}}
        expected_size = 4 * units.Ki
        expected_data = b"*" * expected_size
        self.image.get_data.return_value = io.BytesIO(expected_data)
        hash_value = hashlib.sha256(expected_data).hexdigest()
        hashing_algo = 'sha256'
        self.image.checksum = None
        self.image.os_hash_value = None
        val_data = {
            'os_hash_algo': 'sha256',
            'os_hash_value': hash_value
        }

        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo,
                                                      status='importing')
        hash_calculation.execute()

        self.val_data_task_input.update(val_data=val_data)

        verify_validation_data = import_flow._VerifyValidationData(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, val_data)

        verify_validation_data.execute()
        self.assertEqual('sha256', self.image.os_hash_algo)
        self.assertEqual(hash_value, self.image.os_hash_value)
        self.assertEqual('importing', self.image.status)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

    def test_execute_with_invalid_validation_data(self):
        url = '%s/fake_location_1' % BASE_URI
        self.image.status = 'queued'
        self.image.locations = [{"url": url, "metadata": {"store": "foo"}}]
        expected_size = 4 * units.Ki
        expected_data = b"*" * expected_size
        self.image.get_data.return_value = io.BytesIO(expected_data)
        hashing_algo = CONF.hashing_algorithm
        val_data = {
            'os_hash_algo': hashing_algo,
            'os_hash_value': hashlib.sha512(b'image_service').hexdigest()
        }
        hash_calculation = import_flow._CalculateHash(TASK_ID1, TASK_TYPE,
                                                      self.image_repo,
                                                      IMAGE_ID1,
                                                      hashing_algo,
                                                      status='importing')
        hash_calculation.execute()

        self.assertEqual('importing', self.image.status)
        self.assertEqual(1, len(self.image.locations))
        verify_validation_data = import_flow._VerifyValidationData(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1,
            val_data)
        expected_msg = ("os_hash_value: .* not matched with actual "
                        "os_hash_value: .*")
        self.assertRaisesRegex(exception.InvalidParameterValue,
                               expected_msg,
                               verify_validation_data.execute)
        verify_validation_data.revert(None)
        self.assertIsNone(self.image.os_hash_algo)
        self.assertIsNone(self.image.os_hash_value)
        self.assertIsNone(self.image.checksum)
        self.assertEqual('queued', self.image.status)


class TestSetHashValuesTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSetHashValuesTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.hash_task_input = {
            'image_id': IMAGE_ID1,
        }
        self.image_repo = mock.MagicMock()
        self.image = self.image_repo.get.return_value
        self.image.image_id = IMAGE_ID1
        self.image.disk_format = 'raw'
        self.image.container_format = 'bare'

    def test_execute_with_valid_validation_data(self):
        url = '%s/fake_location_1' % BASE_URI
        self.image.status = 'queued'
        self.image.locations = {"url": url, "metadata": {"store": "foo"}}
        expected_size = 4 * units.Ki
        expected_data = b"*" * expected_size
        self.image.get_data.return_value = io.BytesIO(expected_data)
        hash_value = hashlib.sha512(expected_data).hexdigest()
        val_data = {
            'os_hash_algo': 'sha512',
            'os_hash_value': hash_value
        }
        self.hash_task_input.update(val_data=val_data)

        set_hash_data = import_flow._SetHashValues(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, val_data)

        set_hash_data.execute()
        self.assertEqual('sha512', self.image.os_hash_algo)
        self.assertEqual(hash_value, self.image.os_hash_value)
        self.assertEqual('queued', self.image.status)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)


class TestUpdateLocationTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestUpdateLocationTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.location_task_input = {
            'image_id': IMAGE_ID1,
        }
        self.image_repo = mock.MagicMock()
        self.image = self.image_repo.get.return_value
        self.image.image_id = IMAGE_ID1
        self.image.disk_format = 'raw'
        self.image.container_format = 'bare'
        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)

    def test_execute_with_valid_location(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        self.location_task_input.update(loc_url=self.loc_url)

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

    def test_execute_with_invalid_location(self):
        self.image.locations.append.side_effect = exception.BadStoreUri
        loc_url = 'bogus_url'
        self.image.status = 'queued'
        self.location_task_input.update(loc_url=loc_url)

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, loc_url,
            self.context)
        self.assertRaises(import_flow._InvalidLocation,
                          location_update.execute)
        self.assertEqual('queued', self.image.status)


class TestSetImageToActiveTask(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSetImageToActiveTask, self).setUp()
        self.task_repo = mock.MagicMock()
        self.task = mock.MagicMock()
        self.set_status_task_input = {
            'image_id': IMAGE_ID1,
        }
        self.image_repo = mock.MagicMock()
        self.image = self.image_repo.get.return_value
        self.image.image_id = IMAGE_ID1
        self.image.disk_format = 'raw'
        self.image.container_format = 'bare'
        self.context = context.RequestContext(user_id=TENANT1,
                                              project_id=TENANT1,
                                              overwrite=False)

    def test_execute_set_image_to_active_state(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        self.set_status_task_input.update(loc_url=self.loc_url)

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)
        self.assertEqual('queued', self.image.status)

        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        set_image_active.execute()
        self.assertEqual('active', self.image.status)

    def test_execute_set_image_to_active_state_failure(self):
        self.loc_url = '%s/fake_location_1' % (BASE_URI)
        self.image.status = 'queued'
        self.set_status_task_input.update(loc_url=self.loc_url)

        location_update = import_flow._UpdateLocationTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1, self.loc_url,
            self.context)

        location_update.execute()
        self.assertEqual(1, self.image.locations.append.call_count)
        self.assertEqual('queued', self.image.status)

        # Test if image failed while saving to active state
        self.image_repo.save.side_effect = ValueError
        set_image_active = import_flow._SetImageToActiveTask(
            TASK_ID1, TASK_TYPE, self.image_repo, IMAGE_ID1)
        self.assertRaises(ValueError, set_image_active.execute)

        # Test revert where location added in previous task is popped
        # out incase of this task failure which didn't set image status
        # 'active'.
        self.image_repo.save.side_effect = None
        self.image.status = 'queued'
        set_image_active.revert(None)
        self.assertEqual(0, self.image.locations.pop.call_count)
        self.assertEqual('queued', self.image.status)
