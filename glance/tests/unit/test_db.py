# Copyright 2012 OpenStack Foundation.
# Copyright 2013 IBM Corp.
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
from unittest import mock
import uuid

from oslo_config import cfg
from oslo_db import exception as db_exc
from oslo_utils import encodeutils
from oslo_utils.fixture import uuidsentinel as uuids
from oslo_utils import timeutils
from sqlalchemy import orm as sa_orm

from glance.common import crypt
from glance.common import exception
import glance.context
import glance.db
from glance.db.sqlalchemy import api
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'

UUID1_LOCATION = 'file:///path/to/image'
UUID1_LOCATION_METADATA = {'key': 'value'}
UUID3_LOCATION = 'http://somehost.com/place'

CHECKSUM = '93264c3edf5972c9f1cb309543d38a5c'
CHCKSUM1 = '43264c3edf4972c9f1cb309543d38a55'


TASK_ID_1 = 'b3006bd0-461e-4228-88ea-431c14e918b4'
TASK_ID_2 = '07b6b562-6770-4c8b-a649-37a515144ce9'
TASK_ID_3 = '72d16bb6-4d70-48a5-83fe-14bb842dc737'

NODE_REFERENCE_ID_1 = 1
NODE_REFERENCE_ID_2 = 2


def _db_fixture(id, **kwargs):
    obj = {
        'id': id,
        'name': None,
        'is_public': False,
        'properties': {},
        'checksum': None,
        'owner': None,
        'status': 'queued',
        'tags': [],
        'size': None,
        'locations': [],
        'protected': False,
        'disk_format': None,
        'container_format': None,
        'deleted': False,
        'min_ram': None,
        'min_disk': None,
    }
    if 'visibility' in kwargs:
        obj.pop('is_public')
    obj.update(kwargs)
    return obj


def _db_image_member_fixture(image_id, member_id, **kwargs):
    obj = {
        'image_id': image_id,
        'member': member_id,
    }
    obj.update(kwargs)
    return obj


def _db_task_fixture(task_id, **kwargs):
    default_datetime = timeutils.utcnow()
    obj = {
        'id': task_id,
        'status': kwargs.get('status', 'pending'),
        'type': 'import',
        'input': kwargs.get('input', {}),
        'result': None,
        'owner': None,
        'image_id': kwargs.get('image_id'),
        'user_id': kwargs.get('user_id'),
        'request_id': kwargs.get('request_id'),
        'message': None,
        'expires_at': default_datetime + datetime.timedelta(days=365),
        'created_at': default_datetime,
        'updated_at': default_datetime,
        'deleted_at': None,
        'deleted': False
    }
    obj.update(kwargs)
    return obj


def _db_node_reference_fixture(node_id, node_url, **kwargs):
    obj = {
        'node_reference_id': node_id,
        'node_reference_url': node_url,
    }
    obj.update(kwargs)
    return obj


def _db_cached_images_fixture(id, **kwargs):
    obj = {
        'id': id,
        'image_id': kwargs.get('image_id'),
        'size': kwargs.get('size'),
        'hits': kwargs.get('hits')
    }
    obj.update(kwargs)
    return obj


