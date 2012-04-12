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

import glance.api.v2.image_access
from glance.common import exception
from glance.common import utils
import glance.tests.unit.utils as test_utils


class TestImageAccessController(unittest.TestCase):

    def setUp(self):
        super(TestImageAccessController, self).setUp()
        self.db = test_utils.FakeDB()
        self.controller = \
                glance.api.v2.image_access.ImageAccessController({}, self.db)

    def test_index(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req, test_utils.UUID1)
        expected = [
            {
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT1,
                'can_share': True,
            },
            {
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT2,
                'can_share': False,
            },
        ]
        self.assertEqual(expected, output)

    def test_index_zero_records(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req, test_utils.UUID2)
        expected = []
        self.assertEqual(expected, output)

    def test_index_nonexistant_image(self):
        req = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        self.assertRaises(exception.NotFound,
                          self.controller.index, req, image_id)

    def test_show(self):
        req = test_utils.FakeRequest()
        image_id = test_utils.UUID1
        tenant_id = test_utils.TENANT1
        output = self.controller.show(req, image_id, tenant_id)
        expected = {
            'image_id': image_id,
            'member': tenant_id,
            'can_share': True,
        }
        self.assertEqual(expected, output)

    def test_show_nonexistant_image(self):
        req = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        tenant_id = test_utils.TENANT1
        self.assertRaises(exception.NotFound,
                          self.controller.show, req, image_id, tenant_id)

    def test_show_nonexistant_tenant(self):
        req = test_utils.FakeRequest()
        image_id = test_utils.UUID1
        tenant_id = utils.generate_uuid()
        self.assertRaises(exception.NotFound,
                          self.controller.show, req, image_id, tenant_id)

    def test_create(self):
        fixture = {
            'image_id': test_utils.UUID1,
            'member': utils.generate_uuid(),
            'can_share': True,
        }
        req = test_utils.FakeRequest()
        output = self.controller.create(req, fixture)
        self.assertEqual(fixture, output)


class TestImageAccessDeserializer(unittest.TestCase):
    def setUp(self):
        self.deserializer = glance.api.v2.image_access.RequestDeserializer({})

    def test_create(self):
        fixture = {
            'image_id': test_utils.UUID1,
            'tenant_id': test_utils.TENANT1,
            'can_share': False,
        }
        expected = {
            'image_id': test_utils.UUID1,
            'member': test_utils.TENANT1,
            'can_share': False,
        }
        request = test_utils.FakeRequest()
        request.body = json.dumps(fixture)
        output = self.deserializer.create(request)
        self.assertEqual(output, {'access': expected})

    def _test_create_fails(self, fixture):
        request = test_utils.FakeRequest()
        request.body = json.dumps(fixture)
        self.assertRaises(jsonschema.ValidationError,
                          self.deserializer.create, request)

    def test_create_no_image(self):
        fixture = {'tenant_id': test_utils.TENANT1, 'can_share': True}
        self._test_create_fails(fixture)


class TestImageAccessSerializer(unittest.TestCase):
    serializer = glance.api.v2.image_access.ResponseSerializer()

    def test_show(self):
        fixture = {
            'member': test_utils.TENANT1,
            'image_id': test_utils.UUID1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (test_utils.UUID1, test_utils.TENANT1))
        expected = {
            'access': {
                'image_id': test_utils.UUID1,
                'tenant_id': test_utils.TENANT1,
                'can_share': False,
                'links': [
                    {'rel': 'self', 'href': self_href},
                    {'rel': 'describedby', 'href': '/v2/schemas/image/access'},
                ],
            },
        }
        response = webob.Response()
        self.serializer.show(response, fixture)
        self.assertEqual(expected, json.loads(response.body))

    def test_index(self):
        fixtures = [
            {
                'member': test_utils.TENANT1,
                'image_id': test_utils.UUID1,
                'can_share': False,
            },
            {
                'member': test_utils.TENANT2,
                'image_id': test_utils.UUID2,
                'can_share': True,
            },
        ]
        expected = {
            'access_records': [
                {
                    'image_id': test_utils.UUID1,
                    'tenant_id': test_utils.TENANT1,
                    'can_share': False,
                    'links': [
                        {
                            'rel': 'self',
                            'href': ('/v2/images/%s/access/%s' %
                                    (test_utils.UUID1, test_utils.TENANT1))
                        },
                        {
                            'rel': 'describedby',
                            'href': '/v2/schemas/image/access',
                        },
                    ],
                },
                {
                    'image_id': test_utils.UUID2,
                    'tenant_id': test_utils.TENANT2,
                    'can_share': True,
                    'links': [
                        {
                            'rel': 'self',
                            'href': ('/v2/images/%s/access/%s' %
                                    (test_utils.UUID2, test_utils.TENANT2))
                        },
                        {
                            'rel': 'describedby',
                            'href': '/v2/schemas/image/access',
                        },
                    ],
                },
            ],
            'links': [],
        }
        response = webob.Response()
        self.serializer.index(response, fixtures)
        self.assertEqual(expected, json.loads(response.body))

    def test_create(self):
        fixture = {
            'member': test_utils.TENANT1,
            'image_id': test_utils.UUID1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (test_utils.UUID1, test_utils.TENANT1))
        expected = {
            'access': {
                'image_id': test_utils.UUID1,
                'tenant_id': test_utils.TENANT1,
                'can_share': False,
                'links': [
                    {'rel': 'self', 'href': self_href},
                    {'rel': 'describedby', 'href': '/v2/schemas/image/access'},
                ],
            },
        }
        response = webob.Response()
        self.serializer.create(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual(self_href, response.location)
