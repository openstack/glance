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
import uuid

from oslo.config import cfg
import testtools
import webob

import glance.api.v2.images
from glance.common import exception
from glance.openstack.common import jsonutils
import glance.schema
import glance.store
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
ISOTIME = '2012-05-16T15:27:36Z'


CONF = cfg.CONF

BASE_URI = unit_test_utils.BASE_URI


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

CHKSUM = '93264c3edf5972c9f1cb309543d38a5c'
CHKSUM1 = '43254c3edf6972c9f1cb309543d38a8c'


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


class TestImagesController(base.IsolatedUnitTest):

    def setUp(self):
        super(TestImagesController, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = unit_test_utils.FakeStoreAPI()
        for i in range(1, 4):
            self.store.data['%s/fake_location_%i' % (BASE_URI, i)] = ('Z', 1)
        self._create_images()
        self._create_image_members()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                self.policy,
                                                                self.notifier,
                                                                self.store)
        glance.store.create_stores()

    def _create_images(self):
        self.db.reset()
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHKSUM,
                        name='1', size=256, virtual_size=1024,
                        is_public=True,
                        locations=[{'url': '%s/%s' % (BASE_URI, UUID1),
                                    'metadata': {}}],
                        disk_format='raw',
                        container_format='bare',
                        status='active'),
            _db_fixture(UUID2, owner=TENANT1, checksum=CHKSUM1,
                        name='2', size=512, virtual_size=2048,
                        is_public=True,
                        disk_format='raw',
                        container_format='bare',
                        status='active',
                        tags=['redhat', '64bit', 'power'],
                        properties={'hypervisor_type': 'kvm', 'foo': 'bar',
                                    'bar': 'foo'}),
            _db_fixture(UUID3, owner=TENANT3, checksum=CHKSUM1,
                        name='3', size=512, virtual_size=2048,
                        is_public=True, tags=['windows', '64bit', 'x86']),
            _db_fixture(UUID4, owner=TENANT4, name='4',
                        size=1024, virtual_size=3072),
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
        self.assertEqual(actual, expected)

    def test_index_member_status_accepted(self):
        self.config(limit_param_default=5, api_limit_max=5)
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        output = self.controller.index(request)
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        # can see only the public image
        self.assertEqual(actual, expected)

        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        output = self.controller.index(request)
        self.assertEqual(4, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3, UUID4])
        self.assertEqual(actual, expected)

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
        self.assertEqual(actual, expected)

    def test_index_return_parameters(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID3, limit=1,
                                       sort_key='created_at', sort_dir='desc')
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
        self.assertEqual(actual, expected)
        self.assertEqual(UUID1, output['next_marker'])

    def test_index_no_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID1, limit=2)
        self.assertEqual(0, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([])
        self.assertEqual(actual, expected)
        self.assertTrue('next_marker' not in output)

    def test_index_with_id_filter(self):
        request = unit_test_utils.get_fake_request('/images?id=%s' % UUID1)
        output = self.controller.index(request, filters={'id': UUID1})
        self.assertEqual(1, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1])
        self.assertEqual(actual, expected)

    def test_index_with_checksum_filter_single_image(self):
        req = unit_test_utils.get_fake_request('/images?checksum=%s' % CHKSUM)
        output = self.controller.index(req, filters={'checksum': CHKSUM})
        self.assertEqual(1, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID1]
        self.assertEqual(actual, expected)

    def test_index_with_checksum_filter_multiple_images(self):
        req = unit_test_utils.get_fake_request('/images?checksum=%s' % CHKSUM1)
        output = self.controller.index(req, filters={'checksum': CHKSUM1})
        self.assertEqual(2, len(output['images']))
        actual = list([image.image_id for image in output['images']])
        expected = [UUID3, UUID2]
        self.assertEqual(actual, expected)

    def test_index_with_non_existent_checksum(self):
        req = unit_test_utils.get_fake_request('/images?checksum=236231827')
        output = self.controller.index(req, filters={'checksum': '236231827'})
        self.assertEqual(0, len(output['images']))

    def test_index_size_max_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_max=512')
        output = self.controller.index(request, filters={'size_max': 512})
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_size_min_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_min=512')
        output = self.controller.index(request, filters={'size_min': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_size_range_filter(self):
        path = '/images?size_min=512&size_max=512'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'size_min': 512,
                                                'size_max': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_virtual_size_max_filter(self):
        ref = '/images?virtual_size_max=2048'
        request = unit_test_utils.get_fake_request(ref)
        output = self.controller.index(request,
                                       filters={'virtual_size_max': 2048})
        self.assertEqual(3, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_virtual_size_min_filter(self):
        ref = '/images?virtual_size_min=2048'
        request = unit_test_utils.get_fake_request(ref)
        output = self.controller.index(request,
                                       filters={'virtual_size_min': 2048})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_virtual_size_range_filter(self):
        path = '/images?virtual_size_min=512&virtual_size_max=2048'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'virtual_size_min': 2048,
                                                'virtual_size_max': 2048})
        self.assertEqual(2, len(output['images']))
        actual = set([image.image_id for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

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
        self.assertEqual(actual, expected)

    def test_index_with_nonexistent_name_filter(self):
        request = unit_test_utils.get_fake_request('/images?name=%s' % 'blah')
        images = self.controller.index(request,
                                       filters={'name': 'blah'})['images']
        self.assertEqual(0, len(images))

    def test_index_with_non_default_is_public_filter(self):
        image = _db_fixture(str(uuid.uuid4()),
                            is_public=False,
                            owner=TENANT3)
        self.db.image_create(None, image)
        path = '/images?visibility=private'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request,
                                       filters={'visibility': 'private'})
        self.assertEqual(2, len(output['images']))

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
        self.assertEqual(actual, expected)

    def test_index_with_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, marker=UUID3)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(1, len(actual))
        self.assertTrue(UUID2 in actual)

    def test_index_with_limit(self):
        path = '/images'
        limit = 2
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=limit)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(limit, len(actual))
        self.assertTrue(UUID3 in actual)
        self.assertTrue(UUID2 in actual)

    def test_index_greater_than_limit_max(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=4)
        actual = set([image.image_id for image in output['images']])
        self.assertEqual(3, len(actual))
        self.assertTrue(output['next_marker'] not in output)

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
        output = self.controller.index(request, sort_dir='asc', limit=3)
        actual = [image.image_id for image in output['images']]
        self.assertEqual(3, len(actual))
        self.assertEqual(UUID1, actual[0])
        self.assertEqual(UUID2, actual[1])
        self.assertEqual(UUID3, actual[2])

    def test_index_with_sort_key(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_key='created_at', limit=3)
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
                          self.controller.index, request, sort_key='foo')

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
        self.assertTrue('64bit' in actual[0])
        self.assertTrue('64bit' in actual[1])

    def test_index_with_multi_tags(self):
        path = '/images?tag=power&tag=64bit'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'tags': ['power', '64bit']})
        actual = [image.tags for image in output['images']]
        self.assertEqual(1, len(actual))
        self.assertTrue('64bit' in actual[0])
        self.assertTrue('power' in actual[0])

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
        self.assertTrue(len(tags) == len(properties))
        self.assertTrue('64bit' in tags[0])
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
        self.assertEqual(len(output['images']), 0)

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
        self.assertEqual(output.extra_properties['yin'], 'yang')

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
        self.assertEqual(request.context.tenant, TENANT1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, request, UUID4)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1'}
        output = self.controller.create(request, image=image,
                                        extra_properties={},
                                        tags=[])
        self.assertEqual('image-1', output.name)
        self.assertEqual({}, output.extra_properties)
        self.assertEqual(set([]), output.tags)
        self.assertEqual('private', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.create')
        self.assertEqual(output_log['payload']['name'], 'image-1')

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
        self.assertEqual('private', output.visibility)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.create')
        self.assertEqual(output_log['payload']['name'], 'image-1')

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
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.create')
        self.assertEqual(output_log['payload']['id'], output.image_id)

    def test_create_duplicate_tags(self):
        request = unit_test_utils.get_fake_request()
        tags = ['ping', 'ping']
        output = self.controller.create(request, image={},
                                        extra_properties={}, tags=tags)
        self.assertEqual(set(['ping']), output.tags)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.create')
        self.assertEqual(output_log['payload']['id'], output.image_id)

    def test_create_with_too_many_tags(self):
        self.config(image_tag_quota=1)
        request = unit_test_utils.get_fake_request()
        tags = ['ping', 'pong']
        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.controller.create,
                          request, image={}, extra_properties={},
                          tags=tags)

    def test_update_no_changes(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.update(request, UUID1, changes=[])
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.created_at, output.updated_at)
        self.assertEqual(len(output.tags), 2)
        self.assertTrue('ping' in output.tags)
        self.assertTrue('pong' in output.tags)
        output_logs = self.notifier.get_logs()
        #NOTE(markwash): don't send a notification if nothing is updated
        self.assertTrue(len(output_logs) == 0)

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

    def test_update_replace_base_attribute(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['name'], 'value': 'fedora'}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.name, 'fedora')
        self.assertEqual(output.extra_properties, {'foo': 'bar'})
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_replace_tags(self):
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['tags'], 'value': ['king', 'kong']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.tags), 2)
        self.assertTrue('king' in output.tags)
        self.assertTrue('kong' in output.tags)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_replace_property(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar', 'snitch': 'golden'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual(output.extra_properties['foo'], 'bar')
        self.assertEqual(output.extra_properties['snitch'], 'golden')

        changes = [
            {'op': 'replace', 'path': ['foo'], 'value': 'baz'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.extra_properties['foo'], 'baz')
        self.assertEqual(output.extra_properties['snitch'], 'golden')
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
        self.assertEqual(output.image_id, UUID1)
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
        self.assertEqual(resp.disk_format, 'raw')
        self.assertEqual(resp.container_format, 'bare')

    def test_update_remove_property_while_over_limit(self):
        """
        Ensure that image properties can be removed.

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
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.extra_properties), 1)
        self.assertEqual(output.extra_properties['fizz'], 'buzz')
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_and_remove_property_under_limit(self):
        """
        Ensure that image properties can be removed.

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
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.extra_properties), 1)
        self.assertEqual(output.extra_properties['fizz'], 'buzz')
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
        self.assertEqual(output.extra_properties['x_owner_foo'], 'bar')

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
        self.assertEqual(created_image.extra_properties['spl_creator_policy'],
                         'bar')

        another_request = unit_test_utils.get_fake_request(roles=['spl_role'])
        changes = [
            {'op': 'replace', 'path': ['spl_creator_policy'], 'value': 'par'},
        ]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          another_request, created_image.image_id, changes)
        another_request = unit_test_utils.get_fake_request(roles=['admin'])
        output = self.controller.update(another_request,
                                        created_image.image_id, changes)
        self.assertEqual(output.extra_properties['spl_creator_policy'],
                         'par')

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
        self.assertEqual(output.extra_properties['spl_creator_policy'],
                         'bar')

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
        self.assertEqual(output.extra_properties['x_owner_foo'], 'bar')

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
        self.assertEqual(output.extra_properties['x_owner_foo'], 'baz')

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

    def test_create_non_protected_prop(self):
        """
        Verify property marked with special char '@' is creatable by an unknown
        role
        """
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted_1': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        self.assertEqual(created_image.extra_properties['x_all_permitted_1'],
                         '1')
        another_request = unit_test_utils.get_fake_request(roles=['joe_soap'])
        extra_props = {'x_all_permitted_2': '2'}
        created_image = self.controller.create(another_request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        self.assertEqual(created_image.extra_properties['x_all_permitted_2'],
                         '2')

    def test_read_non_protected_prop(self):
        """
        Verify property marked with special char '@' is readable by an unknown
        role
        """
        self.set_property_protections()
        request = unit_test_utils.get_fake_request(roles=['admin'])
        image = {'name': 'image-1'}
        extra_props = {'x_all_permitted': '1'}
        created_image = self.controller.create(request, image=image,
                                               extra_properties=extra_props,
                                               tags=[])
        another_request = unit_test_utils.get_fake_request(roles=['joe_soap'])
        output = self.controller.show(another_request, created_image.image_id)
        self.assertEqual(output.extra_properties['x_all_permitted'], '1')

    def test_update_non_protected_prop(self):
        """
        Verify property marked with special char '@' is updatable by an unknown
        role
        """
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
        self.assertEqual(output.extra_properties['x_all_permitted'], 'baz')

    def test_delete_non_protected_prop(self):
        """
        Verify property marked with special char '@' is deletable by an unknown
        role
        """
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
        """
        Verify a property protected by special char '!' is creatable by no one
        """
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
        """
        Verify a property protected by special char '!' is readable by no one
        """
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
        """
        Verify a property protected by special char '!' is updatable by no one
        """
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
        """
        Verify a property protected by special char '!' is deletable by no one
        """
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

    def test_update_replace_locations(self):
        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 0)
        self.assertEqual(output.status, 'queued')
        self.assertIsNone(output.size)

        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 1)
        self.assertEqual(new_location, output.locations[0])
        self.assertEqual(output.status, 'active')

    def test_update_replace_locations_non_empty(self):
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_replace_locations_invalid(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 0)
        self.assertEqual(output.status, 'queued')

        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [{'url': 'unknow://foo', 'metadata': {}}]}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_replace_locations_status_exception(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        output = self.controller.update(request, UUID2, changes)
        self.assertEqual(output.image_id, UUID2)
        self.assertEqual(len(output.locations), 0)
        self.assertEqual(output.status, 'queued')

        self.db.image_update(None, UUID2, {'disk_format': None})

        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID2, changes)

    def test_update_add_property(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
            {'op': 'add', 'path': ['snitch'], 'value': 'golden'},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.extra_properties['foo'], 'baz')
        self.assertEqual(output.extra_properties['snitch'], 'golden')
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_base_property(self):
        self.db.image_update(None, UUID1, {'properties': {'foo': 'bar'}})
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['name'], 'value': 'fedora'}]
        self.assertRaises(webob.exc.HTTPConflict, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_property_already_present(self):
        request = unit_test_utils.get_fake_request()
        properties = {'foo': 'bar'}
        self.db.image_update(None, UUID1, {'properties': properties})

        output = self.controller.show(request, UUID1)
        self.assertEqual(output.extra_properties['foo'], 'bar')

        changes = [
            {'op': 'add', 'path': ['foo'], 'value': 'baz'},
        ]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, UUID1, changes)

    def test_update_add_locations(self):
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 2)
        self.assertEqual(new_location, output.locations[1])

    def test_update_add_locations_insertion(self):
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '0'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 2)
        self.assertEqual(new_location, output.locations[0])

    def test_update_add_locations_list(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': {'url': 'foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_locations_invalid(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': {'url': 'unknow://foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

        changes = [{'op': 'add', 'path': ['locations', None],
                    'value': {'url': 'unknow://foo', 'metadata': {}}}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_locations_status_exception(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        output = self.controller.update(request, UUID2, changes)
        self.assertEqual(output.image_id, UUID2)
        self.assertEqual(len(output.locations), 0)
        self.assertEqual(output.status, 'queued')

        self.db.image_update(None, UUID2, {'disk_format': None})

        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID2, changes)

    def test_update_add_duplicate_locations(self):
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 2)
        self.assertEqual(new_location, output.locations[1])

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_replace_duplicate_locations(self):
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 0)
        self.assertEqual(output.status, 'queued')

        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location, new_location]}]

        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          request, UUID1, changes)

    def test_update_add_too_many_locations(self):
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
        self.config(image_location_quota=-1)
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_remove_location_while_over_limit(self):
        """
        Ensure that image locations can be removed.

        Image locations should be able to be removed as long as the image has
        fewer than the limited number of image locations after the
        transaction.
        """
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
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 1)
        self.assertTrue('fake_location_2' in output.locations[0]['url'])
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_add_and_remove_location_under_limit(self):
        """
        Ensure that image locations can be removed.

        Image locations should be able to be added and removed simultaneously
        as long as the image has fewer than the limited number of image
        locations after the transaction.
        """
        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        self.config(show_multiple_locations=True)
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': '%s/fake_location_1' % BASE_URI,
                       'metadata': {}}},
        ]
        self.controller.update(request, UUID1, changes)
        self.config(image_location_quota=1)

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
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 1)
        self.assertTrue('fake_location_3' in output.locations[0]['url'])
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
        self.assertEqual(output.extra_properties['foo'], 'bar')
        self.assertEqual(output.extra_properties['snitch'], 'golden')

        changes = [
            {'op': 'remove', 'path': ['snitch']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.extra_properties, {'foo': 'bar'})
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_remove_missing_property(self):
        request = unit_test_utils.get_fake_request()

        changes = [
            {'op': 'remove', 'path': ['foo']},
        ]
        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.update, request, UUID1, changes)

    def test_update_remove_location(self):
        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)

        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'remove', 'path': ['locations', '0']}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 0)
        self.assertTrue(output.status == 'queued')
        self.assertIsNone(output.size)

        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(len(output.locations), 1)
        self.assertEqual(new_location, output.locations[0])
        self.assertEqual(output.status, 'active')

    def test_update_remove_location_invalid_pos(self):
        request = unit_test_utils.get_fake_request()
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
        def fake_delete_image_from_backend(self, *args, **kwargs):
            raise Exception('fake_backend_exception')

        self.stubs.Set(glance.store, 'delete_image_from_backend',
                       fake_delete_image_from_backend)

        request = unit_test_utils.get_fake_request()
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
        self.assertEqual(output.image_id, UUID1)
        self.assertEqual(output.min_ram, 128)
        self.addDetail('extra_properties',
                       testtools.content.json_content(
                           jsonutils.dumps(output.extra_properties)))
        self.assertEqual(len(output.extra_properties), 2)
        self.assertEqual(output.extra_properties['foo'], 'baz')
        self.assertEqual(output.extra_properties['kb'], 'dvorak')
        self.assertNotEqual(output.created_at, output.updated_at)

    def test_update_invalid_operation(self):
        request = unit_test_utils.get_fake_request()
        change = {'op': 'test', 'path': 'options', 'value': 'puts'}
        try:
            self.controller.update(request, UUID1, [change])
        except AssertionError:
            pass  # AssertionError is the desired behavior
        else:
            self.fail('Failed to raise AssertionError on %s' % change)

    def test_update_duplicate_tags(self):
        request = unit_test_utils.get_fake_request()
        changes = [
            {'op': 'replace', 'path': ['tags'], 'value': ['ping', 'ping']},
        ]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(len(output.tags), 1)
        self.assertTrue('ping' in output.tags)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.update')
        self.assertEqual(output_log['payload']['id'], UUID1)

    def test_delete(self):
        request = unit_test_utils.get_fake_request()
        self.assertTrue(filter(lambda k: UUID1 in k, self.store.data))
        try:
            self.controller.delete(request, UUID1)
            output_logs = self.notifier.get_logs()
            self.assertEqual(len(output_logs), 1)
            output_log = output_logs[0]
            self.assertEqual(output_log['notification_type'], "INFO")
            self.assertEqual(output_log['event_type'], "image.delete")
        except Exception as e:
            self.fail("Delete raised exception: %s" % e)

        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual(deleted_img['status'], 'deleted')
        self.assertFalse(filter(lambda k: UUID1 in k, self.store.data))

    def test_delete_queued_updates_status(self):
        """Ensure status of queued image is updated (LP bug #1048851)"""
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'queued'})
        image_id = image['id']
        self.controller.delete(request, image_id)

        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual(image['status'], 'deleted')

    def test_delete_queued_updates_status_delayed_delete(self):
        """
        Ensure status of queued image is updated (LP bug #1048851)
        to 'deleted' when delayed_delete isenabled
        """
        self.config(delayed_delete=True)
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = self.db.image_create(request.context, {'status': 'queued'})
        image_id = image['id']
        self.controller.delete(request, image_id)

        image = self.db.image_get(request.context, image_id,
                                  force_show_deleted=True)
        self.assertTrue(image['deleted'])
        self.assertEqual(image['status'], 'deleted')

    def test_delete_not_in_store(self):
        request = unit_test_utils.get_fake_request()
        self.assertTrue(filter(lambda k: UUID1 in k, self.store.data))
        for k in self.store.data:
            if UUID1 in k:
                del self.store.data[k]
                break

        self.controller.delete(request, UUID1)
        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual(deleted_img['status'], 'deleted')
        self.assertFalse(filter(lambda k: UUID1 in k, self.store.data))

    def test_delayed_delete(self):
        self.config(delayed_delete=True)
        request = unit_test_utils.get_fake_request()
        self.assertTrue(filter(lambda k: UUID1 in k, self.store.data))

        self.controller.delete(request, UUID1)
        deleted_img = self.db.image_get(request.context, UUID1,
                                        force_show_deleted=True)
        self.assertTrue(deleted_img['deleted'])
        self.assertEqual(deleted_img['status'], 'pending_delete')
        self.assertTrue(filter(lambda k: UUID1 in k, self.store.data))

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


