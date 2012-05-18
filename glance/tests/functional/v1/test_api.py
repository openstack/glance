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

import datetime
import hashlib
import json
import tempfile

import httplib2

from glance.common import utils
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
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. GET /images/detail
        # Verify no public images
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 2. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
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
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 4. GET image
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
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
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key, expected_value,
                               response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(response[expected_key], expected_value,
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               response[expected_key]))

        self.assertEqual(content, "*" * FIVE_KB)
        self.assertEqual(hashlib.md5(content).hexdigest(),
                         hashlib.md5("*" * FIVE_KB).hexdigest())

        # 5. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
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
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
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
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image['images'][0][expected_key]))

        # 7. PUT image with custom properties of "distro" and "arch"
        # Verify 200 returned
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['arch'], "x86_64")
        self.assertEqual(data['image']['properties']['distro'], "Ubuntu")

        # 8. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
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
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image['images'][0][expected_key]))

        # 9. PUT image and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)

        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 1)
        self.assertEqual(data['properties']['arch'], "x86_64")

        # 10. PUT image and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)

        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 2)
        self.assertEqual(data['properties']['arch'], "x86_64")
        self.assertEqual(data['properties']['distro'], "Ubuntu")

        # DELETE image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        self.stop_servers()

    @skip_if_disabled
    def test_queued_process_flow(self):
        """
        We test the process flow where a user registers an image
        with Glance but does not immediately upload an image file.
        Later, the user uploads an image file using a PUT operation.
        We track the changing of image status throughout this process.

        0. GET /images
        - Verify no public images
        1. POST /images with public image named Image1 with no location
           attribute and no image data.
        - Verify 201 returned
        2. GET /images
        - Verify one public image
        3. HEAD image
        - Verify image now in queued status
        4. PUT image with image data
        - Verify 200 returned
        5. HEAD images
        - Verify image now in active status
        6. GET /images
        - Verify one public image
        """

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with public image named Image1
        # with no location or image data
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'], None)
        self.assertEqual(data['image']['size'], 0)
        self.assertEqual(data['image']['container_format'], 'ovf')
        self.assertEqual(data['image']['disk_format'], 'raw')
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        image_id = data['image']['id']

        # 2. GET /images
        # Verify 1 public image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['images'][0]['id'], image_id)
        self.assertEqual(data['images'][0]['checksum'], None)
        self.assertEqual(data['images'][0]['size'], 0)
        self.assertEqual(data['images'][0]['container_format'], 'ovf')
        self.assertEqual(data['images'][0]['disk_format'], 'raw')
        self.assertEqual(data['images'][0]['name'], "Image1")

        # 3. HEAD /images
        # Verify status is in queued
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-status'], "queued")
        self.assertEqual(response['x-image-meta-size'], '0')
        self.assertEqual(response['x-image-meta-id'], image_id)

        # 4. PUT image with image data, verify 200 returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream'}
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                             image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 5. HEAD /images
        # Verify status is in active
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-status'], "active")

        # 6. GET /images
        # Verify 1 public image still...
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['images'][0]['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['images'][0]['id'], image_id)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['container_format'], 'ovf')
        self.assertEqual(data['images'][0]['disk_format'], 'raw')
        self.assertEqual(data['images'][0]['name'], "Image1")

        # DELETE image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        self.stop_servers()

    @skip_if_disabled
    def test_size_greater_2G_mysql(self):
        """
        A test against the actual datastore backend for the registry
        to ensure that the image size property is not truncated.

        :see https://bugs.launchpad.net/glance/+bug/739433
        """

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 1. POST /images with public image named Image1
        # attribute and a size of 5G. Use the HTTP engine with an
        # X-Image-Meta-Location attribute to make Glance forego
        # "adding" the image data.
        # Verify a 201 OK is returned
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Location': 'http://example.com/fakeimage',
                   'X-Image-Meta-Size': str(FIVE_GB),
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)

        # 2. HEAD /images
        # Verify image size is what was passed in, and not truncated
        path = response.get('location')
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-size'], str(FIVE_GB))
        self.assertEqual(response['x-image-meta-name'], 'Image1')
        self.assertEqual(response['x-image-meta-is_public'], 'True')

        self.stop_servers()

    @skip_if_disabled
    def test_traceback_not_consumed(self):
        """
        A test that errors coming from the POST API do not
        get consumed and print the actual error message, and
        not something like &lt;traceback object at 0x1918d40&gt;

        :see https://bugs.launchpad.net/glance/+bug/755912
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # POST /images with binary data, but not setting
        # Content-Type to application/octet-stream, verify a
        # 400 returned and that the error is readable.
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST',
                            body=test_data_file.name)
        self.assertEqual(response.status, 400)
        expected = "Content-Type must be application/octet-stream"
        self.assertTrue(expected in content,
                        "Could not find '%s' in '%s'" % (expected, content))

        self.stop_servers()

    @skip_if_disabled
    def test_filtered_images(self):
        """
        Set up four test images and ensure each query param filter works
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        image_ids = []

        # 1. POST /images with three public images, and one private image
        # with various attributes
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'True',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are on")
        self.assertEqual(data['image']['is_public'], True)
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vhd',
                   'X-Image-Meta-Size': '20',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'False',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are on")
        self.assertEqual(data['image']['is_public'], True)
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '21',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'False',
                   'X-Image-Meta-Property-pants': 'are off'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are off")
        self.assertEqual(data['image']['is_public'], True)
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Private Image',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '22',
                   'X-Image-Meta-Is-Public': 'False',
                   'X-Image-Meta-Protected': 'False'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['is_public'], False)
        image_ids.append(data['image']['id'])

        # 2. GET /images
        # Verify three public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)

        # 3. GET /images with name filter
        # Verify correct images returned with name
        params = "name=My%20Image!"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['name'], "My Image!")

        # 4. GET /images with status filter
        # Verify correct images returned with status
        params = "status=queued"
        path = "http://%s:%d/v1/images/detail?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        for image in data['images']:
            self.assertEqual(image['status'], "queued")

        params = "status=active"
        path = "http://%s:%d/v1/images/detail?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 0)

        # 5. GET /images with container_format filter
        # Verify correct images returned with container_format
        params = "container_format=ovf"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['container_format'], "ovf")

        # 6. GET /images with disk_format filter
        # Verify correct images returned with disk_format
        params = "disk_format=vdi"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['disk_format'], "vdi")

        # 7. GET /images with size_max filter
        # Verify correct images returned with size <= expected
        params = "size_max=20"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertTrue(image['size'] <= 20)

        # 8. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_min=20"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertTrue(image['size'] >= 20)

        # 9. Get /images with is_public=None filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=None"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 4)

        # 10. Get /images with is_public=False filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=False"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['name'], "My Private Image")

        # 11. Get /images with is_public=True filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=True"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        for image in data['images']:
            self.assertNotEqual(image['name'], "My Private Image")

        # 12. Get /images with protected=False filter
        # Verify correct images returned with property
        params = "protected=False"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertNotEqual(image['name'], "Image1")

        # 13. Get /images with protected=True filter
        # Verify correct images returned with property
        params = "protected=True"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['name'], "Image1")

        # 14. GET /images with property filter
        # Verify correct images returned with property
        params = "property-pants=are%20on"
        path = "http://%s:%d/v1/images/detail?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['properties']['pants'], "are on")

        # 15. GET /images with property filter and name filter
        # Verify correct images returned with property and name
        # Make sure you quote the url when using more than one param!
        params = "name=My%20Image!&property-pants=are%20on"
        path = "http://%s:%d/v1/images/detail?%s" % (
                "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['properties']['pants'], "are on")
            self.assertEqual(image['name'], "My Image!")

        # 16. GET /images with past changes-since filter
        yesterday = utils.isotime(datetime.datetime.utcnow() -
                                  datetime.timedelta(1))
        params = "changes-since=%s" % yesterday
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)

        # one timezone west of Greenwich equates to an hour ago
        # taking care to pre-urlencode '+' as '%2B', otherwise the timezone
        # '+' is wrongly decoded as a space
        # TODO(eglynn): investigate '+' --> <SPACE> decoding, an artifact
        # of WSGI/webob dispatch?
        now = datetime.datetime.utcnow()
        hour_ago = now.strftime('%Y-%m-%dT%H:%M:%S%%2B01:00')
        params = "changes-since=%s" % hour_ago
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)

        # 17. GET /images with future changes-since filter
        tomorrow = utils.isotime(datetime.datetime.utcnow() +
                                 datetime.timedelta(1))
        params = "changes-since=%s" % tomorrow
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 0)

        # one timezone east of Greenwich equates to an hour from now
        now = datetime.datetime.utcnow()
        hour_hence = now.strftime('%Y-%m-%dT%H:%M:%S-01:00')
        params = "changes-since=%s" % hour_hence
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 0)

        # 18. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_min=-1"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 400)
        self.assertTrue("filter size_min got -1" in content)

        # 19. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_max=-1"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 400)
        self.assertTrue("filter size_max got -1" in content)

        # 20. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "min_ram=-1"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 400)
        self.assertTrue("Bad value passed to filter min_ram got -1" in content)

        # 21. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "protected=imalittleteapot"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 400)
        self.assertTrue("protected got imalittleteapot" in content)

        # 22. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "is_public=imalittleteapot"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 400)
        self.assertTrue("is_public got imalittleteapot" in content)

        self.stop_servers()

    @skip_if_disabled
    def test_limited_images(self):
        """
        Ensure marker and limit query params work
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        image_ids = []

        # 1. POST /images with three public images with various attributes
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        headers = minimal_headers('Image2')
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        headers = minimal_headers('Image3')
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        # 2. GET /images with all images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        images = json.loads(content)['images']
        self.assertEqual(len(images), 3)

        # 3. GET /images with limit of 2
        # Verify only two images were returned
        params = "limit=2"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images']
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['id'], images[0]['id'])
        self.assertEqual(data[1]['id'], images[1]['id'])

        # 4. GET /images with marker
        # Verify only two images were returned
        params = "marker=%s" % images[0]['id']
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images']
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['id'], images[1]['id'])
        self.assertEqual(data[1]['id'], images[2]['id'])

        # 5. GET /images with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % images[1]['id']
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], images[2]['id'])

        # 6. GET /images/detail with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % images[1]['id']
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], images[2]['id'])

        # DELETE images
        for image_id in image_ids:
            path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                                  image_id)
            http = httplib2.Http()
            response, content = http.request(path, 'DELETE')
            self.assertEqual(response.status, 200)

        self.stop_servers()

    @skip_if_disabled
    def test_ordered_images(self):
        """
        Set up three test images and ensure each query param filter works
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with three public images with various attributes
        image_ids = []
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'ASDF',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'bare',
                   'X-Image-Meta-Disk-Format': 'iso',
                   'X-Image-Meta-Size': '2',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'XYZ',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '5',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        image_ids.append(json.loads(content)['image']['id'])

        # 2. GET /images with no query params
        # Verify three public images sorted by created_at desc
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[2])
        self.assertEqual(data['images'][1]['id'], image_ids[1])
        self.assertEqual(data['images'][2]['id'], image_ids[0])

        # 3. GET /images sorted by name asc
        params = 'sort_key=name&sort_dir=asc'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[1])
        self.assertEqual(data['images'][1]['id'], image_ids[0])
        self.assertEqual(data['images'][2]['id'], image_ids[2])

        # 4. GET /images sorted by size desc
        params = 'sort_key=size&sort_dir=desc'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[0])
        self.assertEqual(data['images'][1]['id'], image_ids[2])
        self.assertEqual(data['images'][2]['id'], image_ids[1])

        # 5. GET /images sorted by size desc with a marker
        params = 'sort_key=size&sort_dir=desc&marker=%s' % image_ids[0]
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], image_ids[2])
        self.assertEqual(data['images'][1]['id'], image_ids[1])

        # 6. GET /images sorted by name asc with a marker
        params = 'sort_key=name&sort_dir=asc&marker=%s' % image_ids[2]
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 0)

        # DELETE images
        for image_id in image_ids:
            path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                                  image_id)
            http = httplib2.Http()
            response, content = http.request(path, 'DELETE')
            self.assertEqual(response.status, 200)

        self.stop_servers()

    @skip_if_disabled
    def test_duplicate_image_upload(self):
        """
        Upload initial image, then attempt to upload duplicate image
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with public image named Image1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)

        image = json.loads(content)['image']

        # 2. POST /images with public image named Image1, and ID: 1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1 Update',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Id': image['id'],
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 409)

        self.stop_servers()

    @skip_if_disabled
    def test_delete_not_existing(self):
        """
        We test the following:

        0. GET /images/1
        - Verify 404
        1. DELETE /images/1
        - Verify 404
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. DELETE /images/1
        # Verify 404 returned
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 404)

        self.stop_servers()

    @skip_if_disabled
    def test_unsupported_default_store(self):
        """
        We test that a mis-configured default_store causes the API server
        to fail to start.
        """
        self.cleanup()
        self.default_store = 'shouldnotexist'

        # ensure failure exit code is available to assert on
        self.api_server.server_control_options += ' --await-child=1'

        # ensure that the API server fails to launch
        self.start_server(self.api_server,
                          expect_launch=False,
                          expected_exitcode=255,
                          **self.__dict__.copy())

    def _do_test_post_image_content_missing_format(self, format):
        """
        We test that missing container/disk format fails with 400 "Bad Request"

        :see https://bugs.launchpad.net/glance/+bug/933702
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)

        # POST /images without given format being specified
        headers = minimal_headers('Image1')
        del headers['X-Image-Meta-' + format]
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        http = httplib2.Http()
        response, content = http.request(path, 'POST',
                            headers=headers,
                            body=test_data_file.name)
        self.assertEqual(response.status, 400)
        type = format.replace('_format', '')
        expected = "Details: Invalid %s format 'None' for image" % type
        self.assertTrue(expected in content,
                        "Could not find '%s' in '%s'" % (expected, content))

        self.stop_servers()

    @skip_if_disabled
    def _do_test_post_image_content_missing_diskformat(self):
        self._do_test_post_image_content_missing_format('container_format')

    @skip_if_disabled
    def _do_test_post_image_content_missing_disk_format(self):
        self._do_test_post_image_content_missing_format('disk_format')

    def _do_test_put_image_content_missing_format(self, format):
        """
        We test that missing container/disk format only fails with
        400 "Bad Request" when the image content is PUT (i.e. not
        on the original POST of a queued image).

        :see https://bugs.launchpad.net/glance/+bug/937216
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # POST queued image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        headers = {
           'X-Image-Meta-Name': 'Image1',
           'X-Image-Meta-Is-Public': 'True',
        }
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        image_id = data['image']['id']

        # PUT image content images without given format being specified
        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        headers = minimal_headers('Image1')
        del headers['X-Image-Meta-' + format]
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        http = httplib2.Http()
        response, content = http.request(path, 'PUT',
                            headers=headers,
                            body=test_data_file.name)
        self.assertEqual(response.status, 400)
        type = format.replace('_format', '')
        expected = "Details: Invalid %s format 'None' for image" % type
        self.assertTrue(expected in content,
                        "Could not find '%s' in '%s'" % (expected, content))

        self.stop_servers()

    @skip_if_disabled
    def _do_test_put_image_content_missing_diskformat(self):
        self._do_test_put_image_content_missing_format('container_format')

    @skip_if_disabled
    def _do_test_put_image_content_missing_disk_format(self):
        self._do_test_put_image_content_missing_format('disk_format')

    @skip_if_disabled
    def test_ownership(self):
        self.cleanup()
        self.api_server.deployment_flavor = 'fakeauth'
        self.registry_server.deployment_flavor = 'fakeauth'
        self.start_servers(**self.__dict__.copy())

        # Add an image with admin privileges and ensure the owner
        # can be set to something other than what was used to authenticate
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }

        create_headers = {
            'X-Image-Meta-Name': 'MyImage',
            'X-Image-Meta-disk_format': 'raw',
            'X-Image-Meta-container_format': 'ovf',
            'X-Image-Meta-Is-Public': 'True',
            'X-Image-Meta-Owner': 'tenant2',
        }
        create_headers.update(auth_headers)

        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=create_headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        image_id = data['image']['id']

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=auth_headers)
        self.assertEqual(response.status, 200)
        self.assertEqual('tenant2', response['x-image-meta-owner'])

        # Now add an image without admin privileges and ensure the owner
        # cannot be set to something other than what was used to authenticate
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:role1',
        }
        create_headers.update(auth_headers)

        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=create_headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        image_id = data['image']['id']

        # We have to be admin to see the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        create_headers.update(auth_headers)

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=auth_headers)
        self.assertEqual(response.status, 200)
        self.assertEqual('tenant1', response['x-image-meta-owner'])

        # Make sure the non-privileged user can't update their owner either
        update_headers = {
            'X-Image-Meta-Name': 'MyImage2',
            'X-Image-Meta-Owner': 'tenant2',
            'X-Auth-Token': 'user1:tenant1:role1',
        }

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=update_headers)
        self.assertEqual(response.status, 200)

        # We have to be admin to see the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=auth_headers)
        self.assertEqual(response.status, 200)
        self.assertEqual('tenant1', response['x-image-meta-owner'])

        # An admin user should be able to update the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant3:admin',
        }

        update_headers = {
            'X-Image-Meta-Name': 'MyImage2',
            'X-Image-Meta-Owner': 'tenant2',
        }
        update_headers.update(auth_headers)

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=update_headers)
        self.assertEqual(response.status, 200)

        path = ("http://%s:%d/v1/images/%s" %
                ("0.0.0.0", self.api_port, image_id))
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD', headers=auth_headers)
        self.assertEqual(response.status, 200)
        self.assertEqual('tenant2', response['x-image-meta-owner'])

        self.stop_servers()
