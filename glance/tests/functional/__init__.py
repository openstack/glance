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
import json
import os
import re
import shutil
import signal
import socket
import time
import urlparse

from sqlalchemy import create_engine

from glance.common import utils
from glance.tests import utils as test_utils

execute, get_unused_port = test_utils.execute, test_utils.get_unused_port


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
        self.conf_file_name = None
        self.conf_base = None
        self.paste_conf_base = None
        self.server_control = './bin/glance-control'
        self.exec_env = None
        self.deployment_flavor = ''
        self.show_image_direct_url = False
        self.enable_v1_api = True
        self.enable_v2_api = True
        self.server_control_options = ''
        self.needs_database = False

    def write_conf(self, **kwargs):
        """
        Writes the configuration file for the server to its intended
        destination.  Returns the name of the configuration file and
        the over-ridden config content (may be useful for populating
        error messages).
        """
        if not self.conf_base:
            raise RuntimeError("Subclass did not populate config_base!")

        conf_override = self.__dict__.copy()
        if kwargs:
            conf_override.update(**kwargs)

        # A config file and paste.ini to use just for this test...we don't want
        # to trample on currently-running Glance servers, now do we?

        conf_dir = os.path.join(self.test_dir, 'etc')
        conf_filepath = os.path.join(conf_dir, "%s.conf" % self.server_name)
        if os.path.exists(conf_filepath):
            os.unlink(conf_filepath)
        paste_conf_filepath = conf_filepath.replace(".conf", "-paste.ini")
        if os.path.exists(paste_conf_filepath):
            os.unlink(paste_conf_filepath)
        utils.safe_mkdirs(conf_dir)

        def override_conf(filepath, overridden):
            with open(filepath, 'wb') as conf_file:
                conf_file.write(overridden)
                conf_file.flush()
                return conf_file.name

        overridden_core = self.conf_base % conf_override
        self.conf_file_name = override_conf(conf_filepath, overridden_core)

        overridden_paste = ''
        if self.paste_conf_base:
            overridden_paste = self.paste_conf_base % conf_override
            override_conf(paste_conf_filepath, overridden_paste)

        overridden = ('==Core config==\n%s\n==Paste config==\n%s' %
                      (overridden_core, overridden_paste))

        return self.conf_file_name, overridden

    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """
        Starts the server.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """

        # Ensure the configuration file is written
        overridden = self.write_conf(**kwargs)[1]

        self.create_database()

        cmd = ("%(server_control)s %(server_name)s start "
               "%(conf_file_name)s --pid-file=%(pid_file)s "
               "%(server_control_options)s"
               % self.__dict__)
        return execute(cmd,
                       no_venv=self.no_venv,
                       exec_env=self.exec_env,
                       expect_exit=expect_exit,
                       expected_exitcode=expected_exitcode,
                       context=overridden)

    def reload(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """
        Call glane-control reload for a specific server.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        cmd = ("%(server_control)s %(server_name)s reload "
               "%(conf_file_name)s --pid-file=%(pid_file)s "
               "%(server_control_options)s"
               % self.__dict__)
        return execute(cmd,
                       no_venv=self.no_venv,
                       exec_env=self.exec_env,
                       expect_exit=expect_exit,
                       expected_exitcode=expected_exitcode)

    def create_database(self):
        """Create database if required for this server"""
        if self.needs_database:
            conf_dir = os.path.join(self.test_dir, 'etc')
            utils.safe_mkdirs(conf_dir)
            conf_filepath = os.path.join(conf_dir, 'glance-manage.conf')

            with open(conf_filepath, 'wb') as conf_file:
                conf_file.write('[DEFAULT]\n')
                conf_file.write('sql_connection = %s' % self.sql_connection)
                conf_file.flush()

            cmd = ('bin/glance-manage db_sync --config-file %s'
                   % conf_filepath)
            execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env,
                    expect_exit=True)

    def stop(self):
        """
        Spin down the server.
        """
        cmd = ("%(server_control)s %(server_name)s stop "
               "%(conf_file_name)s --pid-file=%(pid_file)s"
               % self.__dict__)
        return execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env,
                       expect_exit=True)


class ApiServer(Server):

    """
    Server object that starts/stops/manages the API server
    """

    def __init__(self, test_dir, port, policy_file, delayed_delete=False,
                 pid_file=None):
        super(ApiServer, self).__init__(test_dir, port)
        self.server_name = 'api'
        self.default_store = 'file'
        self.key_file = ""
        self.cert_file = ""
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.image_dir = os.path.join(self.test_dir,
                                         "images")
        self.pid_file = pid_file or os.path.join(self.test_dir,
                                                 "api.pid")
        self.scrubber_datadir = os.path.join(self.test_dir,
                                             "scrubber")
        self.log_file = os.path.join(self.test_dir, "api.log")
        self.s3_store_host = "s3.amazonaws.com"
        self.s3_store_access_key = ""
        self.s3_store_secret_key = ""
        self.s3_store_bucket = ""
        self.s3_store_bucket_url_format = ""
        self.swift_store_auth_address = ""
        self.swift_store_user = ""
        self.swift_store_key = ""
        self.swift_store_container = ""
        self.swift_store_large_object_size = 5 * 1024
        self.swift_store_large_object_chunk_size = 200
        self.swift_store_multi_tenant = False
        self.swift_store_admin_tenants = []
        self.rbd_store_ceph_conf = ""
        self.rbd_store_pool = ""
        self.rbd_store_user = ""
        self.rbd_store_chunk_size = 4
        self.delayed_delete = delayed_delete
        self.owner_is_tenant = True
        self.workers = 0
        self.scrub_time = 5
        self.image_cache_dir = os.path.join(self.test_dir,
                                            'cache')
        self.image_cache_driver = 'sqlite'
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.server_control_options = '--capture-output'

        self.needs_database = True
        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)

        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
filesystem_store_datadir=%(image_dir)s
default_store = %(default_store)s
bind_host = 127.0.0.1
bind_port = %(bind_port)s
key_file = %(key_file)s
cert_file = %(cert_file)s
metadata_encryption_key = %(metadata_encryption_key)s
registry_host = 127.0.0.1
registry_port = %(registry_port)s
log_file = %(log_file)s
s3_store_host = %(s3_store_host)s
s3_store_access_key = %(s3_store_access_key)s
s3_store_secret_key = %(s3_store_secret_key)s
s3_store_bucket = %(s3_store_bucket)s
s3_store_bucket_url_format = %(s3_store_bucket_url_format)s
swift_store_auth_address = %(swift_store_auth_address)s
swift_store_user = %(swift_store_user)s
swift_store_key = %(swift_store_key)s
swift_store_container = %(swift_store_container)s
swift_store_large_object_size = %(swift_store_large_object_size)s
swift_store_large_object_chunk_size = %(swift_store_large_object_chunk_size)s
swift_store_multi_tenant = %(swift_store_multi_tenant)s
swift_store_admin_tenants = %(swift_store_admin_tenants)s
rbd_store_chunk_size = %(rbd_store_chunk_size)s
rbd_store_user = %(rbd_store_user)s
rbd_store_pool = %(rbd_store_pool)s
rbd_store_ceph_conf = %(rbd_store_ceph_conf)s
delayed_delete = %(delayed_delete)s
owner_is_tenant = %(owner_is_tenant)s
workers = %(workers)s
scrub_time = %(scrub_time)s
scrubber_datadir = %(scrubber_datadir)s
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
db_auto_create = False
sql_connection = %(sql_connection)s
show_image_direct_url = %(show_image_direct_url)s
enable_v1_api = %(enable_v1_api)s
enable_v2_api= %(enable_v2_api)s
[paste_deploy]
flavor = %(deployment_flavor)s
"""
        self.paste_conf_base = """[pipeline:glance-api]
pipeline = versionnegotiation unauthenticated-context rootapp

[pipeline:glance-api-caching]
pipeline = versionnegotiation unauthenticated-context cache rootapp

[pipeline:glance-api-cachemanagement]
pipeline =
    versionnegotiation
    unauthenticated-context
    cache
    cache_manage
    rootapp

[pipeline:glance-api-fakeauth]
pipeline = versionnegotiation fakeauth context rootapp

[pipeline:glance-api-noauth]
pipeline = versionnegotiation context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v1: apiv1app
/v2: apiv2app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv1app]
paste.app_factory = glance.api.v1.router:API.factory

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[filter:versionnegotiation]
paste.filter_factory =
 glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:cache]
paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

[filter:cache_manage]
paste.filter_factory =
 glance.api.middleware.cache_manage:CacheManageFilter.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory =
 glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory
"""


class RegistryServer(Server):

    """
    Server object that starts/stops/manages the Registry server
    """

    def __init__(self, test_dir, port):
        super(RegistryServer, self).__init__(test_dir, port)
        self.server_name = 'registry'

        self.needs_database = True
        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)

        self.pid_file = os.path.join(self.test_dir,
                                         "registry.pid")
        self.log_file = os.path.join(self.test_dir, "registry.log")
        self.owner_is_tenant = True
        self.server_control_options = '--capture-output'
        self.workers = 0
        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
