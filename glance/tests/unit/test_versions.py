# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import json
import unittest

import stubout
import webob

from glance import client
from glance.common import exception
from glance.api import versions
from glance.tests import stubs


class VersionsTest(unittest.TestCase):

    """
    Test the version information returned from
    the API service
    """

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get_version_list(self):
        req = webob.Request.blank('/')
        req.accept = "application/json"
        options = {'bind_host': '0.0.0.0',
                   'bind_port': 9292}
        res = req.get_response(versions.Controller(options))
        self.assertEqual(res.status_int, 300)
        self.assertEqual(res.content_type, "application/json")
        results = json.loads(res.body)["versions"]
        expected = [
            {
                "id": "v1.1",
                "status": "CURRENT",
                "links": [
                    {
                        "rel": "self",
                        "href": "http://0.0.0.0:9292/v1/"}]},
            {
                "id": "v1.0",
                "status": "SUPPORTED",
                "links": [
                    {
                        "rel": "self",
                        "href": "http://0.0.0.0:9292/v1/"}]}]
        self.assertEqual(results, expected)

    def test_client_handles_versions(self):
        api_client = client.Client("0.0.0.0", doc_root="")

        self.assertRaises(exception.MultipleChoices,
                          api_client.get_images)
