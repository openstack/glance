# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack, LLC
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

"""Monkey patch tests"""

import datetime
import eventlet
import eventlet.patcher
import time
import webob.dec
import webob.exc

from glance.common import client
from glance.common import exception
from glance.common import wsgi
from glance.openstack.common import timeutils
from glance.tests import functional
from glance.tests import utils


eventlet.patcher.monkey_patch(socket=True)


def MockServerSleepTestApp(name, sleep_time):
    class App(object):
        """
        Test WSGI application concurrency
        """
        def __init__(self):
            """
            Initialize app with a name and port.
            """
            self.name = name
            self.sleep_time = sleep_time

        @webob.dec.wsgify
        def __call__(self, request):
            """
            Handles all requests to the application.
            """
            base = "http://%s" % request.host
            path = request.path_qs

            if path == "/sleep":
                time.sleep(self.sleep_time)
                return "sleep"

            elif path == "/test":
                return "test"

            return "fail"

    return App


class TestClientServerInteractions(functional.FunctionalTest):

    def setUp(self):
        super(TestClientServerInteractions, self).setUp()
        self.port_one = utils.get_unused_port()
        server_one = wsgi.Server()
        self.config(bind_host='127.0.0.1')
        self.config(workers=1)
        self.sleep_time = 1
        server_one.start(MockServerSleepTestApp("one",
                                                self.sleep_time)(),
                         self.port_one)

    def test_time_is_monkey_patched(self):
        """
        Test GET with no redirect
        """

        def fast(port):
            c = client.BaseClient("127.0.0.1", port)
            start = datetime.datetime.now()
            c.do_request("GET", "/test")
            end = datetime.datetime.now()
            secs = timeutils.delta_seconds(start, end)
            self.assertTrue(secs < self.sleep_time,
                            "The test took to long %f" % (secs))

        def slow(port):
            c = client.BaseClient("127.0.0.1", port)
            response = c.do_request("GET", "/sleep")
            self.assertEquals(200, response.status)
            self.assertEquals("sleep", response.read())

        gt = eventlet.spawn(slow, self.port_one)
        gt2 = eventlet.spawn(fast, self.port_one)
        gt.wait()
        gt2.wait()
