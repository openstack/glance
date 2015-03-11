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

from glance.tests import functional
from glance.tests.utils import execute


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

    def test_reload_workers(self):
        """Test SIGHUP picks up new workers value.

        This test requires around 2 minutes time for execution.
        """
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

        for _ in range(6000):
            for server in ('api', 'registry'):
                pre_pids[server] = self._get_children(server)
            if check_pids(pre_pids['api'], workers=1):
                if check_pids(pre_pids['registry'], workers=1):
                    break
            time.sleep(0.01)

        for server in ('api', 'registry'):
            self.assertTrue(check_pids(pre_pids[server], workers=1))
            # Labour costs have fallen
            set_config_value(self._conffile(server), 'workers', '2')
            cmd = "kill -HUP %s" % self._get_parent(server)
            execute(cmd, raise_error=True)

        for _ in range(6000):
            for server in ('api', 'registry'):
                post_pids[server] = self._get_children(server)
            if check_pids(pre_pids['registry'], post_pids['registry']):
                if check_pids(pre_pids['api'], post_pids['api']):
                    break
            time.sleep(0.01)

        for server in ('api', 'registry'):
            self.assertTrue(check_pids(pre_pids[server], post_pids[server]))