bind_host = 127.0.0.1
bind_port = %(bind_port)s
log_file = %(log_file)s
db_auto_create = False
sql_connection = %(sql_connection)s
sql_idle_timeout = 3600
api_limit_max = 1000
limit_param_default = 25
owner_is_tenant = %(owner_is_tenant)s
workers = %(workers)s
[paste_deploy]
flavor = %(deployment_flavor)s
"""
        self.paste_conf_base = """[pipeline:glance-registry]
pipeline = unauthenticated-context registryapp

[pipeline:glance-registry-fakeauth]
pipeline = fakeauth context registryapp

[app:registryapp]
paste.app_factory = glance.registry.api.v1:API.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory =
 glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory
"""


class ScrubberDaemon(Server):
    """
    Server object that starts/stops/manages the Scrubber server
    """

    def __init__(self, test_dir, daemon=False):
        # NOTE(jkoelker): Set the port to 0 since we actually don't listen
        super(ScrubberDaemon, self).__init__(test_dir, 0)
        self.server_name = 'scrubber'
        self.daemon = daemon

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
registry_host = 127.0.0.1
registry_port = %(registry_port)s
"""


class FunctionalTest(test_utils.BaseTestCase):

    """
    Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    inited = False
    disabled = False
    launched_servers = []

    def setUp(self):
        super(FunctionalTest, self).setUp()
        self.test_id, self.test_dir = test_utils.get_isolated_test_env()

        self.api_protocol = 'http'
        self.api_port = get_unused_port()
        self.registry_port = get_unused_port()

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('schema-image.json', conf_dir)
        self.copy_data_file('policy.json', conf_dir)
        self.policy_file = os.path.join(conf_dir, 'policy.json')

        self.api_server = ApiServer(self.test_dir,
                                    self.api_port,
                                    self.policy_file)

        self.registry_server = RegistryServer(self.test_dir,
                                              self.registry_port)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir)

        self.pid_files = [self.api_server.pid_file,
                          self.registry_server.pid_file,
                          self.scrubber_daemon.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []

    def tearDown(self):
        if not self.disabled:
            self.cleanup()
            # We destroy the test data store between each test case,
            # and recreate it, which ensures that we have no side-effects
            # from the tests
            self._reset_database(self.registry_server.sql_connection)
            self._reset_database(self.api_server.sql_connection)
        super(FunctionalTest, self).tearDown()

    def set_policy_rules(self, rules):
        fap = open(self.policy_file, 'w')
        fap.write(json.dumps(rules))
        fap.close()

    def _reset_database(self, conn_string):
        conn_pieces = urlparse.urlparse(conn_string)
        if conn_string.startswith('sqlite'):
            # We leave behind the sqlite DB for failing tests to aid
            # in diagnosis, as the file size is relatively small and
            # won't interfere with subsequent tests as it's in a per-
            # test directory (which is blown-away if the test is green)
            pass
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

    def start_server(self,
                     server,
                     expect_launch,
                     expect_exit=True,
                     expected_exitcode=0,
                     **kwargs):
        """
        Starts a server on an unused port.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the server.

        :param server: the server to launch
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        :param expected_exitcode: expected exitcode from the launcher
        """
        self.cleanup()

        # Start up the requested server
        exitcode, out, err = server.start(expect_exit=expect_exit,
                                          expected_exitcode=expected_exitcode,
                                          **kwargs)
        if expect_exit:
            self.assertEqual(expected_exitcode, exitcode,
                             "Failed to spin up the requested server. "
                             "Got: %s" % err)

            self.assertTrue(re.search("Starting glance-[a-z]+ with", out))

        self.launched_servers.append(server)

        launch_msg = self.wait_for_servers([server], expect_launch)
        self.assertTrue(launch_msg is None, launch_msg)

    def start_with_retry(self, server, port_name, max_retries,
                         expect_launch=True, expect_exit=True,
                         expect_confirmation=True, **kwargs):
        """
        Starts a server, with retries if the server launches but
        fails to start listening on the expected port.

        :param server: the server to launch
        :param port_name: the name of the port attribute
        :param max_retries: the maximum number of attempts
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        :param expect_confirmation: true iff launch confirmation msg
                                    expected on stdout
        """
        launch_msg = None
        for i in range(0, max_retries):
            exitcode, out, err = server.start(expect_exit=expect_exit,
                                              **kwargs)
            name = server.server_name
            self.assertEqual(0, exitcode,
                             "Failed to spin up the %s server. "
                             "Got: %s" % (name, err))
            if expect_confirmation:
                self.assertTrue(("Starting glance-%s with" % name) in out)
            launch_msg = self.wait_for_servers([server], expect_launch)
            if launch_msg:
                server.stop()
                server.bind_port = get_unused_port()
                setattr(self, port_name, server.bind_port)
            else:
                self.launched_servers.append(server)
                break
        self.assertTrue(launch_msg is None, launch_msg)

    def start_servers(self, **kwargs):
        """
        Starts the API and Registry servers (bin/glance-control api start
        & bin/glance-control registry start) on unused ports.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.cleanup()

        # Start up the API and default registry server

        # We start the registry server first, as the API server config
        # depends on the registry port - this ordering allows for
        # retrying the launch on a port clash
        self.start_with_retry(self.registry_server, 'registry_port', 3,
                              **kwargs)
        kwargs['registry_port'] = self.registry_server.bind_port

        self.start_with_retry(self.api_server, 'api_port', 3, **kwargs)

        exitcode, out, err = self.scrubber_daemon.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Scrubber daemon. "
                         "Got: %s" % err)
        self.assertTrue("Starting glance-scrubber with" in out)

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

    def wait_for_servers(self, servers, expect_launch=True, timeout=10):
        """
        Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Glance server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 3 seconds
        :return: None if launch expectation is met, otherwise an
                 assertion message
        """
        now = datetime.datetime.now()
        timeout_time = now + datetime.timedelta(seconds=timeout)
        replied = []
        while (timeout_time > now):
            pinged = 0
            for server in servers:
                if self.ping_server(server.bind_port):
                    pinged += 1
                    if server not in replied:
                        replied.append(server)
            if pinged == len(servers):
                msg = 'Unexpected server launch status'
                return None if expect_launch else msg
            now = datetime.datetime.now()
            time.sleep(0.05)

        failed = list(set(servers) - set(replied))
        msg = 'Unexpected server launch status for: '
        for f in failed:
            msg += ('%s, ' % f.server_name)
            if os.path.exists(f.pid_file):
                pid = int(open(f.pid_file).read().strip())
                trace = f.pid_file.replace('.pid', '.trace')
                cmd = 'strace -p %d -o %s' % (pid, trace)
                execute(cmd, raise_error=False, expect_exit=False)
                time.sleep(0.5)
                if os.path.exists(trace):
                    msg += ('\nstrace:\n%s\n' % open(trace).read())

        if 'NOSE_GLANCELOGCAPTURE' in os.environ:
            msg += self.dump_logs(failed)

        return msg if expect_launch else None

    def reload_server(self,
                      server,
                      expect_launch,
                      expect_exit=True,
                      expected_exitcode=0,
                      **kwargs):
        """
        Reload a running server

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the server.

        :param server: the server to launch
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        :param expected_exitcode: expected exitcode from the launcher
        """
        self.cleanup()

        # Start up the requested server
        exitcode, out, err = server.reload(expect_exit=expect_exit,
                                           expected_exitcode=expected_exitcode,
                                           **kwargs)
        if expect_exit:
            self.assertEqual(expected_exitcode, exitcode,
                             "Failed to spin up the requested server. "
                             "Got: %s" % err)

            self.assertTrue(re.search("Restarting glance-[a-z]+ with", out))

        self.launched_servers.append(server)

        launch_msg = self.wait_for_servers([server], expect_launch)
        self.assertTrue(launch_msg is None, launch_msg)

    def stop_server(self, server, name):
        """
        Called to stop a single server in a normal fashion using the
        glance-control stop method to gracefully shut the server down.

        :param server: the server to stop
        """
        # Spin down the requested server
        exitcode, out, err = server.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the %s server. Got: %s" %
                         (err, name))

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
        self.stop_server(self.api_server, 'API server')
        self.stop_server(self.registry_server, 'Registry server')
        self.stop_server(self.scrubber_daemon, 'Scrubber daemon')

        # If all went well, then just remove the test directory.
        # We only want to check the logs and stuff if something
        # went wrong...
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

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

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def dump_logs(self, servers=None):
        dump = ''
        logs = [s.log_file for s in (servers or self.launched_servers)]
        for log in logs:
            dump += '\nContent of %s:\n\n' % log
            if os.path.exists(log):
                f = open(log, 'r')
                for line in f:
                    dump += line
            else:
                dump += '<empty>'
        return dump
