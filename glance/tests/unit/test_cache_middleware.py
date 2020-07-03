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
from unittest.mock import patch

from oslo_policy import policy
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import http_client as http
from six.moves import range
import testtools
import webob

import glance.api.middleware.cache
import glance.api.policy
from glance.common import exception
from glance import context
from glance.tests.unit import base
from glance.tests.unit import utils as unit_test_utils


class ImageStub(object):
    def __init__(self, image_id, extra_properties=None, visibility='private'):
        if extra_properties is None:
            extra_properties = {}
        self.image_id = image_id
        self.visibility = visibility
        self.status = 'active'
        self.extra_properties = extra_properties
        self.checksum = 'c1234'
        self.size = 123456789
        self.os_hash_algo = None


class TestCacheMiddlewareURLMatching(testtools.TestCase):
    def test_v2_match_id(self):
        req = webob.Request.blank('/v2/images/asdf/file')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(('v2', 'GET', 'asdf'), out)

    def test_v2_no_match_bad_path(self):
        req = webob.Request.blank('/v2/images/asdf')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertIsNone(out)

    def test_no_match_unknown_version(self):
        req = webob.Request.blank('/v3/images/asdf')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertIsNone(out)


class TestCacheMiddlewareRequestStashCacheInfo(testtools.TestCase):
    def setUp(self):
        super(TestCacheMiddlewareRequestStashCacheInfo, self).setUp()
        self.request = webob.Request.blank('')
        self.middleware = glance.api.middleware.cache.CacheFilter

    def test_stash_cache_request_info(self):
        self.middleware._stash_request_info(self.request, 'asdf', 'GET', 'v2')
        self.assertEqual('asdf', self.request.environ['api.cache.image_id'])
        self.assertEqual('GET', self.request.environ['api.cache.method'])
        self.assertEqual('v2', self.request.environ['api.cache.version'])

    def test_fetch_cache_request_info(self):
        self.request.environ['api.cache.image_id'] = 'asdf'
        self.request.environ['api.cache.method'] = 'GET'
        self.request.environ['api.cache.version'] = 'v2'
        (image_id, method, version) = self.middleware._fetch_request_info(
            self.request)
        self.assertEqual('asdf', image_id)
        self.assertEqual('GET', method)
        self.assertEqual('v2', version)

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
    def _enforcer_from_rules(self, unparsed_rules):
        rules = policy.Rules.from_dict(unparsed_rules)
        enforcer = glance.api.policy.Enforcer()
        enforcer.set_rules(rules, overwrite=True)
        return enforcer

    def test_verify_metadata_deleted_image(self):
        """
        Test verify_metadata raises exception.NotFound for a deleted image
        """
        image_meta = {'status': 'deleted', 'is_public': True, 'deleted': True}
        cache_filter = ProcessRequestTestCacheFilter()
        self.assertRaises(exception.NotFound,
                          cache_filter._verify_metadata, image_meta)

    def _test_verify_metadata_zero_size(self, image_meta):
        """
        Test verify_metadata updates metadata with cached image size for images
        with 0 size.

        :param image_meta: Image metadata, which may be either an ImageTarget
                           instance or a legacy v1 dict.
        """
        image_size = 1
        cache_filter = ProcessRequestTestCacheFilter()
        with patch.object(cache_filter.cache, 'get_image_size',
                          return_value=image_size):
            cache_filter._verify_metadata(image_meta)
        self.assertEqual(image_size, image_meta['size'])

    def test_verify_metadata_zero_size(self):
        """
        Test verify_metadata updates metadata with cached image size for images
        with 0 size
        """
        image_meta = {'size': 0, 'deleted': False, 'id': 'test1',
                      'status': 'active'}
        self._test_verify_metadata_zero_size(image_meta)

    def test_verify_metadata_is_image_target_instance_with_zero_size(self):
        """
        Test verify_metadata updates metadata which is ImageTarget instance
        """
        image = ImageStub('test1')
        image.size = 0
        image_meta = glance.api.policy.ImageTarget(image)
        self._test_verify_metadata_zero_size(image_meta)

    def test_v2_process_request_response_headers(self):
        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext()
        request.environ['api.cache.image'] = ImageStub(image_id)

        image_meta = {
            'id': image_id,
            'name': 'fake_image',
            'status': 'active',
            'created_at': '',
            'min_disk': '10G',
            'min_ram': '1024M',
            'protected': False,
            'locations': '',
            'checksum': 'c1234',
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

        cache_filter = ProcessRequestTestCacheFilter()
        response = cache_filter._process_v2_request(
            request, image_id, dummy_img_iterator, image_meta)
        self.assertEqual('application/octet-stream',
                         response.headers['Content-Type'])
        self.assertEqual('c1234', response.headers['Content-MD5'])
        self.assertEqual('123456789', response.headers['Content-Length'])

    def test_v2_process_request_without_checksum(self):
        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext()
        image = ImageStub(image_id)
        image.checksum = None
        request.environ['api.cache.image'] = image

        image_meta = {
            'id': image_id,
            'name': 'fake_image',
            'status': 'active',
            'size': '123456789',
        }

        cache_filter = ProcessRequestTestCacheFilter()
        response = cache_filter._process_v2_request(
            request, image_id, dummy_img_iterator, image_meta)
        self.assertNotIn('Content-MD5', response.headers.keys())

    def test_process_request_without_download_image_policy(self):
        """
        Test for cache middleware skip processing when request
        context has not 'download_image' role.
        """

        def fake_get_v2_image_metadata(*args, **kwargs):
            return {'status': 'active', 'properties': {}}

        image_id = 'test1'
        request = webob.Request.blank('/v2/images/%s/file' % image_id)
        request.context = context.RequestContext()

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v2_image_metadata = fake_get_v2_image_metadata

        enforcer = self._enforcer_from_rules({'download_image': '!'})
        cache_filter.policy = enforcer
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_request, request)

    def test_v2_process_request_download_restricted(self):
        """
        Test process_request for v2 api where _member_ role not able to
        download the image with custom property.
        """
        image_id = 'test1'
        extra_properties = {
            'x_test_key': 'test_1234'
        }

        def fake_get_v2_image_metadata(*args, **kwargs):
            image = ImageStub(image_id, extra_properties=extra_properties)
            request.environ['api.cache.image'] = image
            return glance.api.policy.ImageTarget(image)

        enforcer = self._enforcer_from_rules({
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        })

        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext(roles=['_member_'])
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v2_image_metadata = fake_get_v2_image_metadata

        cache_filter.policy = enforcer
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_request, request)

    def test_v2_process_request_download_permitted(self):
        """
        Test process_request for v2 api where member role able to
        download the image with custom property.
        """
        image_id = 'test1'
        extra_properties = {
            'x_test_key': 'test_1234'
        }

        def fake_get_v2_image_metadata(*args, **kwargs):
            image = ImageStub(image_id, extra_properties=extra_properties)
            request.environ['api.cache.image'] = image
            return glance.api.policy.ImageTarget(image)

        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext(roles=['member'])
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v2_image_metadata = fake_get_v2_image_metadata

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()
        actual = cache_filter.process_request(request)
        self.assertTrue(actual)


