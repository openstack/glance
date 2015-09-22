# Copyright 2011 OpenStack Foundation
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

import httplib2
import sys

from oslo_serialization import jsonutils
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.tests import functional
from glance.tests.utils import minimal_headers
from glance.tests.utils import skip_if_disabled

FIVE_KB = 5 * units.Ki
FIVE_GB = 5 * units.Gi


class TestApi(functional.FunctionalTest):

    """Functional tests using httplib2 against the API server"""

    def _check_image_create(self, headers, status=201,
                            image_data="*" * FIVE_KB):
        # performs image_create request, checks the response and returns
        # content
        http = httplib2.Http()
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = http.request(
            path, 'POST', headers=headers, body=image_data)
        self.assertEqual(status, response.status)
        return content

    def test_checksum_32_chars_at_image_create(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())
        headers = minimal_headers('Image1')
        image_data = "*" * FIVE_KB

        # checksum can be no longer that 32 characters (String(32))
        headers['X-Image-Meta-Checksum'] = 'x' * 42
        content = self._check_image_create(headers, 400)
        self.assertIn("Invalid checksum", content)
        # test positive case as well
        headers['X-Image-Meta-Checksum'] = hashlib.md5(image_data).hexdigest()
        self._check_image_create(headers)

    def test_param_int_too_large_at_create(self):
        # currently 2 params min_disk/min_ram can cause DBError on save
        self.cleanup()
        self.start_servers(**self.__dict__.copy())
        # Integer field can't be greater than max 8-byte signed integer
        for param in ['min_disk', 'min_ram']:
            headers = minimal_headers('Image1')
            # check that long numbers result in 400
            headers['X-Image-Meta-%s' % param] = str(sys.maxint + 1)
            content = self._check_image_create(headers, 400)
            self.assertIn("'%s' value out of range" % param, content)
            # check that integers over 4 byte result in 400
            headers['X-Image-Meta-%s' % param] = str(2 ** 31)
            content = self._check_image_create(headers, 400)
            self.assertIn("'%s' value out of range" % param, content)
            # verify positive case as well
            headers['X-Image-Meta-%s' % param] = str((2 ** 31) - 1)
            self._check_image_create(headers)

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
        8. PUT image with too many custom properties
        - Verify 413 returned
        9. GET image
        - Verify updated information about image was stored
        10. PUT image
        - Remove a previously existing property.
        11. PUT image
        - Add a previously deleted property.
        12. PUT image/members/member1
        - Add member1 to image
        13. PUT image/members/member2
        - Add member2 to image
        14. GET image/members
        - List image members
        15. DELETE image/members/member1
        - Delete image member1
        16. PUT image/members
        - Attempt to replace members with an overlimit amount
        17. PUT image/members/member11
        - Attempt to add a member while at limit
        18. POST /images with another public image named Image2
        - attribute and three custom properties, "distro", "arch" & "foo"
        - Verify a 200 OK is returned
        19. HEAD image2
        - Verify image2 found now
        20. GET /images
        - Verify 2 public images
        21. GET /images with filter on user-defined property "distro".
        - Verify both images are returned
        22. GET /images with filter on user-defined property 'distro' but
        - with non-existent value. Verify no images are returned
        23. GET /images with filter on non-existent user-defined property
        - "boo". Verify no images are returned
        24. GET /images with filter 'arch=i386'
        - Verify only image2 is returned
        25. GET /images with filter 'arch=x86_64'
        - Verify only image1 is returned
        26. GET /images with filter 'foo=bar'
        - Verify only image2 is returned
        27. DELETE image1
        - Delete image
        28. GET image/members
        -  List deleted image members
        29. PUT image/members/member2
        - Update existing member2 of deleted image
        30. PUT image/members/member3
        - Add member3 to deleted image
        31. DELETE image/members/member2
        - Delete member2 from deleted image
        32. DELETE image2
        - Delete image
        33. GET /images
        - Verify no images are listed
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. GET /images/detail
        # Verify no public images
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 2. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        # 3. HEAD image
        # Verify image found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])

        # 4. GET image
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

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
            self.assertEqual(expected_value, response[expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(expected_value, response[expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        self.assertEqual("*" * FIVE_KB, content)
        self.assertEqual(hashlib.md5("*" * FIVE_KB).hexdigest(),
                         hashlib.md5(content).hexdigest())

        # 5. GET /images
        # Verify one public image
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, jsonutils.loads(content))

        # 6. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

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

        image = jsonutils.loads(content)

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
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual("x86_64", data['image']['properties']['arch'])
        self.assertEqual("Ubuntu", data['image']['properties']['distro'])

        # 8. PUT image with too many custom properties
        # Verify 413 returned
        headers = {}
        for i in range(11):  # configured limit is 10
            headers['X-Image-Meta-Property-foo%d' % i] = 'bar'
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(413, response.status)

        # 9. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

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

        image = jsonutils.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value, image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 10. PUT image and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)

        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images'][0]
        self.assertEqual(1, len(data['properties']))
        self.assertEqual("x86_64", data['properties']['arch'])

        # 11. PUT image and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)

        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images'][0]
        self.assertEqual(2, len(data['properties']))
        self.assertEqual("x86_64", data['properties']['arch'])
        self.assertEqual("Ubuntu", data['properties']['distro'])
        self.assertNotEqual(data['created_at'], data['updated_at'])

        # 12. Add member to image
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(204, response.status)

        # 13. Add member to image
        path = ("http://%s:%d/v1/images/%s/members/pattiewhite" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(204, response.status)

        # 14. List image members
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['members']))
        self.assertEqual('pattieblack', data['members'][0]['member_id'])
        self.assertEqual('pattiewhite', data['members'][1]['member_id'])

        # 15. Delete image member
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(204, response.status)

        # 16. Attempt to replace members with an overlimit amount
        # Adding 11 image members should fail since configured limit is 10
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        memberships = []
        for i in range(11):
            member_id = "foo%d" % i
            memberships.append(dict(member_id=member_id))
        http = httplib2.Http()
        body = jsonutils.dumps(dict(memberships=memberships))
        response, content = http.request(path, 'PUT', body=body)
        self.assertEqual(413, response.status)

        # 17. Attempt to add a member while at limit
        # Adding an 11th member should fail since configured limit is 10
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        memberships = []
        for i in range(10):
            member_id = "foo%d" % i
            memberships.append(dict(member_id=member_id))
        http = httplib2.Http()
        body = jsonutils.dumps(dict(memberships=memberships))
        response, content = http.request(path, 'PUT', body=body)
        self.assertEqual(204, response.status)

        path = ("http://%s:%d/v1/images/%s/members/fail_me" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(413, response.status)

        # 18. POST /images with another public image named Image2
        # attribute and three custom properties, "distro", "arch" & "foo".
        # Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image2')
        headers['X-Image-Meta-Property-Distro'] = 'Ubuntu'
        headers['X-Image-Meta-Property-Arch'] = 'i386'
        headers['X-Image-Meta-Property-foo'] = 'bar'
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image2_id = data['image']['id']
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image2", data['image']['name'])
        self.assertTrue(data['image']['is_public'])
        self.assertEqual('Ubuntu', data['image']['properties']['distro'])
        self.assertEqual('i386', data['image']['properties']['arch'])
        self.assertEqual('bar', data['image']['properties']['foo'])

        # 19. HEAD image2
        # Verify image2 found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image2_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image2", response['x-image-meta-name'])

        # 20. GET /images
        # Verify 2 public images
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image_id, images[1]['id'])

        # 21. GET /images with filter on user-defined property 'distro'.
        # Verify both images are returned
        path = "http://%s:%d/v1/images?property-distro=Ubuntu" % (
            "127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image_id, images[1]['id'])

        # 22. GET /images with filter on user-defined property 'distro' but
        # with non-existent value. Verify no images are returned
        path = "http://%s:%d/v1/images?property-distro=fedora" % (
            "127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(0, len(images))

        # 23. GET /images with filter on non-existent user-defined property
        # 'boo'. Verify no images are returned
        path = "http://%s:%d/v1/images?property-boo=bar" % ("127.0.0.1",
                                                            self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(0, len(images))

        # 24. GET /images with filter 'arch=i386'
        # Verify only image2 is returned
        path = "http://%s:%d/v1/images?property-arch=i386" % ("127.0.0.1",
                                                              self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # 25. GET /images with filter 'arch=x86_64'
        # Verify only image1 is returned
        path = "http://%s:%d/v1/images?property-arch=x86_64" % ("127.0.0.1",
                                                                self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # 26. GET /images with filter 'foo=bar'
        # Verify only image2 is returned
        path = "http://%s:%d/v1/images?property-foo=bar" % ("127.0.0.1",
                                                            self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # 27. DELETE image1
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # 28. Try to list members of deleted image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(404, response.status)

        # 29. Try to update member of deleted image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]
        body = jsonutils.dumps(dict(memberships=fixture))
        response, content = http.request(path, 'PUT', body=body)
        self.assertEqual(404, response.status)

        # 30. Try to add member to deleted image
        path = ("http://%s:%d/v1/images/%s/members/chickenpattie" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT')
        self.assertEqual(404, response.status)

        # 31. Try to delete member of deleted image
        path = ("http://%s:%d/v1/images/%s/members/pattieblack" %
                ("127.0.0.1", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(404, response.status)

        # 32. DELETE image2
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image2_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # 33. GET /images
        # Verify no images are listed
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(0, len(images))

        # 34. HEAD /images/detail
        path = "http://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(405, response.status)
        self.assertEqual('GET', response.get('allow'))

        self.stop_servers()

    def test_download_non_exists_image_raises_http_forbidden(self):
        """
        We test the following sequential series of actions:

        0. POST /images with public image named Image1
        and no custom properties
        - Verify 201 returned
        1. HEAD image
        - Verify HTTP headers have correct information we just added
        2. GET image
        - Verify all information on image we just added is correct
        3. DELETE image1
        - Delete the newly added image
        4. GET image
        - Verify that 403 HTTPForbidden exception is raised prior to
          404 HTTPNotFound
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        # 1. HEAD image
        # Verify image found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])

        # 2. GET /images
        # Verify one public image
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, jsonutils.loads(content))

        # 3. DELETE image1
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # 4. GET image
        # Verify that 403 HTTPForbidden exception is raised prior to
        # 404 HTTPNotFound
        rules = {"download_image": '!'}
        self.set_policy_rules(rules)
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(403, response.status)

        self.stop_servers()

    def test_download_non_exists_image_raises_http_not_found(self):
        """
        We test the following sequential series of actions:

        0. POST /images with public image named Image1
        and no custom properties
        - Verify 201 returned
        1. HEAD image
        - Verify HTTP headers have correct information we just added
        2. GET image
        - Verify all information on image we just added is correct
        3. DELETE image1
        - Delete the newly added image
        4. GET image
        - Verify that 404 HTTPNotFound exception is raised
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        # 1. HEAD image
        # Verify image found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])

        # 2. GET /images
        # Verify one public image
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, jsonutils.loads(content))

        # 3. DELETE image1
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # 4. GET image
        # Verify that 404 HTTPNotFound exception is raised
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(404, response.status)

        self.stop_servers()

    def test_status_cannot_be_manipulated_directly(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())
        headers = minimal_headers('Image1')

        # Create a 'queued' image
        http = httplib2.Http()
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Disk-Format': 'raw',
                   'X-Image-Meta-Container-Format': 'bare'}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = http.request(path, 'POST', headers=headers,
                                         body=None)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('queued', image['status'])

        # Ensure status of 'queued' image can't be changed
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image['id'])
        http = httplib2.Http()
        headers = {'X-Image-Meta-Status': 'active'}
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(403, response.status)
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('queued', response['x-image-meta-status'])

        # We allow 'setting' to the same status
        http = httplib2.Http()
        headers = {'X-Image-Meta-Status': 'queued'}
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('queued', response['x-image-meta-status'])

        # Make image active
        http = httplib2.Http()
        headers = {'Content-Type': 'application/octet-stream'}
        response, content = http.request(path, 'PUT', headers=headers,
                                         body='data')
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])

        # Ensure status of 'active' image can't be changed
        http = httplib2.Http()
        headers = {'X-Image-Meta-Status': 'queued'}
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(403, response.status)
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('active', response['x-image-meta-status'])

        # We allow 'setting' to the same status
        http = httplib2.Http()
        headers = {'X-Image-Meta-Status': 'active'}
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('active', response['x-image-meta-status'])

        # Create a 'queued' image, ensure 'status' header is ignored
        http = httplib2.Http()
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Status': 'active'}
        response, content = http.request(path, 'POST', headers=headers,
                                         body=None)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('queued', image['status'])

        # Create an 'active' image, ensure 'status' header is ignored
        http = httplib2.Http()
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Disk-Format': 'raw',
                   'X-Image-Meta-Status': 'queued',
                   'X-Image-Meta-Container-Format': 'bare'}
        response, content = http.request(path, 'POST', headers=headers,
                                         body='data')
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        self.stop_servers()
