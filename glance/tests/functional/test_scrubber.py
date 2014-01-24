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

import httplib2
from six.moves import xrange
import swiftclient

from glance.common import crypt
from glance.openstack.common import jsonutils
from glance.openstack.common import units
from glance.store.swift import StoreLocation
from glance.tests import functional
from glance.tests.functional.store.test_swift import parse_config
from glance.tests.functional.store.test_swift import read_config
from glance.tests.functional.store.test_swift import swift_connect
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
        self.start_servers(delayed_delete=True, daemon=True)

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
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        self.wait_for_scrub(path)

        self.stop_servers()

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False)

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
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
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

    def test_scrubber_app_against_swift(self):
        """
        test that the glance-scrubber script runs successfully against a swift
        backend when not in daemon mode
        """
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.skipTest(msg)

        raw_config = read_config(config_path)
        swift_config = parse_config(raw_config)

        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           default_store='swift', **swift_config)

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
        # ensure the request was successful and the image is active
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # ensure the image is marked pending delete
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # call the scrubber to scrub images
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        # ensure the image has been successfully deleted
        self.wait_for_scrub(path)

        self.stop_servers()

    def test_scrubber_with_metadata_enc(self):
        """
        test that files written to scrubber_data_dir use
        metadata_encryption_key when available to encrypt the location
        """
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.skipTest(msg)

        raw_config = read_config(config_path)
        swift_config = parse_config(raw_config)

        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=True,
                           default_store='swift', **swift_config)

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
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
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
        loc = StoreLocation({})
        loc.parse_uri(decrypted_uri)

        self.assertIn(loc.scheme, ("swift+http", "swift+https"))
        self.assertEqual(image['id'], loc.obj)

        self.wait_for_scrub(path)

        self.stop_servers()

    def test_scrubber_handles_swift_missing(self):
        """
        Test that the scrubber handles the case where the image to be scrubbed
        is missing from swift
        """
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.skipTest(msg)

        raw_config = read_config(config_path)
        swift_config = parse_config(raw_config)

        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           default_store='swift', **swift_config)

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
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # ensure the image is marked pending delete
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # go directly to swift and remove the image object
        swift = swift_connect(swift_config['swift_store_auth_address'],
                              swift_config['swift_store_auth_version'],
                              swift_config['swift_store_user'],
                              swift_config['swift_store_key'])
        swift.delete_object(swift_config['swift_store_container'], image_id)
        try:
            swift.head_object(swift_config['swift_store_container'], image_id)
            self.fail('image should have been deleted from swift')
        except swiftclient.ClientException as e:
            self.assertEqual(e.http_status, 404)

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # run the scrubber app, and ensure it doesn't fall over
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

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
        self.assertEqual(response.status, 201)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # ensure the image is marked pending delete
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
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
        for _ in xrange(wait_for / check_every):
            time.sleep(check_every)

            response, content = http.request(path, 'HEAD')
            if (response['x-image-meta-status'] == 'deleted' and
                    response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')
