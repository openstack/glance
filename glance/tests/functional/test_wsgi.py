# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

"""Tests for `glance.wsgi`."""

import http.client as http
import os
import socket
import time

from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids

from glance.common import wsgi
from glance.tests import functional


class TestWSGIServer(functional.FunctionalTest):
    """WSGI server tests."""
    def test_client_socket_timeout(self):
        self.config(workers=0)
        self.config(client_socket_timeout=1)
        """Verify connections are timed out as per 'client_socket_timeout'"""
        greetings = b'Hello, World!!!'

        def hello_world(env, start_response):
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [greetings]

        server = wsgi.Server()
        server.start(hello_world, 0)
        port = server.sock.getsockname()[1]

        def get_request(delay=0.0):
            sock = socket.socket()
            sock.connect(('127.0.0.1', port))
            time.sleep(delay)
            sock.send(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
            return sock.recv(1024)

        # Should succeed - no timeout
        self.assertIn(greetings, get_request())
        # Should fail - connection timed out so we get nothing from the server
        self.assertFalse(get_request(delay=1.1))


class StagingCleanupBase:
    def _configure_api_server(self):
        self.my_api_server.deployment_flavor = 'noauth'

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': uuids.tenant1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_clean_on_start(self):
        staging = os.path.join(self.test_dir, 'staging')

        # Start the server
        self.start_server()

        # Create an image
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        data = {'name': 'image-1', 'type': 'kernel',
                'disk_format': 'aki',
                'container_format': 'aki'}
        response = self.api_post(path, headers=headers, json=data)
        self.assertEqual(http.CREATED, response.status_code)
        image = jsonutils.loads(response.text)
        image_id = image['id']

        # Stage data for the image
        path = '/v2/images/%s/stage' % image_id
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        image_data = b'ZZZZZ'
        response = self.api_put(path, headers=headers, data=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Create more files in staging, one unrecognized one, and one
        # uuid that matches nothing in the database, and some residue
        # like we would see from failed conversions and decompressions
        # for the image we created above.
        open(os.path.join(staging, 'foo'), 'w')
        open(os.path.join(staging, uuids.stale), 'w')
        open(os.path.join(staging, uuids.converting), 'w')
        converting_fn = os.path.join(staging, '%s.qcow2' % uuids.converting)
        decompressing_fn = os.path.join(staging, '%s.uc' % uuids.decompressing)
        open(converting_fn, 'w')
        open(decompressing_fn, 'w')

        self.start_server(run_staging_cleaner=True)

        # Poll to give it time to come up and do the work. Use the presence
        # of the extra files to determine if the cleanup has run yet.
        for i in range(0, 10):
            try:
                self.api_get('/v2/images')
            except Exception:
                # Not even answering queries yet
                pass
            else:
                files = os.listdir(staging)
                if len(files) == 2:
                    break

            time.sleep(1)

        # We should still find the not-an-image file...
        self.assertTrue(os.path.exists(os.path.join(staging, 'foo')))
        # ...and make sure the actually-staged image file is still present....
        self.assertTrue(os.path.exists(os.path.join(staging, image_id)))
        # ... but the stale image should be gone,
        self.assertFalse(os.path.exists(os.path.join(staging,
                                                     uuids.stale)))
        # ... along with the residue of the conversion ...
        self.assertFalse(os.path.exists(converting_fn))
        # ... and the residue of the decompression.
        self.assertFalse(os.path.exists(decompressing_fn))


class TestStagingCleanupMultistore(functional.SynchronousAPIBase,
                                   StagingCleanupBase):
    """Test for staging store cleanup on API server startup.

    This tests the multistore case.
    """
    def setUp(self):
        super(TestStagingCleanupMultistore, self).setUp()


class TestStagingCleanupSingleStore(functional.SynchronousAPIBase,
                                    StagingCleanupBase):
    """Test for staging store cleanup on API server startup.

    This tests the single store case.
    """
    def setUp(self):
        super(TestStagingCleanupSingleStore, self).setUp(single_store=True)
