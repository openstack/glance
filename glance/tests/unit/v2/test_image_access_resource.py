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

import unittest

import webob.exc

import glance.api.v2.image_access
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
        expected = {
            'access_records': [
                {
                    'image_id': test_utils.UUID1,
                    'tenant_id': test_utils.TENANT1,
                    'can_share': True,
                    'links': [
                        {
                            'rel': 'self',
                            'href': ('/v2/images/%s/access/%s' %
                                (test_utils.UUID1, test_utils.TENANT1)),
                        },
                        {
                            'rel': 'describedby',
                            'href': '/v2/schemas/image/access',
                        },

                    ],
                },
                {
                    'image_id': test_utils.UUID1,
                    'tenant_id': test_utils.TENANT2,
                    'can_share': False,
                    'links': [
                        {
                            'rel': 'self',
                            'href': ('/v2/images/%s/access/%s' %
                                (test_utils.UUID1, test_utils.TENANT2)),
                        },
                        {
                            'rel': 'describedby',
                            'href': '/v2/schemas/image/access',
                        },
                    ],
                },
            ],
            'links': [
                {
                    'rel': 'self',
                    'href': '/v2/images/%s/access' % test_utils.UUID1,
                },
            ],
        }
        self.assertEqual(expected, output)

    def test_index_zero_records(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req, test_utils.UUID2)
        expected = {
            'access_records': [],
            'links': [
                {
                    'rel': 'self',
                    'href': '/v2/images/%s/access' % test_utils.UUID2,
                },
            ],
        }
        self.assertEqual(expected, output)

    def test_index_nonexistant_image(self):
        req = test_utils.FakeRequest()
        image_id = utils.generate_uuid()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.index, req, image_id)
