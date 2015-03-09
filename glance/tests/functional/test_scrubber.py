# Copyright 2011-2012 OpenStack Foundation
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

import os
import sys
import time

import glance_store.location
import httplib2
from oslo.serialization import jsonutils
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.common import crypt
from glance.tests import functional
from glance.tests.utils import execute


TEST_IMAGE_DATA = '*' * 5 * units.Ki
TEST_IMAGE_META = {
    'name': 'test_image',
    'is_public': False,
    'disk_format': 'raw',
    'container_format': 'ovf',
}


class TestScrubber(functional.FunctionalTest):

    """Test that delayed_delete works and the scrubber deletes"""

    def test_delayed_delete(self):
        """
        test that images don't get deleted immediately and that the scrubber
        scrubs them
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=True,
                           metadata_encryption_key='')

        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        self.wait_for_scrub(path)

        self.stop_servers()

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='')

        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # scrub images and make sure they get deleted
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        self.wait_for_scrub(path)

        self.stop_servers()

    def test_scrubber_with_metadata_enc(self):
        """
        test that files written to scrubber_data_dir use
        metadata_encryption_key when available to encrypt the location
        """

        # FIXME(flaper87): It looks like an older commit
        # may have broken this test. The file_queue `add_location`
        # is not being called.
        self.skipTest("Test broken. See bug #1366682")
        self.cleanup()
        self.start_servers(delayed_delete=True,
                           daemon=True,
                           default_store='file')

        # add an image
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }

        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1",
                                              self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # ensure the marker file has encrypted the image location by decrypting
        # it and checking the image_id is intact
        file_path = os.path.join(self.api_server.scrubber_datadir,
                                 str(image_id))
        marker_uri = None
        with open(file_path, 'r') as f:
            marker_uri = f.readline().strip()
        self.assertTrue(marker_uri is not None)

        decrypted_uri = crypt.urlsafe_decrypt(
            self.api_server.metadata_encryption_key, marker_uri)
        loc = glance_store.location.StoreLocation({})
        loc.parse_uri(decrypted_uri)

        self.assertEqual("file", loc.scheme)
        self.assertEqual(image['id'], loc.obj)

        self.wait_for_scrub(path)
        self.stop_servers()

    def test_scrubber_delete_handles_exception(self):
        """
        Test that the scrubber handles the case where an
        exception occurs when _delete() is called. The scrubber
        should not write out queue files in this case.
        """

        # Start servers.
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           default_store='file')

        # Check that we are using a file backend.
        self.assertEqual(self.api_server.default_store, 'file')

        # add an image
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # ensure the image is marked pending delete
        response, content = http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # Remove the file from the backend.
        file_path = os.path.join(self.api_server.image_dir,
                                 str(image_id))
        os.remove(file_path)

        # Wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # run the scrubber app, and ensure it doesn't fall over
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        self.wait_for_scrub(path)

        # Make sure there are no queue files associated with image.
        queue_file_path = os.path.join(self.api_server.scrubber_datadir,
                                       str(image_id))
        self.assertFalse(os.path.exists(queue_file_path))

        self.stop_servers()

    def wait_for_scrub(self, path):
        """
        NOTE(jkoelker) The build servers sometimes take longer than 15 seconds
        to scrub. Give it up to 5 min, checking checking every 15 seconds.
        When/if it flips to deleted, bail immediately.
        """
        http = httplib2.Http()
        wait_for = 300    # seconds
        check_every = 15  # seconds
        for _ in range(wait_for / check_every):
            time.sleep(check_every)

            response, content = http.request(path, 'HEAD')
            if (response['x-image-meta-status'] == 'deleted' and
                    response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')