class TestImageRepo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageRepo, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.context = glance.context.RequestContext(
            user=USER1, tenant=TENANT1)
        self.image_repo = glance.db.ImageRepo(self.context, self.db)
        self.image_factory = glance.domain.ImageFactory()
        self._create_images()
        self._create_image_members()
        # Centralized cache
        self._create_node_references()
        self._create_cached_images()

    def _create_node_references(self):
        self.node_references = [
            _db_node_reference_fixture(NODE_REFERENCE_ID_1, 'node_url_1'),
            _db_node_reference_fixture(NODE_REFERENCE_ID_2, 'node_url_2'),
        ]
        [self.db.node_reference_create(
            None, node_reference['node_reference_url'],
            node_reference_id=node_reference['node_reference_id']
        ) for node_reference in self.node_references]

    def _create_cached_images(self):
        self.cached_images = [
            _db_cached_images_fixture(1, image_id=UUID1, size=256, hits=3),
            _db_cached_images_fixture(1, image_id=UUID3, size=1024, hits=0)
        ]
        [self.db.insert_cache_details(
            None, 'node_url_1', cached_image['image_id'],
            cached_image['size'], hits=cached_image['hits']
        ) for cached_image in self.cached_images]

    def _create_images(self):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHECKSUM,
                        name='1', size=256,
                        is_public=True, status='active',
                        locations=[{'url': UUID1_LOCATION,
                                    'metadata': UUID1_LOCATION_METADATA,
                                    'status': 'active'}]),
            _db_fixture(UUID2, owner=TENANT1, checksum=CHCKSUM1,
                        name='2', size=512, is_public=False),
            _db_fixture(UUID3, owner=TENANT3, checksum=CHCKSUM1,
                        name='3', size=1024, is_public=True,
                        locations=[{'url': UUID3_LOCATION,
                                    'metadata': {},
                                    'status': 'active'}]),
            _db_fixture(UUID4, owner=TENANT4, name='4', size=2048),
        ]
        [self.db.image_create(None, image) for image in self.images]

        # Create tasks associated with image
        self.tasks = [
            _db_task_fixture(
                TASK_ID_1, image_id=UUID1, status='completed',
                input={
                    "image_id": UUID1,
                    "import_req": {
                        "method": {
                            "name": "glance-direct"
                        },
                        "backend": ["fake-store"]
                    },
                },
                user_id=USER1,
                request_id='fake-request-id',
            ),
            _db_task_fixture(
                TASK_ID_2, image_id=UUID1, status='completed',
                input={
                    "image_id": UUID1,
                    "import_req": {
                        "method": {
                            "name": "copy-image"
                        },
                        "all_stores": True,
                        "all_stores_must_succeed": False,
                        "backend": ["fake-store", "fake_store_1"]
                    },
                },
                user_id=USER1,
                request_id='fake-request-id',
            ),
            _db_task_fixture(
                TASK_ID_3, status='completed',
                input={
                    "image_id": UUID2,
                    "import_req": {
                        "method": {
                            "name": "glance-direct"
                        },
                        "backend": ["fake-store"]
                    },
                },
            ),
        ]
        [self.db.task_create(None, task) for task in self.tasks]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def _create_image_members(self):
        self.image_members = [
            _db_image_member_fixture(UUID2, TENANT2),
            _db_image_member_fixture(UUID2, TENANT3, status='accepted'),
        ]
        [self.db.image_member_create(None, image_member)
            for image_member in self.image_members]

    def test_node_reference_get_by_url(self):
        node_reference = self.db.node_reference_get_by_url(self.context,
                                                           'node_url_1')
        self.assertEqual(NODE_REFERENCE_ID_1,
                         node_reference['node_reference_id'])

    def test_node_reference_get_by_url_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.db.node_reference_get_by_url,
                          self.context,
                          'garbage_url')

    def test_get_cached_images(self):
        # Two images are cached on node 'node_url_1'
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_1')
        self.assertEqual(2, len(cached_images))

        # Nothing is cached on node 'node_url_2'
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_2')
        self.assertEqual(0, len(cached_images))

    def test_get_hit_count(self):
        # Hit count will be 3 for image UUID1
        self.assertEqual(3, self.db.get_hit_count(self.context,
                                                  UUID1, 'node_url_1'))

        # Hit count will be 0 for uncached image
        self.assertEqual(0, self.db.get_hit_count(self.context,
                                                  UUID2, 'node_url_1'))

    def test_delete_all_cached_images(self):
        # Verify that we have image cached
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_1')
        self.assertEqual(2, len(cached_images))

        # Delete cached images from node_url_1
        self.db.delete_all_cached_images(self.context, 'node_url_1')

        # Verify that all cached images from node_url_1 are deleted
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_1')
        self.assertEqual(0, len(cached_images))

    def test_delete_cached_image(self):
        # Verify that we have image cached
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_1')
        self.assertEqual(2, len(cached_images))

        # Delete cached image from node_url_1
        self.db.delete_cached_image(self.context, UUID1, 'node_url_1')

        # Verify that given image from node_url_1 is deleted
        cached_images = self.db.get_cached_images(self.context,
                                                  'node_url_1')
        self.assertEqual(1, len(cached_images))

    def test_get_least_recently_accessed(self):
        recently_accessed = self.db.get_least_recently_accessed(
            self.context, 'node_url_1')
        # Verify we will only get one image in response
        self.assertEqual(UUID1, recently_accessed)

    def test_is_image_cached_for_node(self):
        # Verify UUID1 is cached for node_url_1
        self.assertTrue(self.db.is_image_cached_for_node(
            self.context, 'node_url_1', UUID1))

        # Verify UUID3 is not cached for node_url_2
        self.assertFalse(self.db.is_image_cached_for_node(
            self.context, 'node_url_2', UUID3))

    def test_update_hit_count(self):
        # Verify UUID1 on node_url_1 has 3 as hit count
        self.assertEqual(3, self.db.get_hit_count(self.context,
                                                  UUID1, 'node_url_1'))

        # Update the hit count of UUID1
        self.db.update_hit_count(self.context, UUID1, 'node_url_1')

        # Verify hit count is now 4
        self.assertEqual(4, self.db.get_hit_count(self.context,
                                                  UUID1, 'node_url_1'))

    def test_get(self):
        image = self.image_repo.get(UUID1)
        self.assertEqual(UUID1, image.image_id)
        self.assertEqual('1', image.name)
        self.assertEqual(set(['ping', 'pong']), image.tags)
        self.assertEqual('public', image.visibility)
        self.assertEqual('active', image.status)
        self.assertEqual(256, image.size)
        self.assertEqual(TENANT1, image.owner)

    def test_tasks_get_by_image(self):
        tasks = self.db.tasks_get_by_image(self.context, UUID1)
        self.assertEqual(2, len(tasks))
        for task in tasks:
            self.assertEqual(USER1, task['user_id'])
            self.assertEqual('fake-request-id', task['request_id'])
            self.assertEqual(UUID1, task['image_id'])

    def test_tasks_get_by_image_not_exists(self):
        tasks = self.db.tasks_get_by_image(self.context, UUID3)
        self.assertEqual(0, len(tasks))

    def test_location_value(self):
        image = self.image_repo.get(UUID3)
        self.assertEqual(UUID3_LOCATION, image.locations[0]['url'])

    def test_location_data_value(self):
        image = self.image_repo.get(UUID1)
        self.assertEqual(UUID1_LOCATION, image.locations[0]['url'])
        self.assertEqual(UUID1_LOCATION_METADATA,
                         image.locations[0]['metadata'])

    def test_location_data_exists(self):
        image = self.image_repo.get(UUID2)
        self.assertEqual([], image.locations)

    def test_get_not_found(self):
        fake_uuid = str(uuid.uuid4())
        exc = self.assertRaises(exception.ImageNotFound, self.image_repo.get,
                                fake_uuid)
        self.assertIn(fake_uuid, encodeutils.exception_to_unicode(exc))

    def test_get_forbidden(self):
        self.assertRaises(exception.NotFound, self.image_repo.get, UUID4)

    def test_list(self):
        images = self.image_repo.list()
        image_ids = set([i.image_id for i in images])
        self.assertEqual(set([UUID1, UUID2, UUID3]), image_ids)

    def _do_test_list_status(self, status, expected):
        self.context = glance.context.RequestContext(
            user=USER1, tenant=TENANT3)
        self.image_repo = glance.db.ImageRepo(self.context, self.db)
        images = self.image_repo.list(member_status=status)
        self.assertEqual(expected, len(images))

    def test_list_status(self):
        self._do_test_list_status(None, 3)

    def test_list_status_pending(self):
        self._do_test_list_status('pending', 2)

    def test_list_status_rejected(self):
        self._do_test_list_status('rejected', 2)

    def test_list_status_all(self):
        self._do_test_list_status('all', 3)

    def test_list_with_marker(self):
        full_images = self.image_repo.list()
        full_ids = [i.image_id for i in full_images]
        marked_images = self.image_repo.list(marker=full_ids[0])
        actual_ids = [i.image_id for i in marked_images]
        self.assertEqual(full_ids[1:], actual_ids)

    def test_list_with_last_marker(self):
        images = self.image_repo.list()
        marked_images = self.image_repo.list(marker=images[-1].image_id)
        self.assertEqual(0, len(marked_images))

    def test_limited_list(self):
        limited_images = self.image_repo.list(limit=2)
        self.assertEqual(2, len(limited_images))

    def test_list_with_marker_and_limit(self):
        full_images = self.image_repo.list()
        full_ids = [i.image_id for i in full_images]
        marked_images = self.image_repo.list(marker=full_ids[0], limit=1)
        actual_ids = [i.image_id for i in marked_images]
        self.assertEqual(full_ids[1:2], actual_ids)

    def test_list_private_images(self):
        filters = {'visibility': 'private'}
        images = self.image_repo.list(filters=filters)
        self.assertEqual(0, len(images))

    def test_list_shared_images(self):
        filters = {'visibility': 'shared'}
        images = self.image_repo.list(filters=filters)
        image_ids = set([i.image_id for i in images])
        self.assertEqual(set([UUID2]), image_ids)

    def test_list_shared_images_other_tenant(self):
        # Create a private image owned by TENANT3
        image5 = _db_fixture(uuids.image5, owner=TENANT3,
                             name='5', size=512, is_public=False)
        self.db.image_create(None, image5)

        # Get a repo as TENANT3, since it has access to public,
        # shared, and private images
        context = glance.context.RequestContext(user=USER1, tenant=TENANT3)
        image_repo = glance.db.ImageRepo(context, self.db)
        images = {i.image_id: i for i in image_repo.list()}

        # No member set for public image UUID1
        self.assertIsNone(images[UUID1].member)

        # Member should be set to our tenant id for shared image UUID2
        self.assertEqual(TENANT3, images[UUID2].member)

        # No member set for private image5
        self.assertIsNone(images[uuids.image5].member)

    def test_list_all_images(self):
        filters = {'visibility': 'all'}
        images = self.image_repo.list(filters=filters)
        image_ids = set([i.image_id for i in images])
        self.assertEqual(set([UUID1, UUID2, UUID3]), image_ids)

    def test_list_with_checksum_filter_single_image(self):
        filters = {'checksum': CHECKSUM}
        images = self.image_repo.list(filters=filters)
        image_ids = list([i.image_id for i in images])
        self.assertEqual(1, len(image_ids))
        self.assertEqual([UUID1], image_ids)

    def test_list_with_checksum_filter_multiple_images(self):
        filters = {'checksum': CHCKSUM1}
        images = self.image_repo.list(filters=filters)
        image_ids = list([i.image_id for i in images])
        self.assertEqual(2, len(image_ids))
        self.assertIn(UUID2, image_ids)
        self.assertIn(UUID3, image_ids)

    def test_list_with_wrong_checksum(self):
        WRONG_CHKSUM = 'd2fd42f979e1ed1aafadc7eb9354bff839c858cd'
        filters = {'checksum': WRONG_CHKSUM}
        images = self.image_repo.list(filters=filters)
        self.assertEqual(0, len(images))

    def test_list_with_tags_filter_single_tag(self):
        filters = {'tags': ['ping']}
        images = self.image_repo.list(filters=filters)
        image_ids = list([i.image_id for i in images])
        self.assertEqual(1, len(image_ids))
        self.assertEqual([UUID1], image_ids)

    def test_list_with_tags_filter_multiple_tags(self):
        filters = {'tags': ['ping', 'pong']}
        images = self.image_repo.list(filters=filters)
        image_ids = list([i.image_id for i in images])
        self.assertEqual(1, len(image_ids))
        self.assertEqual([UUID1], image_ids)

    def test_list_with_tags_filter_multiple_tags_and_nonexistent(self):
        filters = {'tags': ['ping', 'fake']}
        images = self.image_repo.list(filters=filters)
        image_ids = list([i.image_id for i in images])
        self.assertEqual(0, len(image_ids))

    def test_list_with_wrong_tags(self):
        filters = {'tags': ['fake']}
        images = self.image_repo.list(filters=filters)
        self.assertEqual(0, len(images))

    def test_list_public_images(self):
        filters = {'visibility': 'public'}
        images = self.image_repo.list(filters=filters)
        image_ids = set([i.image_id for i in images])
        self.assertEqual(set([UUID1, UUID3]), image_ids)

    def test_sorted_list(self):
        images = self.image_repo.list(sort_key=['size'], sort_dir=['asc'])
        image_ids = [i.image_id for i in images]
        self.assertEqual([UUID1, UUID2, UUID3], image_ids)

    def test_sorted_list_with_multiple_keys(self):
        temp_id = 'd80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
        image = _db_fixture(temp_id, owner=TENANT1, checksum=CHECKSUM,
                            name='1', size=1024,
                            is_public=True, status='active',
                            locations=[{'url': UUID1_LOCATION,
                                        'metadata': UUID1_LOCATION_METADATA,
                                        'status': 'active'}])
        self.db.image_create(None, image)
        images = self.image_repo.list(sort_key=['name', 'size'],
                                      sort_dir=['asc'])
        image_ids = [i.image_id for i in images]
        self.assertEqual([UUID1, temp_id, UUID2, UUID3], image_ids)

        images = self.image_repo.list(sort_key=['size', 'name'],
                                      sort_dir=['asc'])
        image_ids = [i.image_id for i in images]
        self.assertEqual([UUID1, UUID2, temp_id, UUID3], image_ids)

    def test_sorted_list_with_multiple_dirs(self):
        temp_id = 'd80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
        image = _db_fixture(temp_id, owner=TENANT1, checksum=CHECKSUM,
                            name='1', size=1024,
                            is_public=True, status='active',
                            locations=[{'url': UUID1_LOCATION,
                                        'metadata': UUID1_LOCATION_METADATA,
                                        'status': 'active'}])
        self.db.image_create(None, image)
        images = self.image_repo.list(sort_key=['name', 'size'],
                                      sort_dir=['asc', 'desc'])
        image_ids = [i.image_id for i in images]
        self.assertEqual([temp_id, UUID1, UUID2, UUID3], image_ids)

        images = self.image_repo.list(sort_key=['name', 'size'],
                                      sort_dir=['desc', 'asc'])
        image_ids = [i.image_id for i in images]
        self.assertEqual([UUID3, UUID2, UUID1, temp_id], image_ids)

    def test_add_image(self):
        image = self.image_factory.new_image(name='added image')
        self.assertEqual(image.updated_at, image.created_at)
        self.image_repo.add(image)
        retreived_image = self.image_repo.get(image.image_id)
        self.assertEqual('added image', retreived_image.name)
        self.assertEqual(image.updated_at, retreived_image.updated_at)

    def test_save_image(self):
        image = self.image_repo.get(UUID1)
        original_update_time = image.updated_at
        image.name = 'foo'
        image.tags = ['king', 'kong']
        self.delay_inaccurate_clock()
        self.image_repo.save(image)
        current_update_time = image.updated_at
        self.assertGreater(current_update_time, original_update_time)
        image = self.image_repo.get(UUID1)
        self.assertEqual('foo', image.name)
        self.assertEqual(set(['king', 'kong']), image.tags)
        self.assertEqual(current_update_time, image.updated_at)

    def test_save_image_not_found(self):
        fake_uuid = str(uuid.uuid4())
        image = self.image_repo.get(UUID1)
        image.image_id = fake_uuid
        exc = self.assertRaises(exception.ImageNotFound, self.image_repo.save,
                                image)
        self.assertIn(fake_uuid, encodeutils.exception_to_unicode(exc))

    def test_save_excludes_atomic_props(self):
        fake_uuid = str(uuid.uuid4())
        image = self.image_repo.get(UUID1)

        # Try to set the property normally
        image.extra_properties['os_glance_import_task'] = fake_uuid
        self.image_repo.save(image)

        # Expect it was ignored
        image = self.image_repo.get(UUID1)
        self.assertNotIn('os_glance_import_task', image.extra_properties)

        # Set the property atomically
        self.image_repo.set_property_atomic(image,
                                            'os_glance_import_task', fake_uuid)
        # Expect it is set
        image = self.image_repo.get(UUID1)
        self.assertEqual(fake_uuid,
                         image.extra_properties['os_glance_import_task'])

        # Try to clobber it
        image.extra_properties['os_glance_import_task'] = 'foo'
        self.image_repo.save(image)

        # Expect it is unchanged
        image = self.image_repo.get(UUID1)
        self.assertEqual(fake_uuid,
                         image.extra_properties['os_glance_import_task'])

        # Try to delete it
        del image.extra_properties['os_glance_import_task']
        self.image_repo.save(image)

        # Expect it is still present and set accordingly
        image = self.image_repo.get(UUID1)
        self.assertEqual(fake_uuid,
                         image.extra_properties['os_glance_import_task'])

    def test_remove_image(self):
        image = self.image_repo.get(UUID1)
        previous_update_time = image.updated_at
        self.delay_inaccurate_clock()
        self.image_repo.remove(image)
        self.assertGreater(image.updated_at, previous_update_time)
        self.assertRaises(exception.ImageNotFound, self.image_repo.get, UUID1)

    def test_remove_image_not_found(self):
        fake_uuid = str(uuid.uuid4())
        image = self.image_repo.get(UUID1)
        image.image_id = fake_uuid
        exc = self.assertRaises(
            exception.ImageNotFound, self.image_repo.remove, image)
        self.assertIn(fake_uuid, encodeutils.exception_to_unicode(exc))

    def test_restore_image_status(self):
        image_id = uuid.uuid4()
        image = _db_fixture(image_id, name='restore_test', size=256,
                            is_public=True, status='pending_delete')
        self.db.image_create(self.context, image)
        self.db.image_restore(self.context, image_id)
        image = self.db.image_get(self.context, image_id)
        self.assertEqual(image['status'], 'active')

    def test_restore_image_status_not_found(self):
        image_id = uuid.uuid4()
        self.assertRaises(exception.ImageNotFound,
                          self.db.image_restore,
                          self.context,
                          image_id)

    def test_restore_image_status_not_pending_delete(self):
        image_id = uuid.uuid4()
        image = _db_fixture(image_id, name='restore_test', size=256,
                            is_public=True, status='deleted')
        self.db.image_create(self.context, image)
        self.assertRaises(exception.Conflict,
                          self.db.image_restore,
                          self.context,
                          image_id)

    def test_image_set_property_atomic(self):
        image_id = uuid.uuid4()
        image = _db_fixture(image_id, name='test')

        self.assertRaises(exception.ImageNotFound,
                          self.db.image_set_property_atomic,
                          image_id, 'foo', 'bar')

        self.db.image_create(self.context, image)
        self.db.image_set_property_atomic(image_id, 'foo', 'bar')
        image = self.db.image_get(self.context, image_id)
        self.assertEqual('foo', image['properties'][0]['name'])
        self.assertEqual('bar', image['properties'][0]['value'])

    def test_set_property_atomic(self):
        image = self.image_repo.get(UUID1)
        self.image_repo.set_property_atomic(image, 'foo', 'bar')
        image = self.image_repo.get(image.image_id)
        self.assertEqual({'foo': 'bar'}, image.extra_properties)

    def test_image_delete_property_atomic(self):
        image_id = uuid.uuid4()
        image = _db_fixture(image_id, name='test')

        self.assertRaises(exception.NotFound,
                          self.db.image_delete_property_atomic,
                          image_id, 'foo', 'bar')
        self.db.image_create(self.context, image)
        self.db.image_set_property_atomic(image_id, 'foo', 'bar')
        self.db.image_delete_property_atomic(image_id, 'foo', 'bar')
        image = self.image_repo.get(image_id)
        self.assertEqual({}, image.extra_properties)

    def test_delete_property_atomic(self):
        image = self.image_repo.get(UUID1)
        self.image_repo.set_property_atomic(image, 'foo', 'bar')
        image = self.image_repo.get(image.image_id)
        self.image_repo.delete_property_atomic(image, 'foo', 'bar')
        image = self.image_repo.get(image.image_id)
        self.assertEqual({}, image.extra_properties)


