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

    def _create_images(self):
        self.db.reset()
        self.images = [
            {'id': UUID1, 'owner': TENANT1, 'location': UUID1, 'name': '1'},
            {'id': UUID2, 'owner': TENANT1, 'name': '2'},
            {'id': UUID3, 'owner': TENANT3, 'name': '3'},
            {'id': UUID4, 'owner': TENANT4, 'name': '4'},
        ]
        [self.db.image_create(None, image) for image in self.images]

        self.db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    def test_index(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual(1, len(output))
        actual = set([image['id'] for image in output])
        expected = set([UUID4])
        self.assertEqual(actual, expected)

    def test_index_with_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, marker=UUID3)
        actual = set([image['id'] for image in output])
        self.assertEquals(1, len(actual))
        self.assertTrue(UUID2 in actual)

    def test_index_with_limit(self):
        path = '/images'
        limit = 2
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=limit)
        actual = set([image['id'] for image in output])
        self.assertEquals(limit, len(actual))
        self.assertTrue(UUID4 in actual)
        self.assertTrue(UUID3 in actual)

    def test_index_greater_than_limit_max(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, limit=4)
        actual = set([image['id'] for image in output])
        self.assertEquals(3, len(actual))

    def test_index_default_limit(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request)
        actual = set([image['id'] for image in output])
        self.assertEquals(1, len(actual))

    def test_index_with_sort_dir(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_dir='asc', limit=3)
        actual = [image['id'] for image in output]
        self.assertEquals(3, len(actual))
        self.assertEquals(UUID1, actual[0])
        self.assertEquals(UUID2, actual[1])
        self.assertEquals(UUID3, actual[2])

    def test_index_with_sort_key(self):
        path = '/images'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request, sort_key='id', limit=3)
        actual = [image['id'] for image in output]
        self.assertEquals(3, len(actual))
        self.assertEquals(UUID1, actual[0])
        self.assertEquals(UUID2, actual[1])
        self.assertEquals(UUID3, actual[2])

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
        self.assertEqual([], output)

    def test_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.controller.show(request, image_id=UUID2)
        for key in ['created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'id': UUID2,
            'name': '2',
            'owner': TENANT1,
            'location': None,
            'status': 'queued',
            'is_public': False,
            'tags': [],
            'members': [],
            'properties': {},
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
        }
        self.assertEqual(expected, output)

    def test_create_with_owner_forbidden(self):
        request = unit_test_utils.get_fake_request()
        image = {'name': 'image-1', 'owner': utils.generate_uuid()}
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.create,
                          request, image)

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
            'location': UUID1,
            'status': 'queued',
            'is_public': False,
            'tags': ['ping', 'pong'],
            'properties': {},
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
        schema_api = glance.schema.API()
        self.deserializer = glance.api.v2.images.RequestDeserializer(
            schema_api)

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

    def test_create_readonly_attributes_ignored(self):
        for key in ['created_at', 'updated_at']:
            request = unit_test_utils.get_fake_request()
            request.body = json.dumps({key: ISOTIME})
            output = self.deserializer.create(request)
            expected = {'image': {'properties': {}}}
            self.assertEqual(expected, output)

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

    def test_update_readonly_attributes_ignored(self):
        for key in ['created_at', 'updated_at']:
            request = unit_test_utils.get_fake_request()
            request.body = json.dumps({key: ISOTIME})
            output = self.deserializer.update(request)
            expected = {'image': {'properties': {}}}
            self.assertEqual(expected, output)

    def test_index(self):
        marker = utils.generate_uuid()
        path = '/images?limit=1&marker=%s' % marker
        request = unit_test_utils.get_fake_request(path)
        expected = {'limit': 1,
                    'marker': marker,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc'}
        output = self.deserializer.index(request)
        self.assertEqual(output, expected)

    def test_index_non_integer_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_zero_limit(self):
        request = unit_test_utils.get_fake_request('/images?limit=0')
        expected = {'limit': 0,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc'}
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
        expected = {'sort_key': 'id', 'sort_dir': 'desc'}
        self.assertEqual(output, expected)

    def test_index_sort_dir_asc(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=asc')
        output = self.deserializer.index(request)
        expected = {'sort_key': 'created_at', 'sort_dir': 'asc'}
        self.assertEqual(output, expected)

    def test_index_sort_dir_bad_value(self):
        request = unit_test_utils.get_fake_request('/images?sort_dir=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)


class TestImagesDeserializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithExtendedSchema, self).setUp()
        schema_api = glance.schema.API()
        props = {
            'pants': {
              'type': 'string',
              'required': True,
              'enum': ['on', 'off'],
            },
        }
        schema_api.set_custom_schema_properties('image', props)
        self.deserializer = glance.api.v2.images.RequestDeserializer(
            schema_api)

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
        self.assertRaises(exception.InvalidObject,
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
        self.assertRaises(exception.InvalidObject,
                self.deserializer.update, request)


class TestImagesDeserializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesDeserializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        schema_api = glance.schema.API()
        self.deserializer = glance.api.v2.images.RequestDeserializer(
            schema_api)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.create(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)

    def test_create_with_additional_properties_disallowed(self):
        self.config(allow_additional_image_properties=False)
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_create_with_numeric_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'abc': 123})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_create_with_list_property(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': ['bar']})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_update(self):
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.update(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)

    def test_update_with_additional_properties_disallowed(self):
        self.config(allow_additional_image_properties=False)
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.update, request)


class TestImagesSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializer, self).setUp()
        schema_api = glance.schema.API()
        self.serializer = glance.api.v2.images.ResponseSerializer(schema_api)

    def test_index(self):
        fixtures = [
            {
                'id': unit_test_utils.UUID1,
                'name': 'image-1',
                'is_public': True,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': ['one', 'two'],
            },
            {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'is_public': False,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
                'tags': [],
            },
        ]
        expected = {
            'images': [
                {
                    'id': unit_test_utils.UUID1,
                    'name': 'image-1',
                    'visibility': 'public',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': ['one', 'two'],
                    'links': [
                        {
                            'rel': 'self',
                            'href':
                                '/v2/images/%s' % unit_test_utils.UUID1,
                        },
                        {
                            'rel': 'file',
                            'href':
                                '/v2/images/%s/file' % unit_test_utils.UUID1,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
                {
                    'id': unit_test_utils.UUID2,
                    'name': 'image-2',
                    'visibility': 'private',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'tags': [],
                    'links': [
                        {
                            'rel': 'self',
                            'href':
                                '/v2/images/%s' % unit_test_utils.UUID2,
                        },
                        {
                            'rel': 'file',
                            'href':
                                '/v2/images/%s/file' % unit_test_utils.UUID2,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
            ],
            'links': [],
        }
        response = webob.Response()
        self.serializer.index(response, fixtures)
        self.assertEqual(expected, json.loads(response.body))

    def test_show(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'is_public': True,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': ['three', 'four'],
        }
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'public',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': ['three', 'four'],
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        self.serializer.show(response, fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_create(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': [],
        }
        self_link = '/v2/images/%s' % unit_test_utils.UUID2
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': [],
                'links': [
                    {'rel': 'self', 'href': self_link},
                    {'rel': 'file', 'href': '%s/file' % self_link},
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        self.serializer.create(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual(response.location, self_link)

    def test_update(self):
        fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'is_public': True,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': ['five'],
        }
        self_link = '/v2/images/%s' % unit_test_utils.UUID2
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'public',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': ['five'],
                'links': [
                    {'rel': 'self', 'href': self_link},
                    {'rel': 'file', 'href': '%s/file' % self_link},
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        self.serializer.update(response, fixture)
        self.assertEqual(expected, json.loads(response.body))


class TestImagesSerializerWithExtendedSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithExtendedSchema, self).setUp()
        self.config(allow_additional_image_properties=False)
        self.schema_api = glance.schema.API()
        props = {
            'color': {
                'type': 'string',
                'required': True,
                'enum': ['red', 'green'],
            },
        }
        self.schema_api.set_custom_schema_properties('image', props)
        self.fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'tags': [],
            'properties': {'color': 'green', 'mood': 'grouchy'},
        }

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': [],
                'color': 'green',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_reports_invalid_data(self):
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        self.fixture['properties']['color'] = 'invalid'
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': [],
                'color': 'invalid',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))


class TestImagesSerializerWithAdditionalProperties(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagesSerializerWithAdditionalProperties, self).setUp()
        self.config(allow_additional_image_properties=True)
        self.schema_api = glance.schema.API()
        self.fixture = {
            'id': unit_test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'properties': {
                'marx': 'groucho',
            },
            'tags': [],
        }

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'marx': 'groucho',
                'tags': [],
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_invalid_additional_property(self):
        """Ensure that the serializer passes through invalid additional
        properties (i.e. non-string) without complaining.
        """
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        self.fixture['properties']['marx'] = 123
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'marx': 123,
                'tags': [],
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_with_additional_properties_disabled(self):
        self.config(allow_additional_image_properties=False)
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': unit_test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'tags': [],
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % unit_test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % unit_test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))
