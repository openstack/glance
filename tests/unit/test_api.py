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

import json
import unittest

import stubout
import webob

from glance import server
from glance.registry import controllers
from tests import stubs


class TestImageController(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_filesystem_backend(self.stubs)

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def test_get_root(self):
        """Tests that the root registry API returns "index",
        which is a list of public images
        
        """
        fixture = {'id': 2,
                   'name': 'fake image #2'}
        req = webob.Request.blank('/')
        res = req.get_response(controllers.API())
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k,v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_index(self):
        """Tests that the /images registry API returns list of
        public images
        
        """
        fixture = {'id': 2,
                   'name': 'fake image #2'}
        req = webob.Request.blank('/images')
        res = req.get_response(controllers.API())
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k,v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_details(self):
        """Tests that the /images/detail registry API returns
        a mapping containing a list of detailed image information
        
        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available'
                  }
        req = webob.Request.blank('/images/detail')
        res = req.get_response(controllers.API())
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k,v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_create_image(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel'
                  }

        req = webob.Request.blank('/images')
            
        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(controllers.API())

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k,v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

        # Test ID auto-assigned properly
        self.assertEquals(3, res_dict['image']['id'])

        # Test status was updated properly
        self.assertEquals('available', res_dict['image']['status'])

    def test_create_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'bad status'
                  }

        req = webob.Request.blank('/images')
            
        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        # TODO(jaypipes): Port Nova's Fault infrastructure
        # over to Glance to support exception catching into
        # standard HTTP errors.
        res = req.get_response(controllers.API())
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'image_type': 'ramdisk'
                  }

        req = webob.Request.blank('/images/2')
            
        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(controllers.API())

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k,v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

    def test_update_image_not_existing(self):
        """Tests proper exception is raised if attempt to update non-existing
        image"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'bad status'
                  }

        req = webob.Request.blank('/images/3')
            
        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        # TODO(jaypipes): Port Nova's Fault infrastructure
        # over to Glance to support exception catching into
        # standard HTTP errors.
        res = req.get_response(controllers.API())
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_delete_image(self):
        """Tests that the /images DELETE registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/images')
        res = req.get_response(controllers.API())
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        orig_num_images = len(res_dict['images'])

        # Delete image #2
        req = webob.Request.blank('/images/2')
            
        req.method = 'DELETE'

        res = req.get_response(controllers.API())

        self.assertEquals(res.status_int, 200)

        # Verify one less image
        req = webob.Request.blank('/images')
        res = req.get_response(controllers.API())
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        new_num_images = len(res_dict['images'])
        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests proper exception is raised if attempt to delete non-existing
        image"""

        req = webob.Request.blank('/images/3')
            
        req.method = 'DELETE'

        # TODO(jaypipes): Port Nova's Fault infrastructure
        # over to Glance to support exception catching into
        # standard HTTP errors.
        res = req.get_response(controllers.API())
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_image_meta(self):
        expected_headers = {'x-image-meta-id': 2,
                            'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/2")
        req.method = 'HEAD'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

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

        req = webob.Request.blank("/images/2")
        req.method = 'GET'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code, res.body)

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        req.method = 'DELETE'
        res = req.get_response(server.API())
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
