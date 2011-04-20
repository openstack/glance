# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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
Base test class for running non-stubbed tests (functional tests)

The FunctionalTest class contains helper methods for starting the API
and Registry server, grabbing the logs of each, cleaning up pidfiles,
and spinning down the servers.
"""

import datetime
import os
import random
import shutil
import signal
import socket
import tempfile
import time
import unittest
import urlparse

from tests.utils import execute, get_unused_port

from sqlalchemy import create_engine


class FunctionalTest(unittest.TestCase):

    """
    Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    def setUp(self):

        self.verbose = True
        self.debug = True
        self.test_id = random.randint(0, 100000)
        self.test_dir = os.path.join("/", "tmp", "test.%d" % self.test_id)

        self.api_port = get_unused_port()
        self.api_pid_file = os.path.join(self.test_dir,
                                         "glance-api.pid")
        self.api_log_file = os.path.join(self.test_dir, "apilog")

        self.registry_port = get_unused_port()
        self.registry_pid_file = ("/tmp/test.%d/glance-registry.pid"
                                  % self.test_id)
        self.registry_log_file = os.path.join(self.test_dir, "registrylog")

        self.image_dir = "/tmp/test.%d/images" % self.test_id

        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             "sqlite:///glance.sqlite")
        self.pid_files = [self.api_pid_file,
                          self.registry_pid_file]
        self.files_to_destroy = []

    def tearDown(self):
        self.cleanup()
        # We destroy the test data store between each test case,
        # and recreate it, which ensures that we have no side-effects
        # from the tests
        self._reset_database()

    def _reset_database(self):
        conn_string = self.sql_connection
        conn_pieces = urlparse.urlparse(conn_string)
        if conn_string.startswith('sqlite'):
            # We can just delete the SQLite database, which is
            # the easiest and cleanest solution
            db_path = conn_pieces.path.strip('/')
            if db_path and os.path.exists(db_path):
                os.unlink(db_path)
            # No need to recreate the SQLite DB. SQLite will
            # create it for us if it's not there...
        elif conn_string.startswith('mysql'):
            # We can execute the MySQL client to destroy and re-create
            # the MYSQL database, which is easier and less error-prone
            # than using SQLAlchemy to do this via MetaData...trust me.
            database = conn_pieces.path.strip('/')
            loc_pieces = conn_pieces.netloc.split('@')
            host = loc_pieces[1]
            auth_pieces = loc_pieces[0].split(':')
            user = auth_pieces[0]
            password = ""
            if len(auth_pieces) > 1:
                if auth_pieces[1].strip():
                    password = "-p%s" % auth_pieces[1]
            sql = ("drop database if exists %(database)s; "
                   "create database %(database)s;") % locals()
            cmd = ("mysql -u%(user)s %(password)s -h%(host)s "
                   "-e\"%(sql)s\"") % locals()
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)

    def cleanup(self):
        """
        Makes sure anything we created or started up in the
        tests are destroyed or spun down
        """

        for pid_file in self.pid_files:
            if os.path.exists(pid_file):
                pid = int(open(pid_file).read().strip())
                try:
                    os.killpg(pid, signal.SIGTERM)
                except:
                    pass  # Ignore if the process group is dead
                os.unlink(pid_file)

        for f in self.files_to_destroy:
            if os.path.exists(f):
                os.unlink(f)

    def start_servers(self, **kwargs):
        """
        Starts the API and Registry servers (bin/glance-api and
        bin/glance-registry) on unused ports and returns a tuple
        of the (api_port, registry_port, conf_file_name).

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.cleanup()

        conf_override = self.__dict__.copy()
        if kwargs:
            conf_override.update(**kwargs)

        # A config file to use just for this test...we don't want
        # to trample on currently-running Glance servers, now do we?

        conf_file = tempfile.NamedTemporaryFile()
        conf_contents = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s

[app:glance-api]
paste.app_factory = glance.server:app_factory
filesystem_store_datadir=%(image_dir)s
default_store = file
bind_host = 0.0.0.0
bind_port = %(api_port)s
registry_host = 0.0.0.0
registry_port = %(registry_port)s
log_file = %(api_log_file)s

[app:glance-registry]
paste.app_factory = glance.registry.server:app_factory
bind_host = 0.0.0.0
bind_port = %(registry_port)s
log_file = %(registry_log_file)s
sql_connection = %(sql_connection)s
sql_idle_timeout = 3600
""" % conf_override
        conf_file.write(conf_contents)
        conf_file.flush()
        self.conf_file_name = conf_file.name

        # Start up the API and default registry server
        cmd = ("./bin/glance-control api start "
               "%(conf_file_name)s --pid-file=%(api_pid_file)s"
               % self.__dict__)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the API server. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-api with" in out)

        cmd = ("./bin/glance-control registry start "
               "%(conf_file_name)s --pid-file=%(registry_pid_file)s"
               % self.__dict__)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Registry server. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-registry with" in out)

        self.wait_for_servers()

        return self.api_port, self.registry_port, self.conf_file_name

    def ping_server(self, port):
        """
        Simple ping on the port. If responsive, return True, else
        return False.

        :note We use raw sockets, not ping here, since ping uses ICMP and
        has no concept of ports...
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except socket.error, e:
            return False

    def wait_for_servers(self, timeout=3):
        """
        Tight loop, waiting for both API and registry server to be
        available on the ports. Returns when both are pingable. There
        is a timeout on waiting for the servers to come up.

        :param timeout: Optional, defaults to 3
        """
        now = datetime.datetime.now()
        timeout_time = now + datetime.timedelta(seconds=timeout)
        while (timeout_time > now):
            if self.ping_server(self.api_port) and\
               self.ping_server(self.registry_port):
                return
            now = datetime.datetime.now()
            time.sleep(0.05)
        self.assertFalse(True, "Failed to start servers.")

    def stop_servers(self):
        """
        Called to stop the started servers in a normal fashion. Note
        that cleanup() will stop the servers using a fairly draconian
        method of sending a SIGTERM signal to the servers. Here, we use
        the glance-control stop method to gracefully shut the server down.
        This method also asserts that the shutdown was clean, and so it
        is meant to be called during a normal test case sequence.
        """

        # Spin down the API and default registry server
        cmd = ("./bin/glance-control api stop "
               "%(conf_file_name)s --pid-file=%(api_pid_file)s"
               % self.__dict__)
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode,
                         "Failed to spin down the API server. "
                         "Got: %s" % err)
        cmd = ("./bin/glance-control registry stop "
               "%(conf_file_name)s --pid-file=%(registry_pid_file)s"
               % self.__dict__)
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode,
                         "Failed to spin down the Registry server. "
                         "Got: %s" % err)

        # If all went well, then just remove the test directory.
        # We only want to check the logs and stuff if something
        # went wrong...
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def run_sql_cmd(self, sql):
        engine = create_engine(self.sql_connection, pool_recycle=30)
        return engine.execute(sql)
