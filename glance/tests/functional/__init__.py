# Copyright 2011 OpenStack Foundation
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

import atexit
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import sys
import tempfile
import time

import fixtures
from oslo_serialization import jsonutils
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import six.moves.urllib.parse as urlparse
import testtools

from glance.common import utils
from glance.db.sqlalchemy import api as db_api
from glance import tests as glance_tests
from glance.tests import utils as test_utils

execute, get_unused_port = test_utils.execute, test_utils.get_unused_port
tracecmd_osmap = {'Linux': 'strace', 'FreeBSD': 'truss'}


class Server(object):
    """
    Class used to easily manage starting and stopping
    a server during functional test runs.
    """
    def __init__(self, test_dir, port, sock=None):
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
        self.exec_env = None
        self.deployment_flavor = ''
        self.show_image_direct_url = False
        self.show_multiple_locations = False
        self.property_protection_file = ''
        self.enable_v1_api = True
        self.enable_v2_api = True
        self.enable_v3_api = True
        self.enable_v1_registry = True
        self.enable_v2_registry = True
        self.needs_database = False
        self.log_file = None
        self.sock = sock
        self.fork_socket = True
        self.process_pid = None
        self.server_module = None
        self.stop_kill = False
        self.use_user_token = False
        self.send_identity_credentials = False

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
            with open(filepath, 'w') as conf_file:
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
        self.write_conf(**kwargs)

        self.create_database()

        cmd = ("%(server_module)s --config-file %(conf_file_name)s"
               % {"server_module": self.server_module,
                  "conf_file_name": self.conf_file_name})
        cmd = "%s -m %s" % (sys.executable, cmd)
        # close the sock and release the unused port closer to start time
        if self.exec_env:
            exec_env = self.exec_env.copy()
        else:
            exec_env = {}
        pass_fds = set()
        if self.sock:
            if not self.fork_socket:
                self.sock.close()
                self.sock = None
            else:
                fd = os.dup(self.sock.fileno())
                exec_env[utils.GLANCE_TEST_SOCKET_FD_STR] = str(fd)
                pass_fds.add(fd)
                self.sock.close()

        self.process_pid = test_utils.fork_exec(cmd,
                                                logfile=os.devnull,
                                                exec_env=exec_env,
                                                pass_fds=pass_fds)

        self.stop_kill = not expect_exit
        if self.pid_file:
            pf = open(self.pid_file, 'w')
            pf.write('%d\n' % self.process_pid)
            pf.close()
        if not expect_exit:
            rc = 0
            try:
                os.kill(self.process_pid, 0)
            except OSError:
                raise RuntimeError("The process did not start")
        else:
            rc = test_utils.wait_for_fork(
                self.process_pid,
                expected_exitcode=expected_exitcode)
        # avoid an FD leak
        if self.sock:
            os.close(fd)
            self.sock = None
        return (rc, '', '')

    def reload(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """
        Start and stop the service to reload

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.stop()
        return self.start(expect_exit=expect_exit,
                          expected_exitcode=expected_exitcode, **kwargs)

    def create_database(self):
        """Create database if required for this server"""
        if self.needs_database:
            conf_dir = os.path.join(self.test_dir, 'etc')
            utils.safe_mkdirs(conf_dir)
            conf_filepath = os.path.join(conf_dir, 'glance-manage.conf')

            with open(conf_filepath, 'w') as conf_file:
                conf_file.write('[DEFAULT]\n')
                conf_file.write('sql_connection = %s' % self.sql_connection)
                conf_file.flush()

            glance_db_env = 'GLANCE_DB_TEST_SQLITE_FILE'
            if glance_db_env in os.environ:
                # use the empty db created and cached as a tempfile
                # instead of spending the time creating a new one
                db_location = os.environ[glance_db_env]
                os.system('cp %s %s/tests.sqlite'
                          % (db_location, self.test_dir))
            else:
                cmd = ('%s -m glance.cmd.manage --config-file %s db sync' %
                       (sys.executable, conf_filepath))
                execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env,
                        expect_exit=True)

                # copy the clean db to a temp location so that it
                # can be reused for future tests
                (osf, db_location) = tempfile.mkstemp()
                os.close(osf)
                os.system('cp %s/tests.sqlite %s'
                          % (self.test_dir, db_location))
                os.environ[glance_db_env] = db_location

                # cleanup the temp file when the test suite is
                # complete
                def _delete_cached_db():
                    try:
                        os.remove(os.environ[glance_db_env])
                    except Exception:
                        glance_tests.logger.exception(
                            "Error cleaning up the file %s" %
                            os.environ[glance_db_env])
                atexit.register(_delete_cached_db)

    def stop(self):
        """
        Spin down the server.
        """
        if not self.process_pid:
            raise Exception('why is this being called? %s' % self.server_name)

        if self.stop_kill:
            os.kill(self.process_pid, signal.SIGTERM)
        rc = test_utils.wait_for_fork(self.process_pid, raise_error=False)
        return (rc, '', '')

    def dump_log(self, name):
        log = logging.getLogger(name)
        if not self.log_file or not os.path.exists(self.log_file):
            return
        fptr = open(self.log_file, 'r')
        for line in fptr:
            log.info(line.strip())


class ApiServer(Server):

    """
    Server object that starts/stops/manages the API server
    """

    def __init__(self, test_dir, port, policy_file, delayed_delete=False,
                 pid_file=None, sock=None, **kwargs):
        super(ApiServer, self).__init__(test_dir, port, sock=sock)
        self.server_name = 'api'
        self.server_module = 'glance.cmd.%s' % self.server_name
        self.default_store = kwargs.get("default_store", "file")
        self.key_file = ""
        self.cert_file = ""
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.image_dir = os.path.join(self.test_dir, "images")
        self.pid_file = pid_file or os.path.join(self.test_dir, "api.pid")
        self.log_file = os.path.join(self.test_dir, "api.log")
        self.image_size_cap = 1099511627776
        self.delayed_delete = delayed_delete
        self.owner_is_tenant = True
        self.workers = 0
        self.scrub_time = 5
        self.image_cache_dir = os.path.join(self.test_dir,
                                            'cache')
        self.image_cache_driver = 'sqlite'
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.property_protection_rule_format = 'roles'
        self.image_member_quota = 10
        self.image_property_quota = 10
        self.image_tag_quota = 10
        self.image_location_quota = 2
        self.disable_path = None

        self.needs_database = True
        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.data_api = kwargs.get("data_api",
                                   "glance.db.sqlalchemy.api")
        self.user_storage_quota = '0'
        self.lock_path = self.test_dir

        self.location_strategy = 'location_order'
        self.store_type_location_strategy_preference = ""

        self.send_identity_headers = False

        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
default_log_levels = eventlet.wsgi.server=DEBUG
bind_host = 127.0.0.1
bind_port = %(bind_port)s
key_file = %(key_file)s
cert_file = %(cert_file)s
metadata_encryption_key = %(metadata_encryption_key)s
registry_host = 127.0.0.1
registry_port = %(registry_port)s
use_user_token = %(use_user_token)s
send_identity_credentials = %(send_identity_credentials)s
log_file = %(log_file)s
image_size_cap = %(image_size_cap)d
delayed_delete = %(delayed_delete)s
owner_is_tenant = %(owner_is_tenant)s
workers = %(workers)s
scrub_time = %(scrub_time)s
send_identity_headers = %(send_identity_headers)s
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
data_api = %(data_api)s
sql_connection = %(sql_connection)s
show_image_direct_url = %(show_image_direct_url)s
show_multiple_locations = %(show_multiple_locations)s
user_storage_quota = %(user_storage_quota)s
enable_v1_api = %(enable_v1_api)s
enable_v2_api = %(enable_v2_api)s
enable_v3_api = %(enable_v3_api)s
lock_path = %(lock_path)s
property_protection_file = %(property_protection_file)s
property_protection_rule_format = %(property_protection_rule_format)s
image_member_quota=%(image_member_quota)s
image_property_quota=%(image_property_quota)s
image_tag_quota=%(image_tag_quota)s
image_location_quota=%(image_location_quota)s
location_strategy=%(location_strategy)s
allow_additional_image_properties = True
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
[paste_deploy]
flavor = %(deployment_flavor)s
[store_type_location_strategy]
store_type_preference = %(store_type_location_strategy_preference)s
[glance_store]
filesystem_store_datadir=%(image_dir)s
default_store = %(default_store)s
"""
        self.paste_conf_base = """[pipeline:glance-api]
pipeline = healthcheck versionnegotiation gzip unauthenticated-context rootapp

[pipeline:glance-api-caching]
pipeline = healthcheck versionnegotiation gzip unauthenticated-context
 cache rootapp

[pipeline:glance-api-cachemanagement]
pipeline =
    healthcheck
    versionnegotiation
    gzip
    unauthenticated-context
    cache
    cache_manage
    rootapp

[pipeline:glance-api-fakeauth]
pipeline = healthcheck versionnegotiation gzip fakeauth context rootapp

[pipeline:glance-api-noauth]
pipeline = healthcheck versionnegotiation gzip context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v1: apiv1app
/v2: apiv2app
/v3: apiv3app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv1app]
paste.app_factory = glance.api.v1.router:API.factory

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[app:apiv3app]
paste.app_factory = glance.api.v3.router:API.factory

[filter:healthcheck]
paste.filter_factory = oslo_middleware:Healthcheck.factory
backends = disable_by_file
disable_by_file_path = %(disable_path)s

[filter:versionnegotiation]
paste.filter_factory =
 glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:gzip]
paste.filter_factory = glance.api.middleware.gzip:GzipMiddleware.factory

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

    def __init__(self, test_dir, port, policy_file, sock=None):
        super(RegistryServer, self).__init__(test_dir, port, sock=sock)
        self.server_name = 'registry'
        self.server_module = 'glance.cmd.%s' % self.server_name

        self.needs_database = True
        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)

        self.pid_file = os.path.join(self.test_dir, "registry.pid")
        self.log_file = os.path.join(self.test_dir, "registry.log")
        self.owner_is_tenant = True
        self.workers = 0
        self.api_version = 1
        self.user_storage_quota = '0'
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.disable_path = None

        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
bind_host = 127.0.0.1
bind_port = %(bind_port)s
log_file = %(log_file)s
sql_connection = %(sql_connection)s
sql_idle_timeout = 3600
api_limit_max = 1000
limit_param_default = 25
owner_is_tenant = %(owner_is_tenant)s
enable_v2_registry = %(enable_v2_registry)s
workers = %(workers)s
user_storage_quota = %(user_storage_quota)s
metadata_encryption_key = %(metadata_encryption_key)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
[paste_deploy]
flavor = %(deployment_flavor)s
"""
        self.paste_conf_base = """[pipeline:glance-registry]
pipeline = healthcheck unauthenticated-context registryapp

[pipeline:glance-registry-fakeauth]
pipeline = healthcheck fakeauth context registryapp

[pipeline:glance-registry-trusted-auth]
pipeline = healthcheck context registryapp

[app:registryapp]
paste.app_factory = glance.registry.api:API.factory

[filter:healthcheck]
paste.filter_factory = oslo_middleware:Healthcheck.factory
backends = disable_by_file
disable_by_file_path = %(disable_path)s

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

    def __init__(self, test_dir, policy_file, daemon=False, **kwargs):
        # NOTE(jkoelker): Set the port to 0 since we actually don't listen
        super(ScrubberDaemon, self).__init__(test_dir, 0)
        self.server_name = 'scrubber'
        self.server_module = 'glance.cmd.%s' % self.server_name
        self.daemon = daemon

        self.image_dir = os.path.join(self.test_dir, "images")
        self.scrub_time = 5
        self.pid_file = os.path.join(self.test_dir, "scrubber.pid")
        self.log_file = os.path.join(self.test_dir, "scrubber.log")
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.lock_path = self.test_dir

        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.policy_file = policy_file
        self.policy_default_rule = 'default'

        self.send_identity_headers = False
        self.admin_role = 'admin'

        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
filesystem_store_datadir=%(image_dir)s
log_file = %(log_file)s
daemon = %(daemon)s
wakeup_time = 2
scrub_time = %(scrub_time)s
registry_host = 127.0.0.1
registry_port = %(registry_port)s
metadata_encryption_key = %(metadata_encryption_key)s
lock_path = %(lock_path)s
sql_connection = %(sql_connection)s
sql_idle_timeout = 3600
send_identity_headers = %(send_identity_headers)s
admin_role = %(admin_role)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
"""

    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        if 'daemon' in kwargs:
            expect_exit = False
        return super(ScrubberDaemon, self).start(
            expect_exit=expect_exit,
            expected_exitcode=expected_exitcode,
            **kwargs)


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
        self.test_dir = self.useFixture(fixtures.TempDir()).path

        self.api_protocol = 'http'
        self.api_port, api_sock = test_utils.get_unused_port_and_socket()
        self.registry_port, reg_sock = test_utils.get_unused_port_and_socket()

        self.tracecmd = tracecmd_osmap.get(platform.system())

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('schema-image.json', conf_dir)
        self.copy_data_file('policy.json', conf_dir)
        self.copy_data_file('property-protections.conf', conf_dir)
        self.copy_data_file('property-protections-policies.conf', conf_dir)
        self.property_file_roles = os.path.join(conf_dir,
                                                'property-protections.conf')
        property_policies = 'property-protections-policies.conf'
        self.property_file_policies = os.path.join(conf_dir,
                                                   property_policies)
        self.policy_file = os.path.join(conf_dir, 'policy.json')

        self.api_server = ApiServer(self.test_dir,
                                    self.api_port,
                                    self.policy_file,
                                    sock=api_sock)

        self.registry_server = RegistryServer(self.test_dir,
                                              self.registry_port,
                                              self.policy_file,
                                              sock=reg_sock)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir, self.policy_file)

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

        self.api_server.dump_log('api_server')
        self.registry_server.dump_log('registry_server')
        self.scrubber_daemon.dump_log('scrubber_daemon')

    def set_policy_rules(self, rules):
        fap = open(self.policy_file, 'w')
        fap.write(jsonutils.dumps(rules))
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
                   "create database %(database)s;") % {'database': database}
            cmd = ("mysql -u%(user)s %(password)s -h%(host)s "
                   "-e\"%(sql)s\"") % {'user': user, 'password': password,
                                       'host': host, 'sql': sql}
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)

    def cleanup(self):
        """
        Makes sure anything we created or started up in the
        tests are destroyed or spun down
        """

        # NOTE(jbresnah) call stop on each of the servers instead of
        # checking the pid file.  stop() will wait until the child
        # server is dead.  This eliminates the possibility of a race
        # between a child process listening on a port actually dying
        # and a new process being started
        servers = [self.api_server,
                   self.registry_server,
                   self.scrubber_daemon]
        for s in servers:
            try:
                s.stop()
            except Exception:
                pass

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

        self.launched_servers.append(server)

        launch_msg = self.wait_for_servers([server], expect_launch)
        self.assertTrue(launch_msg is None, launch_msg)

    def start_with_retry(self, server, port_name, max_retries,
                         expect_launch=True,
                         **kwargs):
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
        """
        launch_msg = None
        for i in range(max_retries):
            exitcode, out, err = server.start(expect_exit=not expect_launch,
                                              **kwargs)
            name = server.server_name
            self.assertEqual(0, exitcode,
                             "Failed to spin up the %s server. "
                             "Got: %s" % (name, err))
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
        Starts the API and Registry servers (glance-control api start
        & glance-control registry start) on unused ports.  glance-control
        should be installed into the python path

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
        except socket.error:
            return False

    def wait_for_servers(self, servers, expect_launch=True, timeout=30):
        """
        Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Glance server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 30 seconds
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
                pid = f.process_pid
                trace = f.pid_file.replace('.pid', '.trace')
                if self.tracecmd:
                    cmd = '%s -p %d -o %s' % (self.tracecmd, pid, trace)
                    execute(cmd, raise_error=False, expect_exit=False)
                    time.sleep(0.5)
                    if os.path.exists(trace):
                        msg += ('\n%s:\n%s\n' % (self.tracecmd,
                                                 open(trace).read()))

        self.add_log_details(failed)

        return msg if expect_launch else None

    def stop_server(self, server, name):
        """
        Called to stop a single server in a normal fashion using the
        glance-control stop method to gracefully shut the server down.

        :param server: the server to stop
        """
        # Spin down the requested server
        server.stop()

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

        self._reset_database(self.registry_server.sql_connection)

    def run_sql_cmd(self, sql):
        """
        Provides a crude mechanism to run manual SQL commands for backend
        DB verification within the functional tests.
        The raw result set is returned.
        """
        engine = db_api.get_engine()
        return engine.execute(sql)

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def add_log_details(self, servers=None):
        logs = [s.log_file for s in (servers or self.launched_servers)]
        for log in logs:
            if os.path.exists(log):
                testtools.content.attach_file(self, log)