class TestImagesControllerPolicies(base.IsolatedUnitTest):

    def setUp(self):
        super(TestImagesControllerPolicies, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.controller = glance.api.v2.images.ImagesController(self.db,
                                                                self.policy)

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

    def test_update_depublicize_image_unauthorized(self):
        rules = {"publicize_image": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['visibility'],
                    'value': 'private'}]
        output = self.controller.update(request, UUID1, changes)
        self.assertEqual(output.visibility, 'private')

    def test_update_get_image_location_unauthorized(self):
        rules = {"get_image_location": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

    def test_update_set_image_location_unauthorized(self):
        def fake_delete_image_from_backend(self, *args, **kwargs):
            pass

        rules = {"set_image_location": False}
        self.policy.set_rules(rules)
        new_location = {'url': '%s/fake_location' % BASE_URI, 'metadata': {}}
        request = unit_test_utils.get_fake_request()
        changes = [{'op': 'add', 'path': ['locations', '-'],
                    'value': new_location}]
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          request, UUID1, changes)

        self.stubs.Set(glance.store, 'delete_image_from_backend',
                       fake_delete_image_from_backend)

        changes = [{'op': 'replace', 'path': ['locations'], 'value': []}]
        self.controller.update(request, UUID1, changes)
        changes = [{'op': 'replace', 'path': ['locations'],
                    'value': [new_location]}]
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
        request.body = jsonutils.dumps({})
        output = self.deserializer.create(request)
        expected = {'image': {}, 'extra_properties': {}, 'tags': None}
        self.assertEqual(expected, output)

    def test_create_invalid_id(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({'id': 'gabe'})
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.create,
                          request)

    def test_create_no_body(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.create,
                          request)

    def test_create_full(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
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
            'id': UUID3,
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

    def test_create_readonly_attributes_forbidden(self):
        bodies = [
            #{'created_at': ISOTIME},
            #{'updated_at': ISOTIME},
            #{'status': 'saving'},
            {'direct_url': 'http://example.com'},
            #{'size': 10},
            #{'virtual_size': 10},
            #{'checksum': 'asdf'},
            {'self': 'http://example.com'},
            {'file': 'http://example.com'},
            {'schema': 'http://example.com'},
        ]

        for body in bodies:
            request = unit_test_utils.get_fake_request()
            request.body = jsonutils.dumps(body)
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.deserializer.create, request)

    def _get_fake_patch_request(self, content_type_minor_version=1):
        request = unit_test_utils.get_fake_request()
        template = 'application/openstack-images-v2.%d-json-patch'
        request.content_type = template % content_type_minor_version
        return request

    def test_update_empty_body(self):
        request = self._get_fake_patch_request()
        request.body = jsonutils.dumps([])
        output = self.deserializer.update(request)
        expected = {'changes': []}
        self.assertEqual(output, expected)

    def test_update_unsupported_content_type(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/json-patch'
        request.body = jsonutils.dumps([])
        try:
            self.deserializer.update(request)
        except webob.exc.HTTPUnsupportedMediaType as e:
            # desired result, but must have correct Accept-Patch header
            accept_patch = ['application/openstack-images-v2.1-json-patch',
                            'application/openstack-images-v2.0-json-patch']
            expected = ', '.join(sorted(accept_patch))
            self.assertEqual(e.headers['Accept-Patch'], expected)
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
            request.body = jsonutils.dumps(body)
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
        ]
        for change in changes:
            request = self._get_fake_patch_request()
            request.body = jsonutils.dumps([change])
            self.assertRaises(webob.exc.HTTPBadRequest,
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
        request.body = jsonutils.dumps(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'op': 'replace', 'path': ['name'], 'value': 'fedora'},
            {'op': 'replace', 'path': ['tags'], 'value': ['king', 'kong']},
            {'op': 'replace', 'path': ['foo'], 'value': 'bar'},
            {'op': 'add', 'path': ['bebim'], 'value': 'bap'},
            {'op': 'remove', 'path': ['sparks']},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': 'scheme3://path3', 'metadata': {}}},
            {'op': 'add', 'path': ['locations', '10'],
             'value': {'url': 'scheme4://path4', 'metadata': {}}},
            {'op': 'remove', 'path': ['locations', '2']},
            {'op': 'replace', 'path': ['locations'], 'value': []},
            {'op': 'replace', 'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]}
        self.assertEqual(output, expected)

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
        request.body = jsonutils.dumps(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'op': 'replace', 'path': ['name'], 'value': 'fedora'},
            {'op': 'replace', 'path': ['tags'], 'value': ['king', 'kong']},
            {'op': 'replace', 'path': ['foo'], 'value': 'bar'},
            {'op': 'add', 'path': ['bebim'], 'value': 'bap'},
            {'op': 'remove', 'path': ['sparks']},
            {'op': 'add', 'path': ['locations', '-'],
             'value': {'url': 'scheme3://path3', 'metadata': {}}},
            {'op': 'add', 'path': ['locations', '10'],
             'value': {'url': 'scheme4://path4', 'metadata': {}}},
            {'op': 'remove', 'path': ['locations', '2']},
            {'op': 'replace', 'path': ['locations'], 'value': []},
            {'op': 'replace', 'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]},
        ]}
        self.assertEqual(output, expected)

    def test_update_base_attributes(self):
        request = self._get_fake_patch_request()
        body = [
            {'op': 'replace', 'path': '/id', 'value': UUID1},
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
        request.body = jsonutils.dumps(body)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'op': 'replace', 'path': ['id'], 'value': UUID1},
            {'op': 'replace', 'path': ['name'], 'value': 'fedora'},
            {'op': 'replace', 'path': ['visibility'], 'value': 'public'},
            {'op': 'replace', 'path': ['tags'], 'value': ['king', 'kong']},
            {'op': 'replace', 'path': ['protected'], 'value': True},
            {'op': 'replace', 'path': ['container_format'], 'value': 'bare'},
            {'op': 'replace', 'path': ['disk_format'], 'value': 'raw'},
            {'op': 'replace', 'path': ['min_ram'], 'value': 128},
            {'op': 'replace', 'path': ['min_disk'], 'value': 10},
            {'op': 'replace', 'path': ['locations'], 'value': []},
            {'op': 'replace', 'path': ['locations'],
             'value': [{'url': 'scheme5://path5', 'metadata': {}},
                       {'url': 'scheme6://path6', 'metadata': {}}]}
        ]}
        self.assertEqual(output, expected)

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
            request.body = jsonutils.dumps(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPForbidden:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPForbidden" % key)

    def test_update_readonly_attributes(self):
        samples = {
            'status': 'active',
            'checksum': 'abcdefghijklmnopqrstuvwxyz012345',
            'size': 9001,
            'virtual_size': 9001,
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dumps(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPForbidden:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPForbidden" % key)

    def test_update_reserved_attributes(self):
        samples = {
            'owner': TENANT1,
            'is_public': True,
            'deleted': False,
            'deleted_at': ISOTIME,
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dumps(body)
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
            request.body = jsonutils.dumps(body)
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
            request.body = jsonutils.dumps(doc)
            output = self.deserializer.update(request)
            self.assertEqual(output['changes'][0]['path'], decoded)

    def test_update_deep_limited_attributes(self):
        samples = {
            'locations/1/2': [],
        }

        for key, value in samples.items():
            request = self._get_fake_patch_request()
            body = [{'op': 'replace', 'path': '/%s' % key, 'value': value}]
            request.body = jsonutils.dumps(body)
            try:
                self.deserializer.update(request)
            except webob.exc.HTTPBadRequest:
                pass  # desired behavior
            else:
                self.fail("Updating %s did not result in HTTPBadRequest" % key)

    def test_update_v2_1_missing_operations(self):
        request = self._get_fake_patch_request()
        body = [{'path': '/colburn', 'value': 'arcata'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_1_missing_value(self):
        request = self._get_fake_patch_request()
        body = [{'op': 'replace', 'path': '/colburn'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_1_missing_path(self):
        request = self._get_fake_patch_request()
        body = [{'op': 'replace', 'value': 'arcata'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_multiple_operations(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'replace': '/foo', 'add': '/bar', 'value': 'snore'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_missing_operations(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'value': 'arcata'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update_v2_0_missing_value(self):
        request = self._get_fake_patch_request(content_type_minor_version=0)
        body = [{'replace': '/colburn'}]
        request.body = jsonutils.dumps(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_index(self):
        marker = str(uuid.uuid4())
        path = '/images?limit=1&marker=%s&member_status=pending' % marker
        request = unit_test_utils.get_fake_request(path)
        expected = {'limit': 1,
                    'marker': marker,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc',
                    'member_status': 'pending',
                    'filters': {}}
        output = self.deserializer.index(request)
        self.assertEqual(output, expected)

    def test_index_with_filter(self):
        name = 'My Little Image'
        path = '/images?name=%s' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(output['filters']['name'], name)

    def test_index_strip_params_from_filters(self):
        name = 'My Little Image'
        path = '/images?name=%s' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(output['filters']['name'], name)
        self.assertEqual(len(output['filters']), 1)

    def test_index_with_many_filter(self):
        name = 'My Little Image'
        instance_id = str(uuid.uuid4())
        path = ('/images?name=%(name)s&id=%(instance_id)s' %
                {'name': name, 'instance_id': instance_id})
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(output['filters']['name'], name)
        self.assertEqual(output['filters']['id'], instance_id)

    def test_index_with_filter_and_limit(self):
        name = 'My Little Image'
        path = '/images?name=%s&limit=1' % name
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(output['filters']['name'], name)
        self.assertEqual(output['limit'], 1)

    def test_index_non_integer_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_zero_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=0')
        expected = {'limit': 0,
                    'sort_key': 'created_at',
                    'member_status': 'accepted',
                    'sort_dir': 'desc',
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
        self.assertEqual(output.get('marker'), marker)

    def test_index_marker_not_specified(self):
        request = unit_test_utils.get_fake_request('/images')
        output = self.deserializer.index(request)
        self.assertFalse('marker' in output)

    def test_index_limit_not_specified(self):
        request = unit_test_utils.get_fake_request('/images')
        output = self.deserializer.index(request)
        self.assertFalse('limit' in output)

    def test_index_sort_key_id(self):
        request = unit_test_utils.get_fake_request('/images?sort_key=id')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': 'id',
            'sort_dir': 'desc',
            'member_status': 'accepted',
            'filters': {}
        }
        self.assertEqual(output, expected)

    def test_index_sort_dir_asc(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=asc')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': 'created_at',
            'sort_dir': 'asc',
            'member_status': 'accepted',
            'filters': {}}
        self.assertEqual(output, expected)

    def test_index_sort_dir_bad_value(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_with_tag(self):
        path = '/images?tag=%s&tag=%s' % ('x86', '64bit')
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(sorted(output['filters']['tags']),
                         sorted(['x86', '64bit']))


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
        request.body = jsonutils.dumps({'name': 'image-1', 'pants': 'on'})
        output = self.deserializer.create(request)
        expected = {
            'image': {'name': 'image-1'},
            'extra_properties': {'pants': 'on'},
            'tags': None,
        }
        self.assertEqual(expected, output)

    def test_create_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({'name': 'image-1', 'pants': 'borked'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/pants', 'value': 'off'}]
        request.body = jsonutils.dumps(doc)
        output = self.deserializer.update(request)
        expected = {'changes': [
            {'op': 'add', 'path': ['pants'], 'value': 'off'},
        ]}
        self.assertEqual(expected, output)

    def test_update_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/pants', 'value': 'cutoffs'}]
        request.body = jsonutils.dumps(doc)
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
        request.body = jsonutils.dumps({'foo': 'bar'})
        output = self.deserializer.create(request)
        expected = {'image': {},
                    'extra_properties': {'foo': 'bar'},
                    'tags': None}
        self.assertEqual(expected, output)

    def test_create_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({'abc': 123})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 123}]
        request.body = jsonutils.dumps(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_create_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({'foo': ['bar']})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': ['bar', 'baz']}]
        request.body = jsonutils.dumps(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 'bar'}]
        request.body = jsonutils.dumps(doc)
        output = self.deserializer.update(request)
        change = {'op': 'add', 'path': ['foo'], 'value': 'bar'}
        self.assertEqual(output, {'changes': [change]})


class TestImagesDeserializerNoAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerNoAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=False)
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create_with_additional_properties_disallowed(self):
        self.config(allow_additional_image_properties=False)
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({'foo': 'bar'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.content_type = 'application/openstack-images-v2.1-json-patch'
        doc = [{'op': 'add', 'path': '/foo', 'value': 'bar'}]
        request.body = jsonutils.dumps(doc)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)


class TestImagesSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializer, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()
        self.fixtures = [
            #NOTE(bcwaldon): This first fixture has every property defined
            _domain_fixture(UUID1, name='image-1', size=1024,
                            virtual_size=3072, created_at=DATETIME,
                            updated_at=DATETIME, owner=TENANT1,
                            visibility='public', container_format='ami',
                            tags=['one', 'two'], disk_format='ami',
                            min_ram=128, min_disk=10,
                            checksum='ca425b88f047ce8ec45ee90e813ada91'),

            #NOTE(bcwaldon): This second fixture depends on default behavior
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
                    'tags': set(['one', 'two']),
                    'size': 1024,
                    'virtual_size': 3072,
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
                    'tags': set([]),
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/images/%s' % UUID2,
                    'file': '/v2/images/%s/file' % UUID2,
                    'schema': '/v2/schemas/image',
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
        """Make sure the serializer works fine no mater if current user is
        authorized to get image location if the show_multiple_locations is
        False.
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
        self.assertEqual(response.status_int, 200)

        # The image index should work though the user is forbidden
        result['images'][0].locations = ImageLocations()
        self.serializer.index(response, result)
        self.assertEqual(response.status_int, 200)

    def test_show_full_fixture(self):
        expected = {
            'id': UUID1,
            'name': 'image-1',
            'status': 'queued',
            'visibility': 'public',
            'protected': False,
            'tags': set(['one', 'two']),
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
            'tags': [],
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
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
            'tags': ['one', 'two'],
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
        self.assertEqual(response.status_int, 201)
        actual = jsonutils.loads(response.body)
        actual['tags'] = sorted(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(response.location, '/v2/images/%s' % UUID1)

    def test_update(self):
        expected = {
            'id': UUID1,
            'name': 'image-1',
            'status': 'queued',
            'visibility': 'public',
            'protected': False,
            'tags': set(['one', 'two']),
            'size': 1024,
            'virtual_size': 3072,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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


class TestImagesSerializerWithUnicode(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithUnicode, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()
        self.fixtures = [
            #NOTE(bcwaldon): This first fixture has every property defined
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
                    u'tags': [u'\u2160', u'\u2161'],
                    u'size': 1024,
                    u'virtual_size': 3072,
                    u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
                    u'container_format': u'ami',
                    u'disk_format': u'ami',
                    u'min_ram': 128,
                    u'min_disk': 10,
                    u'created_at': unicode(ISOTIME),
                    u'updated_at': unicode(ISOTIME),
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
            u'tags': set([u'\u2160', u'\u2161']),
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': unicode(ISOTIME),
            u'updated_at': unicode(ISOTIME),
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
            u'tags': [u'\u2160', u'\u2161'],
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': unicode(ISOTIME),
            u'updated_at': unicode(ISOTIME),
            u'self': u'/v2/images/%s' % UUID1,
            u'file': u'/v2/images/%s/file' % UUID1,
            u'schema': u'/v2/schemas/image',
            u'lang': u'Fran\u00E7ais',
            u'dispos\u00E9': u'f\u00E2ch\u00E9',
            u'owner': u'6838eb7b-6ded-434a-882c-b344c77fe8df',
        }
        response = webob.Response()
        self.serializer.create(response, self.fixtures[0])
        self.assertEqual(response.status_int, 201)
        actual = jsonutils.loads(response.body)
        actual['tags'] = sorted(actual['tags'])
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(response.location, '/v2/images/%s' % UUID1)

    def test_update(self):
        expected = {
            u'id': UUID1,
            u'name': u'OpenStack\u2122-1',
            u'status': u'queued',
            u'visibility': u'public',
            u'protected': False,
            u'tags': set([u'\u2160', u'\u2161']),
            u'size': 1024,
            u'virtual_size': 3072,
            u'checksum': u'ca425b88f047ce8ec45ee90e813ada91',
            u'container_format': u'ami',
            u'disk_format': u'ami',
            u'min_ram': 128,
            u'min_disk': 10,
            u'created_at': unicode(ISOTIME),
            u'updated_at': unicode(ISOTIME),
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
            created_at=DATETIME, updated_at=DATETIME, size=1024,
            virtual_size=3072, extra_properties=props)

    def test_show(self):
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, jsonutils.loads(response.body))

    def test_show_invalid_additional_property(self):
        """Ensure that the serializer passes through invalid additional
        properties (i.e. non-string) without complaining.
        """
        serializer = glance.api.v2.images.ResponseSerializer()
        self.fixture.extra_properties['marx'] = 123
        expected = {
            'id': UUID2,
            'name': 'image-2',
            'status': 'queued',
            'visibility': 'private',
            'protected': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
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
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'tags': [],
            'size': 1024,
            'virtual_size': 3072,
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/images/%s' % UUID2,
            'file': '/v2/images/%s/file' % UUID2,
            'schema': '/v2/schemas/image',
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
            locations=[{'url': 'http://some/fake/location',
                        'metadata': {}}])

        self.queued_image = _domain_fixture(
            UUID2, name='image-2', status='active',
            created_at=DATETIME, updated_at=DATETIME,
            checksum='ca425b88f047ce8ec45ee90e813ada91')

        self.location_data_image_url = 'http://abc.com/somewhere'
        self.location_data_image_meta = {'key': 98231}
        self.location_data_image = _domain_fixture(
            UUID2, name='image-2', status='active',
            created_at=DATETIME, updated_at=DATETIME,
            locations=[{'url': self.location_data_image_url,
                        'metadata': self.location_data_image_meta}])

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
        self.assertEqual(images[0]['id'], UUID1)
        self.assertEqual(images[1]['id'], UUID2)

        self.assertEqual(images[0]['direct_url'], 'http://some/fake/location')
        self.assertFalse('direct_url' in images[1])

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
        self.assertFalse('direct_url' in images[0])
        self.assertFalse('direct_url' in images[1])

    def test_show_location_enabled(self):
        self.config(show_image_direct_url=True)
        image = self._do_show(self.active_image)
        self.assertEqual(image['direct_url'], 'http://some/fake/location')

    def test_show_location_enabled_but_not_set(self):
        self.config(show_image_direct_url=True)
        image = self._do_show(self.queued_image)
        self.assertFalse('direct_url' in image)

    def test_show_location_explicitly_disabled(self):
        self.config(show_image_direct_url=False)
        image = self._do_show(self.active_image)
        self.assertFalse('direct_url' in image)


class TestImageSchemaFormatConfiguration(test_utils.BaseTestCase):
    def test_default_disk_formats(self):
        schema = glance.api.v2.images.get_schema()
        expected = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2',
                    'vdi', 'iso']
        actual = schema.properties['disk_format']['enum']
        self.assertEqual(expected, actual)

    def test_custom_disk_formats(self):
        self.config(disk_formats=['gabe'], group="image_format")
        schema = glance.api.v2.images.get_schema()
        expected = ['gabe']
        actual = schema.properties['disk_format']['enum']
        self.assertEqual(expected, actual)

    def test_default_container_formats(self):
        schema = glance.api.v2.images.get_schema()
        expected = ['ami', 'ari', 'aki', 'bare', 'ovf', 'ova']
        actual = schema.properties['container_format']['enum']
        self.assertEqual(expected, actual)

    def test_custom_container_formats(self):
        self.config(container_formats=['mark'], group="image_format")
        schema = glance.api.v2.images.get_schema()
        expected = ['mark']
        actual = schema.properties['container_format']['enum']
        self.assertEqual(expected, actual)
