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

import os
import re
import time

import psutil
import requests

from glance.tests import functional
from glance.tests.utils import execute

TEST_VAR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '../', 'var'))


def set_config_value(filepath, key, value):
    """Set 'key = value' in config file"""
    replacement_line = '%s = %s\n' % (key, value)
    match = re.compile('^%s\s+=' % key).match
    with open(filepath, 'r+') as f:
        lines = f.readlines()
        f.seek(0, 0)
        f.truncate()
        for line in lines:
            f.write(line if not match(line) else replacement_line)


class TestReload(functional.FunctionalTest):
    """Test configuration reload"""

    def setUp(self):
        self.workers = 1
        super(TestReload, self).setUp()

    def tearDown(self):
        self.stop_servers()
        super(TestReload, self).tearDown()

    def ticker(self, message, seconds=60, tick=0.01):
        """
        Allows repeatedly testing for an expected result
        for a finite amount of time.

        :param message: Message to display on timeout
        :param seconds: Time in seconds after which we timeout
        :param tick: Time to sleep before rechecking for expected result
        :returns: 'True' or fails the test with 'message' on timeout
        """
        # We default to allowing 60 seconds timeout but
        # typically only a few hundredths of a second
        # are needed.
        num_ticks = seconds * (1.0 / tick)
        count = 0
        while count < num_ticks:
            count += 1
            time.sleep(tick)
            yield
        self.fail(message)

    def _get_children(self, server):
        pid = None
        pid = self._get_parent(server)
        process = psutil.Process(pid)
        children = process.get_children()
        pids = set()
        for child in children:
            pids.add(child.pid)
        return pids

    def _get_parent(self, server):
        if server == 'api':
            return self.api_server.process_pid
        elif server == 'registry':
            return self.registry_server.process_pid

    def _conffile(self, service):
        conf_dir = os.path.join(self.test_dir, 'etc')
        conf_filepath = os.path.join(conf_dir, '%s.conf' % service)
        return conf_filepath

    def _url(self, protocol, path):
        return '%s://127.0.0.1:%d%s' % (protocol, self.api_port, path)

    def test_reload(self):
        """Test SIGHUP picks up new config values"""
        def check_pids(pre, post=None, workers=2):
            if post is None:
                if len(pre) == workers:
                    return True
                else:
                    return False
            if len(post) == workers:
                # Check new children have different pids
                if post.intersection(pre) == set():
                    return True
            return False
        self.api_server.fork_socket = False
        self.registry_server.fork_socket = False
        self.start_servers(fork_socket=False, **vars(self))

        pre_pids = {}
        post_pids = {}

        # Test changing the workers value creates all new children
        # This recycles the existing socket
        msg = 'Start timeout'
        for _ in self.ticker(msg):
            for server in ('api', 'registry'):
                pre_pids[server] = self._get_children(server)
            if check_pids(pre_pids['api'], workers=1):
                if check_pids(pre_pids['registry'], workers=1):
                    break

        for server in ('api', 'registry'):
            # Labour costs have fallen
            set_config_value(self._conffile(server), 'workers', '2')
            cmd = "kill -HUP %s" % self._get_parent(server)
            execute(cmd, raise_error=True)

        msg = 'Worker change timeout'
        for _ in self.ticker(msg):
            for server in ('api', 'registry'):
                post_pids[server] = self._get_children(server)
            if check_pids(pre_pids['registry'], post_pids['registry']):
                if check_pids(pre_pids['api'], post_pids['api']):
                    break

        # Test changing from http to https
        # This recycles the existing socket
        path = self._url('http', '/')
        response = requests.get(path)
        self.assertEqual(300, response.status_code)
        del response  # close socket so that process audit is reliable

        pre_pids['api'] = self._get_children('api')
        key_file = os.path.join(TEST_VAR_DIR, 'privatekey.key')
        set_config_value(self._conffile('api'), 'key_file', key_file)
        cert_file = os.path.join(TEST_VAR_DIR, 'certificate.crt')
        set_config_value(self._conffile('api'), 'cert_file', cert_file)
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)

        msg = 'http to https timeout'
        for _ in self.ticker(msg):
            post_pids['api'] = self._get_children('api')
            if check_pids(pre_pids['api'], post_pids['api']):
                break

        ca_file = os.path.join(TEST_VAR_DIR, 'ca.crt')
        path = self._url('https', '/')
        response = requests.get(path, verify=ca_file)
        self.assertEqual(300, response.status_code)
        del response

        # Test https restart
        # This recycles the existing socket
        pre_pids['api'] = self._get_children('api')
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)

        msg = 'https restart timeout'
        for _ in self.ticker(msg):
            post_pids['api'] = self._get_children('api')
            if check_pids(pre_pids['api'], post_pids['api']):
                break

        ca_file = os.path.join(TEST_VAR_DIR, 'ca.crt')
        path = self._url('https', '/')
        response = requests.get(path, verify=ca_file)
        self.assertEqual(300, response.status_code)
        del response

        # Test changing the https bind_host
        # This requires a new socket
        pre_pids['api'] = self._get_children('api')
        set_config_value(self._conffile('api'), 'bind_host', '127.0.0.1')
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)

        msg = 'https bind_host timeout'
        for _ in self.ticker(msg):
            post_pids['api'] = self._get_children('api')
            if check_pids(pre_pids['api'], post_pids['api']):
                break

        path = self._url('https', '/')
        response = requests.get(path, verify=ca_file)
        self.assertEqual(300, response.status_code)
        del response

        # Test https -> http
        # This recycles the existing socket
        pre_pids['api'] = self._get_children('api')
        set_config_value(self._conffile('api'), 'key_file', '')
        set_config_value(self._conffile('api'), 'cert_file', '')
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)

        msg = 'https to http timeout'
        for _ in self.ticker(msg):
            post_pids['api'] = self._get_children('api')
            if check_pids(pre_pids['api'], post_pids['api']):
                break

        path = self._url('http', '/')
        response = requests.get(path)
        self.assertEqual(300, response.status_code)
        del response

        # Test changing the http bind_host
        # This requires a new socket
        pre_pids['api'] = self._get_children('api')
        set_config_value(self._conffile('api'), 'bind_host', '127.0.0.1')
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)

        msg = 'http bind_host timeout'
        for _ in self.ticker(msg):
            post_pids['api'] = self._get_children('api')
            if check_pids(pre_pids['api'], post_pids['api']):
                break

        path = self._url('http', '/')
        response = requests.get(path)
        self.assertEqual(300, response.status_code)
        del response

        # Test logging configuration change
        # This recycles the existing socket
        conf_dir = os.path.join(self.test_dir, 'etc')
        log_file = conf_dir + 'new.log'
        self.assertFalse(os.path.exists(log_file))
        set_config_value(self._conffile('api'), 'log_file', log_file)
        cmd = "kill -HUP %s" % self._get_parent('api')
        execute(cmd, raise_error=True)
        msg = 'No new log file created'
        for _ in self.ticker(msg):
            if os.path.exists(log_file):
                break