class TestEncryptedLocations(test_utils.BaseTestCase):
    def setUp(self):
        super(TestEncryptedLocations, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.context = glance.context.RequestContext(
            user=USER1, tenant=TENANT1)
        self.image_repo = glance.db.ImageRepo(self.context, self.db)
        self.image_factory = glance.domain.ImageFactory()
        self.crypt_key = '0123456789abcdef'
        self.config(metadata_encryption_key=self.crypt_key)
        self.foo_bar_location = [{'url': 'foo', 'metadata': {},
                                  'status': 'active'},
                                 {'url': 'bar', 'metadata': {},
                                  'status': 'active'}]

    def test_encrypt_locations_on_add(self):
        image = self.image_factory.new_image(UUID1)
        image.locations = self.foo_bar_location
        self.image_repo.add(image)
        db_data = self.db.image_get(self.context, UUID1)
        self.assertNotEqual(db_data['locations'], ['foo', 'bar'])
        decrypted_locations = [crypt.urlsafe_decrypt(self.crypt_key,
                                                     location['url'])
                               for location in db_data['locations']]
        self.assertEqual([location['url']
                          for location in self.foo_bar_location],
                         decrypted_locations)

    def test_encrypt_locations_on_save(self):
        image = self.image_factory.new_image(UUID1)
        self.image_repo.add(image)
        image.locations = self.foo_bar_location
        self.image_repo.save(image)
        db_data = self.db.image_get(self.context, UUID1)
        self.assertNotEqual(db_data['locations'], ['foo', 'bar'])
        decrypted_locations = [crypt.urlsafe_decrypt(self.crypt_key,
                                                     location['url'])
                               for location in db_data['locations']]
        self.assertEqual([location['url']
                          for location in self.foo_bar_location],
                         decrypted_locations)

    def test_decrypt_locations_on_get(self):
        url_loc = ['ping', 'pong']
        orig_locations = [{'url': location, 'metadata': {}, 'status': 'active'}
                          for location in url_loc]
        encrypted_locs = [crypt.urlsafe_encrypt(self.crypt_key, location)
                          for location in url_loc]
        encrypted_locations = [{'url': location,
                                'metadata': {},
                                'status': 'active'}
                               for location in encrypted_locs]
        self.assertNotEqual(encrypted_locations, orig_locations)
        db_data = _db_fixture(UUID1, owner=TENANT1,
                              locations=encrypted_locations)
        self.db.image_create(None, db_data)
        image = self.image_repo.get(UUID1)
        self.assertIn('id', image.locations[0])
        self.assertIn('id', image.locations[1])
        image.locations[0].pop('id')
        image.locations[1].pop('id')
        self.assertEqual(orig_locations, image.locations)

    def test_decrypt_locations_on_list(self):
        url_loc = ['ping', 'pong']
        orig_locations = [{'url': location, 'metadata': {}, 'status': 'active'}
                          for location in url_loc]
        encrypted_locs = [crypt.urlsafe_encrypt(self.crypt_key, location)
                          for location in url_loc]
        encrypted_locations = [{'url': location,
                                'metadata': {},
                                'status': 'active'}
                               for location in encrypted_locs]
        self.assertNotEqual(encrypted_locations, orig_locations)
        db_data = _db_fixture(UUID1, owner=TENANT1,
                              locations=encrypted_locations)
        self.db.image_create(None, db_data)
        image = self.image_repo.list()[0]
        self.assertIn('id', image.locations[0])
        self.assertIn('id', image.locations[1])
        image.locations[0].pop('id')
        image.locations[1].pop('id')
        self.assertEqual(orig_locations, image.locations)


class TestImageMemberRepo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageMemberRepo, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.context = glance.context.RequestContext(
            user=USER1, tenant=TENANT1)
        self.image_repo = glance.db.ImageRepo(self.context, self.db)
        self.image_member_factory = glance.domain.ImageMemberFactory()
        self._create_images()
        self._create_image_members()
        image = self.image_repo.get(UUID1)
        self.image_member_repo = glance.db.ImageMemberRepo(self.context,
                                                           self.db, image)

    def _create_images(self):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, name='1', size=256,
                        status='active'),
            _db_fixture(UUID2, owner=TENANT1, name='2',
                        size=512, visibility='shared'),
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def _create_image_members(self):
        self.image_members = [
            _db_image_member_fixture(UUID1, TENANT2),
            _db_image_member_fixture(UUID1, TENANT3),
        ]
        [self.db.image_member_create(None, image_member)
            for image_member in self.image_members]

    def test_list(self):
        image_members = self.image_member_repo.list()
        image_member_ids = set([i.member_id for i in image_members])
        self.assertEqual(set([TENANT2, TENANT3]), image_member_ids)

    def test_list_no_members(self):
        image = self.image_repo.get(UUID2)
        self.image_member_repo_uuid2 = glance.db.ImageMemberRepo(
            self.context, self.db, image)
        image_members = self.image_member_repo_uuid2.list()
        image_member_ids = set([i.member_id for i in image_members])
        self.assertEqual(set([]), image_member_ids)

    def test_save_image_member(self):
        image_member = self.image_member_repo.get(TENANT2)
        image_member.status = 'accepted'
        self.image_member_repo.save(image_member)
        image_member_updated = self.image_member_repo.get(TENANT2)
        self.assertEqual(image_member.id, image_member_updated.id)
        self.assertEqual('accepted', image_member_updated.status)

    def test_add_image_member(self):
        image = self.image_repo.get(UUID1)
        image_member = self.image_member_factory.new_image_member(image,
                                                                  TENANT4)
        self.assertIsNone(image_member.id)
        self.image_member_repo.add(image_member)
        retreived_image_member = self.image_member_repo.get(TENANT4)
        self.assertIsNotNone(retreived_image_member.id)
        self.assertEqual(image_member.image_id,
                         retreived_image_member.image_id)
        self.assertEqual(image_member.member_id,
                         retreived_image_member.member_id)
        self.assertEqual('pending', retreived_image_member.status)

    def test_add_duplicate_image_member(self):
        image = self.image_repo.get(UUID1)
        image_member = self.image_member_factory.new_image_member(image,
                                                                  TENANT4)
        self.assertIsNone(image_member.id)
        self.image_member_repo.add(image_member)
        retreived_image_member = self.image_member_repo.get(TENANT4)
        self.assertIsNotNone(retreived_image_member.id)
        self.assertEqual(image_member.image_id,
                         retreived_image_member.image_id)
        self.assertEqual(image_member.member_id,
                         retreived_image_member.member_id)
        self.assertEqual('pending', retreived_image_member.status)

        self.assertRaises(exception.Duplicate, self.image_member_repo.add,
                          image_member)

    def test_get_image_member(self):
        image = self.image_repo.get(UUID1)
        image_member = self.image_member_factory.new_image_member(image,
                                                                  TENANT4)
        self.assertIsNone(image_member.id)
        self.image_member_repo.add(image_member)

        member = self.image_member_repo.get(image_member.member_id)

        self.assertEqual(member.id, image_member.id)
        self.assertEqual(member.image_id, image_member.image_id)
        self.assertEqual(member.member_id, image_member.member_id)
        self.assertEqual('pending', member.status)

    def test_get_nonexistent_image_member(self):
        fake_image_member_id = 'fake'
        self.assertRaises(exception.NotFound, self.image_member_repo.get,
                          fake_image_member_id)

    def test_remove_image_member(self):
        image_member = self.image_member_repo.get(TENANT2)
        self.image_member_repo.remove(image_member)
        self.assertRaises(exception.NotFound, self.image_member_repo.get,
                          TENANT2)

    def test_remove_image_member_does_not_exist(self):
        fake_uuid = str(uuid.uuid4())
        image = self.image_repo.get(UUID2)
        fake_member = glance.domain.ImageMemberFactory().new_image_member(
            image, TENANT4)
        fake_member.id = fake_uuid
        exc = self.assertRaises(exception.NotFound,
                                self.image_member_repo.remove,
                                fake_member)
        self.assertIn(fake_uuid, encodeutils.exception_to_unicode(exc))


