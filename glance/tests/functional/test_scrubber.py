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
from oslo_serialization import jsonutils
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

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

    def _send_http_request(self, path, method, body=None):
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream'
        }
        return httplib2.Http().request(path, method, body, headers)

    def test_delayed_delete(self):
        """
        test that images don't get deleted immediately and that the scrubber
        scrubs them
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=True,
                           metadata_encryption_key='')
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_http_request(path, 'POST', body='XXX')
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image['id'])
        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(200, response.status)
        response, content = self._send_http_request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        self.wait_for_scrub(path)

        self.stop_servers()

    def test_delayed_delete_with_trustedauth_registry(self):
        """
        test that images don't get deleted immediately and that the scrubber
        scrubs them when registry is operating in trustedauth mode
        """
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.registry_server.deployment_flavor = 'trusted-auth'
        self.start_servers(delayed_delete=True, daemon=True,
                           metadata_encryption_key='',
                           send_identity_headers=True)
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': 'deae8923-075d-4287-924b-840fb2644874',
            'X-Roles': 'admin',
        }
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        headers.update(base_headers)
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
        response, content = http.request(path, 'DELETE', headers=base_headers)
        self.assertEqual(200, response.status)

        response, content = http.request(path, 'HEAD', headers=base_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        self.wait_for_scrub(path, headers=base_headers)

        self.stop_servers()

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='')

        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_http_request(path, 'POST', body='XXX')
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image['id'])
        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(200, response.status)

        response, content = self._send_http_request(path, 'HEAD')
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

    def test_scrubber_app_with_trustedauth_registry(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode and with a registry that operates in trustedauth mode
        """
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'
        self.registry_server.deployment_flavor = 'trusted-auth'
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='',
                           send_identity_headers=True)
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': 'deae8923-075d-4287-924b-840fb2644874',
            'X-Roles': 'admin',
        }
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        headers.update(base_headers)
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
        response, content = http.request(path, 'DELETE', headers=base_headers)
        self.assertEqual(200, response.status)

        response, content = http.request(path, 'HEAD', headers=base_headers)
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

        self.wait_for_scrub(path, headers=base_headers)

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
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_http_request(path, 'POST', body='XXX')
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image['id'])
        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # ensure the image is marked pending delete
        response, content = self._send_http_request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # Remove the file from the backend.
        file_path = os.path.join(self.api_server.image_dir, image['id'])
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

        self.stop_servers()

    def wait_for_scrub(self, path, headers=None):
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

            response, content = http.request(path, 'HEAD', headers=headers)
            if (response['x-image-meta-status'] == 'deleted' and
                    response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')
