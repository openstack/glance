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
import stubout
import unittest

import webob

from glance import client
from glance.common import exception
from tests import stubs


class TestBadClients(unittest.TestCase):
    
    """Test exceptions raised for bad clients"""

    def test_bad_protocol(self):
        """Test unsupported protocol raised"""
        c = client.RegistryClient(address="hdsa://127.012..1./")
        self.assertRaises(client.UnsupportedProtocolError,
                          c.get_image,
                          1)

    def test_bad_address(self):
        """Test unsupported protocol raised"""
        c = client.RegistryClient(address="http://127.999.1.1/")
        self.assertRaises(client.ClientConnectionError,
                          c.get_image,
                          1)


class TestRegistryClient(unittest.TestCase):

    """
    Test proper actions made for both valid and invalid requests
    against a Registry service
    """

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_registry_and_store_server(self.stubs)
        self.client = client.RegistryClient()

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get_image_index(self):
        """Test correct set of public image returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2'}
        images = self.client.get_images()
        self.assertEquals(len(images), 1)

        for k,v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_image_details(self):
        """Tests that the detailed info about public images returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available',
                   'files': [
                        {"location": "file://tmp/glance-tests/acct/2.gz.0",
                         "size": 6},
                        {"location": "file://tmp/glance-tests/acct/2.gz.1",
                         "size": 7}],
                   'properties': []}

        expected = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available',
                   'files': [
                        {"location": "file://tmp/glance-tests/acct/2.gz.0",
                         "size": 6},
                        {"location": "file://tmp/glance-tests/acct/2.gz.1",
                         "size": 7}],
                   'properties': {}}

        images = self.client.get_images_detailed()
        self.assertEquals(len(images), 1)

        for k,v in expected.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_image(self):
        """Tests that the detailed info about an image returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available',
                   'files': [
                        {"location": "file://tmp/glance-tests/acct/2.gz.0",
                         "size": 6},
                        {"location": "file://tmp/glance-tests/acct/2.gz.1",
                         "size": 7}],
                   'properties': []}

        expected = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available',
                   'files': [
                        {"location": "file://tmp/glance-tests/acct/2.gz.0",
                         "size": 6},
                        {"location": "file://tmp/glance-tests/acct/2.gz.1",
                         "size": 7}],
                   'properties': {}}

        data = self.client.get_image(2)

        for k,v in expected.iteritems():
            self.assertEquals(v, data[k])

    def test_get_image_non_existing(self):
        """Tests that NotFound is raised when getting a non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          42)

    def test_add_image_basic(self):
        """Tests that we can add image metadata and returns the new id"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel'
                  }
        
        new_id = self.client.add_image(fixture)

        # Test ID auto-assigned properly
        self.assertEquals(3, new_id)

        # Test all other attributes set
        data = self.client.get_image(3)

        for k,v in fixture.iteritems():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('available', data['status'])

    def test_add_image_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'properties': [{'key':'disco',
                                   'value': 'baby'}]
                  }
        expected = {'name': 'fake public image',
                    'is_public': True,
                    'image_type': 'kernel',
                    'properties': {'disco': 'baby'}
                  }
        
        new_id = self.client.add_image(fixture)

        # Test ID auto-assigned properly
        self.assertEquals(3, new_id)

        # Test all other attributes set
        data = self.client.get_image(3)

        for k,v in expected.iteritems():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('available', data['status'])

    def test_add_image_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = {'id': 2,
                   'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'bad status'
                  }

        self.assertRaises(exception.Duplicate,
                          self.client.add_image,
                          fixture)

    def test_add_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'bad status'
                  }

        self.assertRaises(client.BadInputError,
                          self.client.add_image,
                          fixture)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'image_type': 'ramdisk'
                  }

        self.assertTrue(self.client.update_image(2, fixture))

        # Test all other attributes set
        data = self.client.get_image(2)

        for k,v in fixture.iteritems():
            self.assertEquals(v, data[k])

    def test_update_image_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'bad status'
                  }

        self.assertRaises(exception.NotFound,
                          self.client.update_image,
                          3,
                          fixture)

    def test_delete_image(self):
        """Tests that image metadata is deleted properly"""

        # Grab the original number of images
        orig_num_images = len(self.client.get_images())

        # Delete image #2
        self.assertTrue(self.client.delete_image(2))

        # Verify one less image
        new_num_images = len(self.client.get_images())

        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests cannot delete non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.delete_image,
                          3)


class TestGlanceClient(unittest.TestCase):

    """
    Test proper actions made for both valid and invalid requests
    against a Glance service
    """

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_filesystem_backend(self.stubs)
        self.client = client.GlanceClient()
        self.pclient = client.RegistryClient()

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def test_get_image(self):
        """Test a simple file backend retrieval works as expected"""
        expected = 'chunk0chunk42'
        image = self.client.get_image(2)

        self.assertEquals(expected, image)

    def test_get_image_not_existing(self):
        """Test retrieval of a non-existing image returns a 404"""

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          3)

    def test_delete_image(self):
        """Tests that image data is deleted properly"""

        expected = 'chunk0chunk42'
        image = self.client.get_image(2)

        self.assertEquals(expected, image)

        # Delete image #2
        self.assertTrue(self.client.delete_image(2))

        # Delete the image metadata for #2 from Registry
        self.assertTrue(self.pclient.delete_image(2))

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          2)

    def test_delete_image_not_existing(self):
        """Test deletion of a non-existing image returns a 404"""

        self.assertRaises(exception.NotFound,
                          self.client.delete_image,
                          3)
