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

"""
Tests a Glance API server which uses an Swift backend by default

This test requires that a real Swift account is available. It looks
in a file GLANCE_TEST_SWIFT_CONF environ variable for the credentials to
use.

Note that this test clears the entire container from the Swift account
for use by the test case, so make sure you supply credentials for
test accounts only.

If a connection cannot be established, all the test cases are
skipped.
"""

import datetime
import hashlib
import httplib2
import os
import tempfile
import uuid

from glance.openstack.common import jsonutils
from glance.openstack.common import timeutils
from glance.openstack.common import units

from glance.tests import functional
from glance.tests.utils import minimal_headers
from glance.tests.utils import skip_if_disabled

FIVE_KB = 5 * units.Ki
FIVE_GB = 5 * units.Gi
TEST_VAR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '../..', 'var'))


class TestSSL(functional.FunctionalTest):

    """Functional tests verifying SSL communication"""

    def setUp(self):
        super(TestSSL, self).setUp()

        if getattr(self, 'inited', False):
            return

        self.inited = False
        self.disabled = True

        # Test key/cert/CA file created as per:
        #   http://blog.didierstevens.com/2008/12/30/
        #     howto-make-your-own-cert-with-openssl/
        # Note that for these tests certificate.crt had to
        # be created with 'Common Name' set to 127.0.0.1

        self.key_file = os.path.join(TEST_VAR_DIR, 'privatekey.key')
        if not os.path.exists(self.key_file):
            self.disabled_message = ("Could not find private key file %s" %
                                     self.key_file)
            self.inited = True
            return

        self.cert_file = os.path.join(TEST_VAR_DIR, 'certificate.crt')
        if not os.path.exists(self.cert_file):
            self.disabled_message = ("Could not find certificate file %s" %
                                     self.cert_file)
            self.inited = True
            return

        self.ca_file = os.path.join(TEST_VAR_DIR, 'ca.crt')
        if not os.path.exists(self.ca_file):
            self.disabled_message = ("Could not find CA file %s" %
                                     self.ca_file)
            self.inited = True
            return

        self.inited = True
        self.disabled = False

    def tearDown(self):
        super(TestSSL, self).tearDown()
        if getattr(self, 'inited', False):
            return

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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. GET /images/detail
        # Verify no public images
        path = "https://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 2. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path,
                                          'POST',
                                          headers=headers,
                                          body=image_data)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        image_id = data['image']['id']

        # 3. HEAD image
        # Verify image found now
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 4. GET image
        # Verify all information on image we just added is correct
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(jsonutils.loads(content), expected_result)

        # 6. GET /images/detail
        # Verify image and all its metadata
        path = "https://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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

        image = jsonutils.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value,
                             image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 7. PUT image with custom properties of "distro" and "arch"
        # Verify 200 returned
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(data['image']['properties']['arch'], "x86_64")
        self.assertEqual(data['image']['properties']['distro'], "Ubuntu")

        # 8. GET /images/detail
        # Verify image and all its metadata
        path = "https://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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

        image = jsonutils.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value,
                             image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 9. PUT image and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)

        path = "https://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)['images'][0]
        self.assertEqual(len(data['properties']), 1)
        self.assertEqual(data['properties']['arch'], "x86_64")

        # 10. PUT image and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'PUT', headers=headers)
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)

        path = "https://%s:%d/v1/images/detail" % ("127.0.0.1", self.api_port)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)['images'][0]
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
        3. HEAD image
        - Verify image now in queued status
        4. PUT image with image data
        - Verify 200 returned
        5. HEAD image
        - Verify image now in active status
        6. GET /images
        - Verify one public image
        """

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with public image named Image1
        # with no location or image data
        headers = minimal_headers('Image1')
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
        self.assertIsNone(data['image']['checksum'])
        self.assertEqual(data['image']['size'], 0)
        self.assertEqual(data['image']['container_format'], 'ovf')
        self.assertEqual(data['image']['disk_format'], 'raw')
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        image_id = data['image']['id']

        # 2. GET /images
        # Verify 1 public image
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(data['images'][0]['id'], image_id)
        self.assertIsNone(data['images'][0]['checksum'])
        self.assertEqual(data['images'][0]['size'], 0)
        self.assertEqual(data['images'][0]['container_format'], 'ovf')
        self.assertEqual(data['images'][0]['disk_format'], 'raw')
        self.assertEqual(data['images'][0]['name'], "Image1")

        # 3. HEAD /images
        # Verify status is in queued
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-status'], "queued")
        self.assertEqual(response['x-image-meta-size'], '0')
        self.assertEqual(response['x-image-meta-id'], image_id)

        # 4. PUT image with image data, verify 200 returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream'}
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path,
                                          'PUT',
                                          headers=headers,
                                          body=image_data)
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        # 5. HEAD image
        # Verify status is in active
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               image_id)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")
        self.assertEqual(response['x-image-meta-status'], "active")

        # 6. GET /images
        # Verify 1 public image still...
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(data['images'][0]['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['images'][0]['id'], image_id)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['container_format'], 'ovf')
        self.assertEqual(data['images'][0]['disk_format'], 'raw')
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
        self.start_servers(**self.__dict__.copy())

        versions = {'versions': [{
            "id": "v2.2",
            "status": "CURRENT",
            "links": [{
                "rel": "self",
                "href": "https://127.0.0.1:%d/v2/" % self.api_port}]},
            {"id": "v2.1",
             "status": "SUPPORTED",
             "links": [{
                 "rel": "self",
                 "href": "https://127.0.0.1:%d/v2/" % self.api_port}]},
            {"id": "v2.0",
             "status": "SUPPORTED",
             "links": [{
                 "rel": "self",
                 "href": "https://127.0.0.1:%d/v2/" % self.api_port}]},
            {"id": "v1.1",
             "status": "CURRENT",
             "links": [{
                 "rel": "self",
                 "href": "https://127.0.0.1:%d/v1/" % self.api_port}]},
            {"id": "v1.0",
             "status": "SUPPORTED",
             "links": [{
                 "rel": "self",
                 "href": "https://127.0.0.1:%d/v1/" % self.api_port}]}]}
        versions_json = jsonutils.dumps(versions)
        images = {'images': []}
        images_json = jsonutils.dumps(images)

        # 0. GET / with no Accept: header
        # Verify version choices returned.
        # Bug lp:803260  no Accept header causes a 500 in glance-api
        path = "https://%s:%d/" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 1. GET /images with no Accept: header
        # Verify version choices returned.
        path = "https://%s:%d/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 2. GET /v1/images with no Accept: header
        # Verify empty images list returned.
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 3. GET / with Accept: unknown header
        # Verify version choices returned. Verify message in API log about
        # unknown accept header.
        path = "https://%s:%d/" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        headers = {'Accept': 'unknown'}
        response, content = https.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown version. Returning version choices'
                        in open(self.api_server.log_file).read())

        # 4. GET / with an Accept: application/vnd.openstack.images-v1
        # Verify empty image list returned
        path = "https://%s:%d/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = https.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 5. GET /images with a Accept: application/vnd.openstack.compute-v1
        # header. Verify version choices returned. Verify message in API log
        # about unknown accept header.
        path = "https://%s:%d/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        headers = {'Accept': 'application/vnd.openstack.compute-v1'}
        response, content = https.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown version. Returning version choices'
                        in open(self.api_server.log_file).read())

        # 6. GET /v1.0/images with no Accept: header
        # Verify empty image list returned
        path = "https://%s:%d/v1.0/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, images_json)

        # 7. GET /v1.a/images with no Accept: header
        # Verify versions list returned
        path = "https://%s:%d/v1.a/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 8. GET /va.1/images with no Accept: header
        # Verify version choices returned
        path = "https://%s:%d/va.1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 9. GET /versions with no Accept: header
        # Verify version choices returned
        path = "https://%s:%d/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 10. GET /versions with a Accept: application/vnd.openstack.images-v1
        # header. Verify version choices returned.
        path = "https://%s:%d/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        headers = {'Accept': 'application/vnd.openstack.images-v1'}
        response, content = https.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 11. GET /v1/versions with no Accept: header
        # Verify 404 returned
        path = "https://%s:%d/v1/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # 12. GET /v2/versions with no Accept: header
        # Verify version choices returned
        path = "https://%s:%d/v2/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 404)

        # 12b. GET /v3/versions with no Accept: header (where v3 in unknown)
        # Verify version choices returned
        path = "https://%s:%d/v3/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        # 13. GET /images with a Accept: application/vnd.openstack.compute-v3
        # header. Verify version choices returned. Verify message in API log
        # about unknown version in accept header.
        path = "https://%s:%d/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        headers = {'Accept': 'application/vnd.openstack.images-v3'}
        response, content = https.request(path, 'GET', headers=headers)
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)
        self.assertTrue('Unknown version. Returning version choices'
                        in open(self.api_server.log_file).read())

        # 14. GET /v1.2/images with no Accept: header
        # Verify version choices returned
        path = "https://%s:%d/v1.2/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 300)
        self.assertEqual(content, versions_json)

        self.stop_servers()

    @skip_if_disabled
    def test_traceback_not_consumed(self):
        """
        A test that errors coming from the POST API do not get consumed
        and print the actual error message, and
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
        headers = {'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi'}
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path,
                                          'POST',
                                          headers=headers,
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
        self.assertEqual(data['image']['properties']['pants'], "are off")
        self.assertEqual(data['image']['is_public'], True)

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Private Image',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '22',
                   'X-Image-Meta-Is-Public': 'False'}
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)
        self.assertEqual(data['image']['is_public'], False)

        # 2. GET /images
        # Verify three public images
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)

        # 3. GET /images with name filter
        # Verify correct images returned with name
        params = "name=My%20Image!"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['name'], "My Image!")

        # 4. GET /images with status filter
        # Verify correct images returned with status
        params = "status=queued"
        path = "https://%s:%d/v1/images/detail?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)
        for image in data['images']:
            self.assertEqual(image['status'], "queued")

        params = "status=active"
        path = "https://%s:%d/v1/images/detail?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 0)

        # 5. GET /images with container_format filter
        # Verify correct images returned with container_format
        params = "container_format=ovf"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['container_format'], "ovf")

        # 6. GET /images with disk_format filter
        # Verify correct images returned with disk_format
        params = "disk_format=vdi"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['disk_format'], "vdi")

        # 7. GET /images with size_max filter
        # Verify correct images returned with size <= expected
        params = "size_max=20"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertTrue(image['size'] <= 20)

        # 8. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_min=20"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertTrue(image['size'] >= 20)

        # 9. Get /images with is_public=None filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=None"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 4)

        # 10. Get /images with is_public=False filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=False"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['name'], "My Private Image")

        # 11. Get /images with is_public=True filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=True"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)
        for image in data['images']:
            self.assertNotEqual(image['name'], "My Private Image")

        # 12. GET /images with property filter
        # Verify correct images returned with property
        params = "property-pants=are%20on"
        path = "https://%s:%d/v1/images/detail?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        for image in data['images']:
            self.assertEqual(image['properties']['pants'], "are on")

        # 13. GET /images with property filter and name filter
        # Verify correct images returned with property and name
        # Make sure you quote the url when using more than one param!
        params = "name=My%20Image!&property-pants=are%20on"
        path = "https://%s:%d/v1/images/detail?%s" % (
            "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 1)
        for image in data['images']:
            self.assertEqual(image['properties']['pants'], "are on")
            self.assertEqual(image['name'], "My Image!")

        # 14. GET /images with past changes-since filter
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)
        params = "changes-since=%s" % iso1
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)

        # 15. GET /images with future changes-since filter
        dt2 = timeutils.utcnow() + datetime.timedelta(1)
        iso2 = timeutils.isotime(dt2)
        params = "changes-since=%s" % iso2
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 0)

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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. POST /images with three public images with various attributes
        headers = minimal_headers('Image1')
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids = [data['image']['id']]

        headers = minimal_headers('Image2')
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids.append(data['image']['id'])

        headers = minimal_headers('Image3')
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids.append(data['image']['id'])

        # 2. GET /images with limit of 2
        # Verify only two images were returned
        params = "limit=2"
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], image_ids[2])
        self.assertEqual(data['images'][1]['id'], image_ids[1])

        # 3. GET /images with marker
        # Verify only two images were returned
        params = "marker=%s" % image_ids[2]
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], image_ids[1])
        self.assertEqual(data['images'][1]['id'], image_ids[0])

        # 4. GET /images with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % image_ids[1]
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], image_ids[0])

        # 5. GET /images/detail with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % image_ids[2]
        path = "https://%s:%d/v1/images?%s" % (
               "127.0.0.1", self.api_port, params)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], image_ids[1])

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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids = [data['image']['id']]

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'ASDF',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'bare',
                   'X-Image-Meta-Disk-Format': 'iso',
                   'X-Image-Meta-Size': '2',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'XYZ',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '5',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_ids.append(data['image']['id'])

        # 2. GET /images with no query params
        # Verify three public images sorted by created_at desc
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[2])
        self.assertEqual(data['images'][1]['id'], image_ids[1])
        self.assertEqual(data['images'][2]['id'], image_ids[0])

        # 3. GET /images sorted by name asc
        params = 'sort_key=name&sort_dir=asc'
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[1])
        self.assertEqual(data['images'][1]['id'], image_ids[0])
        self.assertEqual(data['images'][2]['id'], image_ids[2])

        # 4. GET /images sorted by size desc
        params = 'sort_key=size&sort_dir=desc'
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 3)
        self.assertEqual(data['images'][0]['id'], image_ids[0])
        self.assertEqual(data['images'][1]['id'], image_ids[2])
        self.assertEqual(data['images'][2]['id'], image_ids[1])
        # 5. GET /images sorted by size desc with a marker
        params = 'sort_key=size&sort_dir=desc&marker=%s' % image_ids[0]
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(data['images'][0]['id'], image_ids[2])
        self.assertEqual(data['images'][1]['id'], image_ids[1])

        # 6. GET /images sorted by name asc with a marker
        params = 'sort_key=name&sort_dir=asc&marker=%s' % image_ids[2]
        path = "https://%s:%d/v1/images?%s" % ("127.0.0.1",
                                               self.api_port, params)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        data = jsonutils.loads(content)
        self.assertEqual(len(data['images']), 0)

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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
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
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = jsonutils.loads(content)

        image_id = data['image']['id']

        # 2. POST /images with public image named Image1, and ID: 1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1 Update',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Id': image_id,
                   'X-Image-Meta-Is-Public': 'True'}
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 409)
        expected = "An image with identifier %s already exists" % image_id
        self.assertTrue(expected in content,
                        "Could not find '%s' in '%s'" % (expected, content))

        self.stop_servers()

    @skip_if_disabled
    def test_delete_not_existing(self):
        """
        We test the following:

        0. GET /images
        - Verify no public images
        1. DELETE random image
        - Verify 404
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        # 0. GET /images
        # Verify no public images
        path = "https://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'GET')
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # 1. DELETE /images/1
        # Verify 404 returned
        path = "https://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                               str(uuid.uuid4()))
        https = httplib2.Http(disable_ssl_certificate_validation=True)
        response, content = https.request(path, 'DELETE')
        self.assertEqual(response.status, 404)

        self.stop_servers()
