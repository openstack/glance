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

import json
import unittest

import jsonschema
import webob

import glance.api.v2.images
from glance.common import exception
from glance.common import utils
import glance.tests.unit.utils as test_utils


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
        output = self.controller.show(request, id=test_utils.UUID2)
        self.assertEqual(output['id'], test_utils.UUID2)

    def test_show_non_existant(self):
        self.assertRaises(exception.NotFound, self.controller.show,
                test_utils.FakeRequest(), id=utils.generate_uuid())


class TestImagesDeserializer(unittest.TestCase):
    def setUp(self):
        self.deserializer = glance.api.v2.images.RequestDeserializer({})

    def test_create(self):
        request = test_utils.FakeRequest()
        request.body = json.dumps({'name': 'image-1'})
        output = self.deserializer.create(request)
        self.assertEqual(output, {'image': {'name': 'image-1'}})

    def test_create_with_id(self):
        request = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        request.body = json.dumps({'id': image_id, 'name': 'image-1'})
        output = self.deserializer.create(request)
        self.assertEqual(output,
                         {'image': {'id': image_id, 'name': 'image-1'}})

    def _test_create_fails(self, body):
        request = test_utils.FakeRequest()
        request.body = json.dumps(body)
        self.assertRaises(jsonschema.ValidationError,
                self.deserializer.create, request)

    def test_create_no_name(self):
        self._test_create_fails({})


class TestImagesSerializer(unittest.TestCase):
    def setUp(self):
        self.serializer = glance.api.v2.images.ResponseSerializer()

    def test_index(self):
        fixtures = [
            {'id': test_utils.UUID1, 'name': 'image-1'},
            {'id': test_utils.UUID2, 'name': 'image-2'},
        ]
        expected = {
            'images': [
                {
                    'id': test_utils.UUID1,
                    'name': 'image-1',
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID1,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
                {
                    'id': test_utils.UUID2,
                    'name': 'image-2',
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID2,
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
        fixture = {'id': test_utils.UUID2, 'name': 'image-2'}
        expected = {
            'image': {
                'id': test_utils.UUID2,
                'name': 'image-2',
                'links': [
                    {
                        'rel': 'self',
                        'href': '/v2/images/%s' % test_utils.UUID2,
                    },
                    {'rel': 'describedby', 'href': '/v2/schemas/image'}
                ],
            },
        }
        response = webob.Response()
        self.serializer.show(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
