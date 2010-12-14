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

import unittest

import stubout
import webob

from glance import server
from glance.parallax import controllers as parallax_controllers
from tests import stubs


class TestImageController(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_parallax_and_store_server(self.stubs)
        stubs.stub_out_parallax_db_image_api(self.stubs)
        stubs.stub_out_filesystem_backend(self.stubs)

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def test_index_raises_not_implemented(self):
        req = webob.Request.blank("/images")
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotImplemented.code)

    def test_show_image_unrecognized_registry_adapter(self):
        req = webob.Request.blank("/images/1?registry=unknown")
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_show_image_basic(self):
        req = webob.Request.blank("/images/2")
        res = req.get_response(server.API())
        self.assertEqual('chunk0chunk42', res.body)

    def test_show_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_image(self):
        req = webob.Request.blank("/images/2")
        req.method = 'DELETE'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, 200)

        # Deletion from registry is not done from Teller on
        # purpose to allow the most flexibility for migrating
        # image file/chunk locations while keeping an image
        # identifier stable.

        req = webob.Request.blank("/images/2")
        req.method = 'DELETE'
        res = req.get_response(parallax_controllers.API())
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/2")
        req.method = 'GET'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code, res.body)

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        req.method = 'DELETE'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
