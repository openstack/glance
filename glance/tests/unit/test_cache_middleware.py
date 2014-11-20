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

from oslo_policy import policy
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import testtools
import webob

import glance.api.middleware.cache
import glance.api.policy
from glance.common import exception
from glance import context
import glance.registry.client.v1.api as registry
from glance.tests.unit import base
from glance.tests.unit import utils as unit_test_utils


class ImageStub(object):
    def __init__(self, image_id, extra_properties={}, visibility='private'):
        self.image_id = image_id
        self.visibility = visibility
        self.status = 'active'
        self.extra_properties = extra_properties
        self.checksum = 'c1234'
        self.size = 123456789


class TestCacheMiddlewareURLMatching(testtools.TestCase):
    def test_v1_no_match_detail(self):
        req = webob.Request.blank('/v1/images/detail')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertIsNone(out)

    def test_v1_no_match_detail_with_query_params(self):
        req = webob.Request.blank('/v1/images/detail?limit=10')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertIsNone(out)

    def test_v1_match_id_with_query_param(self):
        req = webob.Request.blank('/v1/images/asdf?ping=pong')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(('v1', 'GET', 'asdf'), out)

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
    def _enforcer_from_rules(self, unparsed_rules):
        rules = policy.Rules.from_dict(unparsed_rules)
        enforcer = glance.api.policy.Enforcer()
        enforcer.set_rules(rules, overwrite=True)
        return enforcer

    def test_v1_deleted_image_fetch(self):
        """
        Test for determining that when an admin tries to download a deleted
        image it returns 404 Not Found error.
        """
        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
        image_meta = {
            'id': image_id,
            'name': 'fake_image',
            'status': 'deleted',
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
            'deleted': True,
            'updated_at': '',
            'properties': {},
        }
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        self.assertRaises(exception.NotFound, cache_filter._process_v1_request,
                          request, image_id, dummy_img_iterator, image_meta)

    def test_process_v1_request_for_deleted_but_cached_image(self):
        """
        Test for determining image is deleted from cache when it is not found
        in Glance Registry.
        """
        def fake_process_v1_request(request, image_id, image_iterator,
                                    image_meta):
            raise exception.ImageNotFound()

        def fake_get_v1_image_metadata(request, image_id):
            return {'status': 'active', 'properties': {}}

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()

        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(cache_filter, '_get_v1_image_metadata',
                       fake_get_v1_image_metadata)
        self.stubs.Set(cache_filter, '_process_v1_request',
                       fake_process_v1_request)
        cache_filter.process_request(request)
        self.assertIn(image_id, cache_filter.cache.deleted_images)

    def test_v1_process_request_image_fetch(self):

        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
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
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        actual = cache_filter._process_v1_request(
            request, image_id, dummy_img_iterator, image_meta)
        self.assertTrue(actual)

    def test_v1_remove_location_image_fetch(self):

        class CheckNoLocationDataSerializer(object):
            def show(self, response, raw_response):
                return 'location_data' in raw_response['image_meta']

        def dummy_img_iterator():
            for i in range(3):
                yield i

        image_id = 'test1'
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
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter.serializer = CheckNoLocationDataSerializer()
        actual = cache_filter._process_v1_request(
            request, image_id, dummy_img_iterator, image_meta)
        self.assertFalse(actual)

    def test_verify_metadata_deleted_image(self):
        """
        Test verify_metadata raises exception.NotFound for a deleted image
        """
        image_meta = {'status': 'deleted', 'is_public': True, 'deleted': True}
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
        image_meta = {'size': 0, 'deleted': False, 'id': image_id,
                      'status': 'active'}
        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(cache_filter.cache, 'get_image_size',
                       fake_get_image_size)
        cache_filter._verify_metadata(image_meta)
        self.assertEqual(image_size, image_meta['size'])

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
        self.assertEqual(response.headers['Content-Type'],
                         'application/octet-stream')
        self.assertEqual(response.headers['Content-MD5'],
                         'c1234')
        self.assertEqual(response.headers['Content-Length'],
                         '123456789')

    def test_process_request_without_download_image_policy(self):
        """
        Test for cache middleware skip processing when request
        context has not 'download_image' role.
        """

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {'status': 'active', 'properties': {}}

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata

        enforcer = self._enforcer_from_rules({'download_image': '!'})
        cache_filter.policy = enforcer
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_request, request)

    def test_v1_process_request_download_restricted(self):
        """
        Test process_request for v1 api where _member_ role not able to
        download the image with custom property.
        """
        image_id = 'test1'

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {
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
                'x_test_key': 'test_1234'
            }

        enforcer = self._enforcer_from_rules({
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        })

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['_member_'])
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata
        cache_filter.policy = enforcer
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_request, request)

    def test_v1_process_request_download_permitted(self):
        """
        Test process_request for v1 api where member role able to
        download the image with custom property.
        """
        image_id = 'test1'

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {
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
                'x_test_key': 'test_1234'
            }

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['member'])
        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()
        actual = cache_filter.process_request(request)
        self.assertTrue(actual)

    def test_v1_process_request_image_meta_not_found(self):
        """
        Test process_request for v1 api where registry raises NotFound
        exception as image metadata not found.
        """
        image_id = 'test1'

        def fake_get_v1_image_metadata(*args, **kwargs):
            raise exception.NotFound()

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['_member_'])
        cache_filter = ProcessRequestTestCacheFilter()
        self.stubs.Set(registry, 'get_image_metadata',
                       fake_get_v1_image_metadata)

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()
        self.assertRaises(webob.exc.HTTPNotFound,
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
    def test_process_v1_DELETE_response(self):
        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        cache_filter = ProcessRequestTestCacheFilter()
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(request=request, headers=headers)
        actual = cache_filter._process_DELETE_response(resp, image_id)
        self.assertEqual(resp, actual)

    def test_get_status_code(self):
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(headers=headers)
        cache_filter = ProcessRequestTestCacheFilter()
        actual = cache_filter.get_status_code(resp)
        self.assertEqual(200, actual)

    def test_process_response(self):
        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v1')

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {'properties': {}}

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata
        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        headers = {"x-image-meta-deleted": True}
        resp = webob.Response(request=request, headers=headers)
        actual = cache_filter.process_response(resp)
        self.assertEqual(resp, actual)

    def test_process_response_without_download_image_policy(self):
        """
        Test for cache middleware raise webob.exc.HTTPForbidden directly
        when request context has not 'download_image' role.
        """
        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v1')

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {'properties': {}}

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata
        rules = {'download_image': '!'}
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        image_id = 'test1'
        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext()
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_response, resp)
        self.assertEqual([b''], resp.app_iter)

    def test_v1_process_response_download_restricted(self):
        """
        Test process_response for v1 api where _member_ role not able to
        download the image with custom property.
        """
        image_id = 'test1'

        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v1')

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {
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
                'x_test_key': 'test_1234'
            }

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata
        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['_member_'])
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPForbidden,
                          cache_filter.process_response, resp)

    def test_v1_process_response_download_permitted(self):
        """
        Test process_response for v1 api where member role able to
        download the image with custom property.
        """
        image_id = 'test1'

        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v1')

        def fake_get_v1_image_metadata(*args, **kwargs):
            return {
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
                'x_test_key': 'test_1234'
            }

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info
        cache_filter._get_v1_image_metadata = fake_get_v1_image_metadata
        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['member'])
        resp = webob.Response(request=request)
        actual = cache_filter.process_response(resp)
        self.assertEqual(actual, resp)

    def test_v1_process_response_image_meta_not_found(self):
        """
        Test process_response for v1 api where registry raises NotFound
        exception as image metadata not found.
        """
        image_id = 'test1'

        def fake_fetch_request_info(*args, **kwargs):
            return ('test1', 'GET', 'v1')

        def fake_get_v1_image_metadata(*args, **kwargs):
            raise exception.NotFound()

        cache_filter = ProcessRequestTestCacheFilter()
        cache_filter._fetch_request_info = fake_fetch_request_info

        self.stubs.Set(registry, 'get_image_metadata',
                       fake_get_v1_image_metadata)

        rules = {
            "restricted":
            "not ('test_1234':%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        cache_filter.policy = glance.api.policy.Enforcer()

        request = webob.Request.blank('/v1/images/%s' % image_id)
        request.context = context.RequestContext(roles=['_member_'])
        resp = webob.Response(request=request)
        self.assertRaises(webob.exc.HTTPNotFound,
                          cache_filter.process_response, resp)

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
        self.assertEqual(actual, resp)