class TestCacheMiddlewareProcessResponse(base.IsolatedUnitTest):

    def test_get_status_code(self):
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(headers=headers)
        cache_filter = ProcessRequestTestCacheFilter()
        actual = cache_filter.get_status_code(resp)
        self.assertEqual(http.OK, actual)

    def test_v2_process_response_download_restricted(self):
        """
        Test process_response for v2 api where _member_ role not able to
        download the image with custom property.
        """
        image_id = 'test1'
        extra_properties = {
            'x_test_key': 'test_1234'
        }

        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v2')

        def fake_get_v2_image_metadata(*args, **kwargs):
            image = ImageStub(image_id, extra_properties=extra_properties)
            request.environ['api.cache.image'] = image
            return glance.api.policy.ImageTarget(image)

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v2_image_metadata = fake_get_v2_image_metadata

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext(roles=['_member_'])
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_response, resp)

    def test_v2_process_response_download_permitted(self):
        """
        Test process_response for v2 api where member role able to
        download the image with custom property.
        """
        image_id = 'test1'
        extra_properties = {
            'x_test_key': 'test_1234'
        }

        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v2')

        def fake_get_v2_image_metadata(*args, **kwargs):
            image = ImageStub(image_id, extra_properties=extra_properties)
            request.environ['api.cache.image'] = image
            return glance.api.policy.ImageTarget(image)

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v2_image_metadata = fake_get_v2_image_metadata

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        request = webob.Request.blank('/v2/images/test1/file')
        request.context = context.RequestContext(roles=['member'])
        resp = webob.Response(request=request)
        actual = cache_filter.process_response(resp)
        self.assertEqual(resp, actual)
