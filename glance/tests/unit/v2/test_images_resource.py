# Copyright 2012 OpenStack LLC.
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
import json

import webob

import glance.api.v2.images
from glance.common import exception
from glance.common import utils
from glance.openstack.common import cfg
import glance.schema
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils
import glance.store


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
ISOTIME = '2012-05-16T15:27:36Z'


CONF = cfg.CONF


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'


class TestImagesController(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesController, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self._create_images()
        self.controller = glance.api.v2.images.ImagesController(self.db)
        glance.store.create_stores()

    def _create_images(self):
        self.db.reset()
        self.images = [
            {
                'id': UUID1,
                'owner': TENANT1,
                'location': 'swift+http://storeurl.com/container/%s' % UUID1,
                'name': '1',
                'is_public': True,
                'size': 256,
            },
            {
                'id': UUID2,
                'owner': TENANT1,
                'name': '2',
                'is_public': True,
                'size': 512,
            },
            {
                'id': UUID3,
                'owner': TENANT3,
                'name': '3',
                'is_public': True,
                'size': 512,
            },
            {
                'id': UUID4,
                'owner': TENANT4,
                'name': '4',
                'is_public': False,
                'size': 1024,
            },
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def test_index(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual(1, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID3])
        self.assertEqual(actual, expected)

    def test_index_return_parameters(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID3, limit=1,
                                       sort_key='created_at', sort_dir='desc')
        self.assertEqual(1, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID2])
        self.assertEqual(actual, expected)
        self.assertEqual(UUID2, output['next_marker'])

    def test_index_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID3, limit=2)
        self.assertEqual(2, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID2, UUID1])
        self.assertEqual(actual, expected)
        self.assertEqual(UUID1, output['next_marker'])

    def test_index_no_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request, marker=UUID1, limit=2)
        self.assertEqual(0, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([])
        self.assertEqual(actual, expected)
        self.assertTrue('next_marker' not in output)

    def test_index_with_id_filter(self):
        request = unit_test_utils.get_fake_request('/images?id=%s' % UUID1)
        output = self.controller.index(request, filters={'id': UUID1})
        self.assertEqual(1, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID1])
        self.assertEqual(actual, expected)

    def test_index_size_max_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_max=512')
        output = self.controller.index(request, filters={'size_max': 512})
        self.assertEqual(3, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID1, UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_size_min_filter(self):
        request = unit_test_utils.get_fake_request('/images?size_min=512')
        output = self.controller.index(request, filters={'size_min': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_size_range_filter(self):
        path = '/images?size_min=512&size_max=512'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request,
                                       filters={'size_min': 512,
                                                'size_max': 512})
        self.assertEqual(2, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID2, UUID3])
        self.assertEqual(actual, expected)

    def test_index_with_invalid_max_range_filter_value(self):
        request = unit_test_utils.get_fake_request('/images?size_max=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index,
                          request,
                          filters={'size_max': 'blah'})

    def test_index_with_filters_return_many(self):
        path = '/images?owner=%s' % TENANT1
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, filters={'owner': TENANT1})
        self.assertEqual(2, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID1, UUID2])
        self.assertEqual(actual, expected)

    def test_index_with_nonexistant_name_filter(self):
        request = unit_test_utils.get_fake_request('/images?name=%s' % 'blah')
        images = self.controller.index(request,
                                       filters={'name': 'blah'})['images']
        self.assertEqual(0, len(images))

    def test_index_with_non_default_is_public_filter(self):
        image = {
            'id': utils.generate_uuid(),
            'owner': TENANT3,
            'name': '3',
            'is_public': False
        }
        self.db.image_create(None, image)
        path = '/images?visibility=private'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, filters={'is_public': False})
        self.assertEqual(2, len(output['images']))

    def test_index_with_many_filters(self):
        request = unit_test_utils.get_fake_request('/images?owner=%s&name=%s' %
        (TENANT1, '1'))
        output = self.controller.index(request,
                                       filters={'owner': TENANT1, 'name': '2'})
        self.assertEqual(1, len(output['images']))
        actual = set([image['id'] for image in output['images']])
        expected = set([UUID2])
        self.assertEqual(actual, expected)

    def test_index_with_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, marker=UUID3)
        actual = set([image['id'] for image in output['images']])
        self.assertEquals(1, len(actual))
        self.assertTrue(UUID2 in actual)

    def test_index_with_limit(self):
        path = '/images'
        limit = 2
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=limit)
        actual = set([image['id'] for image in output['images']])
        self.assertEquals(limit, len(actual))
        self.assertTrue(UUID3 in actual)
        self.assertTrue(UUID2 in actual)

    def test_index_greater_than_limit_max(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=4)
        actual = set([image['id'] for image in output['images']])
        self.assertEquals(3, len(actual))
        self.assertTrue(output['next_marker'] not in output)

    def test_index_default_limit(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request)
        actual = set([image['id'] for image in output['images']])
        self.assertEquals(1, len(actual))

    def test_index_with_sort_dir(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_dir='asc', limit=3)
        actual = [image['id'] for image in output['images']]
        self.assertEquals(3, len(actual))
        self.assertEquals(UUID1, actual[0])
        self.assertEquals(UUID2, actual[1])
        self.assertEquals(UUID3, actual[2])

    def test_index_with_sort_key(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_key='created_at', limit=3)
        actual = [image['id'] for image in output['images']]
        self.assertEquals(3, len(actual))
        self.assertEquals(UUID3, actual[0])
        self.assertEquals(UUID2, actual[1])
        self.assertEquals(UUID1, actual[2])

    def test_index_with_marker_not_found(self):
        fake_uuid = utils.generate_uuid()
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

    def test_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.show(request, image_id=UUID2)
        for key in ['created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'id': UUID2,
            'name': '2',
            'owner': TENANT1,
            'size': 512,
            'location': None,
            'status': 'queued',
            'is_public': True,
            'tags': [],
            'properties': {},
            'deleted': False,
        }
        self.assertEqual(expected, output)

    def test_show_non_existant(self):
        request = unit_test_utils.get_fake_request()
        image_id = utils.generate_uuid()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, request, image_id)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1'}
        output = self.controller.create(request, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-1',
            'owner': TENANT1,
            'location': None,
            'status': 'queued',
            'is_public': False,
            'properties': {},
            'tags': [],
            'deleted': False,
        }
        self.assertEqual(expected, output)

    def test_create_with_owner_as_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        image = {'name': 'image-1', 'owner': utils.generate_uuid()}
        output = self.controller.create(request, image)
        self.assertEqual(image['owner'], output['owner'])

    def test_create_public_image_as_admin(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1', 'is_public': True}
        output = self.controller.create(request, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-1',
            'owner': TENANT1,
            'location': None,
            'status': 'queued',
            'is_public': True,
            'tags': [],
            'properties': {},
            'deleted': False,
        }
        self.assertEqual(expected, output)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-2'}
        output = self.controller.update(request, UUID1, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-2',
            'owner': TENANT1,
            'size': 256,
            'location': 'swift+http://storeurl.com/container/%s' % UUID1,
            'status': 'queued',
            'is_public': True,
            'tags': ['ping', 'pong'],
            'properties': {},
            'deleted': False,
        }
        self.assertEqual(expected, output)

    def test_update_non_existant(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-2'}
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.update,
                          request, utils.generate_uuid(), image)

    def test_index_with_invalid_marker(self):
        fake_uuid = utils.generate_uuid()
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, marker=fake_uuid)


class TestImagesDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializer, self).setUp()
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create_with_id(self):
        request = unit_test_utils.get_fake_request()
        image_id = utils.generate_uuid()
        request.body = json.dumps({'id': image_id})
        output = self.deserializer.create(request)
        expected = {'image': {'id': image_id, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_with_name(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1'})
        output = self.deserializer.create(request)
        expected = {'image': {'name': 'image-1', 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_with_owner_forbidden(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'owner': TENANT2})
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.deserializer.create, request)

    def test_create_with_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        request.body = json.dumps({'owner': TENANT2})
        output = self.deserializer.create(request)
        expected = {'image': {'owner': TENANT2, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_public(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'visibility': 'public'})
        output = self.deserializer.create(request)
        expected = {'image': {'is_public': True, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_private(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'visibility': 'private'})
        output = self.deserializer.create(request)
        expected = {'image': {'is_public': False, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_readonly_attributes_forbidden(self):
        for key in ['created_at', 'updated_at']:
            request = unit_test_utils.get_fake_request()
            request.body = json.dumps({key: ISOTIME})
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.deserializer.update, request)

    def test_create_status_attribute_forbidden(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'status': 'saving'})
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.deserializer.update, request)

    def test_create_with_tags(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'tags': ['one', 'two']})
        output = self.deserializer.create(request)
        expected = {'image': {'tags': ['one', 'two'], 'properties': {}}}
        self.assertEqual(expected, output)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1', 'visibility': 'public'})
        output = self.deserializer.update(request)
        expected = {
            'image': {
                'name': 'image-1',
                'is_public': True,
                'properties': {},
            },
        }
        self.assertEqual(expected, output)

    def test_update_readonly_attributes_forbidden(self):
        for key in ['created_at', 'updated_at']:
            request = unit_test_utils.get_fake_request()
            request.body = json.dumps({key: ISOTIME})
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.deserializer.update, request)

    def test_update_status_attribute_forbidden(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'status': 'saving'})
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.deserializer.update, request)

    def test_index(self):
        marker = utils.generate_uuid()
        path = '/images?limit=1&marker=%s' % marker
        request = unit_test_utils.get_fake_request(path)
        expected = {'limit': 1,
                    'marker': marker,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc',
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
        instance_id = utils.generate_uuid()
        path = '/images?name=%(name)s&id=%(instance_id)s' % locals()
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

    def test_index_marker(self):
        marker = utils.generate_uuid()
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
            'filters': {}
        }
        self.assertEqual(output, expected)

    def test_index_sort_dir_asc(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=asc')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': 'created_at',
            'sort_dir': 'asc',
            'filters': {}}
        self.assertEqual(output, expected)

    def test_index_sort_dir_bad_value(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)


class TestImagesDeserializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithExtendedSchema, self).setUp()
        self.config(allow_additional_image_properties=False)
        custom_image_properties = {
            'pants': {
                'type': 'string',
                'required': True,
                'enum': ['on', 'off'],
            },
        }
        schema = glance.api.v2.images.get_schema(custom_image_properties)
        self.deserializer = glance.api.v2.images.RequestDeserializer(schema)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1', 'pants': 'on'})
        output = self.deserializer.create(request)
        expected = {
            'image': {
                'name': 'image-1',
                'properties': {'pants': 'on'},
            },
        }
        self.assertEqual(expected, output)

    def test_create_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1', 'pants': 'borked'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1', 'pants': 'off'})
        output = self.deserializer.update(request)
        expected = {
            'image': {
                'name': 'image-1',
                'properties': {'pants': 'off'},
            },
        }
        self.assertEqual(expected, output)

    def test_update_bad_data(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'name': 'image-1', 'pants': 'borked'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                self.deserializer.update, request)


class TestImagesDeserializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.create(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)

    def test_create_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'abc': 123})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_create_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': ['bar']})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.update(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)


class TestImagesDeserializerNoAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerNoAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=False)
        self.deserializer = glance.api.v2.images.RequestDeserializer()

    def test_create_with_additional_properties_disallowed(self):
        self.config(allow_additional_image_properties=False)
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.update, request)


class TestImagesSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializer, self).setUp()
        self.serializer = glance.api.v2.images.ResponseSerializer()

    def test_index(self):
        fixtures = [
            {
                'id': unit_test_utils.UUID1,
                'name': 'image-1',
                'is_public': True,
                'properties': {},
                'checksum': None,
                'owner': TENANT1,
                'status': 'queued',
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': ['one', 'two'],
                'size': 1024,
            },
            {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'is_public': False,
                'owner': None,
                'status': 'queued',
                'properties': {},
                'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': [],
                'size': None,
            },
        ]
        expected = {
            'images': [
                {
                    'id': unit_test_utils.UUID1,
                    'name': 'image-1',
                    'owner': TENANT1,
                    'status': 'queued',
                    'visibility': 'public',
                    'checksum': None,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': ['one', 'two'],
                    'size': 1024,
                    'self': '/v2/images/%s' % unit_test_utils.UUID1,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID1,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID1,
                    'schema': '/v2/schemas/image',
                },
                {
                    'id': unit_test_utils.UUID2,
                    'name': 'image-2',
                    'owner': None,
                    'status': 'queued',
                    'visibility': 'private',
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': [],
                    'size': None,
                    'self': '/v2/images/%s' % unit_test_utils.UUID2,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
                    'schema': '/v2/schemas/image',
                },
            ],
            'first': '/v2/images',
            'schema': '/v2/schemas/images',
        }
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        result = {'images': fixtures}
        self.serializer.index(response, result)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)

    def test_index_next_marker(self):

        fixtures = [
            {
                'id': unit_test_utils.UUID1,
                'name': 'image-1',
                'owner': TENANT1,
                'status': 'queued',
                'is_public': True,
                'checksum': None,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': ['one', 'two'],
                'size': 1024,
            },
            {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'owner': TENANT2,
                'status': 'queued',
                'is_public': False,
                'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': [],
                'size': None,
            },
        ]
        expected = {
            'images': [
                {
                    'id': unit_test_utils.UUID1,
                    'name': 'image-1',
                    'owner': TENANT1,
                    'status': 'queued',
                    'visibility': 'public',
                    'checksum': None,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': ['one', 'two'],
                    'size': 1024,
                    'self': '/v2/images/%s' % unit_test_utils.UUID1,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID1,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID1,
                    'schema': '/v2/schemas/image',
                },
                {
                    'id': unit_test_utils.UUID2,
                    'name': 'image-2',
                    'owner': TENANT2,
                    'status': 'queued',
                    'visibility': 'private',
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': [],
                    'size': None,
                    'self': '/v2/images/%s' % unit_test_utils.UUID2,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
                    'schema': '/v2/schemas/image',
                },
            ],
            'first': '/v2/images',
            'next': '/v2/images?marker=%s' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/images',
        }
        request = webob.Request.blank('/v2/images')
        response = webob.Response(request=request)
        result = {'images': fixtures,
                  'next_marker': unit_test_utils.UUID2,
        }
        self.serializer.index(response, result)
        self.assertEqual(expected, json.loads(response.body))

    def test_index_next_forwarding_query_parameters_no_next(self):
        fixtures = [
            {
                'id': unit_test_utils.UUID1,
                'name': 'image-1',
                'owner': TENANT1,
                'status': 'queued',
                'is_public': True,
                'checksum': None,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': ['one', 'two'],
                'size': 1024,
            },
            {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'owner': TENANT2,
                'status': 'queued',
                'is_public': False,
                'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': [],
                'size': None,
            },
        ]
        expected = {
            'images': [
                {
                    'id': unit_test_utils.UUID1,
                    'name': 'image-1',
                    'owner': TENANT1,
                    'status': 'queued',
                    'visibility': 'public',
                    'checksum': None,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': ['one', 'two'],
                    'size': 1024,
                    'self': '/v2/images/%s' % unit_test_utils.UUID1,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID1,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID1,
                    'schema': '/v2/schemas/image',
                },
                {
                    'id': unit_test_utils.UUID2,
                    'name': 'image-2',
                    'owner': TENANT2,
                    'status': 'queued',
                    'visibility': 'private',
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': [],
                    'size': None,
                    'self': '/v2/images/%s' % unit_test_utils.UUID2,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
                    'schema': '/v2/schemas/image',
                },
            ],
            'first': '/v2/images?sort_key=id&sort_dir=asc&limit=10',
            'schema': '/v2/schemas/images',
        }
        url = '/v2/images?limit=10&sort_key=id&sort_dir=asc'
        request = webob.Request.blank(url)
        response = webob.Response(request=request)
        result = {'images': fixtures}
        self.serializer.index(response, result)
        self.assertEqual(expected, json.loads(response.body))

    def test_index_next_forwarding_query_parameters(self):

        fixtures = [
            {
                'id': unit_test_utils.UUID1,
                'name': 'image-1',
                'owner': TENANT1,
                'status': 'queued',
                'is_public': True,
                'checksum': None,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': ['one', 'two'],
                'size': 1024,
            },
            {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'owner': TENANT2,
                'status': 'queued',
                'is_public': False,
                'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': [],
                'size': None,
            },
        ]
        expected = {
            'images': [
                {
                    'id': unit_test_utils.UUID1,
                    'name': 'image-1',
                    'owner': TENANT1,
                    'status': 'queued',
                    'visibility': 'public',
                    'checksum': None,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': ['one', 'two'],
                    'size': 1024,
                    'self': '/v2/images/%s' % unit_test_utils.UUID1,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID1,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID1,
                    'schema': '/v2/schemas/image',
                },
                {
                    'id': unit_test_utils.UUID2,
                    'name': 'image-2',
                    'owner': TENANT2,
                    'status': 'queued',
                    'visibility': 'private',
                    'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': [],
                    'size': None,
                    'self': '/v2/images/%s' % unit_test_utils.UUID2,
                    'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
                    'schema': '/v2/schemas/image',
                },
            ],
            'first': '/v2/images?sort_key=id&sort_dir=asc&limit=2',
            'next': '/v2/images?sort_key=id&sort_dir=asc&limit=2&marker=%s'
                                                    % unit_test_utils.UUID2,
            'schema': '/v2/schemas/images',
        }
        url = '/v2/images?limit=2&sort_key=id&sort_dir=asc'
        request = webob.Request.blank(url)
        response = webob.Response(request=request)
        result = {'images': fixtures,
                  'next_marker': unit_test_utils.UUID2,
        }
        self.serializer.index(response, result)
        self.assertEqual(expected, json.loads(response.body))

    def test_show(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'is_public': True,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': ['three', 'four'],
            'size': 1024,
        }
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'public',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': ['three', 'four'],
            'size': 1024,
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        self.serializer.show(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)

    def test_create(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'is_public': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': [],
            'size': 1024,
        }
        self_link = '/v2/images/%s' % unit_test_utils.UUID2
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': [],
            'size': 1024,
            'self': self_link,
            'file': '%s/file' % self_link,
            'access': '%s/access' % self_link,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        self.serializer.create(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(response.location, self_link)

    def test_update(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'is_public': True,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': ['five'],
            'size': 1024,
        }
        self_link = '/v2/images/%s' % unit_test_utils.UUID2
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'public',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': ['five'],
            'size': 1024,
            'self': self_link,
            'file': '%s/file' % self_link,
            'access': '%s/access' % self_link,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        self.serializer.update(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)


class TestImagesSerializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithExtendedSchema, self).setUp()
        self.config(allow_additional_image_properties=False)
        custom_image_properties = {
            'color': {
                'type': 'string',
                'required': True,
                'enum': ['red', 'green'],
            },
        }
        schema = glance.api.v2.images.get_schema(custom_image_properties)
        self.serializer = glance.api.v2.images.ResponseSerializer(schema)

        self.fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'is_public': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': [],
            'size': 1024,
            'properties': {'color': 'green', 'mood': 'grouchy'},
        }

    def test_show(self):
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': [],
            'size': 1024,
            'color': 'green',
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        self.serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_reports_invalid_data(self):
        self.fixture['properties']['color'] = 'invalid'
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': [],
            'size': 1024,
            'color': 'invalid',
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        self.serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))


class TestImagesSerializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        self.fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'is_public': False,
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'properties': {
                'marx': 'groucho',
            },
            'tags': [],
            'size': 1024,
        }

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer()
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'marx': 'groucho',
            'tags': [],
            'size': 1024,
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_invalid_additional_property(self):
        """Ensure that the serializer passes through invalid additional
        properties (i.e. non-string) without complaining.
        """
        serializer = glance.api.v2.images.ResponseSerializer()
        self.fixture['properties']['marx'] = 123
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'marx': 123,
            'tags': [],
            'size': 1024,
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_with_additional_properties_disabled(self):
        self.config(allow_additional_image_properties=False)
        serializer = glance.api.v2.images.ResponseSerializer()
        expected = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'owner': TENANT2,
            'status': 'queued',
            'visibility': 'private',
            'checksum': 'ca425b88f047ce8ec45ee90e813ada91',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'tags': [],
            'size': 1024,
            'self': '/v2/images/%s' % unit_test_utils.UUID2,
            'file': '/v2/images/%s/file' % unit_test_utils.UUID2,
            'access': '/v2/images/%s/access' % unit_test_utils.UUID2,
            'schema': '/v2/schemas/image',
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))
