# Copyright 2012 OpenStack Foundation
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

import testtools
import webob

import glance.api.common
from glance.common import config
from glance.common import exception
from glance.tests import utils as test_utils


class SimpleIterator(object):
    def __init__(self, file_object, chunk_size):
        self.file_object = file_object
        self.chunk_size = chunk_size

    def __iter__(self):
        def read_chunk():
            return self.fobj.read(self.chunk_size)

        chunk = read_chunk()
        while chunk:
            yield chunk
            chunk = read_chunk()
        else:
            raise StopIteration()


class TestSizeCheckedIter(testtools.TestCase):
    def _get_image_metadata(self):
        return {'id': 'e31cb99c-fe89-49fb-9cc5-f5104fffa636'}

    def _get_webob_response(self):
        request = webob.Request.blank('/')
        response = webob.Response()
        response.request = request
        return response

    def test_uniform_chunk_size(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(
            resp, meta, 4, ['AB', 'CD'], None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('CD', checked_image.next())
        self.assertRaises(StopIteration, checked_image.next)

    def test_small_last_chunk(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(
            resp, meta, 3, ['AB', 'C'], None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('C', checked_image.next())
        self.assertRaises(StopIteration, checked_image.next)

    def test_variable_chunk_size(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(
            resp, meta, 6, ['AB', '', 'CDE', 'F'], None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('', checked_image.next())
        self.assertEqual('CDE', checked_image.next())
        self.assertEqual('F', checked_image.next())
        self.assertRaises(StopIteration, checked_image.next)

    def test_too_many_chunks(self):
        """An image should streamed regardless of expected_size"""
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(
            resp, meta, 4, ['AB', 'CD', 'EF'], None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('CD', checked_image.next())
        self.assertEqual('EF', checked_image.next())
        self.assertRaises(exception.GlanceException, checked_image.next)

    def test_too_few_chunks(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(resp, meta, 6,
                                                            ['AB', 'CD'],
                                                            None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('CD', checked_image.next())
        self.assertRaises(exception.GlanceException, checked_image.next)

    def test_too_much_data(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(resp, meta, 3,
                                                            ['AB', 'CD'],
                                                            None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('CD', checked_image.next())
        self.assertRaises(exception.GlanceException, checked_image.next)

    def test_too_little_data(self):
        resp = self._get_webob_response()
        meta = self._get_image_metadata()
        checked_image = glance.api.common.size_checked_iter(resp, meta, 6,
                                                            ['AB', 'CD', 'E'],
                                                            None)

        self.assertEqual('AB', checked_image.next())
        self.assertEqual('CD', checked_image.next())
        self.assertEqual('E', checked_image.next())
        self.assertRaises(exception.GlanceException, checked_image.next)


class TestMalformedRequest(test_utils.BaseTestCase):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestMalformedRequest, self).setUp()
        self.config(flavor='',
                    group='paste_deploy',
                    config_file='etc/glance-api-paste.ini')
        self.api = config.load_paste_app('glance-api')

    def test_redirect_incomplete_url(self):
        """Test Glance redirects /v# to /v#/ with correct Location header"""
        req = webob.Request.blank('/v1.1')
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPFound.code, res.status_int)
        self.assertEqual('http://localhost/v1/', res.location)
