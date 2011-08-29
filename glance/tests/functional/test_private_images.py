# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

"""Functional test case that verifies private images functionality"""

import httplib2
import json

from glance.tests import functional
from glance.tests.functional import keystone_utils
from glance.tests.utils import execute, skip_if_disabled

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestPrivateImagesApi(keystone_utils.KeystoneTests):
    """
    Functional tests to verify private images functionality.
    """

    @skip_if_disabled
    def test_private_images_notadmin(self):
        """
        Test that we can upload an owned image; that we can manipulate
        its is_public setting; and that appropriate authorization
        checks are applied to other (non-admin) users.
        """
        self.cleanup()
        self.start_servers()

        # First, we need to push an image up
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Name': 'Image1'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['id'], 1)
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Next, make sure froggy can't list the image
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Shouldn't show up in the detail list, either
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Also check that froggy can't get the image metadata
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 404)

        # Froggy shouldn't be able to get the image, either.
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 404)

        # Froggy shouldn't be able to give themselves permission too
        # easily...
        headers = {'X-Auth-Token': keystone_utils.froggy_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # Froggy shouldn't be able to give themselves ownership,
        # either
        headers = {'X-Auth-Token': keystone_utils.froggy_token,
                   'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # Froggy can't delete it, either
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE', headers=headers)
        self.assertEqual(response.status, 404)

        # Pattieblack should be able to see the image in lists
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # And in the detail list
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")
        self.assertEqual(data['images'][0]['is_public'], False)
        self.assertEqual(data['images'][0]['owner'], 'pattieblack')

        # Pattieblack should be able to get the image metadata
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # And of course the image itself
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # Pattieblack should be able to manipulate is_public
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Pattieblack can't give the image away, however
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Now that the image is public, froggy can see it
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Should also be in details
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")
        self.assertEqual(data['images'][0]['is_public'], True)
        self.assertEqual(data['images'][0]['owner'], 'pattieblack')

        # Froggy can get the image metadata now...
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "True")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # And of course the image itself
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "True")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # Froggy still can't change is-public
        headers = {'X-Auth-Token': keystone_utils.froggy_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # Or give themselves ownership
        headers = {'X-Auth-Token': keystone_utils.froggy_token,
                   'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # Froggy can't delete it, either
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE', headers=headers)
        self.assertEqual(response.status, 404)

        # But pattieblack can
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE', headers=headers)
        self.assertEqual(response.status, 200)

        self.stop_servers()

    @skip_if_disabled
    def test_private_images_admin(self):
        """
        Test that admin users can manipulate is_public and owner
        settings on an image.
        """
        self.cleanup()
        self.start_servers()

        # Need to push an image up
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Name': 'Image1'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['id'], 1)
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Make sure admin does not see image by default
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Shouldn't show up in the detail list, either
        headers = {'X-Auth-Token': keystone_utils.froggy_token}
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Admin should see the image if we're looking for private
        # images specifically
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images?is_public=false" % ("0.0.0.0",
                                                           self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Also in the detail list...
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = ("http://%s:%d/v1/images/detail?is_public=false" %
                ("0.0.0.0", self.api_port))
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")
        self.assertEqual(data['images'][0]['is_public'], False)
        self.assertEqual(data['images'][0]['owner'], 'pattieblack')

        # Admin should be able to get the image metadata
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # And of course the image itself
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # Admin should be able to manipulate is_public
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Admin should also be able to change the ownership of the
        # image
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], 'froggy')

        # Even setting it to no owner
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Owner': ''}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], None)

        # Make sure pattieblack can see it, since it's unowned but
        # public
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # But if we change it back to private...
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Is-Public': 'False'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], None)

        # Now pattieblack can't see it in the list...
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Or in the details list...
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # But pattieblack should be able to access the image metadata
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], '')

        # And of course the image itself
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], '')

        # Pattieblack can't change is-public, though
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # Or give themselves ownership
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Owner': 'pattieblack'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 404)

        # They can't delete it, either
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE', headers=headers)
        self.assertEqual(response.status, 404)

        self.stop_servers()

    @skip_if_disabled
    def test_private_images_anon(self):
        """
        Test that anonymous users can access images but not manipulate
        them.
        """
        self.cleanup()
        self.start_servers()

        # Make sure anonymous user can't push up an image
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 403)

        # Now push up an image for anonymous user to try to access
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Auth-Token': keystone_utils.pattieblack_token,
                   'X-Image-Meta-Name': 'Image1'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['id'], 1)
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], 'pattieblack')

        # Make sure anonymous user can't list the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Shouldn't show up in the detail list, either
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Also check that anonymous can't get the image metadata
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 404)

        # Nor the image, either.
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # Anonymous shouldn't be able to make the image public...
        headers = {'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 403)

        # Nor change ownership...
        headers = {'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 403)

        # Nor even delete it...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 403)

        # Now, let's use our admin credentials and change the
        # ownership to None...
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Owner': ''}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], None)

        # Anonymous user still can't list image...
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Nor see it in details...
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # But they should be able to access the metadata...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], '')

        # And even the image itself...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], '')

        # Anonymous still shouldn't be able to make the image
        # public...
        headers = {'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 403)

        # Nor change ownership...
        headers = {'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 403)

        # Nor even delete it...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 403)

        # Now make the image public...
        headers = {'X-Auth-Token': keystone_utils.admin_token,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)
        self.assertEqual(data['image']['owner'], None)

        # Now the user should see it in the list...
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Especially in the details...
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")
        self.assertEqual(data['images'][0]['is_public'], True)
        self.assertEqual(data['images'][0]['owner'], None)

        # But still can't change ownership...
        headers = {'X-Image-Meta-Owner': 'froggy'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 403)

        # Or delete it...
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 403)

        self.stop_servers()


class TestPrivateImagesCli(keystone_utils.KeystoneTests):
    """
    Functional tests to verify private images functionality through
    bin/glance.
    """

    @skip_if_disabled
    def test_glance_cli(self):
        """
        Test that we can upload an owned image; that we can manipulate
        its is_public setting; and that appropriate authorization
        checks are applied to other (non-admin) users.
        """
        self.cleanup()
        self.start_servers()

        # Add a non-public image
        cmd = ("echo testdata | bin/glance --port=%d --auth_token=%s add "
               "name=MyImage" %
               (self.api_port, keystone_utils.pattieblack_token))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Added new image with ID: 1', out.strip())

        # Verify the attributes of the image
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "MyImage")
        self.assertEqual(response['x-image-meta-is_public'], "False")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # Test that we can update is_public through the CLI
        cmd = ("bin/glance --port=%d --auth_token=%s update 1 is_public=True" %
               (self.api_port, keystone_utils.pattieblack_token))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

        # Verify the appropriate change was made
        headers = {'X-Auth-Token': keystone_utils.pattieblack_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "MyImage")
        self.assertEqual(response['x-image-meta-is_public'], "True")
        self.assertEqual(response['x-image-meta-owner'], "pattieblack")

        # Test that admin can change the owner
        cmd = ("bin/glance --port=%d --auth_token=%s update 1 owner=froggy" %
               (self.api_port, keystone_utils.admin_token))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

        # Verify the appropriate change was made
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "MyImage")
        self.assertEqual(response['x-image-meta-is_public'], "True")
        self.assertEqual(response['x-image-meta-owner'], "froggy")

        # Test that admin can remove the owner
        cmd = ("bin/glance --port=%d --auth_token=%s update 1 owner=" %
               (self.api_port, keystone_utils.admin_token))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

        # Verify the appropriate change was made
        headers = {'X-Auth-Token': keystone_utils.admin_token}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "MyImage")
        self.assertEqual(response['x-image-meta-is_public'], "True")
        self.assertEqual(response['x-image-meta-owner'], '')

        self.stop_servers()
