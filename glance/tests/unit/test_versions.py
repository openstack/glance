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

from oslo_serialization import jsonutils
import webob

from glance.api.middleware import version_negotiation
from glance.api import versions
from glance.common.wsgi import Request as WsgiRequest
from glance.tests.unit import base


class VersionsTest(base.IsolatedUnitTest):

    """Test the version information returned from the API service."""

    def test_get_version_list(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9292/')
        req.accept = 'application/json'
        self.config(bind_host='127.0.0.1', bind_port=9292)
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {
                'id': 'v2.3',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v2/'}],
            },
            {
                'id': 'v2.2',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v2/'}],
            },
            {
                'id': 'v2.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v2/'}],
            },
            {
                'id': 'v2.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v2/'}],
            },
            {
                'id': 'v1.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v1/'}],
            },
            {
                'id': 'v1.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9292/v1/'}],
            },
        ]
        self.assertEqual(expected, results)

    def test_get_version_list_public_endpoint(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9292/')
        req.accept = 'application/json'
        self.config(bind_host='127.0.0.1', bind_port=9292,
                    public_endpoint='https://example.com:9292')
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {
                'id': 'v2.3',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v2/'}],
            },
            {
                'id': 'v2.2',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v2/'}],
            },
            {
                'id': 'v2.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v2/'}],
            },
            {
                'id': 'v2.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v2/'}],
            },
            {
                'id': 'v1.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v1/'}],
            },
            {
                'id': 'v1.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://example.com:9292/v1/'}],
            },
        ]
        self.assertEqual(expected, results)

    def test_get_version_list_secure_proxy_ssl_header(self):
        self.config(secure_proxy_ssl_header='HTTP_X_FORWARDED_PROTO')
        environ = webob.request.environ_from_url('http://localhost:9292')
        req = WsgiRequest(environ)
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {
                'id': 'v2.3',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.2',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v2/'}],
            },
            {
                'id': 'v1.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v1/'}],
            },
            {
                'id': 'v1.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'http://localhost:9292/v1/'}],
            },
        ]
        self.assertEqual(expected, results)

    def test_get_version_list_secure_proxy_ssl_header_https(self):
        self.config(secure_proxy_ssl_header='HTTP_X_FORWARDED_PROTO')
        environ = webob.request.environ_from_url('http://localhost:9292')
        environ['HTTP_X_FORWARDED_PROTO'] = "https"
        req = WsgiRequest(environ)
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {
                'id': 'v2.3',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.2',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v2/'}],
            },
            {
                'id': 'v2.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v2/'}],
            },
            {
                'id': 'v1.1',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v1/'}],
            },
            {
                'id': 'v1.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self',
                           'href': 'https://localhost:9292/v1/'}],
            },
        ]
        self.assertEqual(expected, results)


class VersionNegotiationTest(base.IsolatedUnitTest):

    def setUp(self):
        super(VersionNegotiationTest, self).setUp()
        self.middleware = version_negotiation.VersionNegotiationFilter(None)

    def test_request_url_v1(self):
        request = webob.Request.blank('/v1/images')
        self.middleware.process_request(request)
        self.assertEqual('/v1/images', request.path_info)

    def test_request_url_v1_0(self):
        request = webob.Request.blank('/v1.0/images')
        self.middleware.process_request(request)
        self.assertEqual('/v1/images', request.path_info)

    def test_request_url_v1_1(self):
        request = webob.Request.blank('/v1.1/images')
        self.middleware.process_request(request)
        self.assertEqual('/v1/images', request.path_info)

    def test_request_accept_v1(self):
        request = webob.Request.blank('/images')
        request.headers = {'accept': 'application/vnd.openstack.images-v1'}
        self.middleware.process_request(request)
        self.assertEqual('/v1/images', request.path_info)

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

    def test_request_url_v2_4_unsupported(self):
        request = webob.Request.blank('/v2.4/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)

    def test_request_url_v4_unsupported(self):
        request = webob.Request.blank('/v4/images')
        resp = self.middleware.process_request(request)
        self.assertIsInstance(resp, versions.Controller)
