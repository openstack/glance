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

"""
Tests a Glance API server which uses an S3 backend by default

This test requires that a real S3 account is available. It looks
in a file /tests/functional/test_s3.conf for the credentials to
use.

Note that this test clears the entire bucket from the S3 account
for use by the test case, so make sure you supply credentials for
test accounts only.

If a connection cannot be established, all the test cases are
skipped.
"""

import ConfigParser
import json
import os
import tempfile
import unittest

from tests import functional
from tests.utils import execute

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestS3(functional.FunctionalTest):

    """Functional tests for the S3 backend"""

    # Test machines can set the GLANCE_TEST_MIGRATIONS_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_S3_CONF',
                                      os.path.join('tests', 'functional',
                                                   'test_s3.conf'))

    def setUp(self):
        """
        Test a connection to an S3 store using the credentials
        found in the environs or /tests/functional/test_s3.conf, if found.
        If the connection fails, mark all tests to skip.
        """
        self.inited = False
        self.skip_tests = True

        if self.inited:
            return

        if os.path.exists(TestS3.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestS3.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.__dict__[key] = value
            except ConfigParser.ParsingError, e:
                print ("Failed to read test_s3.conf config file. "
                       "Got error: %s" % e)
                super(TestS3, self).setUp()
                self.inited = True
                return

        from boto.s3.connection import S3Connection
        from boto.exception import S3ResponseError

        try:
            s3_host = self.s3_store_host
            access_key = self.s3_store_access_key
            secret_key = self.s3_store_secret_key
            bucket_name = self.s3_store_bucket
        except AttributeError, e:
            print ("Failed to find required configuration options for "
                   "S3 store. Got error: %s" % e)
            self.inited = True
            super(TestS3, self).setUp()
            return

        s3_conn = S3Connection(access_key, secret_key, host=s3_host)

        self.bucket = None
        try:
            buckets = s3_conn.get_all_buckets()
            for bucket in buckets:
                if bucket.name == bucket_name:
                    self.bucket = bucket
        except S3ResponseError, e:
            print ("Failed to connect to S3 with credentials,"
                   "to find bucket. Got error: %s" % e)
            self.inited = True
            super(TestS3, self).setUp()
            return

        self.s3_conn = s3_conn

        if not self.bucket:
            try:
                self.bucket = s3_conn.create_bucket(bucket_name)
            except boto.exception.S3ResponseError, e:
                print ("Failed to create bucket. Got error: %s" % e)
                self.inited = True
                super(TestS3, self).setUp()
                return
        else:
            self.clear_bucket()

        self.skip_tests = False
        self.inited = True
        self.default_store = 's3'

        super(TestS3, self).setUp()

    def tearDown(self):
        if not self.skip_tests:
            self.clear_bucket()
        super(TestS3, self).tearDown()

    def clear_bucket(self):
        # It's not possible to simply clear a bucket. You
        # need to loop over all the keys and delete them
        # all first...
        keys = self.bucket.list()
        for key in keys:
            key.delete()

    def test_add_list_delete_list(self):
        """
        We test the following:

        0. GET /images
        - Verify no public images
        1. GET /images/detail
        - Verify no public images
        2. HEAD /images/1
        - Verify 404 returned
        3. POST /images with public image named Image1 with a location
        attribute and no custom properties
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
        if self.skip_tests:
            return True

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. GET /images
        # Verify no public images
        cmd = "curl http://0.0.0.0:%d/v1/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        # 1. GET /images/detail
        # Verify no public images
        cmd = "curl http://0.0.0.0:%d/v1/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        # 2. HEAD /images/1
        # Verify 404 returned
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/v1/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 404 Not Found", status_line)

        # 3. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB

        cmd = ("curl -i -X POST "
               "-H 'Expect: ' "  # Necessary otherwise sends 100 Continue
               "-H 'Content-Type: application/octet-stream' "
               "-H 'X-Image-Meta-Name: Image1' "
               "-H 'X-Image-Meta-Is-Public: True' "
               "--data-binary \"%s\" "
               "http://0.0.0.0:%d/v1/images") % (image_data, api_port)

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 201 Created", status_line, out)

        # 4. HEAD /images
        # Verify image found now
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/v1/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)
        self.assertTrue("X-Image-Meta-Name: Image1" in out)

        # 5. GET /images/1
        # Verify all information on image we just added is correct

        cmd = "curl -i http://0.0.0.0:%d/v1/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")

        self.assertEqual("HTTP/1.1 200 OK", lines.pop(0))

        # Handle the headers
        image_headers = {}
        std_headers = {}
        other_lines = []
        for line in lines:
            if line.strip() == '':
                continue
            if line.startswith("X-Image"):
                pieces = line.split(":")
                key = pieces[0].strip()
                value = ":".join(pieces[1:]).strip()
                image_headers[key] = value
            elif ':' in line:
                pieces = line.split(":")
                key = pieces[0].strip()
                value = ":".join(pieces[1:]).strip()
                std_headers[key] = value
            else:
                other_lines.append(line)

        expected_image_headers = {
            'X-Image-Meta-Id': '1',
            'X-Image-Meta-Name': 'Image1',
            'X-Image-Meta-Is_public': 'True',
            'X-Image-Meta-Status': 'active',
            'X-Image-Meta-Disk_format': '',
            'X-Image-Meta-Container_format': '',
            'X-Image-Meta-Size': str(FIVE_KB),
            'X-Image-Meta-Location': 's3://%s:%s@%s/%s/1' % (
                self.s3_store_access_key,
                self.s3_store_secret_key,
                self.s3_store_host,
                self.s3_store_bucket)}

        expected_std_headers = {
            'Content-Length': str(FIVE_KB),
            'Content-Type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertTrue(expected_key in image_headers,
                            "Failed to find key %s in image_headers"
                            % expected_key)
            self.assertEqual(expected_value, image_headers[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image_headers[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertTrue(expected_key in std_headers,
                            "Failed to find key %s in std_headers"
                            % expected_key)
            self.assertEqual(expected_value, std_headers[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               std_headers[expected_key]))

        # Now the image data...
        expected_image_data = "*" * FIVE_KB

        # Should only be a single "line" left, and
        # that's the image data
        self.assertEqual(1, len(other_lines))
        self.assertEqual(expected_image_data, other_lines[0])

        # 6. GET /images
        # Verify no public images
        cmd = "curl http://0.0.0.0:%d/v1/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_result = {"images": [
            {"container_format": None,
             "disk_format": None,
             "id": 1,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, json.loads(out.strip()))

        # 7. GET /images/detail
        # Verify image and all its metadata
        cmd = "curl http://0.0.0.0:%d/v1/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
            'location': 's3://%s:%s@%s/%s/1' % (
                self.s3_store_access_key,
                self.s3_store_secret_key,
                self.s3_store_host,
                self.s3_store_bucket),
            "is_public": True,
            "deleted_at": None,
            "properties": {},
            "size": 5120}

        image = json.loads(out.strip())['images'][0]

        for expected_key, expected_value in expected_image.items():
            self.assertTrue(expected_key in image,
                            "Failed to find key %s in image"
                            % expected_key)
            self.assertEqual(expected_value, expected_image[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image[expected_key]))

        # 8. PUT /images/1 with custom properties of "distro" and "arch"
        # Verify 200 returned

        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Distro: Ubuntu' "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/v1/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        # 9. GET /images/detail
        # Verify image and all its metadata
        cmd = "curl http://0.0.0.0:%d/v1/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
            'location': 's3://%s:%s@%s/%s/1' % (
                self.s3_store_access_key,
                self.s3_store_secret_key,
                self.s3_store_host,
                self.s3_store_bucket),
            "is_public": True,
            "deleted_at": None,
            "properties": {'distro': 'Ubuntu', 'arch': 'x86_64'},
            "size": 5120}

        image = json.loads(out.strip())['images'][0]

        for expected_key, expected_value in expected_image.items():
            self.assertTrue(expected_key in image,
                            "Failed to find key %s in image"
                            % expected_key)
            self.assertEqual(expected_value, image[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image[expected_key]))

        # 10. PUT /images/1 and remove a previously existing property.
        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/v1/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        cmd = "curl http://0.0.0.0:%d/v1/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        image = json.loads(out.strip())['images'][0]
        self.assertEqual(1, len(image['properties']))
        self.assertEqual('x86_64', image['properties']['arch'])

        # 11. PUT /images/1 and add a previously deleted property.
        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Distro: Ubuntu' "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/v1/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        cmd = "curl http://0.0.0.0:%d/v1/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        image = json.loads(out.strip())['images'][0]
        self.assertEqual(2, len(image['properties']))
        self.assertEqual('x86_64', image['properties']['arch'])
        self.assertEqual('Ubuntu', image['properties']['distro'])

        self.stop_servers()

    def test_delete_not_existing(self):
        """
        We test the following:

        0. GET /images/1
        - Verify 404
        1. DELETE /images/1
        - Verify 404
        """
        if self.skip_tests:
            return True

        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. GET /images/1
        # Verify 404 returned
        cmd = "curl -i http://0.0.0.0:%d/v1/images/1" % api_port

        exitcode, out, err = execute(cmd)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 404 Not Found", status_line)

        # 1. DELETE /images/1
        # Verify 404 returned
        cmd = "curl -i -X DELETE http://0.0.0.0:%d/v1/images/1" % api_port

        exitcode, out, err = execute(cmd)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 404 Not Found", status_line)

        self.stop_servers()
