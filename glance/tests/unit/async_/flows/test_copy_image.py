# Copyright 2020 Red Hat, Inc.
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

import datetime
import os
from unittest import mock

import glance_store as store_api
from oslo_config import cfg

from glance.async_.flows._internal_plugins import copy_image
import glance.common.exception as exception
from glance import domain
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF

DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)


TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
FAKEHASHALGO = 'fake-name-for-sha512'
CHKSUM = '93264c3edf5972c9f1cb309543d38a5c'
RESERVED_STORES = {
    'os_glance_staging_store': 'file',
}


def _db_fixture(id, **kwargs):
    obj = {
        'id': id,
        'name': None,
        'visibility': 'shared',
        'properties': {},
        'checksum': None,
        'os_hash_algo': FAKEHASHALGO,
        'os_hash_value': None,
        'owner': None,
        'status': 'queued',
        'tags': [],
        'size': None,
        'virtual_size': None,
        'locations': [],
        'protected': False,
        'disk_format': None,
        'container_format': None,
        'deleted': False,
        'min_ram': None,
        'min_disk': None,
    }
    obj.update(kwargs)
    return obj


class TestCopyImageTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestCopyImageTask, self).setUp()

        self.db = unit_test_utils.FakeDB(initialize=False)
        self._create_images()
        self.image_repo = mock.MagicMock()
        self.task_repo = mock.MagicMock()
        self.image_id = UUID1
        self.staging_store = mock.MagicMock()
        self.task_factory = domain.TaskFactory()

        task_input = {
            "import_req": {
                'method': {
                    'name': 'copy-image',
                },
                'stores': ['fast']
            }
        }
        task_ttl = CONF.task.task_time_to_live

        self.task_type = 'import'
        self.task = self.task_factory.new_task(self.task_type, TENANT1,
                                               task_time_to_live=task_ttl,
                                               task_input=task_input)

        stores = {'cheap': 'file', 'fast': 'file'}
        self.config(enabled_backends=stores)
        store_api.register_store_opts(CONF, reserved_stores=RESERVED_STORES)
        self.config(default_backend='fast', group='glance_store')
        store_api.create_multi_stores(CONF, reserved_stores=RESERVED_STORES)

    def _create_images(self):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHKSUM,
                        name='1', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        locations=[{'url': 'file://%s/%s' % (self.test_dir,
                                                             UUID1),
                                    'metadata': {'store': 'fast'},
                                    'status': 'active'}],
                        created_at=DATETIME + datetime.timedelta(seconds=1)),
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    @mock.patch.object(store_api, 'get_store_from_store_identifier')
    def test_copy_image_to_staging_store(self, mock_store_api):
        mock_store_api.return_value = self.staging_store
        copy_image_task = copy_image._CopyImage(
            self.task.task_id, self.task_type, self.image_repo,
            self.image_id)
        with mock.patch.object(self.image_repo, 'get') as get_mock:
            get_mock.return_value = mock.MagicMock(
                image_id=self.images[0]['id'],
                locations=self.images[0]['locations'],
                status=self.images[0]['status']
            )
            with mock.patch.object(store_api, 'get') as get_data:
                get_data.return_value = (b"dddd", 4)
                copy_image_task.execute()
                self.staging_store.add.assert_called_once()
                mock_store_api.assert_called_once_with(
                    "os_glance_staging_store")

    @mock.patch.object(os, 'unlink')
    @mock.patch.object(os.path, 'getsize')
    @mock.patch.object(os.path, 'exists')
    @mock.patch.object(store_api, 'get_store_from_store_identifier')
    def test_copy_image_to_staging_store_partial_data_exists(
            self, mock_store_api, mock_exists, mock_getsize, mock_unlink):
        mock_store_api.return_value = self.staging_store
        mock_exists.return_value = True
        mock_getsize.return_value = 3

        copy_image_task = copy_image._CopyImage(
            self.task.task_id, self.task_type, self.image_repo,
            self.image_id)
        with mock.patch.object(self.image_repo, 'get') as get_mock:
            get_mock.return_value = mock.MagicMock(
                image_id=self.images[0]['id'],
                locations=self.images[0]['locations'],
                status=self.images[0]['status'],
                size=4
            )
            with mock.patch.object(store_api, 'get') as get_data:
                get_data.return_value = (b"dddd", 4)
                copy_image_task.execute()
                mock_exists.assert_called_once()
                mock_getsize.assert_called_once()
                mock_unlink.assert_called_once()
                self.staging_store.add.assert_called_once()
                mock_store_api.assert_called_once_with(
                    "os_glance_staging_store")

    @mock.patch.object(os, 'unlink')
    @mock.patch.object(os.path, 'getsize')
    @mock.patch.object(os.path, 'exists')
    @mock.patch.object(store_api, 'get_store_from_store_identifier')
    def test_copy_image_to_staging_store_data_exists(
            self, mock_store_api, mock_exists, mock_getsize, mock_unlink):
        mock_store_api.return_value = self.staging_store
        mock_exists.return_value = True
        mock_getsize.return_value = 4

        copy_image_task = copy_image._CopyImage(
            self.task.task_id, self.task_type, self.image_repo,
            self.image_id)
        with mock.patch.object(self.image_repo, 'get') as get_mock:
            get_mock.return_value = mock.MagicMock(
                image_id=self.images[0]['id'],
                locations=self.images[0]['locations'],
                status=self.images[0]['status'],
                size=4
            )
            copy_image_task.execute()
            mock_exists.assert_called_once()
            mock_store_api.assert_called_once_with(
                "os_glance_staging_store")
            mock_getsize.assert_called_once()
            # As valid image data already exists in staging area
            # it does not remove it and also does not download
            # it again to staging area
            mock_unlink.assert_not_called()
            self.staging_store.add.assert_not_called()

    @mock.patch.object(store_api, 'get_store_from_store_identifier')
    def test_copy_non_existing_image_to_staging_store_(self, mock_store_api):
        mock_store_api.return_value = self.staging_store
        copy_image_task = copy_image._CopyImage(
            self.task.task_id, self.task_type, self.image_repo,
            self.image_id)
        with mock.patch.object(self.image_repo, 'get') as get_mock:
            get_mock.side_effect = exception.NotFound()

            self.assertRaises(exception.NotFound, copy_image_task.execute)
            mock_store_api.assert_called_once_with(
                "os_glance_staging_store")
