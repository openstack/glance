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

import http.client as http_client

from oslo_serialization import jsonutils
import webob

from glance.tests import functional
from glance.tests.unit import test_versions as tv


class TestApiVersions(functional.SynchronousAPIBase):
    def setUp(self, bypass_headers=True):
        super(TestApiVersions, self).setUp(bypass_headers=bypass_headers)
        # Use version negotiation pipeline for unauthenticated endpoints
        self.start_server(enable_version_negotiation=True)

    def test_version_configurations(self):
        """Test that versioning is handled properly through all channels"""
        # Use a dummy URL for href comparison since we're testing
        # in-process
        url = 'http://localhost'
        # SynchronousAPIBase sets up multiple backends, so we need
        # both flags
        expected_versions_list = tv.get_versions_list(url,
                                                      enabled_backends=True,
                                                      enabled_cache=True)

        # Verify version choices returned.
        # Access /versions directly instead of / to avoid version
        # negotiation issues
        response = self.api_get('/versions')
        self.assertEqual(http_client.OK, response.status_code)
        content = response.json

        # Compare versions by ID and status, ignoring href URLs which
        # may differ
        actual_versions = content['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        # Create a dict for easier lookup by version ID
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id,
                          "Version %s not in expected list" % actual['id'])
            expected = expected_by_id[actual['id']]
            self.assertEqual(actual['status'], expected['status'])

    def test_v2_api_configuration(self):
        # Use a dummy URL for href comparison since we're testing
        # in-process
        url = 'http://localhost'
        # SynchronousAPIBase sets up multiple backends, so we need
        # both flags
        expected_versions_list = tv.get_versions_list(url,
                                                      enabled_backends=True,
                                                      enabled_cache=True)

        # Verify version choices returned.
        # Access /versions directly instead of / to avoid version
        # negotiation issues
        response = self.api_get('/versions')
        self.assertEqual(http_client.OK, response.status_code)
        content = response.json

        # Compare versions by ID and status, ignoring href URLs which
        # may differ
        actual_versions = content['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        # Create a dict for easier lookup by version ID
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id,
                          "Version %s not in expected list" % actual['id'])
            expected = expected_by_id[actual['id']]
            self.assertEqual(actual['status'], expected['status'])


class TestApiVersionsMultistore(functional.SynchronousAPIBase):
    def setUp(self, bypass_headers=True):
        super(TestApiVersionsMultistore, self).setUp(
            bypass_headers=bypass_headers)
        # Use version negotiation pipeline for unauthenticated endpoints
        self.start_server(enable_version_negotiation=True)

    def test_version_configurations(self):
        """Test that versioning is handled properly through all channels"""
        # Use a dummy URL for href comparison since we're testing in-process
        url = 'http://localhost'
        expected_versions_list = tv.get_versions_list(url,
                                                      enabled_backends=True,
                                                      enabled_cache=True)

        # Verify version choices returned.
        # Access /versions directly instead of / to avoid version
        # negotiation issues
        response = self.api_get('/versions')
        self.assertEqual(http_client.OK, response.status_code)
        content = response.json

        # Compare versions by ID and status, ignoring href URLs which
        # may differ
        actual_versions = content['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        for actual, expected in zip(actual_versions, expected_versions_list):
            self.assertEqual(actual['id'], expected['id'])
            self.assertEqual(actual['status'], expected['status'])

    def test_v2_api_configuration(self):
        # Use a dummy URL for href comparison since we're testing
        # in-process
        url = 'http://localhost'
        expected_versions_list = tv.get_versions_list(url,
                                                      enabled_backends=True,
                                                      enabled_cache=True)

        # Verify version choices returned.
        # Access /versions directly instead of / to avoid version
        # negotiation issues
        response = self.api_get('/versions')
        self.assertEqual(http_client.OK, response.status_code)
        content = response.json

        # Compare versions by ID and status, ignoring href URLs which
        # may differ
        actual_versions = content['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        for actual, expected in zip(actual_versions, expected_versions_list):
            self.assertEqual(actual['id'], expected['id'])
            self.assertEqual(actual['status'], expected['status'])


class TestApiPaths(functional.SynchronousAPIBase):
    def setUp(self, bypass_headers=True):
        super(TestApiPaths, self).setUp(bypass_headers=bypass_headers)
        # Use version negotiation pipeline for unauthenticated endpoints
        self.start_server(enable_version_negotiation=True)

        # Use a dummy URL for href comparison since we're testing
        # in-process
        url = 'http://localhost'
        # SynchronousAPIBase sets up multiple backends, so we need
        # both flags
        self.versions = {'versions': tv.get_versions_list(
            url, enabled_backends=True, enabled_cache=True)}
        images = {'images': []}
        self.images_json = jsonutils.dumps(images)

    def test_get_root_path(self):
        """Assert GET / with `no Accept:` header.
        Verify version choices returned.
        Bug lp:803260  no Accept header causes a 500 in glance-api
        """
        # Create a request to test with
        req = webob.Request.blank('/')
        response = self._call_api(req)
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status_code)
        content = response.json
        # Compare versions by ID and status, ignoring href URLs
        actual_versions = content['versions']
        expected_versions_list = self.versions['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id)
            self.assertEqual(
                actual['status'], expected_by_id[actual['id']]['status'])

    def test_get_root_path_with_unknown_header(self):
        """Assert GET / with Accept: unknown header
        Verify version choices returned. Verify message in API log about
        unknown accept header.
        """
        headers = {'Accept': 'unknown'}
        req = webob.Request.blank('/', headers=headers)
        response = self._call_api(req)
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status_code)
        content = response.json
        # Compare versions by ID and status, ignoring href URLs
        actual_versions = content['versions']
        expected_versions_list = self.versions['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id)
            self.assertEqual(
                actual['status'], expected_by_id[actual['id']]['status'])

    def test_get_va1_images_path(self):
        """Assert GET /va.1/images with no Accept: header
        Verify version choices returned
        """
        req = webob.Request.blank('/va.1/images')
        response = self._call_api(req)
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status_code)
        content = response.json
        # Compare versions by ID and status, ignoring href URLs
        actual_versions = content['versions']
        expected_versions_list = self.versions['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id)
            self.assertEqual(
                actual['status'], expected_by_id[actual['id']]['status'])

    def test_get_versions_path(self):
        """Assert GET /versions with no Accept: header
        Verify version choices returned
        """
        response = self.api_get('/versions')
        self.assertEqual(http_client.OK, response.status_code)
        content = response.json
        # Compare versions by ID and status, ignoring href URLs
        actual_versions = content['versions']
        expected_versions_list = self.versions['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id)
            self.assertEqual(
                actual['status'], expected_by_id[actual['id']]['status'])

    def test_get_versions_choices(self):
        """Verify version choices returned"""
        req = webob.Request.blank('/v10')
        response = self._call_api(req)
        self.assertEqual(http_client.MULTIPLE_CHOICES, response.status_code)
        content = response.json
        # Compare versions by ID and status, ignoring href URLs
        actual_versions = content['versions']
        expected_versions_list = self.versions['versions']
        self.assertEqual(len(actual_versions), len(expected_versions_list))
        expected_by_id = {v['id']: v for v in expected_versions_list}
        for actual in actual_versions:
            self.assertIn(actual['id'], expected_by_id)
            self.assertEqual(
                actual['status'], expected_by_id[actual['id']]['status'])
