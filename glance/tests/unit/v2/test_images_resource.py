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

import webob

import glance.api.v2.images
from glance.common import utils
import glance.tests.unit.utils as test_utils


class TestImagesController(unittest.TestCase):

    def setUp(self):
        super(TestImagesController, self).setUp()
        self.db = test_utils.FakeDB()
        self.controller = glance.api.v2.images.ImagesController({}, self.db)

    def test_index(self):
        req = test_utils.FakeRequest()
        output = self.controller.index(req)
        expected = {
            'images': [
                {
                    'id': test_utils.UUID1,
                    'name': 'image-name',
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID1,
                        },
                        {
                            'rel': 'access',
                            'href': '/v2/images/%s/access' % test_utils.UUID1,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
                {
                    'id': test_utils.UUID2,
                    'name': 'image-name',
                    'links': [
                        {
                            'rel': 'self',
                            'href': '/v2/images/%s' % test_utils.UUID2,
                        },
                        {
                            'rel': 'access',
                            'href': '/v2/images/%s/access' % test_utils.UUID2,
                        },
                        {'rel': 'describedby', 'href': '/v2/schemas/image'}
                    ],
                },
            ],
            'links': [],
        }
        self.assertEqual(expected, output)

    def test_index_zero_images(self):
        self.db.reset()
        req = test_utils.FakeRequest()
        output = self.controller.index(req)
        self.assertEqual({'images': [], 'links': []}, output)

    def test_show(self):
        req = test_utils.FakeRequest()
        output = self.controller.show(req, id=test_utils.UUID2)
        expected = {
            'id': test_utils.UUID2,
            'name': 'image-name',
            'links': [
                {'rel': 'self', 'href': '/v2/images/%s' % test_utils.UUID2},
                {
                    'rel': 'access',
                    'href': '/v2/images/%s/access' % test_utils.UUID2,
                },
                {'rel': 'describedby', 'href': '/v2/schemas/image'}
            ],
        }
        self.assertEqual(expected, output)

    def test_show_non_existant(self):
        self.assertRaises(webob.exc.HTTPNotFound, self.controller.show,
                test_utils.FakeRequest(), id=utils.generate_uuid())
