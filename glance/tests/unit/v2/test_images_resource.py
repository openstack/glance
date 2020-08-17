# Copyright 2012 OpenStack Foundation.
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
import hashlib
import os
from unittest import mock
import uuid

from castellan.common import exception as castellan_exception
import glance_store as store
from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils import fixture
import six
from six.moves import http_client as http
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import testtools
import webob

import glance.api.v2.image_actions
import glance.api.v2.images
from glance.common import exception
from glance.common import store_utils
from glance import domain
import glance.schema
from glance.tests.unit import base
from glance.tests.unit.keymgr import fake as fake_keymgr
import glance.tests.unit.utils as unit_test_utils
from glance.tests.unit.v2 import test_tasks_resource
import glance.tests.utils as test_utils

CONF = cfg.CONF

DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
ISOTIME = '2012-05-16T15:27:36Z'


BASE_URI = unit_test_utils.BASE_URI


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'
UUID5 = '13c58ac4-210d-41ab-8cdb-1adfe4610019'
UUID6 = '6d33fd0f-2438-4419-acd0-ce1d452c97a0'
UUID7 = '75ddbc84-9427-4f3b-8d7d-b0fd0543d9a8'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

CHKSUM = '93264c3edf5972c9f1cb309543d38a5c'
CHKSUM1 = '43254c3edf6972c9f1cb309543d38a8c'

FAKEHASHALGO = 'fake-name-for-sha512'
MULTIHASH1 = hashlib.sha512(b'glance').hexdigest()
MULTIHASH2 = hashlib.sha512(b'image_service').hexdigest()


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


def _domain_fixture(id, **kwargs):
    properties = {
        'image_id': id,
        'name': None,
        'visibility': 'private',
        'checksum': None,
        'os_hash_algo': None,
        'os_hash_value': None,
        'owner': None,
        'status': 'queued',
        'size': None,
        'virtual_size': None,
        'locations': [],
        'protected': False,
        'disk_format': None,
        'container_format': None,
        'min_ram': None,
        'min_disk': None,
        'tags': [],
    }
    properties.update(kwargs)
    return glance.domain.Image(**properties)


def _db_image_member_fixture(image_id, member_id, **kwargs):
    obj = {
        'image_id': image_id,
        'member': member_id,
    }
    obj.update(kwargs)
    return obj


class FakeImage(object):
    def __init__(self, id=None, status='active', container_format='ami',
                 disk_format='ami', locations=None):
        self.id = id or UUID4
        self.status = status
        self.container_format = container_format
        self.disk_format = disk_format
        self.locations = locations
        self.owner = unit_test_utils.TENANT1
        self.created_at = ''
        self.updated_at = ''
        self.min_disk = ''
        self.min_ram = ''
        self.protected = False
        self.checksum = ''
        self.os_hash_algo = ''
        self.os_hash_value = ''
        self.size = 0
        self.virtual_size = 0
        self.visibility = 'public'
        self.os_hidden = False
        self.name = 'foo'
        self.tags = []
        self.extra_properties = {}

        # NOTE(danms): This fixture looks more like the db object than
        # the proxy model. This needs fixing all through the tests
        # below.
        self.image_id = self.id


