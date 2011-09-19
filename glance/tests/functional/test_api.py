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
import httplib2
import json
import os
import tempfile

from glance.tests import functional
from glance.tests.utils import execute, skip_if_disabled

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
        2. HEAD /images/1
        - Verify 404 returned
        3. POST /images with public image named Image1
        and no custom properties
        - Verify 201 returned
        4. HEAD /images/1
        - Verify HTTP headers have correct information we just added
        5. GET /images/1
        - Verify all information on image we just added is correct
        6. GET /images
        - Verify the image we just added is returned
        7. GET /images/detail
        - Verify the image we just added is returned
        8. PUT /images/1 with custom properties of "distro" and "arch"
        - Verify 200 returned
        9. GET /images/1
        - Verify updated information about image was stored
        10. PUT /images/1
        - Remove a previously existing property.
        11. PUT /images/1
        - Add a previously deleted property.
        """
        self.cleanup()
        self.start_servers()

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

        # 2. HEAD /images/1
        # Verify 404 returned
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 404)

        # 3. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 4. HEAD /images/1
        # Verify image found now
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 5. GET /images/1
        # Verify all information on image we just added is correct
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image_headers = {
            'x-image-meta-id': '1',
            'x-image-meta-name': 'Image1',
            'x-image-meta-is_public': 'True',
            'x-image-meta-status': 'active',
            'x-image-meta-disk_format': '',
            'x-image-meta-container_format': '',
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

        # 6. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_result = {"images": [
            {"container_format": None,
             "disk_format": None,
             "id": 1,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(json.loads(content), expected_result)

        # 7. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
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

        # 8. PUT /images/1 with custom properties of "distro" and "arch"
        # Verify 200 returned
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['arch'], "x86_64")
        self.assertEqual(data['image']['properties']['distro'], "Ubuntu")

        # 9. GET /images/detail
        # Verify image and all its metadata
        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
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

        # 10. PUT /images/1 and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)

        path = "http://%s:%d/v1/images/detail" % ("0.0.0.0", self.api_port)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 1)
        self.assertEqual(data['properties']['arch'], "x86_64")

        # 11. PUT /images/1 and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
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
        3. HEAD /images/1
        - Verify image now in queued status
        4. PUT /images/1 with image data
        - Verify 200 returned
        5. HEAD /images/1
        - Verify image now in active status
        6. GET /images
        - Verify one public image
        """

        self.cleanup()
        self.start_servers()

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with public image named Image1
        # with no location or image data
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'], None)
        self.assertEqual(data['image']['size'], 0)
        self.assertEqual(data['image']['container_format'], None)
        self.assertEqual(data['image']['disk_format'], None)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 2. GET /images
        # Verify 1 public image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['checksum'], None)
        self.assertEqual(data['images'][0]['size'], 0)
        self.assertEqual(data['images'][0]['container_format'], None)
        self.assertEqual(data['images'][0]['disk_format'], None)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # 3. HEAD /images
        # Verify status is in queued
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-status'], "queued")
        self.assertEqual(response['x-image-meta-size'], '0')
        self.assertEqual(response['x-image-meta-id'], '1')

        # 4. PUT /images/1 with image data, verify 200 returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream'}
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
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
        path = "http://%s:%d/v1/images/1" % ("0.0.0.0", self.api_port)
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
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['container_format'], None)
        self.assertEqual(data['images'][0]['disk_format'], None)
        self.assertEqual(data['images'][0]['name'], "Image1")

        self.stop_servers()

    @skip_if_disabled
    def test_version_variations(self):
        """
        We test that various calls to the images and root endpoints are
        handled properly, and that usage of the Accept: header does
        content negotiation properly.
        """

        self.cleanup()
        self.start_servers()

        versions = {'versions': [{
            "id": "v1.1",
            "status": "CURRENT",
            "links": [{
                "rel": "self",
                "href": "http://0.0.0.0:%d/v1/" % self.api_port}]}, {
            "id": "v1.0",
            "status": "SUPPORTED",
            "links": [{
                "rel": "self",
                "href": "http://0.0.0.0:%d/v1/" % self.api_port}]}]}
        versions_json = json.dumps(versions)
        images = {'images': []}
        images_json = json.dumps(images)

        # 0. GET / with no Accept: header
        # Verify version choices returned.
        # Bug lp:803260  no Accept header causes a 500 in glance-api
        path = "http://%s:%d/" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 1. GET /images with no Accept: header
        # Verify version choices returned.
        path = "http://%s:%d/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 2. GET /v1/images with no Accept: header
        # Verify empty images list returned.
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 3. GET / with Accept: unknown header
        # Verify version choices returned. Verify message in API log about
        # unknown accept header.
        path = "http://%s:%d/" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'unknown'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 4. GET / with an Accept: application/vnd.openstack.images-v1
        # Verify empty image list returned
        path = "http://%s:%d/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 5. GET /images with a Accept: application/vnd.openstack.compute-v1
        # header. Verify version choices returned. Verify message in API log
        # about unknown accept header.
        path = "http://%s:%d/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.compute-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 6. GET /v1.0/images with no Accept: header
        # Verify empty image list returned
        path = "http://%s:%d/v1.0/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 7. GET /v1.a/images with no Accept: header
        # Verify empty image list returned
        path = "http://%s:%d/v1.a/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 8. GET /va.1/images with no Accept: header
        # Verify version choices returned
        path = "http://%s:%d/va.1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 9. GET /versions with no Accept: header
        # Verify version choices returned
        path = "http://%s:%d/versions" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 10. GET /versions with a Accept: application/vnd.openstack.images-v1
        # header. Verify version choices returned.
        path = "http://%s:%d/versions" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 11. GET /v1/versions with no Accept: header
        # Verify 404 returned
        path = "http://%s:%d/v1/versions" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # 12. GET /v2/versions with no Accept: header
        # Verify version choices returned
        path = "http://%s:%d/v2/versions" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 13. GET /images with a Accept: application/vnd.openstack.compute-v2
        # header. Verify version choices returned. Verify message in API log
        # about unknown version in accept header.
        path = "http://%s:%d/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        headers = {'Accept': 'application/vnd.openstack.images-v2'}
        response, content = http.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown accept header'
                        in open(self.api_server.log_file).read())

        # 14. GET /v1.2/images with no Accept: header
        # Verify version choices returned
        path = "http://%s:%d/v1.2/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown version in versioned URI'
                        in open(self.api_server.log_file).read())

        self.stop_servers()

    @skip_if_disabled
    def test_size_greater_2G_mysql(self):
        """
        A test against the actual datastore backend for the registry
        to ensure that the image size property is not truncated.

        :see https://bugs.launchpad.net/glance/+bug/739433
        """

        self.cleanup()
        self.start_servers()

        # 1. POST /images with public image named Image1
        # attribute and a size of 5G. Use the HTTP engine with an
        # X-Image-Meta-Location attribute to make Glance forego
        # "adding" the image data.
        # Verify a 201 OK is returned
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Location': 'http://example.com/fakeimage',
                   'X-Image-Meta-Size': str(FIVE_GB),
                   'X-Image-Meta-Name': 'Image1',
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
        self.start_servers()

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
        self.start_servers()

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with three public images, and one private image
        # with various attributes
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are on")
        self.assertEqual(data['image']['is_public'], True)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vhd',
                   'X-Image-Meta-Size': '20',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are on")
        self.assertEqual(data['image']['is_public'], True)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '21',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Property-pants': 'are off'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are off")
        self.assertEqual(data['image']['is_public'], True)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Private Image',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '22',
                   'X-Image-Meta-Is-Public': 'False'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['is_public'], False)

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

        # 12. GET /images with property filter
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

        # 13. GET /images with property filter and name filter
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

        self.stop_servers()

    @skip_if_disabled
    def test_limited_images(self):
        """
        Ensure marker and limit query params work
        """
        self.cleanup()
        self.start_servers()

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with three public images with various attributes
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image2',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image3',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)

        # 2. GET /images with limit of 2
        # Verify only two images were returned
        params = "limit=2"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], 3)
        self.assertEqual(data['images'][1]['id'], 2)

        # 3. GET /images with marker
        # Verify only two images were returned
        params = "marker=3"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], 2)
        self.assertEqual(data['images'][1]['id'], 1)

        # 4. GET /images with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=2"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)

        # 5. GET /images/detail with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=3"
        path = "http://%s:%d/v1/images?%s" % (
               "0.0.0.0", self.api_port, params)
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 2)

        self.stop_servers()

    @skip_if_disabled
    def test_ordered_images(self):
        """
        Set up three test images and ensure each query param filter works
        """
        self.cleanup()
        self.start_servers()

        # 0. GET /images
        # Verify no public images
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with three public images with various attributes
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

        # 2. GET /images with no query params
        # Verify three public images sorted by created_at desc
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], 3)
        self.assertEqual(data['images'][1]['id'], 2)
        self.assertEqual(data['images'][2]['id'], 1)

        # 3. GET /images sorted by name asc
        params = 'sort_key=name&sort_dir=asc'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], 2)
        self.assertEqual(data['images'][1]['id'], 1)
        self.assertEqual(data['images'][2]['id'], 3)

        # 4. GET /images sorted by size desc
        params = 'sort_key=size&sort_dir=desc'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][1]['id'], 3)
        self.assertEqual(data['images'][2]['id'], 2)

        # 5. GET /images sorted by size desc with a marker
        params = 'sort_key=size&sort_dir=desc&marker=1'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], 3)
        self.assertEqual(data['images'][1]['id'], 2)

        # 6. GET /images sorted by name asc with a marker
        params = 'sort_key=name&sort_dir=asc&marker=3'
        path = "http://%s:%d/v1/images?%s" % ("0.0.0.0", self.api_port, params)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 0)

        self.stop_servers()

    @skip_if_disabled
    def test_duplicate_image_upload(self):
        """
        Upload initial image, then attempt to upload duplicate image
        """
        self.cleanup()
        self.start_servers()

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

        # 2. POST /images with public image named Image1, and ID: 1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1 Update',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Id': '1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 409)
        expected = "An image with identifier 1 already exists"
        self.assertTrue(expected in content,
                        "Could not find '%s' in '%s'" % (expected, content))

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
