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
import functools
import os
import random
import shutil
import signal
import socket
import tempfile
import time
import unittest
import urlparse

from glance.tests.utils import execute, get_unused_port

from sqlalchemy import create_engine


def runs_sql(func):
    """
    Decorator for a test case method that ensures that the
    sql_connection setting is overridden to ensure a disk-based
    SQLite database so that arbitrary SQL statements can be
    executed out-of-process against the datastore...
    """
    @functools.wraps(func)
    def wrapped(*a, **kwargs):
        test_obj = a[0]
        orig_sql_connection = test_obj.registry_server.sql_connection
        try:
            if orig_sql_connection.startswith('sqlite'):
                test_obj.registry_server.sql_connection =\
                        "sqlite:///tests.sqlite"
            func(*a, **kwargs)
        finally:
            test_obj.registry_server.sql_connection = orig_sql_connection
    return wrapped


class Server(object):
    """
    Class used to easily manage starting and stopping
    a server during functional test runs.
    """
    def __init__(self, test_dir, port):
        """
        Creates a new Server object.

        :param test_dir: The directory where all test stuff is kept. This is
                         passed from the FunctionalTestCase.
        :param port: The port to start a server up on.
        """
        self.verbose = True
        self.debug = True
        self.no_venv = False
        self.test_dir = test_dir
        self.bind_port = port
        self.conf_file = None
        self.conf_base = None
        self.server_control = './bin/glance-control'
        self.exec_env = None

    def write_conf(self, **kwargs):
        """
        Writes the configuration file for the server to its intended
        destination.  Returns the name of the configuration file.
        """

        if self.conf_file:
            return self.conf_file_name
        if not self.conf_base:
            raise RuntimeError("Subclass did not populate config_base!")

        conf_override = self.__dict__.copy()
        if kwargs:
            conf_override.update(**kwargs)

        # A config file to use just for this test...we don't want
        # to trample on currently-running Glance servers, now do we?

        conf_file = tempfile.NamedTemporaryFile()
        conf_file.write(self.conf_base % conf_override)
        conf_file.flush()
        self.conf_file = conf_file
        self.conf_file_name = conf_file.name

        return self.conf_file_name

    def start(self, **kwargs):
        """
        Starts the server.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """

        # Ensure the configuration file is written
        self.write_conf(**kwargs)

        cmd = ("%(server_control)s %(server_name)s start "
               "%(conf_file_name)s --pid-file=%(pid_file)s"
               % self.__dict__)
        return execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env)

    def stop(self):
        """
        Spin down the server.
        """
        cmd = ("%(server_control)s %(server_name)s stop "
               "%(conf_file_name)s --pid-file=%(pid_file)s"
               % self.__dict__)
        return execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env)


class ApiServer(Server):

    """
    Server object that starts/stops/manages the API server
    """

    def __init__(self, test_dir, port, registry_port, delayed_delete=False):
        super(ApiServer, self).__init__(test_dir, port)
        self.server_name = 'api'
        self.default_store = 'file'
        self.image_dir = os.path.join(self.test_dir,
                                         "images")
        self.pid_file = os.path.join(self.test_dir,
                                         "api.pid")
        self.scrubber_datadir = os.path.join(self.test_dir,
                                             "scrubber")
        self.log_file = os.path.join(self.test_dir, "api.log")
        self.registry_port = registry_port
        self.s3_store_host = "s3.amazonaws.com"
        self.s3_store_access_key = ""
        self.s3_store_secret_key = ""
        self.s3_store_bucket = ""
        self.swift_store_auth_address = ""
        self.swift_store_user = ""
        self.swift_store_key = ""
        self.swift_store_container = ""
        self.swift_store_large_object_size = 5 * 1024
        self.swift_store_large_object_chunk_size = 200
        self.delayed_delete = delayed_delete
        self.owner_is_tenant = True
        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
filesystem_store_datadir=%(image_dir)s
default_store = %(default_store)s
bind_host = 0.0.0.0
bind_port = %(bind_port)s
registry_host = 0.0.0.0
registry_port = %(registry_port)s
log_file = %(log_file)s
s3_store_host = %(s3_store_host)s
s3_store_access_key = %(s3_store_access_key)s
s3_store_secret_key = %(s3_store_secret_key)s
s3_store_bucket = %(s3_store_bucket)s
swift_store_auth_address = %(swift_store_auth_address)s
swift_store_user = %(swift_store_user)s
swift_store_key = %(swift_store_key)s
swift_store_container = %(swift_store_container)s
swift_store_large_object_size = %(swift_store_large_object_size)s
swift_store_large_object_chunk_size = %(swift_store_large_object_chunk_size)s
delayed_delete = %(delayed_delete)s
owner_is_tenant = %(owner_is_tenant)s
scrub_time = 5
scrubber_datadir = %(scrubber_datadir)s

