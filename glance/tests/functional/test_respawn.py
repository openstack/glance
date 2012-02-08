# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Red Hat, Inc
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

"""Functional test case for the glance-control --respawn option """

import httplib2
import os
import time
import socket
import signal
import sys
import time

from glance.tests import functional
from glance.tests.utils import execute, skip_if_disabled


class TestRespawn(functional.FunctionalTest):

    """Functional test for glance-control --respawn """

    def get_versions(self):
        path = "http://%s:%d" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 300)

    def get_pid(self):
        return int(open(self.api_server.pid_file).read().strip())

    def kill_server(self):
        pid = self.get_pid()
        os.killpg(pid, signal.SIGKILL)
        return pid

    def wait_for(self, predicate):
        count = 0
        while count < 50:
            if predicate():
                break
            else:
                time.sleep(0.1)
                count += 1
        self.assertTrue(predicate())

    def connection_unavailable(self, type):
        try:
            self.get_versions()
            self.fail('%s server should not be respawned' % type)
        except socket.error:
            exc_value = sys.exc_info()[1]
            self.assertTrue('Connection refused' in exc_value or
                            'ECONNREFUSED' in exc_value)

    @skip_if_disabled
    def test_respawn(self):
        """
        We test that the '--respawn' option causes the API server
        to be respawned after death but not after a deliberate stop
        """
        self.cleanup()
        self.api_server.server_control_options += ' --respawn'

        # start API server, allowing glance-control to continue running
        self.start_server(self.api_server,
                          expect_launch=True,
                          expect_exit=False,
                          **self.__dict__.copy())

        # ensure the service pid has been cached
        pid_cached = lambda: os.path.exists(self.api_server.pid_file)
        self.wait_for(pid_cached)

        # ensure glance-control has had a chance to waitpid on child
        time.sleep(1)

        # verify server health with version negotiation
        self.get_versions()

        # server is killed ungracefully
        old_pid = self.kill_server()

        # ... but should be respawned

        # wait for pid to cycle
        pid_changed = lambda: old_pid != self.get_pid()
        self.wait_for(pid_changed)

        # ensure API service port is re-activated
        self.wait_for_servers([self.api_server.bind_port])

        # verify server health with version negotiation
        self.get_versions()

        # deliberately stop server, it should not be respawned
        proc_file = '/proc/%d' % self.get_pid()
        self.stop_server(self.api_server, 'API server')

        # ensure last server process has gone away
        process_died = lambda: not os.path.exists(proc_file)
        self.wait_for(process_died)

        # deliberately stopped server should not be respawned
        self.wait_for_servers([self.api_server.bind_port], False)

        # ensure the server has not been respawned
        self.connection_unavailable('deliberately stopped')

    @skip_if_disabled
    def test_bouncing(self):
        """
        We test that the '--respawn' option doesn't cause bouncing
        API server to be respawned
        """
        self.cleanup()
        self.api_server.server_control_options += ' --respawn'
        self.api_server.default_store = 'shouldnotexist'

        # start API server, allowing glance-control to continue running
        self.start_server(self.api_server,
                          expect_launch=False,
                          expect_exit=False,
                          **self.__dict__.copy())

        # ensure the service pid has been cached
        pid_cached = lambda: os.path.exists(self.api_server.pid_file)
        self.wait_for(pid_cached)

        # ensure glance-control has had a chance to waitpid on child
        time.sleep(1)

        # bouncing server should not be respawned
        self.wait_for_servers([self.api_server.bind_port], False)

        # ensure server process has gone away
        process_died = lambda: not os.path.exists('/proc/%d' % self.get_pid())
        self.wait_for(process_died)

        # ensure the server has not been respawned
        self.connection_unavailable('bouncing')
