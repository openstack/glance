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

import glance.api.middleware.cache
from glance.common import exception
from glance import context
import glance.db.sqlalchemy.api as db
import glance.registry.client.v1.api as registry
from glance.tests.unit import base
from glance.tests.unit import utils as unit_test_utils


class TestCacheMiddlewareURLMatching(testtools.TestCase):
    def test_v1_no_match_detail(self):
        req = webob.Request.blank('/v1/images/detail')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_v1_no_match_detail_with_query_params(self):
        req = webob.Request.blank('/v1/images/detail?limit=10')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_v1_match_id_with_query_param(self):
        req = webob.Request.blank('/v1/images/asdf?ping=pong')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(out, ('v1', 'GET', 'asdf'))

    def test_v2_match_id(self):
        req = webob.Request.blank('/v2/images/asdf/file')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(out, ('v2', 'GET', 'asdf'))

    def test_v2_no_match_bad_path(self):
        req = webob.Request.blank('/v2/images/asdf')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_no_match_unknown_version(self):
        req = webob.Request.blank('/v3/images/asdf')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)


class TestCacheMiddlewareRequestStashCacheInfo(testtools.TestCase):
    def setUp(self):
        super(TestCacheMiddlewareRequestStashCacheInfo, self).setUp()
        self.request = webob.Request.blank('')
        self.middleware = glance.api.middleware.cache.CacheFilter

    def test_stash_cache_request_info(self):
        self.middleware._stash_request_info(self.request, 'asdf', 'GET')
        self.assertEqual(self.request.environ['api.cache.image_id'], 'asdf')
        self.assertEqual(self.request.environ['api.cache.method'], 'GET')

    def test_fetch_cache_request_info(self):
        self.request.environ['api.cache.image_id'] = 'asdf'
        self.request.environ['api.cache.method'] = 'GET'
        (image_id, method) = self.middleware._fetch_request_info(self.request)
        self.assertEqual('asdf', image_id)
        self.assertEqual('GET', method)

    def test_fetch_cache_request_info_unset(self):
        out = self.middleware._fetch_request_info(self.request)
        self.assertIsNone(out)


class ChecksumTestCacheFilter(glance.api.middleware.cache.CacheFilter):
    def __init__(self):
        class DummyCache(object):
            def get_caching_iter(self, image_id, image_checksum, app_iter):
                self.image_checksum = image_checksum

        self.cache = DummyCache()
        self.policy = unit_test_utils.FakePolicyEnforcer()


class TestCacheMiddlewareChecksumVerification(base.IsolatedUnitTest):
    def setUp(self):
        super(TestCacheMiddlewareChecksumVerification, self).setUp()
        self.context = context.RequestContext(is_admin=True)
        self.request = webob.Request.blank('')
        self.request.context = self.context

    def test_checksum_v1_header(self):
        cache_filter = ChecksumTestCacheFilter()
        headers = {"x-image-meta-checksum": "1234567890"}
        resp = webob.Response(request=self.request, headers=headers)
        cache_filter._process_GET_response(resp, None)

        self.assertEqual("1234567890", cache_filter.cache.image_checksum)

    def test_checksum_v2_header(self):
        cache_filter = ChecksumTestCacheFilter()
        headers = {
            "x-image-meta-checksum": "1234567890",
            "Content-MD5": "abcdefghi"
        }
        resp = webob.Response(request=self.request, headers=headers)
        cache_filter._process_GET_response(resp, None)

        self.assertEqual("abcdefghi", cache_filter.cache.image_checksum)

    def test_checksum_missing_header(self):
        cache_filter = ChecksumTestCacheFilter()
        resp = webob.Response(request=self.request)
        cache_filter._process_GET_response(resp, None)

        self.assertIsNone(cache_filter.cache.image_checksum)


class FakeImageSerializer(object):
    def show(self, response, raw_response):
        return True


class ProcessRequestTestCacheFilter(glance.api.middleware.cache.CacheFilter):
    def __init__(self):
        self.serializer = FakeImageSerializer()

        class DummyCache(object):
            def __init__(self):
                self.deleted_images = []

            def is_cached(self, image_id):
                return True

            def get_caching_iter(self, image_id, image_checksum, app_iter):
                pass

            def delete_cached_image(self, image_id):
                self.deleted_images.append(image_id)

            def get_image_size(self, image_id):
                pass

        self.cache = DummyCache()
        self.policy = unit_test_utils.FakePolicyEnforcer()


