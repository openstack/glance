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
import unittest

import webob

import glance.api.v2.images
from glance.common import exception
from glance.common import utils
import glance.schema
import glance.tests.unit.utils as test_utils
import glance.tests.utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
ISOTIME = '2012-05-16T15:27:36Z'


class TestImagesController(unittest.TestCase):
    def setUp(self):
        super(TestImagesController, self).setUp()
        self.db = test_utils.FakeDB()
        self.controller = glance.api.v2.images.ImagesController({}, self.db)

    def test_index(self):
        request = test_utils.FakeRequest()
        output = self.controller.index(request)
        self.assertEqual(2, len(output))
        self.assertEqual(output[0]['id'], test_utils.UUID1)
        self.assertEqual(output[1]['id'], test_utils.UUID2)

    def test_index_zero_images(self):
        self.db.reset()
        request = test_utils.FakeRequest()
        output = self.controller.index(request)
        self.assertEqual([], output)

    def test_show(self):
        request = test_utils.FakeRequest()
        output = self.controller.show(request, image_id=test_utils.UUID2)
        self.assertEqual(output['id'], test_utils.UUID2)

    def test_show_non_existant(self):
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.show,
                test_utils.FakeRequest(), image_id=utils.generate_uuid())

    def test_create(self):
        request = test_utils.FakeRequest()
        image = {'name': 'image-1'}
        output = self.controller.create(request, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-1',
            'owner': test_utils.TENANT1,
            'location': None,
            'status': 'queued',
            'is_public': False,
            'properties': {},
        }
        self.assertEqual(expected, output)

    def test_create_with_owner_forbidden(self):
        request = test_utils.FakeRequest()
        image = {'name': 'image-1', 'owner': utils.generate_uuid()}
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.create,
                          request, image)

    def test_create_public_image_as_admin(self):
        request = test_utils.FakeRequest()
        image = {'name': 'image-1', 'is_public': True}
        output = self.controller.create(request, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-1',
            'owner': test_utils.TENANT1,
            'location': None,
            'status': 'queued',
            'is_public': True,
            'properties': {},
        }
        self.assertEqual(expected, output)

    def test_update(self):
        request = test_utils.FakeRequest()
        image = {'name': 'image-2'}
        output = self.controller.update(request, test_utils.UUID1, image)
        for key in ['id', 'created_at', 'updated_at']:
            output.pop(key)
        expected = {
            'name': 'image-2',
            'owner': test_utils.TENANT1,
            'location': test_utils.UUID1,
            'status': 'queued',
            'is_public': False,
            'properties': {},
        }
        self.assertEqual(expected, output)

    def test_update_non_existant(self):
        request = test_utils.FakeRequest()
        image = {'name': 'image-2'}
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.update,
                          request, utils.generate_uuid(), image)


class TestImagesDeserializer(unittest.TestCase):
    def setUp(self):
        self.conf = glance.tests.utils.TestConfigOpts()
        schema_api = glance.schema.API(self.conf)
        self.deserializer = glance.api.v2.images.RequestDeserializer(
                {}, schema_api)

    def test_create_with_id(self):
        request = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        request.body = json.dumps({'id': image_id})
        output = self.deserializer.create(request)
        expected = {'image': {'id': image_id, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_with_name(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'name': 'image-1'})
        output = self.deserializer.create(request)
        expected = {'image': {'name': 'image-1', 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_public(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'visibility': 'public'})
        output = self.deserializer.create(request)
        expected = {'image': {'is_public': True, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_private(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'visibility': 'private'})
        output = self.deserializer.create(request)
        expected = {'image': {'is_public': False, 'properties': {}}}
        self.assertEqual(expected, output)

    def test_create_readonly_attributes_ignored(self):
        for key in ['created_at', 'updated_at']:
            request = test_utils.FakeRequest()
            request.body = json.dumps({key: ISOTIME})
            output = self.deserializer.create(request)
            expected = {'image': {'properties': {}}}
            self.assertEqual(expected, output)

    def test_update(self):
        request = test_utils.FakeRequest()
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
            request = test_utils.FakeRequest()
            request.body = json.dumps({key: ISOTIME})
            output = self.deserializer.update(request)
            expected = {'image': {'properties': {}}}
            self.assertEqual(expected, output)


class TestImagesDeserializerWithExtendedSchema(unittest.TestCase):
    def setUp(self):
        conf = glance.tests.utils.TestConfigOpts()
        schema_api = glance.schema.API(conf)
        props = {
            'pants': {
              'type': 'string',
              'required': True,
              'enum': ['on', 'off'],
            },
        }
        schema_api.set_custom_schema_properties('image', props)
        self.deserializer = glance.api.v2.images.RequestDeserializer(
                {}, schema_api)

    def test_create(self):
        request = test_utils.FakeRequest()
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
        request = test_utils.FakeRequest()
        request.body = json.dumps({'name': 'image-1', 'pants': 'borked'})
        self.assertRaises(exception.InvalidObject,
                self.deserializer.create, request)

    def test_update(self):
        request = test_utils.FakeRequest()
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
        request = test_utils.FakeRequest()
        request.body = json.dumps({'name': 'image-1', 'pants': 'borked'})
        self.assertRaises(exception.InvalidObject,
                self.deserializer.update, request)


class TestImagesDeserializerWithAdditionalProperties(unittest.TestCase):
    def setUp(self):
        self.conf = glance.tests.utils.TestConfigOpts()
        self.conf.allow_additional_image_properties = True
        schema_api = glance.schema.API(self.conf)
        self.deserializer = glance.api.v2.images.RequestDeserializer(
                {}, schema_api)

    def test_create(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.create(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)

    def test_create_with_additional_properties_disallowed(self):
        self.conf.allow_additional_image_properties = False
        request = test_utils.FakeRequest()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_create_with_numeric_property(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'abc': 123})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_create_with_list_property(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'foo': ['bar']})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.create, request)

    def test_update(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'foo': 'bar'})
        output = self.deserializer.update(request)
        expected = {'image': {'properties': {'foo': 'bar'}}}
        self.assertEqual(expected, output)

    def test_update_with_additional_properties_disallowed(self):
        self.conf.allow_additional_image_properties = False
        request = test_utils.FakeRequest()
        request.body = json.dumps({'foo': 'bar'})
        self.assertRaises(exception.InvalidObject,
                          self.deserializer.update, request)


