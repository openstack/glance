# Copyright 2012 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the 'License'); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Version-independent api tests"""


import json

import httplib2

from glance.tests import functional


class TestRootApi(functional.FunctionalTest):

    def test_version_variations(self):
        """Test that versioning is handled properly through all channels"""

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        url = 'http://0.0.0.0:%d/v%%s/' % self.api_port
        versions = {'versions': [
            {
                'id': 'v2',
                'status': 'EXPERIMENTAL',
                'links': [{'rel': 'self', 'href': url % '2'}],
            },
            {
                'id': 'v1.1',
                'status': 'CURRENT',
                'links': [{'rel': 'self', 'href': url % '1'}],
            },
            {
                'id': 'v1.0',
                'status': 'SUPPORTED',
                'links': [{'rel': 'self', 'href': url % '1'}],
            },
        ]}
        versions_json = json.dumps(versions)
        images = {'images': []}
        images_json = json.dumps(images)

        # 0. GET / with no Accept: header
        # Verify version choices returned.
        # Bug lp:803260  no Accept header causes a 500 in glance-api
        path = 'http://%s:%d' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 1. GET /images with no Accept: header
        # Verify version choices returned.
        path = 'http://%s:%d/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 2. GET /v1/images with no Accept: header
        # Verify empty images list returned.
        path = 'http://%s:%d/v1/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 3. GET / with Accept: unknown header
        # Verify version choices returned. Verify message in API log about
        # unknown accept header.
        path = 'http://%s:%d/' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'unknown'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 4. GET / with an Accept: application/vnd.openstack.images-v1
        # Verify empty image list returned
        path = 'http://%s:%d/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 5. GET /images with a Accept: application/vnd.openstack.compute-v1
        # header. Verify version choices returned. Verify message in API log
        # about unknown accept header.
        path = 'http://%s:%d/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.compute-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 6. GET /v1.0/images with no Accept: header
        # Verify empty image list returned
        path = 'http://%s:%d/v1.0/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 7. GET /v1.a/images with no Accept: header
        # Verify empty image list returned
        path = 'http://%s:%d/v1.a/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 8. GET /va.1/images with no Accept: header
        # Verify version choices returned
        path = 'http://%s:%d/va.1/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 9. GET /versions with no Accept: header
        # Verify version choices returned
        path = 'http://%s:%d/versions' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 10. GET /versions with a Accept: application/vnd.openstack.images-v1
        # header. Verify version choices returned.
        path = 'http://%s:%d/versions' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 11. GET /v1/versions with no Accept: header
        # Verify 404 returned
        path = 'http://%s:%d/v1/versions' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # 12. GET /v2/versions with no Accept: header
        # Verify version choices returned
        path = 'http://%s:%d/v2/versions' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 13. GET /images with a Accept: application/vnd.openstack.compute-v2
        # header. Verify version choices returned. Verify message in API log
        # about unknown version in accept header.
        path = 'http://%s:%d/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v2'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 14. GET /v1.2/images with no Accept: header
        # Verify version choices returned
        path = 'http://%s:%d/v1.2/images' % ('0.0.0.0', self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown version in versioned URI'
                        in open(self.api_server.log_file).read())

        self.stop_servers()
