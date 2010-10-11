# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

import stubout
import unittest2 as unittest
from webob import Request, exc

from glance.teller import controllers
from tests import stubs


class TestImageController(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        self.image_controller = controllers.ImageController()

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_index_image_with_no_uri_should_raise_http_bad_request(self):
        # uri must be specified
        request = Request.blank("/image")
        response = self.image_controller.index(request)
        self.assertEqual(response.status_int, 400) # should be 422?

    def test_index_image_unrecognized_registry_adapter(self):
        # FIXME: need urllib.quote here?
        image_uri = "http://parallax-success/myacct/my-image"
        request = self._make_request(image_uri, "unknownregistry")
        response = self.image_controller.index(request)
        self.assertEqual(response.status_int, 400) # should be 422?

    def test_index_image_where_image_exists_should_return_the_data(self):
        # FIXME: need urllib.quote here?
        stubs.stub_out_parallax(self.stubs)
        stubs.stub_out_filesystem_backend(self.stubs)
        image_uri = "http://parallax/myacct/my-image"
        request = self._make_request(image_uri)
        response = self.image_controller.index(request)
        self.assertEqual("/chunk0/chunk1", response.body)

    def test_index_image_where_image_doesnt_exist_should_raise_not_found(self):
        image_uri = "http://bad-parallax-uri/myacct/does-not-exist"
        request = self._make_request(image_uri)
        self.assertRaises(exc.HTTPNotFound, self.image_controller.index,
                          request)

    def _make_request(self, image_uri, registry="parallax"):
        return Request.blank("/image?uri=%s&registry=%s" % (image_uri, registry))
