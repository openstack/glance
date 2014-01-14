# Copyright 2012 OpenStack Foundation
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
Functional tests for the File store interface
"""

import BaseHTTPServer
import os
import signal
import testtools

import glance.store.http
import glance.tests.functional.store as store_tests


def get_handler_class(fixture):
    class StaticHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(fixture)))
            self.end_headers()
            self.wfile.write(fixture)
            return

        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(fixture)))
            self.end_headers()
            return

        def log_message(*args, **kwargs):
            # Override this method to prevent debug output from going
            # to stderr during testing
            return

    return StaticHTTPRequestHandler


def http_server(image_id, image_data):
    server_address = ('127.0.0.1', 0)
    handler_class = get_handler_class(image_data)
    httpd = BaseHTTPServer.HTTPServer(server_address, handler_class)
    port = httpd.socket.getsockname()[1]

    pid = os.fork()
    if pid == 0:
        httpd.serve_forever()
    else:
        return pid, port


class TestHTTPStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.http.Store'
    store_cls = glance.store.http.Store
    store_name = 'http'

    def setUp(self):
        super(TestHTTPStore, self).setUp()
        self.kill_pid = None

    def tearDown(self):
        if self.kill_pid is not None:
            os.kill(self.kill_pid, signal.SIGKILL)

        super(TestHTTPStore, self).tearDown()

    def get_store(self, **kwargs):
        store = glance.store.http.Store(context=kwargs.get('context'))
        store.configure()
        return store

    def stash_image(self, image_id, image_data):
        self.kill_pid, http_port = http_server(image_id, image_data)
        return 'http://127.0.0.1:%s/' % (http_port,)
