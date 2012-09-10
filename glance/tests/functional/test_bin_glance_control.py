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
import signal
import socket
import sys
import tempfile
import time

from glance.tests import functional
from glance.tests.utils import skip_if_disabled


class TestGlanceControl(functional.FunctionalTest):

    """Functional test for glance-control"""

    def get_versions(self):
        path = "http://%s:%d" % ("127.0.0.1", self.api_port)
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

    def _do_test_fallback_pidfile(self, pid_file):
        self.cleanup()

        self.api_server.pid_file = pid_file
        exitcode, out, err = self.api_server.start(expect_exit=True,
                                                   **self.__dict__.copy())
        lines = out.split('\n')
        warn = ('Falling back to a temp file, '
                'you can stop glance-api service using:')
        self.assertTrue(warn in lines)
        fallback = lines[lines.index(warn) + 1].split()[-1]
        self.assertTrue(os.path.exists(fallback))
        self.api_server.pid_file = fallback
        self.assertTrue(os.path.exists('/proc/%s' % self.get_pid()))

        self.stop_server(self.api_server, 'API server')

    @skip_if_disabled
    def test_fallback_pidfile_uncreateable_dir(self):
        """
        We test that glance-control falls back to a temporary pid file
        for non-existent pid file directory that cannot be created.
        """
        parent = tempfile.mkdtemp()
        os.chmod(parent, 0)
        pid_file = os.path.join(parent, 'pids', 'api.pid')
        self._do_test_fallback_pidfile(pid_file)

    @skip_if_disabled
    def test_fallback_pidfile_unwriteable_dir(self):
        """
        We test that glance-control falls back to a temporary pid file
        for unwriteable pid file directory.
        """
        parent = tempfile.mkdtemp()
        os.chmod(parent, 0)
        pid_file = os.path.join(parent, 'api.pid')
        self._do_test_fallback_pidfile(pid_file)

    @skip_if_disabled
    def test_respawn(self):
        """
        We test that the '--respawn' option causes the API server
        to be respawned after death but not after a deliberate stop
        """
        self.cleanup()
        self.api_server.server_control_options += ' --respawn'

        # start API server, allowing glance-control to continue running
        self.start_with_retry(self.api_server,
                              'api_port',
                              3,
                              expect_launch=True,
                              expect_exit=False,
                              expect_confirmation=False,
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
        launch_msg = self.wait_for_servers([self.api_server])
        self.assertTrue(launch_msg is None, launch_msg)

        # verify server health with version negotiation
        self.get_versions()

        # deliberately stop server, it should not be respawned
        proc_file = '/proc/%d' % self.get_pid()
        self.stop_server(self.api_server, 'API server')

        # ensure last server process has gone away
        process_died = lambda: not os.path.exists(proc_file)
        self.wait_for(process_died)

        # deliberately stopped server should not be respawned
        launch_msg = self.wait_for_servers([self.api_server], False)
        self.assertTrue(launch_msg is None, launch_msg)

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

        exitcode, out, err = self.api_server.start(**self.__dict__.copy())

        # ensure the service pid has been cached
        pid_cached = lambda: os.path.exists(self.api_server.pid_file)
        self.wait_for(pid_cached)

        # ensure glance-control has had a chance to waitpid on child
        time.sleep(1)

        # bouncing server should not be respawned
        launch_msg = self.wait_for_servers([self.api_server], False)
        self.assertTrue(launch_msg is None, launch_msg)

        # ensure server process has gone away
        process_died = lambda: not os.path.exists('/proc/%d' % self.get_pid())
        self.wait_for(process_died)

        # ensure the server has not been respawned
        self.connection_unavailable('bouncing')

    @skip_if_disabled
    def test_reload(self):
        """Exercise `glance-control api reload`"""
        self.cleanup()

        # start API server, allowing glance-control to continue running
        self.start_with_retry(self.api_server,
                              'api_port',
                              3,
                              expect_launch=True,
                              expect_exit=False,
                              expect_confirmation=False,
                              **self.__dict__.copy())

        # ensure the service pid has been cached
        pid_cached = lambda: os.path.exists(self.api_server.pid_file)
        self.wait_for(pid_cached)

        # ensure glance-control has had a chance to waitpid on child
        time.sleep(1)

        # verify server health with version negotiation
        self.get_versions()

        self.reload_server(self.api_server, True)

        # ensure API service port is re-activated
        launch_msg = self.wait_for_servers([self.api_server])
        self.assertTrue(launch_msg is None, launch_msg)

        # verify server health with version negotiation
        self.get_versions()

        # deliberately stop server
        proc_file = '/proc/%d' % self.get_pid()
        self.stop_server(self.api_server, 'API server')

        # ensure last server process has gone away
        process_died = lambda: not os.path.exists(proc_file)
        self.wait_for(process_died)

        # deliberately stopped server should not be respawned
        launch_msg = self.wait_for_servers([self.api_server], False)
        self.assertTrue(launch_msg is None, launch_msg)

        # ensure the server has not been respawned
        self.connection_unavailable('deliberately stopped')
