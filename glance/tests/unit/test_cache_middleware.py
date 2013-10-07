# Copyright 2012 OpenStack, LLC
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

import webob

import glance.api.middleware.cache
from glance import context
from glance.tests.unit import base
from glance.tests.unit import utils as unit_test_utils


class ChecksumTestCacheFilter(glance.api.middleware.cache.CacheFilter):
    def __init__(self):
        class DummyCache(object):
            def get_caching_iter(self, image_id, image_checksum,
                    app_iter):
                self.image_checksum = image_checksum

        self.cache = DummyCache()
        self.policy = unit_test_utils.FakePolicyEnforcer()


class TestCacheMiddleware(base.IsolatedUnitTest):
    def setUp(self):
        super(TestCacheMiddleware, self).setUp()
        self.context = context.RequestContext(is_admin=True)
        self.request = webob.Request.blank('')
        self.request.context = self.context

    def test_no_match_detail(self):
        req = webob.Request.blank('/v1/images/detail')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_no_match_detail_with_query_params(self):
        req = webob.Request.blank('/v1/images/detail?limit=10')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_match_id_with_query_param(self):
        req = webob.Request.blank('/v1/images/asdf?ping=pong')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(out, ('v1', 'GET', 'asdf'))

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

        self.assertEqual(None, cache_filter.cache.image_checksum)


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

        self.assertEqual(None, cache_filter.process_request(request))


class TestCacheMiddlewareProcessResponse(base.IsolatedUnitTest):
    def test_process_response_without_download_image_policy(self):
        """
        Test for cache middleware raise webob.exc.HTTPForbidden directly
        when request context has not 'download_image' role.
        """
        cache_filter = ProcessRequestTestCacheFilter()
        rules = {'download_image': '!'}
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        request.environ['api.cache.image_id'] = 'test1'
        request.environ['api.cache.method'] = 'GET'
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_response, resp)
        self.assertEqual([''], resp.app_iter)
