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

import time

import httplib2
import psutil
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.tests import functional
from glance.tests.utils import execute


class TestMultiprocessing(functional.FunctionalTest):
    """Functional tests for the bin/glance CLI tool"""

    def setUp(self):
        self.workers = 2
        super(TestMultiprocessing, self).setUp()

    def test_multiprocessing(self):
        """Spin up the api servers with multiprocessing on"""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)
        self.stop_servers()

    def _get_children(self):
        api_pid = self.api_server.process_pid
        process = psutil.Process(api_pid)

        children = process.get_children()
        pids = [str(child.pid) for child in children]
        return pids

    def test_interrupt_avoids_respawn_storm(self):
        """
        Ensure an interrupt signal does not cause a respawn storm.
        See bug #978130
        """
        self.start_servers(**self.__dict__.copy())

        children = self._get_children()
        cmd = "kill -INT %s" % ' '.join(children)
        execute(cmd, raise_error=True)

        for _ in range(9):
            # Yeah. This totally isn't a race condition. Randomly fails
            # set at 0.05. Works most of the time at 0.10
            time.sleep(0.10)
            # ensure number of children hasn't grown
            self.assertTrue(len(children) >= len(self._get_children()))
            for child in self._get_children():
                # ensure no new children spawned
                self.assertIn(child, children, child)

        self.stop_servers()