[pipeline:glance-api]
pipeline = versionnegotiation context apiv1app

[pipeline:versions]
pipeline = versionsapp

[app:versionsapp]
paste.app_factory = glance.api.versions:app_factory

[app:apiv1app]
paste.app_factory = glance.api.v1:app_factory

[filter:versionnegotiation]
paste.filter_factory = glance.api.middleware.version_negotiation:filter_factory

[filter:context]
paste.filter_factory = glance.common.context:filter_factory
"""


class RegistryServer(Server):

    """
    Server object that starts/stops/manages the Registry server
    """

    def __init__(self, test_dir, port):
        super(RegistryServer, self).__init__(test_dir, port)
        self.server_name = 'registry'

        default_sql_connection = 'sqlite:///'
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)

        self.pid_file = os.path.join(self.test_dir,
                                         "registry.pid")
        self.log_file = os.path.join(self.test_dir, "registry.log")
        self.owner_is_tenant = True
        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
bind_host = 0.0.0.0
bind_port = %(bind_port)s
log_file = %(log_file)s
sql_connection = %(sql_connection)s
sql_idle_timeout = 3600
api_limit_max = 1000
limit_param_default = 25
owner_is_tenant = %(owner_is_tenant)s

[pipeline:glance-registry]
pipeline = context registryapp

[app:registryapp]
paste.app_factory = glance.registry.server:app_factory

[filter:context]
context_class = glance.registry.context.RequestContext
paste.filter_factory = glance.common.context:filter_factory
"""


class ScrubberDaemon(Server):
    """
    Server object that starts/stops/manages the Scrubber server
    """

    def __init__(self, test_dir, registry_port, daemon=False):
        # NOTE(jkoelker): Set the port to 0 since we actually don't listen
        super(ScrubberDaemon, self).__init__(test_dir, 0)
        self.server_name = 'scrubber'
        self.daemon = daemon

        self.registry_port = registry_port
        self.scrubber_datadir = os.path.join(self.test_dir,
                                             "scrubber")
        self.pid_file = os.path.join(self.test_dir, "scrubber.pid")
        self.log_file = os.path.join(self.test_dir, "scrubber.log")
        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
log_file = %(log_file)s
daemon = %(daemon)s
wakeup_time = 2
scrubber_datadir = %(scrubber_datadir)s
registry_host = 0.0.0.0
registry_port = %(registry_port)s

[app:glance-scrubber]
paste.app_factory = glance.store.scrubber:app_factory
"""


class FunctionalTest(unittest.TestCase):

    """
    Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    disabled = False

    def setUp(self):

        self.test_id = random.randint(0, 100000)
        self.test_dir = os.path.join("/", "tmp", "test.%d" % self.test_id)

        self.api_port = get_unused_port()
        self.registry_port = get_unused_port()

        self.api_server = ApiServer(self.test_dir,
                                    self.api_port,
                                    self.registry_port)
        self.registry_server = RegistryServer(self.test_dir,
                                              self.registry_port)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir,
                                              self.registry_port)

        self.pid_files = [self.api_server.pid_file,
                          self.registry_server.pid_file,
                          self.scrubber_daemon.pid_file]
        self.files_to_destroy = []

    def tearDown(self):
        if not self.disabled:
            self.cleanup()
            # We destroy the test data store between each test case,
            # and recreate it, which ensures that we have no side-effects
            # from the tests
            self._reset_database(self.registry_server.sql_connection)

    def _reset_database(self, conn_string):
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

        # Start up the API and default registry server
        exitcode, out, err = self.api_server.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the API server. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-api with" in out)

        exitcode, out, err = self.registry_server.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Registry server. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-registry with" in out)

        exitcode, out, err = self.scrubber_daemon.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Scrubber daemon. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-scrubber with" in out)

        self.wait_for_servers()

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

        :param timeout: Optional, defaults to 3 seconds
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
        exitcode, out, err = self.api_server.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the API server. "
                         "Got: %s" % err)

        exitcode, out, err = self.registry_server.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the Registry server. "
                         "Got: %s" % err)

        exitcode, out, err = self.scrubber_daemon.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the Scrubber daemon. "
                         "Got: %s" % err)
        # If all went well, then just remove the test directory.
        # We only want to check the logs and stuff if something
        # went wrong...
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

        # We do this here because the @runs_sql decorator above
        # actually resets the registry server's sql_connection
        # to the original (usually memory-based SQLite connection)
        # and this block of code is run *before* the finally:
        # block in that decorator...
        self._reset_database(self.registry_server.sql_connection)

    def run_sql_cmd(self, sql):
        """
        Provides a crude mechanism to run manual SQL commands for backend
        DB verification within the functional tests.
        The raw result set is returned.
        """
        engine = create_engine(self.registry_server.sql_connection,
                               pool_recycle=30)
        return engine.execute(sql)