class TestCacheMiddlewareProcessRequest(base.IsolatedUnitTest):
    def test_v1_deleted_image_fetch(self):
        """
        Test for determining that when an admin tries to download a deleted
        image it returns 404 Not Found error.
        """
        def fake_get_image_metadata(context, image_id):
            return {'deleted': True}

        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(registry, 'get_image_metadata',
                       fake_get_image_metadata)
        self.assertRaises(exception.NotFound, cache_filter._process_v1_request,
                          request, image_id, dummy_img_iterator)

    def test_process_v1_request_for_deleted_but_cached_image(self):
        """
        Test for determining image is deleted from cache when it is not found
        in Glance Registry.
        """
        def fake_process_v1_request(request, image_id, image_iterator):
            raise exception.NotFound()

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()

        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(cache_filter, '_process_v1_request',
                       fake_process_v1_request)
        cache_filter.process_request(request)
        self.assertTrue(image_id in cache_filter.cache.deleted_images)

    def test_v1_process_request_image_fetch(self):

        def fake_get_image_metadata(context, image_id):
            return {'is_public': True, 'deleted': False, 'size': '20'}

        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(registry, 'get_image_metadata',
                       fake_get_image_metadata)
        actual = cache_filter._process_v1_request(
            request, image_id, dummy_img_iterator)
        self.assertTrue(actual)

    def test_v1_remove_location_image_fetch(self):

        class CheckNoLocationDataSerializer(object):
            def show(self, response, raw_response):
                return 'location_data' in raw_response['image_meta']

        def fake_get_image_metadata(context, image_id):
            return {'location_data': {'url': "file:///some/path",
                                      'metadata': {}},
                    'is_public': True, 'deleted': False, 'size': '20'}

        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter.serializer = CheckNoLocationDataSerializer()
        self.stubs.Set(registry, 'get_image_metadata',
                       fake_get_image_metadata)
        actual = cache_filter._process_v1_request(
            request, image_id, dummy_img_iterator)
        self.assertFalse(actual)

    def test_verify_metadata_deleted_image(self):
        """
        Test verify_metadata raises exception.NotFound for a deleted image
        """
        image_meta = {'is_public': True, 'deleted': True}
        cache_filter = ProcessRequestTestCacheFilter()
        self.assertRaises(exception.NotFound,
                          cache_filter._verify_metadata, image_meta)

    def test_verify_metadata_zero_size(self):
        """
        Test verify_metadata updates metadata with cached image size for images
        with 0 size
        """
        image_size = 1

        def fake_get_image_size(image_id):
            return image_size

        image_id = 'test1'
        image_meta = {'size': 0, 'deleted': False, 'id': image_id}
        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(cache_filter.cache, 'get_image_size',
                       fake_get_image_size)
        cache_filter._verify_metadata(image_meta)
        self.assertTrue(image_meta['size'] == image_size)

    def test_v2_process_request_response_headers(self):
        def dummy_img_iterator():
            for i in range(3):
                yield i

        def fake_image_get(self, image_id):
            return {
                'id': 'test1',
                'name': 'fake_image',
                'status': 'active',
                'created_at': '',
                'min_disk': '10G',
                'min_ram': '1024M',
                'protected': False,
                'locations': '',
                'checksum': 'c352f4e7121c6eae958bc1570324f17e',
                'owner': '',
                'disk_format': 'raw',
                'container_format': 'bare',
                'size': '123456789',
                'virtual_size': '123456789',
                'is_public': 'public',
                'deleted': False,
                'updated_at': '',
                'properties': {},
            }

        def fake_image_tag_get_all(context, image_id, session=None):
            return None

        image_id = 'test1'
        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext()

        self.stubs.Set(db, 'image_get', fake_image_get)
        self.stubs.Set(db, 'image_tag_get_all', fake_image_tag_get_all)

        cache_filter = ProcessRequestTestCacheFilter()
        response = cache_filter._process_v2_request(
            request, image_id, dummy_img_iterator)
        self.assertEqual(response.headers['Content-Type'],
                         'application/octet-stream')
        self.assertEqual(response.headers['Content-MD5'],
                         'c352f4e7121c6eae958bc1570324f17e')
        self.assertEqual(response.headers['Content-Length'],
                         '123456789')

    def test_process_request_without_download_image_policy(self):
        """
        Test for cache middleware skip processing when request
        context has not 'download_image' role.
        """
        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()

        cache_filter = ProcessRequestTestCacheFilter()

        rules = {'download_image': '!'}
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        self.assertIsNone(cache_filter.process_request(request))


class TestCacheMiddlewareProcessResponse(base.IsolatedUnitTest):
    def test_process_v1_DELETE_response(self):
        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(request=request, headers=headers)
        actual = cache_filter._process_DELETE_response(resp, image_id)
        self.assertEqual(actual, resp)

    def test_get_status_code(self):
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(headers=headers)
        cache_filter = ProcessRequestTestCacheFilter()
        actual = cache_filter.get_status_code(resp)
        self.assertEqual(200, actual)

    def test_process_response(self):
        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET')

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(request=request, headers=headers)
        actual = cache_filter.process_response(resp)
        self.assertEqual(actual, resp)

    def test_process_response_without_download_image_policy(self):
        """
        Test for cache middleware raise webob.exc.HTTPForbidden directly
        when request context has not 'download_image' role.
        """
        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET')

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        rules = {'download_image': '!'}
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_response, resp)
        self.assertEqual([''], resp.app_iter)