class TestTaskRepo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTaskRepo, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.context = glance.context.RequestContext(user=USER1,
                                                     tenant=TENANT1)
        self.task_repo = glance.db.TaskRepo(self.context, self.db)
        self.task_factory = glance.domain.TaskFactory()
        self.fake_task_input = ('{"import_from": '
                                '"swift://cloud.foo/account/mycontainer/path"'
                                ',"import_from_format": "qcow2"}')
        self._create_tasks()

    def _create_tasks(self):
        self.tasks = [
            _db_task_fixture(UUID1, type='import', status='pending',
                             input=self.fake_task_input,
                             result='',
                             owner=TENANT1,
                             message='',
                             ),
            _db_task_fixture(UUID2, type='import', status='processing',
                             input=self.fake_task_input,
                             result='',
                             owner=TENANT1,
                             message='',
                             ),
            _db_task_fixture(UUID3, type='import', status='failure',
                             input=self.fake_task_input,
                             result='',
                             owner=TENANT1,
                             message='',
                             ),
            _db_task_fixture(UUID4, type='import', status='success',
                             input=self.fake_task_input,
                             result='',
                             owner=TENANT2,
                             message='',
                             ),
        ]
        [self.db.task_create(None, task) for task in self.tasks]

    def test_get(self):
        task = self.task_repo.get(UUID1)
        self.assertEqual(task.task_id, UUID1)
        self.assertEqual('import', task.type)
        self.assertEqual('pending', task.status)
        self.assertEqual(task.task_input, self.fake_task_input)
        self.assertEqual('', task.result)
        self.assertEqual('', task.message)
        self.assertEqual(task.owner, TENANT1)

    def test_get_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.task_repo.get,
                          str(uuid.uuid4()))

    def test_get_forbidden(self):
        self.assertRaises(exception.NotFound,
                          self.task_repo.get,
                          UUID4)

    def test_list(self):
        tasks = self.task_repo.list()
        task_ids = set([i.task_id for i in tasks])
        self.assertEqual(set([UUID1, UUID2, UUID3]), task_ids)

    def test_list_with_type(self):
        filters = {'type': 'import'}
        tasks = self.task_repo.list(filters=filters)
        task_ids = set([i.task_id for i in tasks])
        self.assertEqual(set([UUID1, UUID2, UUID3]), task_ids)

    def test_list_with_status(self):
        filters = {'status': 'failure'}
        tasks = self.task_repo.list(filters=filters)
        task_ids = set([i.task_id for i in tasks])
        self.assertEqual(set([UUID3]), task_ids)

    def test_list_with_marker(self):
        full_tasks = self.task_repo.list()
        full_ids = [i.task_id for i in full_tasks]
        marked_tasks = self.task_repo.list(marker=full_ids[0])
        actual_ids = [i.task_id for i in marked_tasks]
        self.assertEqual(full_ids[1:], actual_ids)

    def test_list_with_last_marker(self):
        tasks = self.task_repo.list()
        marked_tasks = self.task_repo.list(marker=tasks[-1].task_id)
        self.assertEqual(0, len(marked_tasks))

    def test_limited_list(self):
        limited_tasks = self.task_repo.list(limit=2)
        self.assertEqual(2, len(limited_tasks))

    def test_list_with_marker_and_limit(self):
        full_tasks = self.task_repo.list()
        full_ids = [i.task_id for i in full_tasks]
        marked_tasks = self.task_repo.list(marker=full_ids[0], limit=1)
        actual_ids = [i.task_id for i in marked_tasks]
        self.assertEqual(full_ids[1:2], actual_ids)

    def test_sorted_list(self):
        tasks = self.task_repo.list(sort_key='status', sort_dir='desc')
        task_ids = [i.task_id for i in tasks]
        self.assertEqual([UUID2, UUID1, UUID3], task_ids)

    def test_add_task(self):
        task_type = 'import'
        image_id = 'fake_image_id'
        user_id = 'fake_user'
        request_id = 'fake_request_id'
        task = self.task_factory.new_task(task_type, None, image_id,
                                          user_id, request_id,
                                          task_input=self.fake_task_input)
        self.assertEqual(task.updated_at, task.created_at)
        self.task_repo.add(task)
        retrieved_task = self.task_repo.get(task.task_id)
        self.assertEqual(task.updated_at, retrieved_task.updated_at)
        self.assertEqual(self.fake_task_input, retrieved_task.task_input)
        self.assertEqual(image_id, task.image_id)
        self.assertEqual(user_id, task.user_id)
        self.assertEqual(request_id, task.request_id)

    def test_save_task(self):
        task = self.task_repo.get(UUID1)
        original_update_time = task.updated_at
        self.delay_inaccurate_clock()
        self.task_repo.save(task)
        current_update_time = task.updated_at
        self.assertGreater(current_update_time, original_update_time)
        task = self.task_repo.get(UUID1)
        self.assertEqual(current_update_time, task.updated_at)

    def test_remove_task(self):
        task = self.task_repo.get(UUID1)
        self.task_repo.remove(task)
        self.assertRaises(exception.NotFound,
                          self.task_repo.get,
                          task.task_id)


