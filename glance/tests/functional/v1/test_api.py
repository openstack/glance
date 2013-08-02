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

"""Functional test case that utilizes httplib2 against the API server"""

import hashlib
import json

import httplib2

from glance.tests import functional
from glance.tests.utils import skip_if_disabled, minimal_headers

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestApi(functional.FunctionalTest):

    """Functional tests using httplib2 against the API server"""

    @skip_if_disabled
    def test_get_head_simple_post(self):
        """
        We test the following sequential series of actions:

        0. GET /images
        - Verify no public images
        1. GET /images/detail
        - Verify no public images
        2. POST /images with public image named Image1
        and no custom properties
        - Verify 201 returned
        3. HEAD image
        - Verify HTTP headers have correct information we just added
        4. GET image
        - Verify all information on image we just added is correct
        5. GET /images
        - Verify the image we just added is returned
        6. GET /images/detail
        - Verify the image we just added is returned
        7. PUT image with custom properties of "distro" and "arch"
        - Verify 200 returned
        8. GET image
        - Verify updated information about image was stored
        9. PUT image
        - Remove a previously existing property.
        10. PUT image
        - Add a previously deleted property.
        11. PUT image/members/member1
        - Add member1 to image
        12. PUT image/members/member2
        - Add member2 to image
        13. GET image/members
        - List image members
        14. DELETE image/members/member1
        - Delete image member1
        15. DELETE image
        - Delete image
        16. GET image/members
        -  List deleted image members
        17. PUT image/members/member2
        - Update existing member2 of deleted image
        18. PUT image/members/member3
        - Add member3 to deleted image
        19. DELETE image/members/member2
        - Delete member2 from deleted image
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. GET /images/detail
        # Verify no public images
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 2. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        image_id = data['image']['id']
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 3. HEAD image
        # Verify image found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 4. GET image
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image_headers = {
            'x-image-meta-id': image_id,
            'x-image-meta-name': 'Image1',
            'x-image-meta-is_public': 'True',
            'x-image-meta-status': 'active',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'x-image-meta-size': str(FIVE_KB)}

        expected_std_headers = {
            'content-length': str(FIVE_KB),
            'content-type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(hashlib.md5(content).hexdigest(),
                         hashlib.md5("*" * FIVE_KB).hexdigest())

        # 5. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(json.loads(content), expected_result)

        # 6. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": "ovf",
            "disk_format": "raw",
            "id": image_id,
            "is_public": True,
            "deleted_at": None,
            "properties": {},
            "size": 5120}

        image = json.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value, image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 7. PUT image with custom properties of "distro" and "arch"
        # Verify 200 returned
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['arch'], "x86_64")
        self.assertEqual(data['image']['properties']['distro'], "Ubuntu")

        # 8. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": "ovf",
            "disk_format": "raw",
            "id": image_id,
            "is_public": True,
            "deleted_at": None,
            "properties": {'distro': 'Ubuntu', 'arch': 'x86_64'},
            "size": 5120}

        image = json.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value, image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 9. PUT image and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)

        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 1)
        self.assertEqual(data['properties']['arch'], "x86_64")

        # 10. PUT image and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)

        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 2)
        self.assertEqual(data['properties']['arch'], "x86_64")
        self.assertEqual(data['properties']['distro'], "Ubuntu")
        self.assertNotEqual(data['created_at'], data['updated_at'])

        # 11. Add member to image
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(response.status, 204)

        # 12. Add member to image
        path = ("http://%s:%d/v1/images/%s/members/pattiewhite" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(response.status, 204)

        # 13. List image members
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['members']), 2)
        self.assertEqual(data['members'][0]['member_id'], 'pattieblack')
        self.assertEqual(data['members'][1]['member_id'], 'pattiewhite')

        # 14. Delete image member
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 204)

        # 15. DELETE image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # 16. Try to list members of deleted image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # 17. Try to update member of deleted image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]
        body = json.dumps(dict(memberships=fixture))
        response, content = http.request(path, 'PUT', body=body)
        self.assertEqual(response.status, 404)

        # 18. Try to add member to deleted image
        path = ("http://%s:%d/v1/images/%s/members/chickenpattie" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(response.status, 404)

        # 19. Try to delete member of deleted image
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 404)

        self.stop_servers()
