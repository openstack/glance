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

import os
import socket
import time

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
            # Socket timeouts are handled rather inconsistently on Windows.
            # recv may either return nothing OR raise a ConnectionAbortedError.
            exp_exc = OSError if os.name == 'nt' else ()

            try:
                sock = socket.socket()
                sock.connect(('127.0.0.1', port))
                time.sleep(delay)
                sock.send(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
                return sock.recv(1024)
            except exp_exc:
                return None

        # Should succeed - no timeout
        self.assertIn(greetings, get_request())
        # Should fail - connection timed out so we get nothing from the server
        self.assertFalse(get_request(delay=1.1))
