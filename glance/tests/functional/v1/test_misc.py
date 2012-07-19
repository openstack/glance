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

import hashlib
import httplib2
import json
import os
import tempfile

from glance.tests import functional
from glance.tests.utils import execute, minimal_headers, minimal_add_command

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestMiscellaneous(functional.FunctionalTest):

    """Some random tests for various bugs and stuff"""

    def setUp(self):
        super(TestMiscellaneous, self).setUp()

        # NOTE(sirp): This is needed in case we are running the tests under an
        # environment in which OS_AUTH_STRATEGY=keystone. The test server we
        # spin up won't have keystone support, so we need to switch to the
        # NoAuth strategy.
        os.environ['OS_AUTH_STRATEGY'] = 'noauth'
        os.environ['OS_AUTH_URL'] = ''

    def test_api_response_when_image_deleted_from_filesystem(self):
        """
        A test for LP bug #781410 -- glance should fail more gracefully
        on requests for images that have been removed from the fs
        """

        self.cleanup()
        self.start_servers()

        # 1. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
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

        # 2. REMOVE the image from the filesystem
        image_path = "%s/images/%s" % (self.test_dir, data['image']['id'])
        os.remove(image_path)

        # 3. HEAD /images/1
        # Verify image found now
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              data['image']['id'])
        http = httplib2.Http()
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual(response['x-image-meta-name'], "Image1")

        # 4. GET /images/1
        # Verify the api throws the apropriate 404 error
        path = "http://%s:%d/v1/images/1" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 404)

        self.stop_servers()

    def test_exception_not_eaten_from_registry_to_api(self):
        """
        A test for LP bug #704854 -- Exception thrown by registry
        server is consumed by API server.

        We start both servers daemonized.

        We then use curl to try adding an image that does not
        meet validation requirements on the registry server and test
        that the error returned from the API server to curl is appropriate
        """
        self.cleanup()
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        cmd = "curl -g http://127.0.0.1:%d/v1/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        cmd = ("curl -X POST -H 'Content-Type: application/octet-stream' "
               "-H 'X-Image-Meta-Name: ImageName' "
               "-H 'X-Image-Meta-Disk-Format: Invalid' "
               "http://127.0.0.1:%d/v1/images" % api_port)
        ignored, out, err = execute(cmd)

        self.assertTrue('Invalid disk format' in out,
                        "Could not find 'Invalid disk format' "
                        "in output: %s" % out)

        self.stop_servers()

    def test_api_treats_size_as_a_normal_property(self):
        """
        A test for LP bug #825024 -- glance client currently
        treats size as a normal property.
        """

        self.cleanup()
        self.start_servers()

        # 1. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            image_file_name = image_file.name
            suffix = 'size=12345 --silent-upload < %s' % image_file_name
            cmd = minimal_add_command(self.api_port, 'MyImage', suffix)

            exitcode, out, err = execute(cmd)

        image_id = out.strip().split(':')[1].strip()
        self.assertEqual(0, exitcode)
        self.assertTrue('Found non-settable field size. Removing.' in out)
        self.assertTrue('Added new image with ID: %s' % image_id in out)

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d show %s" % (self.api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertFalse("12345" in out)

        self.stop_servers()
