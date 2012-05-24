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

import webob

from glance.api.v2 import image_access
from glance.common import exception
from glance.common import utils
import glance.schema
import glance.tests.unit.utils as test_utils
import glance.tests.utils


class TestImageAccessController(unittest.TestCase):

    def setUp(self):
        super(TestImageAccessController, self).setUp()
        self.db = test_utils.FakeDB()
        self.controller = image_access.Controller({}, self.db)

    def test_index(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req, test_utils.UUID1)
        expected = [
            {
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT1,
                'can_share': True,
                'deleted': False,
            },
            {
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT2,
                'can_share': False,
                'deleted': False,
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
            'deleted': False,
        }
        self.assertEqual(expected, output)

    def test_show_nonexistant_image(self):
        req = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        tenant_id = test_utils.TENANT1
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, req, image_id, tenant_id)

    def test_show_nonexistant_tenant(self):
        req = test_utils.FakeRequest()
        image_id = test_utils.UUID1
        tenant_id = utils.generate_uuid()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, req, image_id, tenant_id)

    def test_create(self):
        member = utils.generate_uuid()
        fixture = {
            'member': member,
            'can_share': True,
        }
        expected = {
            'image_id': test_utils.UUID1,
            'member': member,
            'can_share': True,
            'deleted': False,
        }
        req = test_utils.FakeRequest()
        output = self.controller.create(req, test_utils.UUID1, fixture)
        self.assertEqual(expected, output)


class TestImageAccessDeserializer(unittest.TestCase):
    def setUp(self):
        conf = glance.tests.utils.TestConfigOpts()
        schema_api = glance.schema.API(conf)
        self.deserializer = image_access.RequestDeserializer({}, schema_api)

    def test_create(self):
        fixture = {
            'tenant_id': test_utils.TENANT1,
            'can_share': False,
        }
        expected = {
            'access_record': {
                'member': test_utils.TENANT1,
                'can_share': False,
            },
        }
        request = test_utils.FakeRequest()
        request.body = json.dumps(fixture)
        output = self.deserializer.create(request)
        self.assertEqual(expected, output)


class TestImageAccessDeserializerWithExtendedSchema(unittest.TestCase):
    def setUp(self):
        conf = glance.tests.utils.TestConfigOpts()
        schema_api = glance.schema.API(conf)
        props = {
            'color': {
              'type': 'string',
              'required': True,
              'enum': ['blue', 'red'],
            },
        }
        schema_api.set_custom_schema_properties('access', props)
        self.deserializer = image_access.RequestDeserializer({}, schema_api)

    def test_create(self):
        fixture = {
            'tenant_id': test_utils.TENANT1,
            'can_share': False,
            'color': 'blue',
        }
        expected = {
            'access_record': {
                'member': test_utils.TENANT1,
                'can_share': False,
                'color': 'blue',
            },
        }
        request = test_utils.FakeRequest()
        request.body = json.dumps(fixture)
        output = self.deserializer.create(request)
        self.assertEqual(expected, output)

    def test_create_bad_data(self):
        fixture = {
            'tenant_id': test_utils.TENANT1,
            'can_share': False,
            'color': 'purple',
        }
        request = test_utils.FakeRequest()
        request.body = json.dumps(fixture)
        self.assertRaises(exception.InvalidObject,
                self.deserializer.create, request)


class TestImageAccessSerializer(unittest.TestCase):
    serializer = image_access.ResponseSerializer()

    def test_show(self):
        fixture = {
            'image_id': test_utils.UUID1,
            'member': test_utils.TENANT1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (test_utils.UUID1, test_utils.TENANT1))
        expected = {
            'access_record': {
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
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT1,
                'can_share': False,
            },
            {
                'image_id': test_utils.UUID1,
                'member': test_utils.TENANT2,
                'can_share': True,
            },
        ]
        expected = {
            'access_records': [
                {
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
                    'tenant_id': test_utils.TENANT2,
                    'can_share': True,
                    'links': [
                        {
                            'rel': 'self',
                            'href': ('/v2/images/%s/access/%s' %
                                    (test_utils.UUID1, test_utils.TENANT2))
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
            'image_id': test_utils.UUID1,
            'member': test_utils.TENANT1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (test_utils.UUID1, test_utils.TENANT1))
        expected = {
            'access': {
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
