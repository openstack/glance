# Copyright 2012 OpenStack Foundation.
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

import http.client as http

import ddt
import webob

from oslo_serialization import jsonutils

from glance.api.middleware import version_negotiation
from glance.api import versions
from glance.tests.unit import base


# make this public so it doesn't need to be repeated for the
# functional tests
def get_versions_list(url, enabled_backends=False,
                      enabled_cache=False):
    image_versions = [
        {
            'id': 'v2.15',
            'status': 'CURRENT',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.9',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.7',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.6',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.5',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.4',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.3',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.2',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.1',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
        {
            'id': 'v2.0',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        },
    ]
    if enabled_backends:
        image_versions = [
            {
                'id': 'v2.15',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.13',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.12',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.11',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.10',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.9',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            },
            {
                'id': 'v2.8',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': '%s/v2/' % url}],
            }
        ] + image_versions[2:]

    if enabled_cache:
        image_versions[0]['status'] = 'SUPPORTED'
        image_versions.insert(1, {
            'id': 'v2.14',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        })
        image_versions.insert(0, {
            'id': 'v2.16',
            'status': 'CURRENT',
            'links': [{'rel': 'self',
                       'href': '%s/v2/' % url}],
        })

    return image_versions


class VersionsTest(base.IsolatedUnitTest):

    """Test the version information returned from the API service."""

    def test_get_version_list(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9292/')
        req.accept = 'application/json'
        self.config(bind_host='127.0.0.1', bind_port=9292)
        res = versions.Controller().index(req)
        self.assertEqual(http.MULTIPLE_CHOICES, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('http://127.0.0.1:9292')
        self.assertEqual(expected, results)

        self.config(enabled_backends='slow:one,fast:two')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('http://127.0.0.1:9292',
                                     enabled_backends=True)
        self.assertEqual(expected, results)

        self.config(image_cache_dir='/tmp/cache')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('http://127.0.0.1:9292',
                                     enabled_backends=True,
                                     enabled_cache=True)
        self.assertEqual(expected, results)

    def test_get_version_list_public_endpoint(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9292/')
        req.accept = 'application/json'
        self.config(bind_host='127.0.0.1', bind_port=9292,
                    public_endpoint='https://example.com:9292')
        res = versions.Controller().index(req)
        self.assertEqual(http.MULTIPLE_CHOICES, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('https://example.com:9292')
        self.assertEqual(expected, results)

        self.config(enabled_backends='slow:one,fast:two')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('https://example.com:9292',
                                     enabled_backends=True)
        self.assertEqual(expected, results)

        self.config(image_cache_dir='/tmp/cache')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list('https://example.com:9292',
                                     enabled_backends=True,
                                     enabled_cache=True)
        self.assertEqual(expected, results)

    def test_get_version_list_for_external_app(self):
        url = 'http://customhost:9292/app/api'
        req = webob.Request.blank('/', base_url=url)
        self.config(bind_host='127.0.0.1', bind_port=9292)
        res = versions.Controller().index(req)
        self.assertEqual(http.MULTIPLE_CHOICES, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list(url)
        self.assertEqual(expected, results)

        self.config(enabled_backends='slow:one,fast:two')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list(url, enabled_backends=True)
        self.assertEqual(expected, results)

        self.config(image_cache_dir='/tmp/cache')
        res = versions.Controller().index(req)
        results = jsonutils.loads(res.body)['versions']
        expected = get_versions_list(url,
                                     enabled_backends=True,
                                     enabled_cache=True)


class VersionNegotiationTest(base.IsolatedUnitTest):

    def setUp(self):
        super(VersionNegotiationTest, self).setUp()
        self.middleware = version_negotiation.VersionNegotiationFilter(None)

    def test_request_url_v2(self):
        request = webob.Request.blank('/v2/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_0(self):
        request = webob.Request.blank('/v2.0/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_1(self):
        request = webob.Request.blank('/v2.1/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_2(self):
        request = webob.Request.blank('/v2.2/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_3(self):
        request = webob.Request.blank('/v2.3/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_4(self):
        request = webob.Request.blank('/v2.4/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_5(self):
        request = webob.Request.blank('/v2.5/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_6(self):
        request = webob.Request.blank('/v2.6/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_7(self):
        request = webob.Request.blank('/v2.7/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_9(self):
        request = webob.Request.blank('/v2.9/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_15(self):
        request = webob.Request.blank('/v2.15/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    # note: these need separate unsupported/supported tests to reset the
    # the memoized allowed_versions in the VersionNegotiationFilter instance
    def test_request_url_v2_8_default_unsupported(self):
        request = webob.Request.blank('/v2.8/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_8_enabled_supported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.8/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_10_default_unsupported(self):
        request = webob.Request.blank('/v2.10/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_10_enabled_supported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.10/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_11_default_unsupported(self):
        request = webob.Request.blank('/v2.11/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_11_enabled_supported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.11/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_12_default_unsupported(self):
        request = webob.Request.blank('/v2.12/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_12_enabled_supported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.12/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_13_default_unsupported(self):
        request = webob.Request.blank('/v2.13/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_13_enabled_supported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.13/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_14_default_unsupported(self):
        request = webob.Request.blank('/v2.14/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_14_enabled_supported(self):
        self.config(image_cache_dir='/tmp/cache')
        request = webob.Request.blank('/v2.14/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    def test_request_url_v2_16_default_unsupported(self):
        request = webob.Request.blank('/v2.16/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_16_enabled_supported(self):
        self.config(image_cache_dir='/tmp/cache')
        request = webob.Request.blank('/v2.16/images')
        self.middleware.process_request(request)
        self.assertEqual('/v2/images', request.path_info)

    # version 2.17 does not exist
    def test_request_url_v2_17_default_unsupported(self):
        request = webob.Request.blank('/v2.17/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v2_17_enabled_unsupported(self):
        self.config(enabled_backends='slow:one,fast:two')
        request = webob.Request.blank('/v2.17/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)


@ddt.ddt
class VersionsAndNegotiationTest(VersionNegotiationTest, VersionsTest):

    """
    Test that versions mentioned in the versions response are correctly
    negotiated.
    """

    def _get_list_of_version_ids(self, status):
        request = webob.Request.blank('/')
        request.accept = 'application/json'
        response = versions.Controller().index(request)
        v_list = jsonutils.loads(response.body)['versions']
        return [v['id'] for v in v_list if v['status'] == status]

    def _assert_version_is_negotiated(self, version_id):
        request = webob.Request.blank("/%s/images" % version_id)
        self.middleware.process_request(request)
        major = version_id.split('.', 1)[0]
        expected = "/%s/images" % major
        self.assertEqual(expected, request.path_info)

    # the content of the version list depends on two configuration
    # options:
    #   - CONF.enabled_backends
    #   - CONF.image_cache_dir
    # So we need to check a bunch of combinations
    cache = '/var/cache'
    multistore = 'slow:one,fast:two'

    combos = ((None, None),
              (None, multistore),
              (cache, None),
              (cache, multistore))

    @ddt.data(*combos)
    @ddt.unpack
    def test_current_is_negotiated(self, cache, multistore):
        # NOTE(rosmaita): Bug 1609571: the versions response was correct, but
        # the negotiation had not been updated for the CURRENT version.
        self.config(enabled_backends=multistore)
        self.config(image_cache_dir=cache)
        to_check = self._get_list_of_version_ids('CURRENT')
        self.assertTrue(to_check)
        for version_id in to_check:
            self._assert_version_is_negotiated(version_id)

    @ddt.data(*combos)
    @ddt.unpack
    def test_supported_is_negotiated(self, cache, multistore):
        self.config(enabled_backends=multistore)
        self.config(image_cache_dir=cache)
        to_check = self._get_list_of_version_ids('SUPPORTED')
        for version_id in to_check:
            self._assert_version_is_negotiated(version_id)

    @ddt.data(*combos)
    @ddt.unpack
    def test_deprecated_is_negotiated(self, cache, multistore):
        self.config(enabled_backends=multistore)
        self.config(image_cache_dir=cache)
        to_check = self._get_list_of_version_ids('DEPRECATED')
        for version_id in to_check:
            self._assert_version_is_negotiated(version_id)

    @ddt.data(*combos)
    @ddt.unpack
    def test_experimental_is_negotiated(self, cache, multistore):
        self.config(enabled_backends=multistore)
        self.config(image_cache_dir=cache)
        to_check = self._get_list_of_version_ids('EXPERIMENTAL')
        for version_id in to_check:
            self._assert_version_is_negotiated(version_id)
