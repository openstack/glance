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

import webob

import glance.api.v2.image_access
from glance.common import exception
from glance.common import utils
import glance.schema
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


class TestImageAccessController(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageAccessController, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.controller = glance.api.v2.image_access.Controller(self.db)

    def test_index(self):
        req = unit_test_utils.get_fake_request()
        output = self.controller.index(req, unit_test_utils.UUID1)
        expected = {
            'access_records': [
                {
                    'image_id': unit_test_utils.UUID1,
                    'member': unit_test_utils.TENANT1,
                    'can_share': True,
                    'deleted': False,
                    'deleted_at': None,
                },
                {
                    'image_id': unit_test_utils.UUID1,
                    'member': unit_test_utils.TENANT2,
                    'can_share': False,
                    'deleted': False,
                    'deleted_at': None,
                },
            ],
            'image_id': unit_test_utils.UUID1,
        }
        self.assertEqual(expected, output)

    def test_index_zero_records(self):
        req = unit_test_utils.get_fake_request()
        output = self.controller.index(req, unit_test_utils.UUID2)
        expected = {
            'access_records': [],
            'image_id': unit_test_utils.UUID2,
        }
        self.assertEqual(expected, output)

    def test_index_nonexistant_image(self):
        req = unit_test_utils.get_fake_request()
        image_id = utils.generate_uuid()
        self.assertRaises(exception.NotFound,
                          self.controller.index, req, image_id)

    def test_show(self):
        req = unit_test_utils.get_fake_request()
        image_id = unit_test_utils.UUID1
        tenant_id = unit_test_utils.TENANT1
        output = self.controller.show(req, image_id, tenant_id)
        expected = {
            'image_id': image_id,
            'member': tenant_id,
            'can_share': True,
            'deleted': False,
            'deleted_at': None,
        }
        self.assertEqual(expected, output)

    def test_show_nonexistant_image(self):
        req = unit_test_utils.get_fake_request()
        image_id = utils.generate_uuid()
        tenant_id = unit_test_utils.TENANT1
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, req, image_id, tenant_id)

    def test_show_nonexistant_tenant(self):
        req = unit_test_utils.get_fake_request()
        image_id = unit_test_utils.UUID1
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
            'image_id': unit_test_utils.UUID1,
            'member': member,
            'can_share': True,
            'deleted': False,
            'deleted_at': None,
        }
        req = unit_test_utils.get_fake_request()
        output = self.controller.create(req, unit_test_utils.UUID1, fixture)
        self.assertEqual(expected, output)


class TestImageAccessDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageAccessDeserializer, self).setUp()
        self.deserializer = glance.api.v2.image_access.RequestDeserializer()

    def test_create(self):
        fixture = {
            'tenant_id': unit_test_utils.TENANT1,
            'can_share': False,
        }
        expected = {
            'access_record': {
                'member': unit_test_utils.TENANT1,
                'can_share': False,
            },
        }
        request = unit_test_utils.get_fake_request()
        request.body = json.dumps(fixture)
        output = self.deserializer.create(request)
        self.assertEqual(expected, output)


class TestImageAccessSerializer(test_utils.BaseTestCase):
    serializer = glance.api.v2.image_access.ResponseSerializer()

    def test_show(self):
        fixture = {
            'image_id': unit_test_utils.UUID1,
            'member': unit_test_utils.TENANT1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (unit_test_utils.UUID1, unit_test_utils.TENANT1))
        expected = {
            'tenant_id': unit_test_utils.TENANT1,
            'can_share': False,
            'self': self_href,
            'schema': '/v2/schemas/image/access',
            'image': '/v2/images/%s' % unit_test_utils.UUID1,
        }
        response = webob.Response()
        self.serializer.show(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)

    def test_index(self):
        fixtures = [
            {
                'image_id': unit_test_utils.UUID1,
                'member': unit_test_utils.TENANT1,
                'can_share': False,
            },
            {
                'image_id': unit_test_utils.UUID1,
                'member': unit_test_utils.TENANT2,
                'can_share': True,
            },
        ]
        result = {
            'access_records': fixtures,
            'image_id': unit_test_utils.UUID1,
        }
        expected = {
            'access_records': [
                {
                    'tenant_id': unit_test_utils.TENANT1,
                    'can_share': False,
                    'self': ('/v2/images/%s/access/%s' %
                                    (unit_test_utils.UUID1,
                                     unit_test_utils.TENANT1)),
                    'schema': '/v2/schemas/image/access',
                    'image': '/v2/images/%s' % unit_test_utils.UUID1,
                },
                {
                    'tenant_id': unit_test_utils.TENANT2,
                    'can_share': True,
                    'self': ('/v2/images/%s/access/%s' %
                                    (unit_test_utils.UUID1,
                                     unit_test_utils.TENANT2)),
                    'schema': '/v2/schemas/image/access',
                    'image': '/v2/images/%s' % unit_test_utils.UUID1,
                },
            ],
           'first': '/v2/images/%s/access' % unit_test_utils.UUID1,
           'schema': '/v2/schemas/image/accesses',

        }
        response = webob.Response()
        self.serializer.index(response, result)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)

    def test_index_zero_access_records(self):
        result = {
            'access_records': [],
            'image_id': unit_test_utils.UUID1,
        }
        response = webob.Response()
        self.serializer.index(response, result)
        first_link = '/v2/images/%s/access' % unit_test_utils.UUID1
        expected = {
            'access_records': [],
            'first': first_link,
            'schema': '/v2/schemas/image/accesses',
        }
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)

    def test_create(self):
        fixture = {
            'image_id': unit_test_utils.UUID1,
            'member': unit_test_utils.TENANT1,
            'can_share': False,
        }
        self_href = ('/v2/images/%s/access/%s' %
                (unit_test_utils.UUID1, unit_test_utils.TENANT1))
        expected = {
            'tenant_id': unit_test_utils.TENANT1,
            'can_share': False,
            'self': self_href,
            'schema': '/v2/schemas/image/access',
            'image': '/v2/images/%s' % unit_test_utils.UUID1,
        }
        response = webob.Response()
        self.serializer.create(response, fixture)
        self.assertEqual(expected, json.loads(response.body))
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(self_href, response.location)
