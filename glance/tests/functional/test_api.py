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

"""Version-independent api tests"""


import httplib2
from oslo_serialization import jsonutils
from six.moves import http_client

from glance.tests import functional


def _generate_v2_versions(url):
    version_list = []
    version_list.extend([
        {
            'id': 'v2.9',
            'status': 'CURRENT',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.7',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.6',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.5',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.4',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.3',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.2',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.1',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        },
        {
            'id': 'v2.0',
            'status': 'SUPPORTED',
            'links': [{'rel': 'self', 'href': url % '2'}],
        }
    ])
    v2_versions = {'versions': version_list}
    return v2_versions


def _generate_all_versions(url):
    v2 = _generate_v2_versions(url)
    all_versions = {'versions': v2['versions']}
    return all_versions


class TestApiVersions(functional.FunctionalTest):

    def test_version_configurations(self):
        """Test that versioning is handled properly through all channels"""
        self.start_servers(**self.__dict__.copy())

        url = 'http://127.0.0.1:%d/v%%s/' % self.api_port
        versions = _generate_all_versions(url)

        # Verify version choices returned.
        path = 'http://%s:%d' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(versions, content)

    def test_v2_api_configuration(self):
        self.api_server.enable_v2_api = True
        self.start_servers(**self.__dict__.copy())

        url = 'http://127.0.0.1:%d/v%%s/' % self.api_port
        versions = _generate_v2_versions(url)

        # Verify version choices returned.
        path = 'http://%s:%d' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(versions, content)


class TestApiPaths(functional.FunctionalTest):
    def setUp(self):
        super(TestApiPaths, self).setUp()
        self.start_servers(**self.__dict__.copy())

        url = 'http://127.0.0.1:%d/v%%s/' % self.api_port
        self.versions = _generate_all_versions(url)
        images = {'images': []}
        self.images_json = jsonutils.dumps(images)

    def test_get_root_path(self):
        """Assert GET / with `no Accept:` header.
        Verify version choices returned.
        Bug lp:803260  no Accept header causes a 500 in glance-api
        """
        path = 'http://%s:%d' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(self.versions, content)

    def test_get_root_path_with_unknown_header(self):
        """Assert GET / with Accept: unknown header
        Verify version choices returned. Verify message in API log about
        unknown accept header.
        """
        path = 'http://%s:%d/' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'unknown'}
        response, content_json = http.request(path, 'GET', headers=headers)
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(self.versions, content)

    def test_get_va1_images_path(self):
        """Assert GET /va.1/images with no Accept: header
        Verify version choices returned
        """
        path = 'http://%s:%d/va.1/images' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(self.versions, content)

    def test_get_versions_path(self):
        """Assert GET /versions with no Accept: header
        Verify version choices returned
        """
        path = 'http://%s:%d/versions' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.OK, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(self.versions, content)

    def test_get_versions_choices(self):
        """Verify version choices returned"""
        path = 'http://%s:%d/v10' % ('127.0.0.1', self.api_port)
        http = httplib2.Http()
        response, content_json = http.request(path, 'GET')
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status)
        content = jsonutils.loads(content_json.decode())
        self.assertEqual(self.versions, content)