class TestImagesController(base.IsolatedUnitTest):

    def setUp(self):
        super(TestImagesController, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = unit_test_utils.FakeStoreAPI()
        for i in range(1, 4):
            self.store.data['%s/fake_location_%i' % (BASE_URI, i)] = ('Z', 1)
        self.store_utils = unit_test_utils.FakeStoreUtils(self.store)
        self._create_images()
        self._create_image_members()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                self.policy,
                                                                self.notifier,
                                                                self.store)
        self.action_controller = (glance.api.v2.image_actions.
                                  ImageActionsController(self.db,
                                                         self.policy,
                                                         self.notifier,
                                                         self.store))
        self.controller.gateway.store_utils = self.store_utils
        self.controller._key_manager = fake_keymgr.fake_api()
        store.create_stores()

    def _create_images(self):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHKSUM,
                        os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
                        name='1', size=256, virtual_size=1024,
                        visibility='public',
                        locations=[{'url': '%s/%s' % (BASE_URI, UUID1),
                                    'metadata': {}, 'status': 'active'}],
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        created_at=DATETIME,
                        updated_at=DATETIME),
            _db_fixture(UUID2, owner=TENANT1, checksum=CHKSUM1,
                        os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH2,
                        name='2', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        created_at=DATETIME + datetime.timedelta(seconds=1),
                        updated_at=DATETIME + datetime.timedelta(seconds=1)),
            _db_fixture(UUID3, owner=TENANT3, checksum=CHKSUM1,
                        os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH2,
                        name='3', size=512, virtual_size=2048,
                        visibility='public', tags=['windows', '64bit', 'x86'],
                        created_at=DATETIME + datetime.timedelta(seconds=2),
                        updated_at=DATETIME + datetime.timedelta(seconds=2)),
            _db_fixture(UUID4, owner=TENANT4, name='4',
                        size=1024, virtual_size=3072,
                        created_at=DATETIME + datetime.timedelta(seconds=3),
                        updated_at=DATETIME + datetime.timedelta(seconds=3)),
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def _create_image_members(self):
        self.image_members = [
            _db_image_member_fixture(UUID4, TENANT2),
            _db_image_member_fixture(UUID4, TENANT3,
                                     status='accepted'),
        ]
        [self.db.image_member_create(None, image_member)
            for image_member in self.image_members]

    def test_index(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID3])
        self.assertEqual(expected, actual)

    def test_index_member_status_accepted(self):
        self.config(limit_param_default=5, api_limit_max=5)
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        output = self.controller.index(request)
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        # can see only the public image
        self.assertEqual(expected, actual)

        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        output = self.controller.index(request)
        self.assertEqual(4, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3, UUID4])
        self.assertEqual(expected, actual)

    def test_index_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.controller.index(request)
        self.assertEqual(4, len(output['images']))

    def test_index_admin_deleted_images_hidden(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.controller.delete(request, UUID1)
        output = self.controller.index(request)
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3, UUID4])
        self.assertEqual(expected, actual)

    def test_index_return_parameters(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID3, limit=1,
                                       sort_key=['created_at'],
                                       sort_dir=['desc'])
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2])
        self.assertEqual(actual, expected)
        self.assertEqual(UUID2, output['next_marker'])

    def test_index_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID3, limit=2)
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID1])
        self.assertEqual(expected, actual)
        self.assertEqual(UUID1, output['next_marker'])

    def test_index_no_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID1, limit=2)
        self.assertEqual(0, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([])
        self.assertEqual(expected, actual)
        self.assertNotIn('next_marker', output)

    def test_index_with_id_filter(self):
        request = unit_test_utils.get_fake_request('/images?id=%s' % UUID1)
        output = self.controller.index(request, filters={'id': UUID1})
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1])
        self.assertEqual(expected, actual)

    def test_index_with_invalid_hidden_filter(self):
        request = unit_test_utils.get_fake_request('/images?os_hidden=abcd')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request,
                          filters={'os_hidden': 'abcd'})

    def test_index_with_checksum_filter_single_image(self):
        req = unit_test_utils.get_fake_request('/images?checksum=%s' % CHKSUM)
        output = self.controller.index(req, filters={'checksum': CHKSUM})
        self.assertEqual(1, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID1]
        self.assertEqual(expected, actual)

    def test_index_with_checksum_filter_multiple_images(self):
        req = unit_test_utils.get_fake_request('/images?checksum=%s' % CHKSUM1)
        output = self.controller.index(req, filters={'checksum': CHKSUM1})
        self.assertEqual(2, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID3, UUID2]
        self.assertEqual(expected, actual)

    def test_index_with_non_existent_checksum(self):
        req = unit_test_utils.get_fake_request('/images?checksum=236231827')
        output = self.controller.index(req, filters={'checksum': '236231827'})
        self.assertEqual(0, len(output['images']))

    def test_index_with_os_hash_value_filter_single_image(self):
        req = unit_test_utils.get_fake_request(
            '/images?os_hash_value=%s' % MULTIHASH1)
        output = self.controller.index(req,
                                       filters={'os_hash_value': MULTIHASH1})
        self.assertEqual(1, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID1]
        self.assertEqual(expected, actual)

    def test_index_with_os_hash_value_filter_multiple_images(self):
        req = unit_test_utils.get_fake_request(
            '/images?os_hash_value=%s' % MULTIHASH2)
        output = self.controller.index(req,
                                       filters={'os_hash_value': MULTIHASH2})
        self.assertEqual(2, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID3, UUID2]
        self.assertEqual(expected, actual)

    def test_index_with_non_existent_os_hash_value(self):
        fake_hash_value = hashlib.sha512(b'not_used_in_fixtures').hexdigest()
        req = unit_test_utils.get_fake_request(
            '/images?os_hash_value=%s' % fake_hash_value)
        output = self.controller.index(req,
                                       filters={'checksum': fake_hash_value})
        self.assertEqual(0, len(output['images']))

    def test_index_size_max_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_max=512')
        output = self.controller.index(request, filters={'size_max': 512})
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_size_min_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_min=512')
        output = self.controller.index(request, filters={'size_min': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_size_range_filter(self):
        path = '/images?size_min=512&size_max=512'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'size_min': 512,
                                                'size_max': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_virtual_size_max_filter(self):
        ref = '/images?virtual_size_max=2048'
        request = unit_test_utils.get_fake_request(ref)
        output = self.controller.index(request,
                                       filters={'virtual_size_max': 2048})
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_virtual_size_min_filter(self):
        ref = '/images?virtual_size_min=2048'
        request = unit_test_utils.get_fake_request(ref)
        output = self.controller.index(request,
                                       filters={'virtual_size_min': 2048})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_virtual_size_range_filter(self):
        path = '/images?virtual_size_min=512&virtual_size_max=2048'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'virtual_size_min': 2048,
                                                'virtual_size_max': 2048})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(expected, actual)

    def test_index_with_invalid_max_range_filter_value(self):
        request = unit_test_utils.get_fake_request('/images?size_max=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index,
                          request,
                          filters={'size_max': 'blah'})

    def test_index_with_filters_return_many(self):
        path = '/images?status=queued'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, filters={'status': 'queued'})
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID3])
        self.assertEqual(expected, actual)

    def test_index_with_nonexistent_name_filter(self):
        request = unit_test_utils.get_fake_request('/images?name=%s' % 'blah')
        images = self.controller.index(request,
                                       filters={'name': 'blah'})['images']
        self.assertEqual(0, len(images))

    def test_index_with_non_default_is_public_filter(self):
        private_uuid = str(uuid.uuid4())
        new_image = _db_fixture(private_uuid,
                                visibility='private',
                                owner=TENANT3)
        self.db.image_create(None, new_image)

        path = '/images?visibility=private'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request,
                                       filters={'visibility': 'private'})
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([private_uuid])
        self.assertEqual(expected, actual)

        path = '/images?visibility=shared'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request,
                                       filters={'visibility': 'shared'})
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID4])
        self.assertEqual(expected, actual)

    def test_index_with_many_filters(self):
        url = '/images?status=queued&name=3'
        request = unit_test_utils.get_fake_request(url)
        output = self.controller.index(request,
                                       filters={
                                           'status': 'queued',
                                           'name': '3',
                                       })
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID3])
        self.assertEqual(expected, actual)

    def test_index_with_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, marker=UUID3)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(1, len(actual))
        self.assertIn(UUID2, actual)

    def test_index_with_limit(self):
        path = '/images'
        limit = 2
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=limit)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(limit, len(actual))
        self.assertIn(UUID3, actual)
        self.assertIn(UUID2, actual)

    def test_index_greater_than_limit_max(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=4)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(3, len(actual))
        self.assertNotIn(output['next_marker'], output)

    def test_index_default_limit(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(1, len(actual))

    def test_index_with_sort_dir(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_dir=['asc'], limit=3)
        actual = [image.image_id for image in output['images']]
        self.assertEqual(3, len(actual))
        self.assertEqual(UUID1, actual[0])
        self.assertEqual(UUID2, actual[1])
        self.assertEqual(UUID3, actual[2])

    def test_index_with_sort_key(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_key=['created_at'],
                                       limit=3)
        actual = [image.image_id for image in output['images']]
        self.assertEqual(3, len(actual))
        self.assertEqual(UUID3, actual[0])
        self.assertEqual(UUID2, actual[1])
        self.assertEqual(UUID1, actual[2])

    def test_index_with_multiple_sort_keys(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       sort_key=['created_at', 'name'],
                                       limit=3)
        actual = [image.image_id for image in output['images']]
        self.assertEqual(3, len(actual))
        self.assertEqual(UUID3, actual[0])
        self.assertEqual(UUID2, actual[1])
        self.assertEqual(UUID1, actual[2])

    def test_index_with_marker_not_found(self):
        fake_uuid = str(uuid.uuid4())
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, marker=fake_uuid)

    def test_index_invalid_sort_key(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, sort_key=['foo'])

    def test_index_zero_images(self):
        self.db.reset()
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual([], output['images'])

    def test_index_with_tags(self):
        path = '/images?tag=64bit'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, filters={'tags': ['64bit']})
        actual = [image.tags for image in output['images']]
        self.assertEqual(2, len(actual))
        self.assertIn('64bit', actual[0])
        self.assertIn('64bit', actual[1])

    def test_index_with_multi_tags(self):
        path = '/images?tag=power&tag=64bit'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'tags': ['power', '64bit']})
        actual = [image.tags for image in output['images']]
        self.assertEqual(1, len(actual))
        self.assertIn('64bit', actual[0])
        self.assertIn('power', actual[0])

    def test_index_with_multi_tags_and_nonexistent(self):
        path = '/images?tag=power&tag=fake'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'tags': ['power', 'fake']})
        actual = [image.tags for image in output['images']]
        self.assertEqual(0, len(actual))

    def test_index_with_tags_and_properties(self):
        path = '/images?tag=64bit&hypervisor_type=kvm'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'tags': ['64bit'],
                                                'hypervisor_type': 'kvm'})
        tags = [image.tags for image in output['images']]
        properties = [image.extra_properties for image in output['images']]
        self.assertEqual(len(tags), len(properties))
        self.assertIn('64bit', tags[0])
        self.assertEqual('kvm', properties[0]['hypervisor_type'])

    def test_index_with_multiple_properties(self):
        path = '/images?foo=bar&hypervisor_type=kvm'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'foo': 'bar',
                                                'hypervisor_type': 'kvm'})
        properties = [image.extra_properties for image in output['images']]
        self.assertEqual('kvm', properties[0]['hypervisor_type'])
        self.assertEqual('bar', properties[0]['foo'])

    def test_index_with_core_and_extra_property(self):
        path = '/images?disk_format=raw&foo=bar'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'foo': 'bar',
                                                'disk_format': 'raw'})
        properties = [image.extra_properties for image in output['images']]
        self.assertEqual(1, len(output['images']))
        self.assertEqual('raw', output['images'][0].disk_format)
        self.assertEqual('bar', properties[0]['foo'])

    def test_index_with_nonexistent_properties(self):
        path = '/images?abc=xyz&pudding=banana'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'abc': 'xyz',
                                                'pudding': 'banana'})
        self.assertEqual(0, len(output['images']))

    def test_index_with_non_existent_tags(self):
        path = '/images?tag=fake'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'tags': ['fake']})
        actual = [image.tags for image in output['images']]
        self.assertEqual(0, len(actual))

    def test_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.show(request, image_id=UUID2)
        self.assertEqual(UUID2, output.image_id)
        self.assertEqual('2', output.name)

    def test_show_deleted_properties(self):
        """Ensure that the api filters out deleted image properties."""

        # get the image properties into the odd state
        image = {
            'id': str(uuid.uuid4()),
            'status': 'active',
            'properties': {'poo': 'bear'},
        }
        self.db.image_create(None, image)
        self.db.image_update(None, image['id'],
                             {'properties': {'yin': 'yang'}},
                             purge_props=True)

        request = unit_test_utils.get_fake_request()
        output = self.controller.show(request, image['id'])
        self.assertEqual('yang', output.extra_properties['yin'])

    def test_show_non_existent(self):
        request = unit_test_utils.get_fake_request()
        image_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, request, image_id)

    def test_show_deleted_image_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.controller.delete(request, UUID1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, request, UUID1)

    def test_show_not_allowed(self):
        request = unit_test_utils.get_fake_request()
        self.assertEqual(TENANT1, request.context.project_id)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, request, UUID4)

    def test_image_import_raises_conflict_if_container_format_is_none(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(container_format=None)
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict_if_disk_format_is_none(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(disk_format=None)
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='queued')
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict_for_web_download(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'web-download'}})

    def test_image_import_raises_conflict_for_invalid_status_change(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    @mock.patch('glance.db.simple.api.image_set_property_atomic')
    @mock.patch('glance.api.common.get_thread_pool')
    def test_image_import_raises_bad_request(self, mock_gpt, mock_spa):
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='uploading')
            # NOTE(abhishekk): Due to
            # https://bugs.launchpad.net/glance/+bug/1712463 taskflow is not
            # executing. Once it is fixed instead of mocking spawn method
            # we should mock execute method of _ImportToStore task.
            mock_gpt.return_value.spawn.side_effect = ValueError
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})
            self.assertTrue(mock_gpt.return_value.spawn.called)

    def test_image_import_invalid_uri_filtering(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='queued')
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'web-download',
                                          'uri': 'fake_uri'}})

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1'}
        output = self.controller.create(request, image=image,
                                        extra_properties={},
                                        tags=[])
        self.assertEqual('image-1', output.name)
        self.assertEqual({}, output.extra_properties)
        self.assertEqual(set([]), output.tags)
        self.assertEqual('shared', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.create', output_log['event_type'])
        self.assertEqual('image-1', output_log['payload']['name'])

    def test_create_disabled_notification(self):
        self.config(disabled_notifications=["image.create"])
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1'}
        output = self.controller.create(request, image=image,
                                        extra_properties={},
                                        tags=[])
        self.assertEqual('image-1', output.name)
        self.assertEqual({}, output.extra_properties)
        self.assertEqual(set([]), output.tags)
        self.assertEqual('shared', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_create_with_properties(self):
        request = unit_test_utils.get_fake_request()
        image_properties = {'foo': 'bar'}
        image = {'name': 'image-1'}
        output = self.controller.create(request, image=image,
                                        extra_properties=image_properties,
                                        tags=[])
        self.assertEqual('image-1', output.name)
        self.assertEqual(image_properties, output.extra_properties)
        self.assertEqual(set([]), output.tags)
        self.assertEqual('shared', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.create', output_log['event_type'])
        self.assertEqual('image-1', output_log['payload']['name'])

    def test_create_with_too_many_properties(self):
        self.config(image_property_quota=1)
        request = unit_test_utils.get_fake_request()
        image_properties = {'foo': 'bar', 'foo2': 'bar'}
        image = {'name': 'image-1'}
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.create, request,
                          image=image,
                          extra_properties=image_properties,
                          tags=[])

    def test_create_with_bad_min_disk_size(self):
        request = unit_test_utils.get_fake_request()
        image = {'min_disk': -42, 'name': 'image-1'}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create, request,
                          image=image,
                          extra_properties={},
                          tags=[])

    def test_create_with_bad_min_ram_size(self):
        request = unit_test_utils.get_fake_request()
        image = {'min_ram': -42, 'name': 'image-1'}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create, request,
                          image=image,
                          extra_properties={},
                          tags=[])

    def test_create_public_image_as_admin(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1', 'visibility': 'public'}
        output = self.controller.create(request, image=image,
                                        extra_properties={}, tags=[])
        self.assertEqual('public', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.create', output_log['event_type'])
        self.assertEqual(output.image_id, output_log['payload']['id'])

    def test_create_dup_id(self):
        request = unit_test_utils.get_fake_request()
        image = {'image_id': UUID4}

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.create,
                          request,
                          image=image,
                          extra_properties={},
                          tags=[])

    def test_create_duplicate_tags(self):
        request = unit_test_utils.get_fake_request()
        tags = ['ping', 'ping']
        output = self.controller.create(request, image={},
                                        extra_properties={}, tags=tags)
        self.assertEqual(set(['ping']), output.tags)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.create', output_log['event_type'])
        self.assertEqual(output.image_id, output_log['payload']['id'])

    def test_create_with_too_many_tags(self):
        self.config(image_tag_quota=1)
        request = unit_test_utils.get_fake_request()
        tags = ['ping', 'pong']
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.create,
                          request, image={}, extra_properties={},
                          tags=tags)

    def test_create_with_owner_non_admin(self):
        request = unit_test_utils.get_fake_request()
        request.context.is_admin = False
        image = {'owner': '12345'}
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.create,
                          request, image=image, extra_properties={},
                          tags=[])

        request = unit_test_utils.get_fake_request()
        request.context.is_admin = False
        image = {'owner': TENANT1}
        output = self.controller.create(request, image=image,
                                        extra_properties={}, tags=[])
        self.assertEqual(TENANT1, output.owner)

    def test_create_with_owner_admin(self):
        request = unit_test_utils.get_fake_request()
        request.context.is_admin = True
        image = {'owner': '12345'}
        output = self.controller.create(request, image=image,
                                        extra_properties={}, tags=[])
        self.assertEqual('12345', output.owner)

    def test_create_with_duplicate_location(self):
        request = unit_test_utils.get_fake_request()
        location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        image = {'name': 'image-1', 'locations': [location, location]}
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.create,
                          request, image=image, extra_properties={},
                          tags=[])

    def test_create_unexpected_property(self):
        request = unit_test_utils.get_fake_request()
        image_properties = {'unexpected': 'unexpected'}
        image = {'name': 'image-1'}
        with mock.patch.object(domain.ImageFactory, 'new_image',
                               side_effect=TypeError):
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.controller.create, request, image=image,
                              extra_properties=image_properties, tags=[])

    def test_create_reserved_property(self):
        request = unit_test_utils.get_fake_request()
        image_properties = {'reserved': 'reserved'}
        image = {'name': 'image-1'}
        with mock.patch.object(domain.ImageFactory, 'new_image',
                               side_effect=exception.ReservedProperty(
                                   property='reserved')):
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.create, request, image=image,
                              extra_properties=image_properties, tags=[])

    def test_create_readonly_property(self):
        request = unit_test_utils.get_fake_request()
        image_properties = {'readonly': 'readonly'}
        image = {'name': 'image-1'}
        with mock.patch.object(domain.ImageFactory, 'new_image',
                               side_effect=exception.ReadonlyProperty(
                                   property='readonly')):
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.create, request, image=image,
                              extra_properties=image_properties, tags=[])

    def test_update_no_changes(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.update(request, UUID1, changes=[])
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(output.created_at, output.updated_at)
        self.assertEqual(2, len(output.tags))
        self.assertIn('ping', output.tags)
        self.assertIn('pong', output.tags)
        output_logs = self.notifier.get_logs()
        # NOTE(markwash): don't send a notification if nothing is updated
        self.assertEqual(0, len(output_logs))

    def test_update_queued_image_with_hidden(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['os_hidden'], 'value': 'true'}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID3, changes=changes)

    def test_update_with_bad_min_disk(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['min_disk'], 'value': -42}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes=changes)

    def test_update_with_bad_min_ram(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['min_ram'], 'value': -42}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes=changes)

    def test_update_image_doesnt_exist(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.update,
                          request, str(uuid.uuid4()), changes=[])

    def test_update_deleted_image_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.controller.delete(request, UUID1)
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.update,
                          request, UUID1, changes=[])

    def test_update_with_too_many_properties(self):
        self.config(show_multiple_locations=True)
        self.config(user_storage_quota='1')
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.update,
                          request, UUID1, changes=changes)

    def test_update_replace_base_attribute(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        request.context.is_admin = True
        changes = [{'op': 'replace', 'path': ['name'], 'value': 'fedora'},
                   {'op': 'replace', 'path': ['owner'], 'value': TENANT3}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual('fedora', output.name)
        self.assertEqual(TENANT3, output.owner)
        self.assertEqual({'foo': 'bar'}, output.extra_properties)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_replace_onwer_non_admin(self):
        request = unit_test_utils.get_fake_request()
        request.context.is_admin = False
        changes = [{'op': 'replace', 'path': ['owner'], 'value': TENANT3}]
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.update, request, UUID1, changes)

    def test_update_replace_tags(self):
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['tags'], 'value': ['king', 'kong']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(2, len(output.tags))
        self.assertIn('king', output.tags)
        self.assertIn('kong', output.tags)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_replace_property(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar', 'snitch': 'golden'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual('bar', output.extra_properties['foo'])
        self.assertEqual('golden', output.extra_properties['snitch'])

        changes = [
            {'op': 'replace', 'path': ['foo'], 'value': 'baz'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual('baz', output.extra_properties['foo'])
        self.assertEqual('golden', output.extra_properties['snitch'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_too_many_properties(self):
        self.config(image_property_quota=1)
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
        ]
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.update, request,
                          UUID1, changes)

    def test_update_add_and_remove_too_many_properties(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_property_quota=1)

        # We must remove two properties to avoid being
        # over the limit of 1 property
        changes = [
            {'op': 'remove', 'path': ['foo']},
            {'op': 'add', 'path': ['fizz'], 'value': 'buzz'},
        ]
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.update, request,
                          UUID1, changes)

    def test_update_add_unlimited_properties(self):
        self.config(image_property_quota=-1)
        request = unit_test_utils.get_fake_request()
        output = self.controller.show(request, UUID1)

        changes = [{'op': 'add',
                    'path': ['foo'],
                    'value': 'bar'}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_format_properties(self):
        statuses_for_immutability = ['active', 'saving', 'killed']
        request = unit_test_utils.get_fake_request(is_admin=True)
        for status in statuses_for_immutability:
            image = {
                'id': str(uuid.uuid4()),
                'status': status,
                'disk_format': 'ari',
                'container_format': 'ari',
            }
            self.db.image_create(None, image)
            changes = [
                {'op': 'replace', 'path': ['disk_format'], 'value': 'ami'},
            ]
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.update,
                              request, image['id'], changes)
            changes = [
                {'op': 'replace',
                 'path': ['container_format'],
                 'value': 'ami'},
            ]
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.update,
                              request, image['id'], changes)
        self.db.image_update(None, image['id'], {'status': 'queued'})

        changes = [
            {'op': 'replace', 'path': ['disk_format'], 'value': 'raw'},
            {'op': 'replace', 'path': ['container_format'], 'value': 'bare'},
        ]
        resp = self.controller.update(request, image['id'], changes)
        self.assertEqual('raw', resp.disk_format)
        self.assertEqual('bare', resp.container_format)

    def test_update_remove_property_while_over_limit(self):
        """Ensure that image properties can be removed.

        Image properties should be able to be removed as long as the image has
        fewer than the limited number of image properties after the
        transaction.

        """
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
            {'op': 'add', 'path': ['fizz'], 'value': 'buzz'},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_property_quota=1)

        # We must remove two properties to avoid being
        # over the limit of 1 property
        changes = [
            {'op': 'remove', 'path': ['foo']},
            {'op': 'remove', 'path': ['snitch']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(1, len(output.extra_properties))
        self.assertEqual('buzz', output.extra_properties['fizz'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_and_remove_property_under_limit(self):
        """Ensure that image properties can be removed.

        Image properties should be able to be added and removed simultaneously
        as long as the image has fewer than the limited number of image
        properties after the transaction.

        """
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_property_quota=1)

        # We must remove two properties to avoid being
        # over the limit of 1 property
        changes = [
            {'op': 'remove', 'path': ['foo']},
            {'op': 'remove', 'path': ['snitch']},
            {'op': 'add', 'path': ['fizz'], 'value': 'buzz'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(1, len(output.extra_properties))
        self.assertEqual('buzz', output.extra_properties['fizz'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_replace_missing_property(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'replace', 'path': 'foo', 'value': 'baz'},
        ]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, UUID1, changes)

    def test_prop_protection_with_create_and_permitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties={},
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'add', 'path': ['x_owner_foo'], 'value': 'bar'},
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('bar', output.extra_properties['x_owner_foo'])

    def test_prop_protection_with_update_and_permitted_policy(self):
        self.set_property_protections(use_policies=True)
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        request = unit_test_utils.get_fake_request(roles=['spl_role'])
        image = {'name': 'image-1'}
        extra_props = {'spl_creator_policy': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        self.assertEqual('bar',
                         created_image.extra_properties['spl_creator_policy'])

        another_request = unit_test_utils.get_fake_request(roles=['spl_role'])
        changes = [
            {'op': 'replace', 'path': ['spl_creator_policy'], 'value': 'par'},
        ]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          another_request, created_image.image_id, changes)
        another_request = unit_test_utils.get_fake_request(roles=['admin'])
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('par',
                         output.extra_properties['spl_creator_policy'])

    def test_prop_protection_with_create_with_patch_and_policy(self):
        self.set_property_protections(use_policies=True)
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        request = unit_test_utils.get_fake_request(roles=['spl_role', 'admin'])
        image = {'name': 'image-1'}
        extra_props = {'spl_default_policy': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        changes = [
            {'op': 'add', 'path': ['spl_creator_policy'], 'value': 'bar'},
        ]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          another_request, created_image.image_id, changes)

        another_request = unit_test_utils.get_fake_request(roles=['spl_role'])
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('bar',
                         output.extra_properties['spl_creator_policy'])

    def test_prop_protection_with_create_and_unpermitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties={},
                                               tags=[])
        roles = ['fake_member']
        another_request = unit_test_utils.get_fake_request(roles=roles)
        changes = [
            {'op': 'add', 'path': ['x_owner_foo'], 'value': 'bar'},
        ]
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.update, another_request,
                          created_image.image_id, changes)

    def test_prop_protection_with_show_and_permitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertEqual('bar', output.extra_properties['x_owner_foo'])

    def test_prop_protection_with_show_and_unpermitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['member'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertRaises(KeyError, output.extra_properties.__getitem__,
                          'x_owner_foo')

    def test_prop_protection_with_update_and_permitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'replace', 'path': ['x_owner_foo'], 'value': 'baz'},
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('baz', output.extra_properties['x_owner_foo'])

    def test_prop_protection_with_update_and_unpermitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        changes = [
            {'op': 'replace', 'path': ['x_owner_foo'], 'value': 'baz'},
        ]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          another_request, created_image.image_id, changes)

    def test_prop_protection_with_delete_and_permitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'remove', 'path': ['x_owner_foo']}
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertRaises(KeyError, output.extra_properties.__getitem__,
                          'x_owner_foo')

    def test_prop_protection_with_delete_and_unpermitted_role(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_owner_foo': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        changes = [
            {'op': 'remove', 'path': ['x_owner_foo']}
        ]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          another_request, created_image.image_id, changes)

    def test_create_protected_prop_case_insensitive(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties={},
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'add', 'path': ['x_case_insensitive'], 'value': '1'},
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('1', output.extra_properties['x_case_insensitive'])

    def test_read_protected_prop_case_insensitive(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_case_insensitive': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertEqual('1', output.extra_properties['x_case_insensitive'])

    def test_update_protected_prop_case_insensitive(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_case_insensitive': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'replace', 'path': ['x_case_insensitive'], 'value': '2'},
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('2', output.extra_properties['x_case_insensitive'])

    def test_delete_protected_prop_case_insensitive(self):
        enforcer = glance.api.policy.Enforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                enforcer,
                                                                self.notifier,
                                                                self.store)
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_case_insensitive': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'remove', 'path': ['x_case_insensitive']}
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertRaises(KeyError, output.extra_properties.__getitem__,
                          'x_case_insensitive')

    def test_create_non_protected_prop(self):
        """Property marked with special char @ creatable by an unknown role"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted_1': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        self.assertEqual('1',
                         created_image.extra_properties['x_all_permitted_1'])
        another_request = unit_test_utils.get_fake_request(roles=['joe_soap'])
        extra_props = {'x_all_permitted_2': '2'}
        created_image = self.controller.create(another_request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        self.assertEqual('2',
                         created_image.extra_properties['x_all_permitted_2'])

    def test_read_non_protected_prop(self):
        """Property marked with special char @ readable by an unknown role"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['joe_soap'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertEqual('1', output.extra_properties['x_all_permitted'])

    def test_update_non_protected_prop(self):
        """Property marked with special char @ updatable by an unknown role"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['joe_soap'])
        changes = [
            {'op': 'replace', 'path': ['x_all_permitted'], 'value': 'baz'},
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual('baz', output.extra_properties['x_all_permitted'])

    def test_delete_non_protected_prop(self):
        """Property marked with special char @ deletable by an unknown role"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['member'])
        changes = [
            {'op': 'remove', 'path': ['x_all_permitted']}
        ]
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertRaises(KeyError, output.extra_properties.__getitem__,
                          'x_all_permitted')

    def test_create_locked_down_protected_prop(self):
        """Property marked with special char ! creatable by no one"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties={},
                                               tags=[])
        roles = ['fake_member']
        another_request = unit_test_utils.get_fake_request(roles=roles)
        changes = [
            {'op': 'add', 'path': ['x_none_permitted'], 'value': 'bar'},
        ]
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.update, another_request,
                          created_image.image_id, changes)

    def test_read_locked_down_protected_prop(self):
        """Property marked with special char ! readable by no one"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['member'])
        image = {'name': 'image-1'}
        extra_props = {'x_none_read': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertRaises(KeyError, output.extra_properties.__getitem__,
                          'x_none_read')

    def test_update_locked_down_protected_prop(self):
        """Property marked with special char ! updatable by no one"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_none_update': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        changes = [
            {'op': 'replace', 'path': ['x_none_update'], 'value': 'baz'},
        ]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          another_request, created_image.image_id, changes)

    def test_delete_locked_down_protected_prop(self):
        """Property marked with special char ! deletable by no one"""
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_none_delete': 'bar'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['fake_role'])
        changes = [
            {'op': 'remove', 'path': ['x_none_delete']}
        ]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          another_request, created_image.image_id, changes)

    def test_update_replace_locations_non_empty(self):
        self.config(show_multiple_locations=True)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_replace_locations_metadata_update(self):
        self.config(show_multiple_locations=True)
        location = {'url': '%s/%s' % (BASE_URI, UUID1),
                    'metadata': {'a': 1}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [location]}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual({'a': 1}, output.locations[0]['metadata'])

    def test_locations_actions_with_locations_invisible(self):
        self.config(show_multiple_locations=False)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_replace_locations_invalid(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_property(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual('baz', output.extra_properties['foo'])
        self.assertEqual('golden', output.extra_properties['snitch'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_base_property_json_schema_version_4(self):
        request = unit_test_utils.get_fake_request()
        changes = [{
            'json_schema_version': 4, 'op': 'add',
            'path': ['name'], 'value': 'fedora'
        }]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_extra_property_json_schema_version_4(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        changes = [{
            'json_schema_version': 4, 'op': 'add',
            'path': ['foo'], 'value': 'baz'
        }]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_base_property_json_schema_version_10(self):
        request = unit_test_utils.get_fake_request()
        changes = [{
            'json_schema_version': 10, 'op': 'add',
            'path': ['name'], 'value': 'fedora'
        }]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual('fedora', output.name)

    def test_update_add_extra_property_json_schema_version_10(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        changes = [{
            'json_schema_version': 10, 'op': 'add',
            'path': ['foo'], 'value': 'baz'
        }]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual({'foo': 'baz'}, output.extra_properties)

    def test_update_add_property_already_present_json_schema_version_4(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual('bar', output.extra_properties['foo'])

        changes = [
            {'json_schema_version': 4, 'op': 'add',
             'path': ['foo'], 'value': 'baz'},
        ]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, UUID1, changes)

    def test_update_add_property_already_present_json_schema_version_10(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual('bar', output.extra_properties['foo'])

        changes = [
            {'json_schema_version': 10, 'op': 'add',
             'path': ['foo'], 'value': 'baz'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual({'foo': 'baz'}, output.extra_properties)

    def test_update_add_locations(self):
        self.config(show_multiple_locations=True)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(2, len(output.locations))
        self.assertEqual(new_location, output.locations[1])

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_replace_locations_on_queued(self,
                                         mock_get_size,
                                         mock_get_size_uri,
                                         mock_set_acls,
                                         mock_check_loc,
                                         mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued',
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location1 = {'url': '%s/fake_location_1' % BASE_URI,
                         'metadata': {},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        new_location2 = {'url': '%s/fake_location_2' % BASE_URI,
                         'metadata': {},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location1, new_location2]}]
        output = self.controller.update(request, image_id, changes)
        self.assertEqual(image_id, output.image_id)
        self.assertEqual(2, len(output.locations))
        self.assertEqual(new_location1['url'], output.locations[0]['url'])
        self.assertEqual(new_location2['url'], output.locations[1]['url'])
        self.assertEqual('active', output.status)
        self.assertEqual(CHKSUM, output.checksum)
        self.assertEqual('sha512', output.os_hash_algo)
        self.assertEqual(MULTIHASH1, output.os_hash_value)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_replace_locations_identify_associated_store(
            self, mock_get_size, mock_get_size_uri, mock_set_acls,
            mock_check_loc, mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        self.config(enabled_backends={'fake-store': 'http'})
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued',
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location1 = {'url': '%s/fake_location_1' % BASE_URI,
                         'metadata': {},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        new_location2 = {'url': '%s/fake_location_2' % BASE_URI,
                         'metadata': {},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location1, new_location2]}]

        with mock.patch.object(store_utils,
                               '_get_store_id_from_uri') as mock_store:
            mock_store.return_value = 'fake-store'
            # ensure location metadata is updated
            new_location1['metadata']['store'] = 'fake-store'
            new_location1['metadata']['store'] = 'fake-store'

            output = self.controller.update(request, image_id, changes)
            self.assertEqual(2, len(output.locations))
            self.assertEqual(image_id, output.image_id)
            self.assertEqual(new_location1, output.locations[0])
            self.assertEqual(new_location2, output.locations[1])
            self.assertEqual('active', output.status)
            self.assertEqual(CHKSUM, output.checksum)
            self.assertEqual('sha512', output.os_hash_algo)
            self.assertEqual(MULTIHASH1, output.os_hash_value)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_replace_locations_unknon_locations(
            self, mock_get_size, mock_get_size_uri, mock_set_acls,
            mock_check_loc, mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        self.config(enabled_backends={'fake-store': 'http'})
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued',
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location1 = {'url': 'unknown://whocares',
                         'metadata': {},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        new_location2 = {'url': 'unknown://whatever',
                         'metadata': {'store': 'unkstore'},
                         'validation_data': {'checksum': CHKSUM,
                                             'os_hash_algo': 'sha512',
                                             'os_hash_value': MULTIHASH1}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location1, new_location2]}]

        output = self.controller.update(request, image_id, changes)
        self.assertEqual(2, len(output.locations))
        self.assertEqual(image_id, output.image_id)
        self.assertEqual('active', output.status)
        self.assertEqual(CHKSUM, output.checksum)
        self.assertEqual('sha512', output.os_hash_algo)
        self.assertEqual(MULTIHASH1, output.os_hash_value)
        # ensure location metadata is same
        self.assertEqual(new_location1, output.locations[0])
        self.assertEqual(new_location2, output.locations[1])

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_new_validation_data_on_active(self,
                                                        mock_get_size,
                                                        mock_get_size_uri,
                                                        mock_set_acls,
                                                        mock_check_loc,
                                                        mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {},
                        'validation_data': {'checksum': CHKSUM,
                                            'os_hash_algo': 'sha512',
                                            'os_hash_value': MULTIHASH1}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              "may only be provided when image status "
                              "is 'queued'",
                              self.controller.update,
                              request, image_id, changes)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_replace_locations_different_validation_data(self,
                                                         mock_get_size,
                                                         mock_get_size_uri,
                                                         mock_set_acls,
                                                         mock_check_loc,
                                                         mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        checksum=CHKSUM,
                        os_hash_algo='sha512',
                        os_hash_value=MULTIHASH1),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {},
                        'validation_data': {'checksum': CHKSUM1,
                                            'os_hash_algo': 'sha512',
                                            'os_hash_value': MULTIHASH2}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              "already set with a different value",
                              self.controller.update,
                              request, image_id, changes)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_on_queued(self,
                                    mock_get_size,
                                    mock_get_size_uri,
                                    mock_set_acls,
                                    mock_check_loc,
                                    mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1, checksum=CHKSUM,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued'),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, image_id, changes)
        self.assertEqual(image_id, output.image_id)
        self.assertEqual(1, len(output.locations))
        self.assertEqual(new_location, output.locations[0])
        self.assertEqual('active', output.status)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_identify_associated_store(
            self, mock_get_size, mock_get_size_uri, mock_set_acls,
            mock_check_loc, mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        self.config(enabled_backends={'fake-store': 'http'})
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1, checksum=CHKSUM,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued'),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        with mock.patch.object(store_utils,
                               '_get_store_id_from_uri') as mock_store:
            mock_store.return_value = 'fake-store'
            output = self.controller.update(request, image_id, changes)

            self.assertEqual(image_id, output.image_id)
            self.assertEqual(1, len(output.locations))
            self.assertEqual('active', output.status)
            # ensure location metadata is updated
            new_location['metadata']['store'] = 'fake-store'
            self.assertEqual(new_location, output.locations[0])

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_unknown_locations(
            self, mock_get_size, mock_get_size_uri, mock_set_acls,
            mock_check_loc, mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        self.config(enabled_backends={'fake-store': 'http'})
        image_id = str(uuid.uuid4())

        self.images = [
            _db_fixture(image_id, owner=TENANT1, checksum=CHKSUM,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued'),
        ]
        self.db.image_create(None, self.images[0])

        new_location = {'url': 'unknown://whocares', 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]

        output = self.controller.update(request, image_id, changes)

        self.assertEqual(image_id, output.image_id)
        self.assertEqual('active', output.status)
        self.assertEqual(1, len(output.locations))
        # ensure location metadata is same
        self.assertEqual(new_location, output.locations[0])

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_invalid_validation_data(self,
                                                  mock_get_size,
                                                  mock_get_size_uri,
                                                  mock_set_acls,
                                                  mock_check_loc,
                                                  mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='queued'),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()

        location = {
            'url': '%s/fake_location_1' % BASE_URI,
            'metadata': {},
            'validation_data': {}
        }
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': location}]

        changes[0]['value']['validation_data'] = {
            'checksum': 'something the same length as md5',
            'os_hash_algo': 'sha512',
            'os_hash_value': MULTIHASH1,
        }
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              'checksum .* is not a valid hexadecimal value',
                              self.controller.update,
                              request, image_id, changes)

        changes[0]['value']['validation_data'] = {
            'checksum': '0123456789abcdef',
            'os_hash_algo': 'sha512',
            'os_hash_value': MULTIHASH1,
        }
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              'checksum .* is not the correct size',
                              self.controller.update,
                              request, image_id, changes)

        changes[0]['value']['validation_data'] = {
            'checksum': CHKSUM,
            'os_hash_algo': 'sha256',
            'os_hash_value': MULTIHASH1,
        }
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              'os_hash_algo must be sha512',
                              self.controller.update,
                              request, image_id, changes)

        changes[0]['value']['validation_data'] = {
            'checksum': CHKSUM,
            'os_hash_algo': 'sha512',
            'os_hash_value': 'not a hex value',
        }
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              'os_hash_value .* is not a valid hexadecimal '
                              'value',
                              self.controller.update,
                              request, image_id, changes)

        changes[0]['value']['validation_data'] = {
            'checksum': CHKSUM,
            'os_hash_algo': 'sha512',
            'os_hash_value': '0123456789abcdef',
        }
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              'os_hash_value .* is not the correct size '
                              'for sha512',
                              self.controller.update,
                              request, image_id, changes)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_same_validation_data(self,
                                               mock_get_size,
                                               mock_get_size_uri,
                                               mock_set_acls,
                                               mock_check_loc,
                                               mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        os_hash_value = '6513f21e44aa3da349f248188a44bc304a3653a04122d8fb45' \
                        '35423c8e1d14cd6a153f735bb0982e2161b5b5186106570c17' \
                        'a9e58b64dd39390617cd5a350f78'
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        checksum='checksum1',
                        os_hash_algo='sha512',
                        os_hash_value=os_hash_value),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {},
                        'validation_data': {'checksum': 'checksum1',
                                            'os_hash_algo': 'sha512',
                                            'os_hash_value': os_hash_value}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, image_id, changes)
        self.assertEqual(image_id, output.image_id)
        self.assertEqual(1, len(output.locations))
        self.assertEqual(new_location, output.locations[0])
        self.assertEqual('active', output.status)

    @mock.patch.object(glance.quota, '_calc_required_size')
    @mock.patch.object(glance.location, '_check_image_location')
    @mock.patch.object(glance.location.ImageRepoProxy, '_set_acls')
    @mock.patch.object(store, 'get_size_from_uri_and_backend')
    @mock.patch.object(store, 'get_size_from_backend')
    def test_add_location_different_validation_data(self,
                                                    mock_get_size,
                                                    mock_get_size_uri,
                                                    mock_set_acls,
                                                    mock_check_loc,
                                                    mock_calc):
        mock_calc.return_value = 1
        mock_get_size.return_value = 1
        mock_get_size_uri.return_value = 1
        self.config(show_multiple_locations=True)
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        checksum=CHKSUM,
                        os_hash_algo='sha512',
                        os_hash_value=MULTIHASH1),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location_1' % BASE_URI,
                        'metadata': {},
                        'validation_data': {'checksum': CHKSUM1,
                                            'os_hash_algo': 'sha512',
                                            'os_hash_value': MULTIHASH2}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        six.assertRaisesRegex(self,
                              webob.exc.HTTPConflict,
                              "already set with a different value",
                              self.controller.update,
                              request, image_id, changes)

    def _test_update_locations_status(self, image_status, update):
        self.config(show_multiple_locations=True)
        self.images = [
            _db_fixture('1', owner=TENANT1, checksum=CHKSUM,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status=image_status),
        ]
        request = unit_test_utils.get_fake_request()
        if image_status == 'deactivated':
            self.db.image_create(request.context, self.images[0])
        else:
            self.db.image_create(None, self.images[0])
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': update, 'path': ['locations', '-'],
                    'value': new_location}]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, '1', changes)

    def test_location_add_not_permitted_status_saving(self):
        self._test_update_locations_status('saving', 'add')

    def test_location_add_not_permitted_status_deactivated(self):
        self._test_update_locations_status('deactivated', 'add')

    def test_location_add_not_permitted_status_deleted(self):
        self._test_update_locations_status('deleted', 'add')

    def test_location_add_not_permitted_status_pending_delete(self):
        self._test_update_locations_status('pending_delete', 'add')

    def test_location_add_not_permitted_status_killed(self):
        self._test_update_locations_status('killed', 'add')

    def test_location_add_not_permitted_status_importing(self):
        self._test_update_locations_status('importing', 'add')

    def test_location_add_not_permitted_status_uploading(self):
        self._test_update_locations_status('uploading', 'add')

    def test_location_remove_not_permitted_status_saving(self):
        self._test_update_locations_status('saving', 'remove')

    def test_location_remove_not_permitted_status_deactivated(self):
        self._test_update_locations_status('deactivated', 'remove')

    def test_location_remove_not_permitted_status_deleted(self):
        self._test_update_locations_status('deleted', 'remove')

    def test_location_remove_not_permitted_status_pending_delete(self):
        self._test_update_locations_status('pending_delete', 'remove')

    def test_location_remove_not_permitted_status_killed(self):
        self._test_update_locations_status('killed', 'remove')

    def test_location_remove_not_permitted_status_queued(self):
        self._test_update_locations_status('queued', 'remove')

    def test_location_remove_not_permitted_status_importing(self):
        self._test_update_locations_status('importing', 'remove')

    def test_location_remove_not_permitted_status_uploading(self):
        self._test_update_locations_status('uploading', 'remove')

    def test_location_replace_not_permitted_status_saving(self):
        self._test_update_locations_status('saving', 'replace')

    def test_location_replace_not_permitted_status_deactivated(self):
        self._test_update_locations_status('deactivated', 'replace')

    def test_location_replace_not_permitted_status_deleted(self):
        self._test_update_locations_status('deleted', 'replace')

    def test_location_replace_not_permitted_status_pending_delete(self):
        self._test_update_locations_status('pending_delete', 'replace')

    def test_location_replace_not_permitted_status_killed(self):
        self._test_update_locations_status('killed', 'replace')

    def test_location_replace_not_permitted_status_importing(self):
        self._test_update_locations_status('importing', 'replace')

    def test_location_replace_not_permitted_status_uploading(self):
        self._test_update_locations_status('uploading', 'replace')

    def test_update_add_locations_insertion(self):
        self.config(show_multiple_locations=True)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '0'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(2, len(output.locations))
        self.assertEqual(new_location, output.locations[0])

    def test_update_add_locations_list(self):
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': {'url': 'foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_locations_invalid(self):
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': {'url': 'unknow://foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

        changes = [{'op': 'add', 'path': ['locations', None],
                    'value': {'url': 'unknow://foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_duplicate_locations(self):
        self.config(show_multiple_locations=True)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(2, len(output.locations))
        self.assertEqual(new_location, output.locations[1])

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_too_many_locations(self):
        self.config(show_multiple_locations=True)
        self.config(image_location_quota=1)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_2' % BASE_URI,
                       'metadata': {}}},
        ]
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.update, request,
                          UUID1, changes)

    def test_update_add_and_remove_too_many_locations(self):
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_2' % BASE_URI,
                       'metadata': {}}},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_location_quota=1)

        # We must remove two properties to avoid being
        # over the limit of 1 property
        changes = [
            {'op': 'remove', 'path': ['locations', '0']},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_3' % BASE_URI,
                       'metadata': {}}},
        ]
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.update, request,
                          UUID1, changes)

    def test_update_add_unlimited_locations(self):
        self.config(show_multiple_locations=True)
        self.config(image_location_quota=-1)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_remove_location_while_over_limit(self):
        """Ensure that image locations can be removed.

        Image locations should be able to be removed as long as the image has
        fewer than the limited number of image locations after the
        transaction.
        """
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_2' % BASE_URI,
                       'metadata': {}}},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_location_quota=1)
        self.config(show_multiple_locations=True)

        # We must remove two locations to avoid being over
        # the limit of 1 location
        changes = [
            {'op': 'remove', 'path': ['locations', '0']},
            {'op': 'remove', 'path': ['locations', '0']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(1, len(output.locations))
        self.assertIn('fake_location_2', output.locations[0]['url'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_and_remove_location_under_limit(self):
        """Ensure that image locations can be removed.

        Image locations should be able to be added and removed simultaneously
        as long as the image has fewer than the limited number of image
        locations after the transaction.
        """
        self.mock_object(store, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_2' % BASE_URI,
                       'metadata': {}}},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_location_quota=2)

        # We must remove two properties to avoid being
        # over the limit of 1 property
        changes = [
            {'op': 'remove', 'path': ['locations', '0']},
            {'op': 'remove', 'path': ['locations', '0']},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_3' % BASE_URI,
                       'metadata': {}}},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(2, len(output.locations))
        self.assertIn('fake_location_3', output.locations[1]['url'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_remove_base_property(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'remove', 'path': ['name']}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_remove_property(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar', 'snitch': 'golden'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual('bar', output.extra_properties['foo'])
        self.assertEqual('golden', output.extra_properties['snitch'])

        changes = [
            {'op': 'remove', 'path': ['snitch']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual({'foo': 'bar'}, output.extra_properties)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_remove_missing_property(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'remove', 'path': ['foo']},
        ]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, UUID1, changes)

    def test_update_remove_location(self):
        self.config(show_multiple_locations=True)
        self.mock_object(store, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)

        request = unit_test_utils.get_fake_request()
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        self.controller.update(request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', '0']}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(1, len(output.locations))
        self.assertEqual('active', output.status)

    def test_update_remove_location_invalid_pos(self):
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location' % BASE_URI,
                       'metadata': {}}}]
        self.controller.update(request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', None]}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', '-1']}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', '99']}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', 'x']}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_remove_location_store_exception(self):
        self.config(show_multiple_locations=True)

        def fake_delete_image_location_from_backend(self, *args, **kwargs):
            raise Exception('fake_backend_exception')

        self.mock_object(self.store_utils,
                         'delete_image_location_from_backend',
                         fake_delete_image_location_from_backend)

        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location' % BASE_URI,
                       'metadata': {}}}]
        self.controller.update(request, UUID1, changes)
        changes = [{'op': 'remove', 'path': ['locations', '0']}]
        self.assertRaises(webob.exc.HTTPInternalServerError,
                          self.controller.update, request, UUID1, changes)

    def test_update_multiple_changes(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar', 'snitch': 'golden'}
        self.db.image_update(None, UUID1, {'properties': properties})

        changes = [
            {'op': 'replace', 'path': ['min_ram'], 'value': 128},
            {'op': 'replace', 'path': ['foo'], 'value': 'baz'},
            {'op': 'remove', 'path': ['snitch']},
            {'op': 'add', 'path': ['kb'], 'value': 'dvorak'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(UUID1, output.image_id)
        self.assertEqual(128, output.min_ram)
        self.addDetail('extra_properties',
                       testtools.content.json_content(
                           jsonutils.dumps(output.extra_properties)))
        self.assertEqual(2, len(output.extra_properties))
        self.assertEqual('baz', output.extra_properties['foo'])
        self.assertEqual('dvorak', output.extra_properties['kb'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_invalid_operation(self):
        request = unit_test_utils.get_fake_request()
        change = {'op': 'test', 'path': 'options', 'value': 'puts'}
        try:
            self.controller.update(request, UUID1, [change])
        except AttributeError:
            pass  # AttributeError is the desired behavior
        else:
            self.fail('Failed to raise AssertionError on %s' % change)

    def test_update_duplicate_tags(self):
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['tags'], 'value': ['ping', 'ping']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(1, len(output.tags))
        self.assertIn('ping', output.tags)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.update', output_log['event_type'])
        self.assertEqual(UUID1, output_log['payload']['id'])

    def test_update_disabled_notification(self):
        self.config(disabled_notifications=["image.update"])
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['name'], 'value': 'Ping Pong'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual('Ping Pong', output.name)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_delete(self):
        request = unit_test_utils.get_fake_request()
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)
        try:
            self.controller.delete(request, UUID1)
            output_logs = self.notifier.get_logs()
            self.assertEqual(1, len(output_logs))
            output_log = output_logs[0]
            self.assertEqual('INFO', output_log['notification_type'])
            self.assertEqual("image.delete", output_log['event_type'])
        except Exception as e:
            self.fail("Delete raised exception: %s" % e)

        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('deleted', deleted_img['status'])
        self.assertNotIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

    @mock.patch.object(store, 'get_store_from_store_identifier')
    @mock.patch.object(store.location, 'get_location_from_uri_and_backend')
    @mock.patch.object(store_utils, 'get_dir_separator')
    def test_verify_staging_data_deleted_on_image_delete(
            self, mock_get_dir_separator, mock_location,
            mock_store):
        self.config(enabled_backends={'fake-store': 'file'})
        fake_staging_store = mock.Mock()
        mock_store.return_value = fake_staging_store
        mock_get_dir_separator.return_value = (
            "/", "/tmp/os_glance_staging_store")
        image_id = str(uuid.uuid4())
        self.images = [
            _db_fixture(image_id, owner=TENANT1,
                        name='1',
                        disk_format='raw',
                        container_format='bare',
                        status='importing',
                        checksum=None,
                        os_hash_algo=None,
                        os_hash_value=None),
        ]
        self.db.image_create(None, self.images[0])
        request = unit_test_utils.get_fake_request()
        try:
            self.controller.delete(request, image_id)
            self.assertEqual(1, mock_store.call_count)
            mock_store.assert_called_once_with("os_glance_staging_store")
            self.assertEqual(1, mock_location.call_count)
            fake_staging_store.delete.assert_called_once()
        except Exception as e:
            self.fail("Delete raised exception: %s" % e)

        deleted_img = self.db.image_get(request.context, image_id,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('deleted', deleted_img['status'])

    def test_delete_with_tags(self):
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['tags'],
             'value': ['many', 'cool', 'new', 'tags']},
        ]
        self.controller.update(request, UUID1, changes)
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)
        self.controller.delete(request, UUID1)
        output_logs = self.notifier.get_logs()

        # Get `delete` event from logs
        output_delete_logs = [output_log for output_log in output_logs
                              if output_log['event_type'] == 'image.delete']

        self.assertEqual(1, len(output_delete_logs))
        output_log = output_delete_logs[0]

        self.assertEqual('INFO', output_log['notification_type'])

        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('deleted', deleted_img['status'])
        self.assertNotIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

    def test_delete_disabled_notification(self):
        self.config(disabled_notifications=["image.delete"])
        request = unit_test_utils.get_fake_request()
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)
        try:
            self.controller.delete(request, UUID1)
            output_logs = self.notifier.get_logs()
            self.assertEqual(0, len(output_logs))
        except Exception as e:
            self.fail("Delete raised exception: %s" % e)

        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('deleted', deleted_img['status'])
        self.assertNotIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

    def test_delete_queued_updates_status(self):
        """Ensure status of queued image is updated (LP bug #1048851)"""
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'queued'})
        image_id = image['id']
        self.controller.delete(request, image_id)

        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_delete_queued_updates_status_delayed_delete(self):
        """Ensure status of queued image is updated (LP bug #1048851).

        Must be set to 'deleted' when delayed_delete isenabled.
        """
        self.config(delayed_delete=True)

        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'queued'})
        image_id = image['id']
        self.controller.delete(request, image_id)

        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_delete_not_in_store(self):
        request = unit_test_utils.get_fake_request()
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)
        for k in self.store.data:
            if UUID1 in k:
                del self.store.data[k]
                break

        self.controller.delete(request, UUID1)
        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('deleted', deleted_img['status'])
        self.assertNotIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

    def test_delayed_delete(self):
        self.config(delayed_delete=True)
        request = unit_test_utils.get_fake_request()
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

        self.controller.delete(request, UUID1)
        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual('pending_delete', deleted_img['status'])
        self.assertIn('%s/%s' % (BASE_URI, UUID1), self.store.data)

    def test_delete_non_existent(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.delete,
                          request, str(uuid.uuid4()))

    def test_delete_already_deleted_image_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.controller.delete(request, UUID1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete, request, UUID1)

    def test_delete_not_allowed(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.delete,
                          request, UUID4)

    def test_delete_in_use(self):
        def fake_safe_delete_from_backend(self, *args, **kwargs):
            raise store.exceptions.InUseByStore()
        self.mock_object(self.store_utils, 'safe_delete_from_backend',
                         fake_safe_delete_from_backend)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPConflict, self.controller.delete,
                          request, UUID1)

    def test_delete_has_snapshot(self):
        def fake_safe_delete_from_backend(self, *args, **kwargs):
            raise store.exceptions.HasSnapshot()
        self.mock_object(self.store_utils, 'safe_delete_from_backend',
                         fake_safe_delete_from_backend)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPConflict, self.controller.delete,
                          request, UUID1)

    def test_delete_to_unallowed_status(self):
        # from deactivated to pending-delete
        self.config(delayed_delete=True)
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.action_controller.deactivate(request, UUID1)

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.delete,
                          request, UUID1)

    def test_delete_uploading_status_image(self):
        """Ensure uploading image is deleted (LP bug #1733289)
        Ensure image stuck in uploading state is deleted (LP bug #1836140)
        """
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'uploading'})
        image_id = image['id']
        with mock.patch.object(os.path, 'exists') as mock_exists:
            mock_exists.return_value = True
            with mock.patch.object(os, "unlink") as mock_unlik:
                self.controller.delete(request, image_id)

                self.assertEqual(1, mock_exists.call_count)
                self.assertEqual(1, mock_unlik.call_count)

        # Ensure that image is deleted
        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_deletion_of_staging_data_failed(self):
        """Ensure uploading image is deleted (LP bug #1733289)
        Ensure image stuck in uploading state is deleted (LP bug #1836140)
        """
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'uploading'})
        image_id = image['id']
        with mock.patch.object(os.path, 'exists') as mock_exists:
            mock_exists.return_value = False
            with mock.patch.object(os, "unlink") as mock_unlik:
                self.controller.delete(request, image_id)

                self.assertEqual(1, mock_exists.call_count)
                self.assertEqual(0, mock_unlik.call_count)

        # Ensure that image is deleted
        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_delete_from_store_no_multistore(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_from_store, request,
                          "the IDs should", "not matter")

    def test_index_with_invalid_marker(self):
        fake_uuid = str(uuid.uuid4())
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, marker=fake_uuid)

    def test_invalid_locations_op_pos(self):
        pos = self.controller._get_locations_op_pos(None, 2, True)
        self.assertIsNone(pos)
        pos = self.controller._get_locations_op_pos('1', None, True)
        self.assertIsNone(pos)

    @mock.patch('glance.db.simple.api.image_set_property_atomic')
    @mock.patch.object(glance.api.authorization.TaskFactoryProxy, 'new_task')
    @mock.patch.object(glance.domain.TaskExecutorFactory, 'new_task_executor')
    @mock.patch('glance.api.common.get_thread_pool')
    def test_image_import(self, mock_gtp, mock_nte, mock_nt, mock_spa):
        request = unit_test_utils.get_fake_request()
        image = FakeImage(status='uploading')
        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = image
            output = self.controller.import_image(
                request, UUID4, {'method': {'name': 'glance-direct'}})

        self.assertEqual(UUID4, output)

        # Make sure we set the lock on the image
        mock_spa.assert_called_once_with(UUID4, 'os_glance_import_task',
                                         mock_nt.return_value.task_id)

        # Make sure we grabbed a thread pool, and that we asked it
        # to spawn the task's run method with it.
        mock_gtp.assert_called_once_with('tasks_pool')
        mock_gtp.return_value.spawn.assert_called_once_with(
            mock_nt.return_value.run, mock_nte.return_value)

    @mock.patch.object(glance.domain.TaskFactory, 'new_task')
    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'get')
    def test_image_import_not_allowed(self, mock_get, mock_new_task):
        # NOTE(danms): FakeImage is owned by utils.TENANT1. Try to do the
        # import as TENANT2 and we should get an HTTPForbidden
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        mock_get.return_value = FakeImage(status='uploading')
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.import_image,
                          request, UUID4, {'method': {'name':
                                                      'glance-direct'}})
        # NOTE(danms): Make sure we failed early and never even created
        # a task
        mock_new_task.assert_not_called()

    @mock.patch('glance.db.simple.api.image_set_property_atomic')
    @mock.patch('glance.context.RequestContext.elevated')
    @mock.patch.object(glance.domain.TaskFactory, 'new_task')
    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'get')
    def test_image_import_copy_allowed_by_policy(self, mock_get,
                                                 mock_new_task,
                                                 mock_elevated,
                                                 mock_spa,
                                                 allowed=True):
        # NOTE(danms): FakeImage is owned by utils.TENANT1. Try to do the
        # import as TENANT2, but with a policy exception
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        mock_get.return_value = FakeImage(status='active', locations=[])

        self.policy.rules = {'copy_image': allowed}

        req_body = {'method': {'name': 'copy-image'},
                    'stores': ['cheap']}

        with mock.patch.object(
                self.controller.gateway,
                'get_task_executor_factory',
                side_effect=self.controller.gateway.get_task_executor_factory
        ) as mock_tef:
            self.controller.import_image(request, UUID4, req_body)
            # Make sure we passed an admin context to our task executor factory
            mock_tef.assert_called_once_with(
                request.context,
                admin_context=mock_elevated.return_value)

        expected_input = {'image_id': UUID4,
                          'import_req': mock.ANY,
                          'backend': mock.ANY}
        mock_new_task.assert_called_with(task_type='api_image_import',
                                         owner=TENANT2,
                                         task_input=expected_input)

    def test_image_import_copy_not_allowed_by_policy(self):
        # Make sure that if the policy check fails, we fail a copy-image with
        # Forbidden
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.test_image_import_copy_allowed_by_policy,
                          allowed=False)

    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'get')
    def test_image_import_locked(self, mock_get):
        task = test_tasks_resource._db_fixture(test_tasks_resource.UUID1,
                                               status='pending')
        self.db.task_create(None, task)
        image = FakeImage(status='uploading')
        # Image is locked with a valid task that has not aged out, so
        # the lock will not be busted.
        image.extra_properties['os_glance_import_task'] = task['id']
        mock_get.return_value = image

        request = unit_test_utils.get_fake_request(tenant=TENANT1)
        req_body = {'method': {'name': 'glance-direct'}}

        exc = self.assertRaises(webob.exc.HTTPConflict,
                                self.controller.import_image,
                                request, UUID1, req_body)
        self.assertEqual('Image has active task', str(exc))

    @mock.patch('glance.db.simple.api.image_set_property_atomic')
    @mock.patch('glance.db.simple.api.image_delete_property_atomic')
    @mock.patch.object(glance.api.authorization.TaskFactoryProxy, 'new_task')
    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'get')
    def test_image_import_locked_by_reaped_task(self, mock_get, mock_nt,
                                                mock_dpi, mock_spi):
        image = FakeImage(status='uploading')
        # Image is locked by some other task that TaskRepo will not find
        image.extra_properties['os_glance_import_task'] = 'missing'
        mock_get.return_value = image

        request = unit_test_utils.get_fake_request(tenant=TENANT1)
        req_body = {'method': {'name': 'glance-direct'}}

        mock_nt.return_value.task_id = 'mytask'
        self.controller.import_image(request, UUID1, req_body)

        # We should have atomically deleted the missing task lock
        mock_dpi.assert_called_once_with(image.id, 'os_glance_import_task',
                                         'missing')
        # We should have atomically grabbed the lock with our task id
        mock_spi.assert_called_once_with(image.id, 'os_glance_import_task',
                                         'mytask')

    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'save')
    @mock.patch('glance.db.simple.api.image_set_property_atomic')
    @mock.patch('glance.db.simple.api.image_delete_property_atomic')
    @mock.patch.object(glance.api.authorization.TaskFactoryProxy, 'new_task')
    @mock.patch.object(glance.api.authorization.ImageRepoProxy, 'get')
    def test_image_import_locked_by_bustable_task(self, mock_get, mock_nt,
                                                  mock_dpi, mock_spi,
                                                  mock_save,
                                                  task_status='processing'):
        if task_status == 'processing':
            # NOTE(danms): Only set task_input on one of the tested
            # states to make sure we don't choke on a task without
            # some of the data set yet.
            task_input = {'backend': ['store2']}
        else:
            task_input = {}
        task = test_tasks_resource._db_fixture(
            test_tasks_resource.UUID1,
            status=task_status,
            input=task_input)
        self.db.task_create(None, task)
        image = FakeImage(status='uploading')
        # Image is locked by a task in 'processing' state
        image.extra_properties['os_glance_import_task'] = task['id']
        image.extra_properties['os_glance_importing_to_stores'] = 'store2'
        mock_get.return_value = image

        request = unit_test_utils.get_fake_request(tenant=TENANT1)
        req_body = {'method': {'name': 'glance-direct'}}

        # Task has only been running for ten minutes
        time_fixture = fixture.TimeFixture(task['updated_at'] +
                                           datetime.timedelta(minutes=10))
        self.useFixture(time_fixture)

        mock_nt.return_value.task_id = 'mytask'

        # Task holds the lock, API refuses to bust it
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.import_image,
                          request, UUID1, req_body)
        mock_dpi.assert_not_called()
        mock_spi.assert_not_called()
        mock_nt.assert_not_called()

        # Fast forward to 90 minutes from now
        time_fixture.advance_time_delta(datetime.timedelta(minutes=90))
        self.controller.import_image(request, UUID1, req_body)

        # API deleted the other task's lock and locked it for us
        mock_dpi.assert_called_once_with(image.id, 'os_glance_import_task',
                                         task['id'])
        mock_spi.assert_called_once_with(image.id, 'os_glance_import_task',
                                         'mytask')

        # If we stored task_input with information about the stores
        # and thus triggered the cleanup code, make sure that cleanup
        # happened here.
        if task_status == 'processing':
            self.assertNotIn('store2',
                             image.extra_properties[
                                 'os_glance_importing_to_stores'])

    def test_image_import_locked_by_bustable_terminal_task_failure(self):
        # Make sure we don't fail with a task status transition error
        self.test_image_import_locked_by_bustable_task(task_status='failure')

    def test_image_import_locked_by_bustable_terminal_task_success(self):
        # Make sure we don't fail with a task status transition error
        self.test_image_import_locked_by_bustable_task(task_status='success')

    def test_cleanup_stale_task_progress(self):
        img_repo = mock.MagicMock()
        image = mock.MagicMock()
        task = mock.MagicMock()

        # No backend info from the old task, means no action
        task.task_input = {}
        image.extra_properties = {}
        self.controller._cleanup_stale_task_progress(img_repo, image, task)
        img_repo.save.assert_not_called()

        # If we have info but no stores, no action
        task.task_input = {'backend': []}
        self.controller._cleanup_stale_task_progress(img_repo, image, task)
        img_repo.save.assert_not_called()

        # If task had stores, but image does not have those stores in
        # the lists, no action
        task.task_input = {'backend': ['store1', 'store2']}
        self.controller._cleanup_stale_task_progress(img_repo, image, task)
        img_repo.save.assert_not_called()

        # If the image has stores in the lists, but not the ones we care
        # about, make sure they are not disturbed
        image.extra_properties = {'os_glance_failed_import': 'store3'}
        self.controller._cleanup_stale_task_progress(img_repo, image, task)
        img_repo.save.assert_not_called()

        # Only if the image has stores that relate to our old task should
        # take action, and only on those stores.
        image.extra_properties = {
            'os_glance_importing_to_stores': 'foo,store1,bar',
            'os_glance_failed_import': 'foo,store2,bar',
        }
        self.controller._cleanup_stale_task_progress(img_repo, image, task)
        img_repo.save.assert_called_once_with(image)
        self.assertEqual({'os_glance_importing_to_stores': 'foo,bar',
                          'os_glance_failed_import': 'foo,bar'},
                         image.extra_properties)

    def test_bust_import_lock_race_to_delete(self):
        image_repo = mock.MagicMock()
        task_repo = mock.MagicMock()
        image = mock.MagicMock()
        task = mock.MagicMock(id='foo')
        # Simulate a race where we tried to bust a specific lock and
        # someone else already had, and/or re-locked it
        image_repo.delete_property_atomic.side_effect = exception.NotFound
        self.assertRaises(exception.Conflict,
                          self.controller._bust_import_lock,
                          image_repo, task_repo,
                          image, task, task.id)

    def test_enforce_lock_log_not_bustable(self, task_status='processing'):
        task = test_tasks_resource._db_fixture(
            test_tasks_resource.UUID1,
            status=task_status)
        self.db.task_create(None, task)
        request = unit_test_utils.get_fake_request(tenant=TENANT1)
        image = FakeImage()
        image.extra_properties['os_glance_import_task'] = task['id']

        # Freeze time to make this repeatable
        time_fixture = fixture.TimeFixture(task['updated_at'] +
                                           datetime.timedelta(minutes=55))
        self.useFixture(time_fixture)

        expected_expire = 300
        if task_status == 'pending':
            # NOTE(danms): Tasks in 'pending' get double the expiry time,
            # so we'd be expecting an extra hour here.
            expected_expire += 3600

        with mock.patch.object(glance.api.v2.images, 'LOG') as mock_log:
            self.assertRaises(exception.Conflict,
                              self.controller._enforce_import_lock,
                              request, image)
            mock_log.warning.assert_called_once_with(
                'Image %(image)s has active import task %(task)s in '
                'status %(status)s; lock remains valid for %(expire)i '
                'more seconds',
                {'image': image.id,
                 'task': task['id'],
                 'status': task_status,
                 'expire': expected_expire})

    def test_enforce_lock_pending_takes_longer(self):
        self.test_enforce_lock_log_not_bustable(task_status='pending')

    def test_delete_encryption_key_no_encryption_key(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties={})
        self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key_no_deletion_policy(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key_do_not_delete(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
            'cinder_encryption_key_deletion_policy': 'do_not_delete',
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key_forbidden(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        with mock.patch.object(self.controller._key_manager, 'delete',
                               side_effect=castellan_exception.Forbidden):
            self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key_not_found(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        with mock.patch.object(self.controller._key_manager, 'delete',
                               side_effect=castellan_exception.ManagedObjectNotFoundError):  # noqa
            self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key_error(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        with mock.patch.object(self.controller._key_manager, 'delete',
                               side_effect=castellan_exception.KeyManagerError):  # noqa
            self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is still there
        key = self.controller._key_manager.get(request.context,
                                               fake_encryption_key)
        self.assertEqual(fake_encryption_key, key._id)

    def test_delete_encryption_key(self):
        request = unit_test_utils.get_fake_request()
        fake_encryption_key = self.controller._key_manager.store(
            request.context, mock.Mock())
        props = {
            'cinder_encryption_key_id': fake_encryption_key,
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        image = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)
        self.controller._delete_encryption_key(request.context, image)
        # Make sure the encrytion key is gone
        self.assertRaises(KeyError,
                          self.controller._key_manager.get,
                          request.context, fake_encryption_key)

    def test_delete_no_encryption_key_id(self):
        request = unit_test_utils.get_fake_request()
        extra_props = {
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        created_image = self.controller.create(request,
                                               image={'name': 'image-1'},
                                               extra_properties=extra_props,
                                               tags=[])
        image_id = created_image.image_id
        self.controller.delete(request, image_id)
        # Ensure that image is deleted
        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_delete_invalid_encryption_key_id(self):
        request = unit_test_utils.get_fake_request()
        extra_props = {
            'cinder_encryption_key_id': 'invalid',
            'cinder_encryption_key_deletion_policy': 'on_image_deletion',
        }
        created_image = self.controller.create(request,
                                               image={'name': 'image-1'},
                                               extra_properties=extra_props,
                                               tags=[])
        image_id = created_image.image_id
        self.controller.delete(request, image_id)
        # Ensure that image is deleted
        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])

    def test_delete_invalid_encryption_key_deletion_policy(self):
        request = unit_test_utils.get_fake_request()
        extra_props = {
            'cinder_encryption_key_deletion_policy': 'invalid',
        }
        created_image = self.controller.create(request,
                                               image={'name': 'image-1'},
                                               extra_properties=extra_props,
                                               tags=[])
        image_id = created_image.image_id
        self.controller.delete(request, image_id)
        # Ensure that image is deleted
        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual('deleted', image['status'])


class TestImagesControllerPolicies(base.IsolatedUnitTest):

    def setUp(self):
        super(TestImagesControllerPolicies, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                self.policy)
        store = unit_test_utils.FakeStoreAPI()
        self.store_utils = unit_test_utils.FakeStoreUtils(store)

    def test_index_unauthorized(self):
        rules = {"get_images": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.index,
                          request)

    def test_show_unauthorized(self):
        rules = {"get_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.show,
                          request, image_id=UUID2)

    def test_create_image_unauthorized(self):
        rules = {"add_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1'}
        extra_properties = {}
        tags = []
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.create,
                          request, image, extra_properties, tags)

    def test_create_public_image_unauthorized(self):
        rules = {"publicize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1', 'visibility': 'public'}
        extra_properties = {}
        tags = []
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.create,
                          request, image, extra_properties, tags)

    def test_create_community_image_unauthorized(self):
        rules = {"communitize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-c1', 'visibility': 'community'}
        extra_properties = {}
        tags = []
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.create,
                          request, image, extra_properties, tags)

    def test_update_unauthorized(self):
        rules = {"modify_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['name'], 'value': 'image-2'}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_publicize_image_unauthorized(self):
        rules = {"publicize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['visibility'],
                    'value': 'public'}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_communitize_image_unauthorized(self):
        rules = {"communitize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['visibility'],
                    'value': 'community'}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_depublicize_image_unauthorized(self):
        rules = {"publicize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['visibility'],
                    'value': 'private'}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual('private', output.visibility)

    def test_update_decommunitize_image_unauthorized(self):
        rules = {"communitize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['visibility'],
                    'value': 'private'}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual('private', output.visibility)

    def test_update_get_image_location_unauthorized(self):
        rules = {"get_image_location": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_set_image_location_unauthorized(self):
        def fake_delete_image_location_from_backend(self, *args, **kwargs):
            pass

        rules = {"set_image_location": False}
        self.policy.set_rules(rules)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_delete_image_location_unauthorized(self):
        rules = {"delete_image_location": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_delete_unauthorized(self):
        rules = {"delete_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.delete,
                          request, UUID1)


class TestImagesDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializer, self).setUp()
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create_minimal(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({})
        output = self.deserializer.create(request)
        expected = {'image': {}, 'extra_properties': {}, 'tags': []}
        self.assertEqual(expected, output)

    def test_create_invalid_id(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'id': 'gabe'})
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.create,
                          request)

    def test_create_id_to_image_id(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'id': UUID4})
        output = self.deserializer.create(request)
        expected = {'image': {'image_id': UUID4},
                    'extra_properties': {},
                    'tags': []}
        self.assertEqual(expected, output)

    def test_create_no_body(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.create,
                          request)

    def test_create_full(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'id': UUID3,
            'name': 'image-1',
            'visibility': 'public',
            'tags': ['one', 'two'],
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'foo': 'bar',
            'protected': True,
        })
        output = self.deserializer.create(request)
        properties = {
            'image_id': UUID3,
            'name': 'image-1',
            'visibility': 'public',
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'protected': True,
        }
        self.maxDiff = None
        expected = {'image': properties,
                    'extra_properties': {'foo': 'bar'},
                    'tags': ['one', 'two']}
        self.assertEqual(expected, output)

    def test_create_invalid_property_key(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'id': UUID3,
            'name': 'image-1',
            'visibility': 'public',
            'tags': ['one', 'two'],
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'f' * 256: 'bar',
            'protected': True,
        })
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.create,
                          request)

    def test_create_readonly_attributes_forbidden(self):
        bodies = [
            {'direct_url': 'http://example.com'},
            {'self': 'http://example.com'},
            {'file': 'http://example.com'},
            {'schema': 'http://example.com'},
        ]

        for body in bodies:
            request = unit_test_utils.get_fake_request()
            request.body = jsonutils.dump_as_bytes(body)
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.deserializer.create, request)

    def _get_fake_patch_request(self, content_type_minor_version=1):
        request = unit_test_utils.get_fake_request()
        template = 'application/openstack-images-v2.%d-json-patch'
        request.content_type = template % content_type_minor_version
        return request

    def test_update_empty_body(self):
        request = self._get_fake_patch_request()
        request.body = jsonutils.dump_as_bytes([])
        output = self.deserializer.update(request)
        expected = {'changes': []}
        self.assertEqual(expected, output)

    def test_update_unsupported_content_type(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/json-patch'
        request.body = jsonutils.dump_as_bytes([])
        try:
            self.deserializer.update(request)
        except webob.exc.HTTPUnsupportedMediaType as e:
            # desired result, but must have correct Accept-Patch header
            accept_patch = ['application/openstack-images-v2.1-json-patch',
                            'application/openstack-images-v2.0-json-patch']
            expected = ', '.join(sorted(accept_patch))
            self.assertEqual(expected, e.headers['Accept-Patch'])
        else:
            self.fail('Did not raise HTTPUnsupportedMediaType')

    def test_update_body_not_a_list(self):
        bodies = [
            {'op': 'add', 'path': '/someprop', 'value': 'somevalue'},
            'just some string',
            123,
            True,
            False,
            None,
        ]
        for body in bodies:
            request = self._get_fake_patch_request()
            request.body = jsonutils.dump_as_bytes(body)
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.deserializer.update, request)

    def test_update_invalid_changes(self):
        changes = [
            ['a', 'list', 'of', 'stuff'],
            'just some string',
            123,
            True,
            False,
            None,
            {'op': 'invalid', 'path': '/name', 'value': 'fedora'}
        ]
        for change in changes:
            request = self._get_fake_patch_request()
            request.body = jsonutils.dump_as_bytes([change])
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.deserializer.update, request)

    def test_update_invalid_validation_data(self):
        request = self._get_fake_patch_request()
        changes = [{
            'op': 'add',
            'path': '/locations/0',
            'value': {
                'url': 'http://localhost/fake',
                'metadata': {},
            }
        }]

        changes[0]['value']['validation_data'] = {
            'os_hash_algo': 'sha512',
            'os_hash_value': MULTIHASH1,
            'checksum': CHKSUM,
        }
        request.body = jsonutils.dump_as_bytes(changes)
        self.deserializer.update(request)

        changes[0]['value']['validation_data'] = {
            'os_hash_algo': 'sha512',
            'os_hash_value': MULTIHASH1,
            'checksum': CHKSUM,
            'bogus_key': 'bogus_value',
        }
        request.body = jsonutils.dump_as_bytes(changes)
        six.assertRaisesRegex(self,
                              webob.exc.HTTPBadRequest,
                              'Additional properties are not allowed',
                              self.deserializer.update, request)

        changes[0]['value']['validation_data'] = {
            'checksum': CHKSUM,
        }
        request.body = jsonutils.dump_as_bytes(changes)
        six.assertRaisesRegex(self,
                              webob.exc.HTTPBadRequest,
                              'os_hash.* is a required property',
                              self.deserializer.update, request)

    def test_update(self):
        request = self._get_fake_patch_request()
        body = [
            {'op': 'replace', 'path': '/name', 'value': 'fedora'},
            {'op': 'replace', 'path': '/tags', 'value': ['king', 'kong']},
            {'op': 'replace', 'path': '/foo', 'value': 'bar'},
            {'op': 'add', 'path': '/bebim', 'value': 'bap'},
            {'op': 'remove', 'path': '/sparks'},
            {'op': 'add', 'path': '/locations/-',
             'value': {'url': 'scheme3://path3', 'metadata': {}}},
            {'op': 'add', 'path': '/locations/10',
             'value': {'url': 'scheme4://path4', 'metadata': {}}},
            {'op': 'remove', 'path': '/locations/2'},
            {'op': 'replace', 'path': '/locations', 'value': []},
            {'op': 'replace', 'path': '/locations',
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]
        request.body = jsonutils.dump_as_bytes(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['name'], 'value': 'fedora'},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['tags'], 'value': ['king', 'kong']},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['foo'], 'value': 'bar'},
            {'json_schema_version': 10, 'op': 'add',
             'path': ['bebim'], 'value': 'bap'},
            {'json_schema_version': 10, 'op': 'remove',
             'path': ['sparks']},
            {'json_schema_version': 10, 'op': 'add',
             'path': ['locations', '-'],
             'value': {'url': 'scheme3://path3', 'metadata': {}}},
            {'json_schema_version': 10, 'op': 'add',
             'path': ['locations', '10'],
             'value': {'url': 'scheme4://path4', 'metadata': {}}},
            {'json_schema_version': 10, 'op': 'remove',
             'path': ['locations', '2']},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['locations'], 'value': []},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]}
        self.assertEqual(expected, output)

    def test_update_v2_0_compatibility(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [
            {'replace': '/name', 'value': 'fedora'},
            {'replace': '/tags', 'value': ['king', 'kong']},
            {'replace': '/foo', 'value': 'bar'},
            {'add': '/bebim', 'value': 'bap'},
            {'remove': '/sparks'},
            {'add': '/locations/-', 'value': {'url': 'scheme3://path3',
                                              'metadata': {}}},
            {'add': '/locations/10', 'value': {'url': 'scheme4://path4',
                                               'metadata': {}}},
            {'remove': '/locations/2'},
            {'replace': '/locations', 'value': []},
            {'replace': '/locations',
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]
        request.body = jsonutils.dump_as_bytes(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'json_schema_version': 4, 'op': 'replace',
             'path': ['name'], 'value': 'fedora'},
            {'json_schema_version': 4, 'op': 'replace',
             'path': ['tags'], 'value': ['king', 'kong']},
            {'json_schema_version': 4, 'op': 'replace',
             'path': ['foo'], 'value': 'bar'},
            {'json_schema_version': 4, 'op': 'add',
             'path': ['bebim'], 'value': 'bap'},
            {'json_schema_version': 4, 'op': 'remove', 'path': ['sparks']},
            {'json_schema_version': 4, 'op': 'add',
             'path': ['locations', '-'],
             'value': {'url': 'scheme3://path3', 'metadata': {}}},
            {'json_schema_version': 4, 'op': 'add',
             'path': ['locations', '10'],
             'value': {'url': 'scheme4://path4', 'metadata': {}}},
            {'json_schema_version': 4, 'op': 'remove',
             'path': ['locations', '2']},
            {'json_schema_version': 4, 'op': 'replace',
             'path': ['locations'], 'value': []},
            {'json_schema_version': 4, 'op': 'replace', 'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]}
        self.assertEqual(expected, output)

    def test_update_base_attributes(self):
        request = self._get_fake_patch_request()
        body = [
            {'op': 'replace', 'path': '/name', 'value': 'fedora'},
            {'op': 'replace', 'path': '/visibility', 'value': 'public'},
            {'op': 'replace', 'path': '/tags', 'value': ['king', 'kong']},
            {'op': 'replace', 'path': '/protected', 'value': True},
            {'op': 'replace', 'path': '/container_format', 'value': 'bare'},
            {'op': 'replace', 'path': '/disk_format', 'value': 'raw'},
            {'op': 'replace', 'path': '/min_ram', 'value': 128},
            {'op': 'replace', 'path': '/min_disk', 'value': 10},
            {'op': 'replace', 'path': '/locations', 'value': []},
            {'op': 'replace', 'path': '/locations',
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]}
        ]
        request.body = jsonutils.dump_as_bytes(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['name'], 'value': 'fedora'},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['visibility'], 'value': 'public'},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['tags'], 'value': ['king', 'kong']},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['protected'], 'value': True},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['container_format'], 'value': 'bare'},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['disk_format'], 'value': 'raw'},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['min_ram'], 'value': 128},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['min_disk'], 'value': 10},
            {'json_schema_version': 10, 'op': 'replace',
             'path': ['locations'], 'value': []},
            {'json_schema_version': 10, 'op': 'replace', 'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]}
        ]}
        self.assertEqual(expected, output)

    def test_update_disallowed_attributes(self):
        samples = {
            'direct_url': '/a/b/c/d',
            'self': '/e/f/g/h',
            'file': '/e/f/g/h/file',
            'schema': '/i/j/k',
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dump_as_bytes(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPForbidden:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPForbidden" % key)

    def test_update_readonly_attributes(self):
        samples = {
            'id': '00000000-0000-0000-0000-000000000000',
            'status': 'active',
            'checksum': 'abcdefghijklmnopqrstuvwxyz012345',
            'os_hash_algo': 'supersecure',
            'os_hash_value': 'a' * 32 + 'b' * 32 + 'c' * 32 + 'd' * 32,
            'size': 9001,
            'virtual_size': 9001,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dump_as_bytes(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPForbidden:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPForbidden" % key)

    def test_update_reserved_attributes(self):
        samples = {
            'deleted': False,
            'deleted_at': ISOTIME,
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dump_as_bytes(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPForbidden:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPForbidden" % key)

    def test_update_invalid_attributes(self):
        keys = [
            'noslash',
            '///twoslash',
            '/two/   /slash',
            '/      /      ',
            '/trailingslash/',
            '/lone~tilde',
            '/trailingtilde~'
        ]

        for key in keys:
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '%s' % key, 'value': 'dummy'}]
            request.body = jsonutils.dump_as_bytes(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPBadRequest:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPBadRequest" % key)

    def test_update_pointer_encoding(self):
        samples = {
            '/keywith~1slash': [u'keywith/slash'],
            '/keywith~0tilde': [u'keywith~tilde'],
            '/tricky~01': [u'tricky~1'],
        }

        for encoded, decoded in samples.items():
            request = self._get_fake_patch_request()
            doc = [{'op': 'replace', 'path': '%s' % encoded, 'value': 'dummy'}]
            request.body = jsonutils.dump_as_bytes(doc)
            output = self.deserializer.update(request)
            self.assertEqual(decoded, output['changes'][0]['path'])

    def test_update_deep_limited_attributes(self):
        samples = {
            'locations/1/2': [],
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dump_as_bytes(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPBadRequest:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPBadRequest" % key)

    def test_update_v2_1_missing_operations(self):
        request = self._get_fake_patch_request()
        body = [{'path': '/colburn', 'value': 'arcata'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_1_missing_value(self):
        request = self._get_fake_patch_request()
        body = [{'op': 'replace', 'path': '/colburn'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_1_missing_path(self):
        request = self._get_fake_patch_request()
        body = [{'op': 'replace', 'value': 'arcata'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_multiple_operations(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'replace': '/foo', 'add': '/bar', 'value': 'snore'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_missing_operations(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'value': 'arcata'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_missing_value(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'replace': '/colburn'}]
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_index(self):
        marker = str(uuid.uuid4())
        path = '/images?limit=1&marker=%s&member_status=pending' % marker
        request = unit_test_utils.get_fake_request(path)
        expected = {'limit': 1,
                    'marker': marker,
                    'sort_key': ['created_at'],
                    'sort_dir': ['desc'],
                    'member_status': 'pending',
                    'filters': {}}
        output = self.deserializer.index(request)
        self.assertEqual(expected, output)

    def test_index_with_filter(self):
        name = 'My Little Image'
        path = '/images?name=%s' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(name, output['filters']['name'])

    def test_index_strip_params_from_filters(self):
        name = 'My Little Image'
        path = '/images?name=%s' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(name, output['filters']['name'])
        self.assertEqual(1, len(output['filters']))

    def test_index_with_many_filter(self):
        name = 'My Little Image'
        instance_id = str(uuid.uuid4())
        path = ('/images?name=%(name)s&id=%(instance_id)s' %
                {'name': name, 'instance_id': instance_id})
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(name, output['filters']['name'])
        self.assertEqual(instance_id, output['filters']['id'])

    def test_index_with_filter_and_limit(self):
        name = 'My Little Image'
        path = '/images?name=%s&limit=1' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(name, output['filters']['name'])
        self.assertEqual(1, output['limit'])

    def test_index_non_integer_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_zero_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=0')
        expected = {'limit': 0,
                    'sort_key': ['created_at'],
                    'member_status': 'accepted',
                    'sort_dir': ['desc'],
                    'filters': {}}
        output = self.deserializer.index(request)
        self.assertEqual(expected, output)

    def test_index_negative_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=-1')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_fraction(self):
        request = unit_test_utils.get_fake_request('/images?limit=1.1')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_invalid_status(self):
        path = '/images?member_status=blah'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_marker(self):
        marker = str(uuid.uuid4())
        path = '/images?marker=%s' % marker
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(marker, output.get('marker'))

    def test_index_marker_not_specified(self):
        request = unit_test_utils.get_fake_request('/images')
        output = self.deserializer.index(request)
        self.assertNotIn('marker', output)

    def test_index_limit_not_specified(self):
        request = unit_test_utils.get_fake_request('/images')
        output = self.deserializer.index(request)
        self.assertNotIn('limit', output)

    def test_index_sort_key_id(self):
        request = unit_test_utils.get_fake_request('/images?sort_key=id')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['id'],
            'sort_dir': ['desc'],
            'member_status': 'accepted',
            'filters': {}
        }
        self.assertEqual(expected, output)

    def test_index_multiple_sort_keys(self):
        request = unit_test_utils.get_fake_request('/images?'
                                                   'sort_key=name&'
                                                   'sort_key=size')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['desc'],
            'member_status': 'accepted',
            'filters': {}
        }
        self.assertEqual(expected, output)

    def test_index_invalid_multiple_sort_keys(self):
        # blah is an invalid sort key
        request = unit_test_utils.get_fake_request('/images?'
                                                   'sort_key=name&'
                                                   'sort_key=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_dir_asc(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=asc')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['created_at'],
            'sort_dir': ['asc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_multiple_sort_dirs(self):
        req_string = ('/images?sort_key=name&sort_dir=asc&'
                      'sort_key=id&sort_dir=desc')
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'id'],
            'sort_dir': ['asc', 'desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_single_key_default_dir(self):
        req_string = '/images?sort=name'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name'],
            'sort_dir': ['desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_single_key_desc_dir(self):
        req_string = '/images?sort=name:desc'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name'],
            'sort_dir': ['desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_multiple_keys_default_dir(self):
        req_string = '/images?sort=name,size'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['desc', 'desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_multiple_keys_asc_dir(self):
        req_string = '/images?sort=name:asc,size:asc'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['asc', 'asc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_multiple_keys_different_dirs(self):
        req_string = '/images?sort=name:desc,size:asc'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['desc', 'asc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_new_sorting_syntax_multiple_keys_optional_dir(self):
        req_string = '/images?sort=name:asc,size'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['asc', 'desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

        req_string = '/images?sort=name,size:asc'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'size'],
            'sort_dir': ['desc', 'asc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

        req_string = '/images?sort=name,id:asc,size'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'id', 'size'],
            'sort_dir': ['desc', 'asc', 'desc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

        req_string = '/images?sort=name:asc,id,size:asc'
        request = unit_test_utils.get_fake_request(req_string)
        output = self.deserializer.index(request)
        expected = {
            'sort_key': ['name', 'id', 'size'],
            'sort_dir': ['asc', 'desc', 'asc'],
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_sort_wrong_sort_dirs_number(self):
        req_string = '/images?sort_key=name&sort_dir=asc&sort_dir=desc'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_dirs_fewer_than_keys(self):
        req_string = ('/images?sort_key=name&sort_dir=asc&sort_key=id&'
                      'sort_dir=asc&sort_key=created_at')
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_wrong_sort_dirs_number_without_key(self):
        req_string = '/images?sort_dir=asc&sort_dir=desc'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_private_key(self):
        request = unit_test_utils.get_fake_request('/images?sort_key=min_ram')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_key_invalid_value(self):
        # blah is an invalid sort key
        request = unit_test_utils.get_fake_request('/images?sort_key=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_sort_dir_invalid_value(self):
        # foo is an invalid sort dir
        request = unit_test_utils.get_fake_request('/images?sort_dir=foo')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_new_sorting_syntax_invalid_request(self):
        # 'blah' is not a supported sorting key
        req_string = '/images?sort=blah'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

        req_string = '/images?sort=name,blah'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

        # 'foo' isn't a valid sort direction
        req_string = '/images?sort=name:foo'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)
        # 'asc:desc' isn't a valid sort direction
        req_string = '/images?sort=name:asc:desc'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_combined_sorting_syntax(self):
        req_string = '/images?sort_dir=name&sort=name'
        request = unit_test_utils.get_fake_request(req_string)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_with_tag(self):
        path = '/images?tag=%s&tag=%s' % ('x86', '64bit')
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(sorted(['x86', '64bit']),
                         sorted(output['filters']['tags']))

    def test_image_import(self):
        # Bug 1754634: make sure that what's considered valid
        # is determined by the config option
        self.config(enabled_import_methods=['party-time'])
        request = unit_test_utils.get_fake_request()
        import_body = {
            "method": {
                "name": "party-time"
            }
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        output = self.deserializer.import_image(request)
        expected = {"body": import_body}
        self.assertEqual(expected, output)

    def test_import_image_invalid_body(self):
        request = unit_test_utils.get_fake_request()
        import_body = {
            "method1": {
                "name": "glance-direct"
            }
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.import_image,
                          request)

    def test_import_image_invalid_input(self):
        request = unit_test_utils.get_fake_request()
        import_body = {
            "method": {
                "abcd": "glance-direct"
            }
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.import_image,
                          request)

    def test_import_image_with_all_stores_not_boolean(self):
        request = unit_test_utils.get_fake_request()
        import_body = {
            'method': {
                'name': 'glance-direct'
            },
            'all_stores': "true"
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.import_image,
                          request)

    def test_import_image_with_allow_failure_not_boolean(self):
        request = unit_test_utils.get_fake_request()
        import_body = {
            'method': {
                'name': 'glance-direct'
            },
            'all_stores_must_succeed': "true"
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.import_image,
                          request)

    def _get_request_for_method(self, method_name):
        request = unit_test_utils.get_fake_request()
        import_body = {
            "method": {
                "name": method_name
            }
        }
        request.body = jsonutils.dump_as_bytes(import_body)
        return request

    KNOWN_IMPORT_METHODS = ['glance-direct', 'web-download']

    def test_import_image_invalid_import_method(self):
        # Bug 1754634: make sure that what's considered valid
        # is determined by the config option.  So put known bad
        # name in config, and known good name in request
        self.config(enabled_import_methods=['bad-method-name'])
        for m in self.KNOWN_IMPORT_METHODS:
            request = self._get_request_for_method(m)
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.deserializer.import_image,
                              request)


class TestImagesDeserializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithExtendedSchema, self).setUp()
        self.config(allow_additional_image_properties=False)
        custom_image_properties = {
            'pants': {
                'type': 'string',
                'enum': ['on', 'off'],
            },
        }
        schema = glance.api.v2.images.get_schema(custom_image_properties)
        self.deserializer = glance.api.v2.images.RequestDeserializer(schema)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'name': 'image-1',
            'pants': 'on'
        })
        output = self.deserializer.create(request)
        expected = {
            'image': {'name': 'image-1'},
            'extra_properties': {'pants': 'on'},
            'tags': [],
        }
        self.assertEqual(expected, output)

    def test_create_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'name': 'image-1',
            'pants': 'borked'
        })
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/pants', 'value': 'off'}]
        request.body = jsonutils.dump_as_bytes(doc)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'json_schema_version': 10, 'op': 'add',
             'path': ['pants'], 'value': 'off'},
        ]}
        self.assertEqual(expected, output)

    def test_update_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/pants', 'value': 'cutoffs'}]
        request.body = jsonutils.dump_as_bytes(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update,
                          request)


class TestImagesDeserializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'foo': 'bar'})
        output = self.deserializer.create(request)
        expected = {'image': {},
                    'extra_properties': {'foo': 'bar'},
                    'tags': []}
        self.assertEqual(expected, output)

    def test_create_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'abc': 123})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 123}]
        request.body = jsonutils.dump_as_bytes(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_create_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'foo': ['bar']})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': ['bar', 'baz']}]
        request.body = jsonutils.dump_as_bytes(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 'bar'}]
        request.body = jsonutils.dump_as_bytes(doc)
        output = self.deserializer.update(request)
        change = {
            'json_schema_version': 10, 'op': 'add',
            'path': ['foo'], 'value': 'bar'
        }
        self.assertEqual({'changes': [change]}, output)


class TestImagesDeserializerNoAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerNoAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=False)
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create_with_additional_properties_disallowed(self):
        self.config(allow_additional_image_properties=False)
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'foo': 'bar'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_neg_create_with_stores(self):
        self.config(allow_additional_image_properties=True)
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({'stores': 'test'})
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 'bar'}]
        request.body = jsonutils.dump_as_bytes(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)


class TestImagesSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializer, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()
        self.fixtures = [
            # NOTE(bcwaldon): This first fixture has every property defined
            _domain_fixture(UUID1, name='image-1', size=1024,
                            virtual_size=3072, created_at=DATETIME,
                            updated_at=DATETIME, owner=TENANT1,
                            visibility='public', container_format='ami',
                            tags=['one', 'two'], disk_format='ami',
                            min_ram=128, min_disk=10,
                            checksum='ca425b88f047ce8ec45ee90e813ada91',
                            os_hash_algo=FAKEHASHALGO,
                            os_hash_value=MULTIHASH1),

            # NOTE(bcwaldon): This second fixture depends on default behavior
            # and sets most values to None
            _domain_fixture(UUID2, created_at=DATETIME, updated_at=DATETIME),
        ]

    def test_index(self):
        expected = {
            'images': [
                {
                    'id': UUID1,
                    'name': 'image-1',
                    'status': 'queued',
                    'visibility': 'public',
                    'protected': False,
                    'os_hidden': False,
                    'tags': set(['one', 'two']),
                    'size': 1024,
                    'virtual_size': 3072,
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                    'os_hash_algo': FAKEHASHALGO,
                    'os_hash_value': MULTIHASH1,
                    'container_format': 'ami',
                    'disk_format': 'ami',
                    'min_ram': 128,
                    'min_disk': 10,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/images/%s' % UUID1,
                    'file': '/v2/images/%s/file' % UUID1,
                    'schema': '/v2/schemas/image',
                    'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                },
                {
                    'id': UUID2,
                    'status': 'queued',
                    'visibility': 'private',
                    'protected': False,
                    'os_hidden': False,
                    'tags': set([]),
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/images/%s' % UUID2,
                    'file': '/v2/images/%s/file' % UUID2,
                    'schema': '/v2/schemas/image',
                    'size': None,
                    'name': None,
                    'owner': None,
                    'min_ram': None,
                    'min_disk': None,
                    'checksum': None,
                    'os_hash_algo': None,
                    'os_hash_value': None,
                    'disk_format': None,
                    'virtual_size': None,
                    'container_format': None,

                },
            ],
            'first': '/v2/images',
            'schema': '/v2/schemas/images',
        }
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        result = {'images': self.fixtures}
        self.serializer.index(response, result)
        actual = jsonutils.loads(response.body)
        for image in actual['images']:
            image['tags'] = set(image['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_index_next_marker(self):
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        result = {'images': self.fixtures, 'next_marker': UUID2}
        self.serializer.index(response, result)
        output = jsonutils.loads(response.body)
        self.assertEqual('/v2/images?marker=%s' % UUID2, output['next'])

    def test_index_carries_query_parameters(self):
        url = '/v2/images?limit=10&sort_key=id&sort_dir=asc'
        request = webob.Request.blank(url)
        response = webob.Response(request=request)
        result = {'images': self.fixtures, 'next_marker': UUID2}
        self.serializer.index(response, result)
        output = jsonutils.loads(response.body)

        expected_url = '/v2/images?limit=10&sort_dir=asc&sort_key=id'
        self.assertEqual(unit_test_utils.sort_url_by_qs_keys(expected_url),
                         unit_test_utils.sort_url_by_qs_keys(output['first']))
        expect_next = '/v2/images?limit=10&marker=%s&sort_dir=asc&sort_key=id'
        self.assertEqual(unit_test_utils.sort_url_by_qs_keys(
                         expect_next % UUID2),
                         unit_test_utils.sort_url_by_qs_keys(output['next']))

    def test_index_forbidden_get_image_location(self):
        """Make sure the serializer works fine.

        No mater if current user is authorized to get image location if the
        show_multiple_locations is False.

        """
        class ImageLocations(object):

            def __len__(self):
                raise exception.Forbidden()

        self.config(show_multiple_locations=False)
        self.config(show_image_direct_url=False)
        url = '/v2/images?limit=10&sort_key=id&sort_dir=asc'
        request = webob.Request.blank(url)
        response = webob.Response(request=request)
        result = {'images': self.fixtures}
        self.assertEqual(http.OK, response.status_int)

        # The image index should work though the user is forbidden
        result['images'][0].locations = ImageLocations()
        self.serializer.index(response, result)
        self.assertEqual(http.OK, response.status_int)

    def test_show_full_fixture(self):
        expected = {
            'id': UUID1,
            'name': 'image-1',
            'status': 'queued',
            'visibility': 'public',
            'protected': False,
            'os_hidden': False,
            'tags': set(['one', 'two']),
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID1,
            'file': '/v2/images/%s/file' % UUID1,
            'schema': '/v2/schemas/image',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.show(response, self.fixtures[0])
        actual = jsonutils.loads(response.body)
        actual['tags'] = set(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_show_minimal_fixture(self):
        expected = {
            'id': UUID2,
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'tags': [],
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'size': None,
            'name': None,
            'owner': None,
            'min_ram': None,
            'min_disk': None,
            'checksum': None,
            'os_hash_algo': None,
            'os_hash_value': None,
            'disk_format': None,
            'virtual_size': None,
            'container_format': None,
        }
        response = webob.Response()
        self.serializer.show(response, self.fixtures[1])
        self.assertEqual(expected, jsonutils.loads(response.body))

    def test_create(self):
        expected = {
            'id': UUID1,
            'name': 'image-1',
            'status': 'queued',
            'visibility': 'public',
            'protected': False,
            'os_hidden': False,
            'tags': ['one', 'two'],
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID1,
            'file': '/v2/images/%s/file' % UUID1,
            'schema': '/v2/schemas/image',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(http.CREATED, response.status_int)
        actual = jsonutils.loads(response.body)
        actual['tags'] = sorted(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual('/v2/images/%s' % UUID1, response.location)

    def test_create_has_import_methods_header(self):
        # NOTE(rosmaita): enabled_import_methods is defined as type
        # oslo.config.cfg.ListOpt, so it is stored internally as a list
        # but is converted to a string for output in the HTTP header

        header_name = 'OpenStack-image-import-methods'

        # check multiple methods
        enabled_methods = ['one', 'two', 'three']
        self.config(enabled_import_methods=enabled_methods)
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(http.CREATED, response.status_int)
        header_value = response.headers.get(header_name)
        self.assertIsNotNone(header_value)
        self.assertCountEqual(enabled_methods, header_value.split(','))

        # check single method
        self.config(enabled_import_methods=['swift-party-time'])
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(http.CREATED, response.status_int)
        header_value = response.headers.get(header_name)
        self.assertIsNotNone(header_value)
        self.assertEqual('swift-party-time', header_value)

        # no header for empty config value
        self.config(enabled_import_methods=[])
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(http.CREATED, response.status_int)
        headers = response.headers.keys()
        self.assertNotIn(header_name, headers)

    def test_update(self):
        expected = {
            'id': UUID1,
            'name': 'image-1',
            'status': 'queued',
            'visibility': 'public',
            'protected': False,
            'os_hidden': False,
            'tags': set(['one', 'two']),
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'container_format': 'ami',
            'disk_format': 'ami',
            'min_ram': 128,
            'min_disk': 10,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID1,
            'file': '/v2/images/%s/file' % UUID1,
            'schema': '/v2/schemas/image',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.update(response, self.fixtures[0])
        actual = jsonutils.loads(response.body)
        actual['tags'] = set(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_import_image(self):
        response = webob.Response()
        self.serializer.import_image(response, {})
        self.assertEqual(http.ACCEPTED, response.status_int)
        self.assertEqual('0', response.headers['Content-Length'])


class TestImagesSerializerWithUnicode(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithUnicode, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()
        self.fixtures = [
            # NOTE(bcwaldon): This first fixture has every property defined
            _domain_fixture(UUID1, **{
                'name': u'OpenStack\u2122-1',
                'size': 1024,
                'virtual_size': 3072,
                'tags': [u'\u2160', u'\u2161'],
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'owner': TENANT1,
                'visibility': 'public',
                'container_format': 'ami',
                'disk_format': 'ami',
                'min_ram': 128,
                'min_disk': 10,
                'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
                'os_hash_algo': FAKEHASHALGO,
                'os_hash_value': MULTIHASH1,
                'extra_properties': {'lang': u'Fran\u00E7ais',
                                     u'dispos\u00E9': u'f\u00E2ch\u00E9'},
            }),
        ]

    def test_index(self):
        expected = {
            u'images': [
                {
                    u'id': UUID1,
                    u'name': u'OpenStack\u2122-1',
                    u'status': u'queued',
                    u'visibility': u'public',
                    u'protected': False,
                    u'os_hidden': False,
                    u'tags': [u'\u2160', u'\u2161'],
                    u'size': 1024,
                    u'virtual_size': 3072,
                    u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
                    u'os_hash_algo': six.text_type(FAKEHASHALGO),
                    u'os_hash_value': six.text_type(MULTIHASH1),
                    u'container_format': u'ami',
                    u'disk_format': u'ami',
                    u'min_ram': 128,
                    u'min_disk': 10,
                    u'created_at': six.text_type(ISOTIME),
                    u'updated_at': six.text_type(ISOTIME),
                    u'self': u'/v2/images/%s' % UUID1,
                    u'file': u'/v2/images/%s/file' % UUID1,
                    u'schema': u'/v2/schemas/image',
                    u'lang': u'Fran\u00E7ais',
                    u'dispos\u00E9': u'f\u00E2ch\u00E9',
                    u'owner': u'6838eb7b-6ded-434a-882c-b344c77fe8df',
                },
            ],
            u'first': u'/v2/images',
            u'schema': u'/v2/schemas/images',
        }
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        result = {u'images': self.fixtures}
        self.serializer.index(response, result)
        actual = jsonutils.loads(response.body)
        actual['images'][0]['tags'] = sorted(actual['images'][0]['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_show_full_fixture(self):
        expected = {
            u'id': UUID1,
            u'name': u'OpenStack\u2122-1',
            u'status': u'queued',
            u'visibility': u'public',
            u'protected': False,
            u'os_hidden': False,
            u'tags': set([u'\u2160', u'\u2161']),
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'os_hash_algo': six.text_type(FAKEHASHALGO),
            u'os_hash_value': six.text_type(MULTIHASH1),
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': six.text_type(ISOTIME),
            u'updated_at': six.text_type(ISOTIME),
            u'self': u'/v2/images/%s' % UUID1,
            u'file': u'/v2/images/%s/file' % UUID1,
            u'schema': u'/v2/schemas/image',
            u'lang': u'Fran\u00E7ais',
            u'dispos\u00E9': u'f\u00E2ch\u00E9',
            u'owner': u'6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.show(response, self.fixtures[0])
        actual = jsonutils.loads(response.body)
        actual['tags'] = set(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_create(self):
        expected = {
            u'id': UUID1,
            u'name': u'OpenStack\u2122-1',
            u'status': u'queued',
            u'visibility': u'public',
            u'protected': False,
            u'os_hidden': False,
            u'tags': [u'\u2160', u'\u2161'],
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'os_hash_algo': six.text_type(FAKEHASHALGO),
            u'os_hash_value': six.text_type(MULTIHASH1),
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': six.text_type(ISOTIME),
            u'updated_at': six.text_type(ISOTIME),
            u'self': u'/v2/images/%s' % UUID1,
            u'file': u'/v2/images/%s/file' % UUID1,
            u'schema': u'/v2/schemas/image',
            u'lang': u'Fran\u00E7ais',
            u'dispos\u00E9': u'f\u00E2ch\u00E9',
            u'owner': u'6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(http.CREATED, response.status_int)
        actual = jsonutils.loads(response.body)
        actual['tags'] = sorted(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual('/v2/images/%s' % UUID1, response.location)

    def test_update(self):
        expected = {
            u'id': UUID1,
            u'name': u'OpenStack\u2122-1',
            u'status': u'queued',
            u'visibility': u'public',
            u'protected': False,
            u'os_hidden': False,
            u'tags': set([u'\u2160', u'\u2161']),
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'os_hash_algo': six.text_type(FAKEHASHALGO),
            u'os_hash_value': six.text_type(MULTIHASH1),
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': six.text_type(ISOTIME),
            u'updated_at': six.text_type(ISOTIME),
            u'self': u'/v2/images/%s' % UUID1,
            u'file': u'/v2/images/%s/file' % UUID1,
            u'schema': u'/v2/schemas/image',
            u'lang': u'Fran\u00E7ais',
            u'dispos\u00E9': u'f\u00E2ch\u00E9',
            u'owner': u'6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.update(response, self.fixtures[0])
        actual = jsonutils.loads(response.body)
        actual['tags'] = set(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)


class TestImagesSerializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithExtendedSchema, self).setUp()
        self.config(allow_additional_image_properties=False)
        custom_image_properties = {
            'color': {
                'type': 'string',
                'enum': ['red', 'green'],
            },
        }
        schema = glance.api.v2.images.get_schema(custom_image_properties)
        self.serializer = glance.api.v2.images.ResponseSerializer(schema)

        props = dict(color='green', mood='grouchy')
        self.fixture = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)

    def test_show(self):
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'color': 'green',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'min_ram': None,
            'min_disk': None,
            'disk_format': None,
            'container_format': None,
        }
        response = webob.Response()
        self.serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))

    def test_show_reports_invalid_data(self):
        self.fixture.extra_properties['color'] = 'invalid'
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'color': 'invalid',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'min_ram': None,
            'min_disk': None,
            'disk_format': None,
            'container_format': None,
        }
        response = webob.Response()
        self.serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))


class TestImagesSerializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        self.fixture = _domain_fixture(
            UUID2, name='image-2', owner=TENANT2,
            checksum='ca425b88f047ce8ec45ee90e813ada91',
            os_hash_algo=FAKEHASHALGO, os_hash_value=MULTIHASH1,
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties={'marx': 'groucho'})

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer()
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'marx': 'groucho',
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'min_ram': None,
            'min_disk': None,
            'disk_format': None,
            'container_format': None,
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))

    def test_show_invalid_additional_property(self):
        """Ensure that the serializer passes
        through invalid additional properties.

        It must not complains with i.e. non-string.
        """
        serializer = glance.api.v2.images.ResponseSerializer()
        self.fixture.extra_properties['marx'] = 123
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'marx': 123,
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'min_ram': None,
            'min_disk': None,
            'disk_format': None,
            'container_format': None,
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))

    def test_show_with_additional_properties_disabled(self):
        self.config(allow_additional_image_properties=False)
        serializer = glance.api.v2.images.ResponseSerializer()
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'os_hidden': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'os_hash_algo': FAKEHASHALGO,
            'os_hash_value': MULTIHASH1,
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
            'min_ram': None,
            'min_disk': None,
            'disk_format': None,
            'container_format': None,
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))


class TestImagesSerializerDirectUrl(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerDirectUrl, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()

        self.active_image = _domain_fixture(
            UUID1, name='image-1', visibility='public',
            status='active', size=1024, virtual_size=3072,
            created_at=DATETIME, updated_at=DATETIME,
            locations=[{'id': '1', 'url': 'http://some/fake/location',
                        'metadata': {}, 'status': 'active'}])

        self.queued_image = _domain_fixture(
            UUID2, name='image-2', status='active',
            created_at=DATETIME, updated_at=DATETIME,
            checksum='ca425b88f047ce8ec45ee90e813ada91')

        self.location_data_image_url = 'http://abc.com/somewhere'
        self.location_data_image_meta = {'key': 98231}
        self.location_data_image = _domain_fixture(
            UUID2, name='image-2', status='active',
            created_at=DATETIME, updated_at=DATETIME,
            locations=[{'id': '2',
                        'url': self.location_data_image_url,
                        'metadata': self.location_data_image_meta,
                        'status': 'active'}])

    def _do_index(self):
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        self.serializer.index(response,
                              {'images': [self.active_image,
                                          self.queued_image]})
        return jsonutils.loads(response.body)['images']

    def _do_show(self, image):
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        self.serializer.show(response, image)
        return jsonutils.loads(response.body)

    def test_index_store_location_enabled(self):
        self.config(show_image_direct_url=True)
        images = self._do_index()

        # NOTE(markwash): ordering sanity check
        self.assertEqual(UUID1, images[0]['id'])
        self.assertEqual(UUID2, images[1]['id'])

        self.assertEqual('http://some/fake/location', images[0]['direct_url'])
        self.assertNotIn('direct_url', images[1])

    def test_index_store_multiple_location_enabled(self):
        self.config(show_multiple_locations=True)
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        self.serializer.index(response,
                              {'images': [self.location_data_image]}),
        images = jsonutils.loads(response.body)['images']
        location = images[0]['locations'][0]
        self.assertEqual(location['url'], self.location_data_image_url)
        self.assertEqual(location['metadata'], self.location_data_image_meta)

    def test_index_store_location_explicitly_disabled(self):
        self.config(show_image_direct_url=False)
        images = self._do_index()
        self.assertNotIn('direct_url', images[0])
        self.assertNotIn('direct_url', images[1])

    def test_show_location_enabled(self):
        self.config(show_image_direct_url=True)
        image = self._do_show(self.active_image)
        self.assertEqual('http://some/fake/location', image['direct_url'])

    def test_show_location_enabled_but_not_set(self):
        self.config(show_image_direct_url=True)
        image = self._do_show(self.queued_image)
        self.assertNotIn('direct_url', image)

    def test_show_location_explicitly_disabled(self):
        self.config(show_image_direct_url=False)
        image = self._do_show(self.active_image)
        self.assertNotIn('direct_url', image)


class TestImageSchemaFormatConfiguration(test_utils.BaseTestCase):

    def test_default_disk_formats(self):
        schema = glance.api.v2.images.get_schema()
        expected = [None, 'ami', 'ari', 'aki', 'vhd', 'vhdx', 'vmdk',
                    'raw', 'qcow2', 'vdi', 'iso', 'ploop']
        actual = schema.properties['disk_format']['enum']
        self.assertEqual(expected, actual)

    def test_custom_disk_formats(self):
        self.config(disk_formats=['gabe'], group="image_format")
        schema = glance.api.v2.images.get_schema()
        expected = [None, 'gabe']
        actual = schema.properties['disk_format']['enum']
        self.assertEqual(expected, actual)

    def test_default_container_formats(self):
        schema = glance.api.v2.images.get_schema()
        expected = [None, 'ami', 'ari', 'aki', 'bare', 'ovf', 'ova', 'docker',
                    'compressed']
        actual = schema.properties['container_format']['enum']
        self.assertEqual(expected, actual)

    def test_custom_container_formats(self):
        self.config(container_formats=['mark'], group="image_format")
        schema = glance.api.v2.images.get_schema()
        expected = [None, 'mark']
        actual = schema.properties['container_format']['enum']
        self.assertEqual(expected, actual)


class TestImageSchemaDeterminePropertyBasis(test_utils.BaseTestCase):

    def test_custom_property_marked_as_non_base(self):
        self.config(allow_additional_image_properties=False)
        custom_image_properties = {
            'pants': {
                'type': 'string',
            },
        }
        schema = glance.api.v2.images.get_schema(custom_image_properties)
        self.assertFalse(schema.properties['pants'].get('is_base', True))

    def test_base_property_marked_as_base(self):
        schema = glance.api.v2.images.get_schema()
        self.assertTrue(schema.properties['disk_format'].get('is_base', True))


class TestMultiImagesController(base.MultiIsolatedUnitTest):

    def setUp(self):
        super(TestMultiImagesController, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = store
        self._create_images()
        self._create_image_members()
        stores = {'cheap': 'file', 'fast': 'file', 'empty': 'file'}
        self.config(enabled_backends=stores)
        self.store.register_store_opts(CONF)
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                self.policy,
                                                                self.notifier,
                                                                self.store)

    def _create_images(self):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHKSUM,
                        name='1', size=256, virtual_size=1024,
                        visibility='public',
                        locations=[{'url': '%s/%s' % (BASE_URI, UUID1),
                                    'metadata': {}, 'status': 'active'}],
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        created_at=DATETIME),
            _db_fixture(UUID2, owner=TENANT1, checksum=CHKSUM1,
                        name='2', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        locations=[{'url': 'file://%s/%s' % (self.test_dir,
                                                             UUID2),
                                    'metadata': {}, 'status': 'active'}],
                        created_at=DATETIME + datetime.timedelta(seconds=1)),
            _db_fixture(UUID5, owner=TENANT3, checksum=CHKSUM1,
                        name='2', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        locations=[{'url': 'file://%s/%s' % (self.test_dir,
                                                             UUID2),
                                    'metadata': {}, 'status': 'active'}],
                        created_at=DATETIME + datetime.timedelta(seconds=1)),
            _db_fixture(UUID3, owner=TENANT3, checksum=CHKSUM1,
                        name='3', size=512, virtual_size=2048,
                        visibility='public', tags=['windows', '64bit', 'x86'],
                        created_at=DATETIME + datetime.timedelta(seconds=2)),
            _db_fixture(UUID4, owner=TENANT4, name='4',
                        size=1024, virtual_size=3072,
                        created_at=DATETIME + datetime.timedelta(seconds=3)),
            _db_fixture(UUID6, owner=TENANT3, checksum=CHKSUM1,
                        name='3', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        locations=[{'url': 'file://%s/%s' % (self.test_dir,
                                                             UUID6),
                                    'metadata': {'store': 'fast'},
                                    'status': 'active'},
                                   {'url': 'file://%s/%s' % (self.test_dir2,
                                                             UUID6),
                                    'metadata': {'store': 'cheap'},
                                    'status': 'active'}],
                        created_at=DATETIME + datetime.timedelta(seconds=1)),
            _db_fixture(UUID7, owner=TENANT3, checksum=CHKSUM1,
                        name='3', size=512, virtual_size=2048,
                        visibility='public',
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'},
                        locations=[{'url': 'file://%s/%s' % (self.test_dir,
                                                             UUID7),
                                    'metadata': {'store': 'fast'},
                                    'status': 'active'}],
                        created_at=DATETIME + datetime.timedelta(seconds=1)),
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def _create_image_members(self):
        self.image_members = [
            _db_image_member_fixture(UUID4, TENANT2),
            _db_image_member_fixture(UUID4, TENANT3,
                                     status='accepted'),
        ]
        [self.db.image_member_create(None, image_member)
            for image_member in self.image_members]

    def test_image_import_image_not_exist(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.import_image,
                          request, 'invalid_image',
                          {'method': {'name': 'glance-direct'}})

    def test_image_import_with_active_image(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.import_image,
                          request, UUID2,
                          {'method': {'name': 'glance-direct'}})

    def test_delete_from_store_as_non_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.delete_from_store,
                          request,
                          "fast",
                          UUID6)

    def test_delete_from_store_non_active(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.delete_from_store,
                          request,
                          "fast",
                          UUID3)

    def test_delete_from_store_no_image(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_from_store,
                          request,
                          "fast",
                          "nonexisting")

    def test_delete_from_store_invalid_store(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.delete_from_store,
                          request,
                          "burn",
                          UUID6)

    def test_delete_from_store_not_in_store(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_from_store,
                          request,
                          "empty",
                          UUID6)

    def test_delete_from_store_one_location(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.delete_from_store,
                          request,
                          "fast",
                          UUID7)

    def test_delete_from_store_as_non_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.controller.delete_from_store(request, "fast", UUID6)
        image = self.controller.show(request, UUID6)
        self.assertEqual(1, len(image.locations))
        self.assertEqual("cheap", image.locations[0]['metadata']['store'])

    def test_delete_from_store_as_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.controller.delete_from_store(request, "fast", UUID6)
        image = self.controller.show(request, UUID6)
        self.assertEqual(1, len(image.locations))
        self.assertEqual("cheap", image.locations[0]['metadata']['store'])

    def test_image_lazy_loading_store(self):
        # assert existing image does not have store in metadata
        existing_image = self.images[1]
        self.assertNotIn('store', existing_image['locations'][0]['metadata'])

        # assert: store information will be added by lazy loading
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(store_utils,
                               "_get_store_id_from_uri") as mock_uri:
            mock_uri.return_value = "fast"
            image = self.controller.show(request, UUID2)
            for loc in image.locations:
                self.assertIn('store', loc['metadata'])

    def test_image_lazy_loading_store_different_owner(self):
        # assert existing image does not have store in metadata
        existing_image = self.images[2]
        self.assertNotIn('store', existing_image['locations'][0]['metadata'])

        # assert: store information will be added by lazy loading even if owner
        # is different
        request = unit_test_utils.get_fake_request()
        request.headers.update({'X-Tenant_id': TENANT1})
        with mock.patch.object(store_utils,
                               "_get_store_id_from_uri") as mock_uri:
            mock_uri.return_value = "fast"
            image = self.controller.show(request, UUID5)
            for loc in image.locations:
                self.assertIn('store', loc['metadata'])

    def test_image_import_invalid_backend_in_request_header(self):
        request = unit_test_utils.get_fake_request()
        request.headers['x-image-meta-store'] = 'dummy'
        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='uploading')
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image,
                              request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict_if_disk_format_is_none(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(disk_format=None)
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='queued')
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'glance-direct'}})

    def test_image_import_raises_conflict_for_web_download(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID4,
                              {'method': {'name': 'web-download'}})

    def test_copy_image_stores_specified_in_header_and_body(self):
        request = unit_test_utils.get_fake_request()
        request.headers['x-image-meta-store'] = 'fast'

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPBadRequest,
                              self.controller.import_image, request, UUID7,
                              {'method': {'name': 'copy-image'},
                               'stores': ["fast"]})

    def test_copy_image_non_existing_image(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.side_effect = exception.NotFound
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.controller.import_image, request, UUID1,
                              {'method': {'name': 'copy-image'},
                               'stores': ["fast"]})

    def test_copy_image_with_all_stores(self):
        request = unit_test_utils.get_fake_request()
        locations = {'url': 'file://%s/%s' % (self.test_dir,
                                              UUID7),
                     'metadata': {'store': 'fast'},
                     'status': 'active'},

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            with mock.patch.object(self.store,
                                   'get_store_from_store_identifier'):
                mock_get.return_value = FakeImage(id=UUID7, status='active',
                                                  locations=locations)
                self.assertIsNotNone(self.controller.import_image(
                    request, UUID7, {'method': {'name': 'copy-image'},
                                     'all_stores': True}))

    def test_copy_non_active_image(self):
        request = unit_test_utils.get_fake_request()

        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(status='uploading')
            self.assertRaises(webob.exc.HTTPConflict,
                              self.controller.import_image, request, UUID1,
                              {'method': {'name': 'copy-image'},
                               'stores': ["fast"]})

    def test_copy_image_in_existing_store(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.import_image, request, UUID6,
                          {'method': {'name': 'copy-image'},
                           'stores': ["fast"]})

    def test_copy_image_to_other_stores(self):
        request = unit_test_utils.get_fake_request()
        locations = {'url': 'file://%s/%s' % (self.test_dir,
                                              UUID7),
                     'metadata': {'store': 'fast'},
                     'status': 'active'},
        with mock.patch.object(
                glance.api.authorization.ImageRepoProxy, 'get') as mock_get:
            mock_get.return_value = FakeImage(id=UUID7, status='active',
                                              locations=locations)

            output = self.controller.import_image(
                request, UUID7, {'method': {'name': 'copy-image'},
                                 'stores': ["cheap"]})

        self.assertEqual(UUID7, output)