class TestImagesSerializer(unittest.TestCase):
    def setUp(self):
        conf = glance.tests.utils.TestConfigOpts()
        schema_api = glance.schema.API(conf)
        self.serializer = glance.api.v2.images.ResponseSerializer(schema_api)

    def test_index(self):
        fixtures = [
            {
                'id': test_utils.UUID1,
                'name': 'image-1',
                'is_public': True,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
            },
            {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'is_public': False,
                'properties': {},
                'created_at': DATETIME,
                'updated_at': DATETIME,
            },
        ]
        expected = {
            'images': [
                {
                    'id': test_utils.UUID1,
                    'name': 'image-1',
                    'visibility': 'public',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID1,
                        },
                        {
                            'rel': 'file',
                            'href': '/v2/images/%s/file' % test_utils.UUID1,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
                {
                    'id': test_utils.UUID2,
                    'name': 'image-2',
                    'visibility': 'private',
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID2,
                        },
                        {
                            'rel': 'file',
                            'href': '/v2/images/%s/file' % test_utils.UUID2,
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
            'id': test_utils.UUID2,
            'name': 'image-2',
            'is_public': True,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
        }
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'public',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
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
            'id': test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
        }
        self_link = '/v2/images/%s' % test_utils.UUID2
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
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
            'id': test_utils.UUID2,
            'name': 'image-2',
            'is_public': True,
            'properties': {},
            'created_at': DATETIME,
            'updated_at': DATETIME,
        }
        self_link = '/v2/images/%s' % test_utils.UUID2
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'public',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
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


class TestImagesSerializerWithExtendedSchema(unittest.TestCase):
    def setUp(self):
        self.conf = glance.tests.utils.TestConfigOpts()
        self.conf.allow_additional_image_properties = False
        self.schema_api = glance.schema.API(self.conf)
        props = {
            'color': {
                'type': 'string',
                'required': True,
                'enum': ['red', 'green'],
            },
        }
        self.schema_api.set_custom_schema_properties('image', props)
        self.fixture = {
            'id': test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'properties': {'color': 'green', 'mood': 'grouchy'},
        }

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'color': 'green',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
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
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'color': 'invalid',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))


class TestImagesSerializerWithAdditionalProperties(unittest.TestCase):
    def setUp(self):
        self.conf = glance.tests.utils.TestConfigOpts()
        self.conf.allow_additional_image_properties = True
        self.schema_api = glance.schema.API(self.conf)
        self.fixture = {
            'id': test_utils.UUID2,
            'name': 'image-2',
            'is_public': False,
            'created_at': DATETIME,
            'updated_at': DATETIME,
            'properties': {
                'marx': 'groucho',
            },
        }

    def test_show(self):
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'marx': 'groucho',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
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
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'marx': 123,
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_show_with_additional_properties_disabled(self):
        self.conf.allow_additional_image_properties = False
        serializer = glance.api.v2.images.ResponseSerializer(self.schema_api)
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'visibility': 'private',
                'created_at': ISOTIME,
                'updated_at': ISOTIME,
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {
                        'rel': 'file',
                        'href': '/v2/images/%s/file' % test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        serializer.show(response, self.fixture)
        self.assertEqual(expected, json.loads(response.body))