class RetryOnDeadlockTestCase(test_utils.BaseTestCase):

    def test_raise_deadlock(self):

        class TestException(Exception):
            pass

        self.attempts = 3

        def _mock_get_session():
            def _raise_exceptions():
                self.attempts -= 1
                if self.attempts <= 0:
                    raise TestException("Exit")
                raise db_exc.DBDeadlock("Fake Exception")
            return _raise_exceptions

        with mock.patch.object(api, 'get_session') as sess:
            sess.side_effect = _mock_get_session()

            try:
                api.image_update(None, 'fake-id', {})
            except TestException:
                self.assertEqual(3, sess.call_count)

        # Test retry on image destroy if db deadlock occurs
        self.attempts = 3
        with mock.patch.object(api, 'get_session') as sess:
            sess.side_effect = _mock_get_session()

            try:
                api.image_destroy(None, 'fake-id')
            except TestException:
                self.assertEqual(3, sess.call_count)


class TestImageDeleteRace(test_utils.BaseTestCase):

    @mock.patch.object(api, 'get_session')
    @mock.patch.object(api, 'LOG')
    def test_image_property_delete_stale_data(
        self, mock_LOG, mock_get_session,
    ):
        mock_context = mock.MagicMock()
        mock_session = mock_get_session.return_value
        mock_result = (mock_session.query.return_value.
                       filter_by.return_value.
                       one.return_value)
        mock_result.delete.side_effect = sa_orm.exc.StaleDataError('myerror')
        # StaleDataError should not be raised
        r = api.image_property_delete(mock_context, 'myprop', 'myimage')
        # We should not get the property back
        self.assertIsNone(r)
        # Make sure we logged it
        mock_LOG.debug.assert_called_once_with(
            'StaleDataError while deleting property %(prop)r '
            'from image %(image)r likely means we raced during delete: '
            '%(err)s', {'prop': 'myprop', 'image': 'myimage',
                        'err': 'myerror'})

    @mock.patch.object(api, 'get_session')
    def test_image_property_delete_exception(self, mock_get_session):
        mock_context = mock.MagicMock()
        mock_session = mock_get_session.return_value
        mock_result = (mock_session.query.return_value.
                       filter_by.return_value.
                       one.return_value)
        mock_result.delete.side_effect = RuntimeError
        # Any other exception should be raised
        self.assertRaises(RuntimeError,
                          api.image_property_delete,
                          mock_context, 'myprop', 'myimage')
