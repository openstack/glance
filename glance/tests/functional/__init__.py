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

import abc
import atexit
import datetime
import errno
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from testtools import content as ttc
import textwrap
import time
from unittest import mock
import urllib.parse as urlparse
import uuid

import fixtures
import glance_store
from os_win import utilsfactory as os_win_utilsfactory
from oslo_config import cfg
from oslo_serialization import jsonutils
import testtools
import webob

from glance.common import config
from glance.common import utils
from glance.common import wsgi
from glance.db.sqlalchemy import api as db_api
from glance import tests as glance_tests
from glance.tests import utils as test_utils

execute, get_unused_port = test_utils.execute, test_utils.get_unused_port
tracecmd_osmap = {'Linux': 'strace', 'FreeBSD': 'truss'}

if os.name == 'nt':
    SQLITE_CONN_TEMPLATE = 'sqlite:///%s/tests.sqlite'
else:
    SQLITE_CONN_TEMPLATE = 'sqlite:////%s/tests.sqlite'


CONF = cfg.CONF


import glance.async_
# NOTE(danms): Default to eventlet threading for tests
try:
    glance.async_.set_threadpool_model('eventlet')
except RuntimeError:
    pass


class BaseServer(metaclass=abc.ABCMeta):
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
        self.needs_database = False
        self.log_file = None
        self.sock = sock
        self.fork_socket = True
        self.process_pid = None
        self.server_module = None
        self.stop_kill = False

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

    @abc.abstractmethod
    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        pass

    @abc.abstractmethod
    def stop(self):
        pass

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
                conf_file.write('[database]\n')
                conf_file.write('connection = %s' % self.sql_connection)
                conf_file.flush()

            glance_db_env = 'GLANCE_DB_TEST_SQLITE_FILE'
            if glance_db_env in os.environ:
                # use the empty db created and cached as a tempfile
                # instead of spending the time creating a new one
                db_location = os.environ[glance_db_env]
                shutil.copyfile(db_location, "%s/tests.sqlite" % self.test_dir)
            else:
                cmd = ('%s -m glance.cmd.manage --config-file %s db sync' %
                       (sys.executable, conf_filepath))
                execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env,
                        expect_exit=True)

                # copy the clean db to a temp location so that it
                # can be reused for future tests
                (osf, db_location) = tempfile.mkstemp()
                os.close(osf)
                shutil.copyfile('%s/tests.sqlite' % self.test_dir, db_location)
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

    def dump_log(self):
        if not self.log_file:
            return "log_file not set for {name}".format(name=self.server_name)
        elif not os.path.exists(self.log_file):
            return "{log_file} for {name} did not exist".format(
                log_file=self.log_file, name=self.server_name)
        with open(self.log_file, 'r') as fptr:
            return fptr.read().strip()


class PosixServer(BaseServer):
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
                expected_exitcode=expected_exitcode,
                force=False)
        # avoid an FD leak
        if self.sock:
            os.close(fd)
            self.sock = None
        return (rc, '', '')

    def stop(self):
        """
        Spin down the server.
        """
        if not self.process_pid:
            raise Exception('why is this being called? %s' % self.server_name)

        if self.stop_kill:
            os.kill(self.process_pid, signal.SIGTERM)
        rc = test_utils.wait_for_fork(self.process_pid, raise_error=False,
                                      force=self.stop_kill)
        return (rc, '', '')


class Win32Server(BaseServer):
    def __init__(self, *args, **kwargs):
        super(Win32Server, self).__init__(*args, **kwargs)

        self._processutils = os_win_utilsfactory.get_processutils()

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

        # Passing socket objects on Windows is a bit more cumbersome.
        # We don't really have to do it.
        if self.sock:
            self.sock.close()
            self.sock = None

        self.process = subprocess.Popen(
            cmd,
            env=self.exec_env)
        self.process_pid = self.process.pid

        try:
            self.job_handle = self._processutils.kill_process_on_job_close(
                self.process_pid)
        except Exception:
            # Could not associate child process with a job, killing it.
            self.process.kill()
            raise

        self.stop_kill = not expect_exit
        if self.pid_file:
            pf = open(self.pid_file, 'w')
            pf.write('%d\n' % self.process_pid)
            pf.close()

        rc = 0
        if expect_exit:
            self.process.communicate()
            rc = self.process.returncode

        return (rc, '', '')

    def stop(self):
        """
        Spin down the server.
        """
        if not self.process_pid:
            raise Exception('Server "%s" process not running.'
                            % self.server_name)

        if self.stop_kill:
            self.process.terminate()
        return (0, '', '')


if os.name == 'nt':
    Server = Win32Server
else:
    Server = PosixServer


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
        self.bind_host = "127.0.0.1"
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.image_dir = os.path.join(self.test_dir, "images")
        self.pid_file = pid_file or os.path.join(self.test_dir, "api.pid")
        self.log_file = os.path.join(self.test_dir, "api.log")
        self.image_size_cap = 1099511627776
        self.delayed_delete = delayed_delete
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

        self.enforce_new_defaults = True

        self.needs_database = True
        default_sql_connection = SQLITE_CONN_TEMPLATE % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.user_storage_quota = '0'
        self.lock_path = self.test_dir

        self.location_strategy = 'location_order'
        self.store_type_location_strategy_preference = ""

        self.node_staging_uri = 'file://%s' % os.path.join(
            self.test_dir, 'staging')

        self.conf_base = """[DEFAULT]
debug = %(debug)s
default_log_levels = eventlet.wsgi.server=DEBUG,stevedore.extension=INFO
bind_host = %(bind_host)s
bind_port = %(bind_port)s
metadata_encryption_key = %(metadata_encryption_key)s
log_file = %(log_file)s
image_size_cap = %(image_size_cap)d
delayed_delete = %(delayed_delete)s
workers = %(workers)s
scrub_time = %(scrub_time)s
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
show_image_direct_url = %(show_image_direct_url)s
show_multiple_locations = %(show_multiple_locations)s
user_storage_quota = %(user_storage_quota)s
lock_path = %(lock_path)s
property_protection_file = %(property_protection_file)s
property_protection_rule_format = %(property_protection_rule_format)s
image_member_quota=%(image_member_quota)s
image_property_quota=%(image_property_quota)s
image_tag_quota=%(image_tag_quota)s
image_location_quota=%(image_location_quota)s
location_strategy=%(location_strategy)s
node_staging_uri=%(node_staging_uri)s
[database]
connection = %(sql_connection)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
enforce_new_defaults=%(enforce_new_defaults)s
[paste_deploy]
flavor = %(deployment_flavor)s
[store_type_location_strategy]
store_type_preference = %(store_type_location_strategy_preference)s
[glance_store]
filesystem_store_datadir=%(image_dir)s
default_store = %(default_store)s
[import_filtering_opts]
allowed_ports = []
"""
        self.paste_conf_base = """[composite:glance-api]
paste.composite_factory = glance.api:root_app_factory
/: api
/healthcheck: healthcheck

[pipeline:api]
pipeline =
    cors
    versionnegotiation
    gzip
    unauthenticated-context
    rootapp

[composite:glance-api-caching]
paste.composite_factory = glance.api:root_app_factory
/: api-caching
/healthcheck: healthcheck

[pipeline:api-caching]
pipeline = cors versionnegotiation gzip context cache rootapp

[composite:glance-api-cachemanagement]
paste.composite_factory = glance.api:root_app_factory
/: api-cachemanagement
/healthcheck: healthcheck

[pipeline:api-cachemanagement]
pipeline =
    cors
    versionnegotiation
    gzip
    unauthenticated-context
    cache
    cache_manage
    rootapp

[composite:glance-api-fakeauth]
paste.composite_factory = glance.api:root_app_factory
/: api-fakeauth
/healthcheck: healthcheck

[pipeline:api-fakeauth]
pipeline = cors versionnegotiation gzip fakeauth context rootapp

[composite:glance-api-noauth]
paste.composite_factory = glance.api:root_app_factory
/: api-noauth
/healthcheck: healthcheck

[pipeline:api-noauth]
pipeline = cors versionnegotiation gzip context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v2: apiv2app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[app:healthcheck]
paste.app_factory = oslo_middleware:Healthcheck.app_factory
backends = disable_by_file
disable_by_file_path = %(disable_path)s

[filter:versionnegotiation]
paste.filter_factory = glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:gzip]
paste.filter_factory = glance.api.middleware.gzip:GzipMiddleware.factory

[filter:cache]
paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

[filter:cache_manage]
paste.filter_factory = glance.api.middleware.cache_manage:CacheManageFilter.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory = glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory

[filter:cors]
paste.filter_factory = oslo_middleware.cors:filter_factory
allowed_origin=http://valid.example.com
"""


class ApiServerForMultipleBackend(Server):

    """
    Server object that starts/stops/manages the API server
    """

    def __init__(self, test_dir, port, policy_file, delayed_delete=False,
                 pid_file=None, sock=None, **kwargs):
        super(ApiServerForMultipleBackend, self).__init__(
            test_dir, port, sock=sock)
        self.server_name = 'api'
        self.server_module = 'glance.cmd.%s' % self.server_name
        self.default_backend = kwargs.get("default_backend", "file1")
        self.bind_host = "127.0.0.1"
        self.metadata_encryption_key = "012345678901234567890123456789ab"
        self.image_dir_backend_1 = os.path.join(self.test_dir, "images_1")
        self.image_dir_backend_2 = os.path.join(self.test_dir, "images_2")
        self.image_dir_backend_3 = os.path.join(self.test_dir, "images_3")
        self.staging_dir = os.path.join(self.test_dir, "staging")
        self.pid_file = pid_file or os.path.join(self.test_dir,
                                                 "multiple_backend_api.pid")
        self.log_file = os.path.join(self.test_dir, "multiple_backend_api.log")
        self.image_size_cap = 1099511627776
        self.delayed_delete = delayed_delete
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

        self.enforce_new_defaults = True

        self.needs_database = True
        default_sql_connection = SQLITE_CONN_TEMPLATE % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.user_storage_quota = '0'
        self.lock_path = self.test_dir

        self.location_strategy = 'location_order'
        self.store_type_location_strategy_preference = ""

        self.conf_base = """[DEFAULT]
debug = %(debug)s
default_log_levels = eventlet.wsgi.server=DEBUG,stevedore.extension=INFO
bind_host = %(bind_host)s
bind_port = %(bind_port)s
metadata_encryption_key = %(metadata_encryption_key)s
log_file = %(log_file)s
image_size_cap = %(image_size_cap)d
delayed_delete = %(delayed_delete)s
workers = %(workers)s
scrub_time = %(scrub_time)s
image_cache_dir = %(image_cache_dir)s
image_cache_driver = %(image_cache_driver)s
show_image_direct_url = %(show_image_direct_url)s
show_multiple_locations = %(show_multiple_locations)s
user_storage_quota = %(user_storage_quota)s
lock_path = %(lock_path)s
property_protection_file = %(property_protection_file)s
property_protection_rule_format = %(property_protection_rule_format)s
image_member_quota=%(image_member_quota)s
image_property_quota=%(image_property_quota)s
image_tag_quota=%(image_tag_quota)s
image_location_quota=%(image_location_quota)s
location_strategy=%(location_strategy)s
enabled_backends=file1:file,file2:file,file3:file
[database]
connection = %(sql_connection)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
enforce_new_defaults=%(enforce_new_defaults)s
[paste_deploy]
flavor = %(deployment_flavor)s
[store_type_location_strategy]
store_type_preference = %(store_type_location_strategy_preference)s
[glance_store]
default_backend = %(default_backend)s
[file1]
filesystem_store_datadir=%(image_dir_backend_1)s
[file2]
filesystem_store_datadir=%(image_dir_backend_2)s
[file3]
filesystem_store_datadir=%(image_dir_backend_3)s
[import_filtering_opts]
allowed_ports = []
[os_glance_staging_store]
filesystem_store_datadir=%(staging_dir)s
"""
        self.paste_conf_base = """[composite:glance-api]
paste.composite_factory = glance.api:root_app_factory
/: api
/healthcheck: healthcheck

[pipeline:api]
pipeline =
    cors
    versionnegotiation
    gzip
    unauthenticated-context
    rootapp

[composite:glance-api-caching]
paste.composite_factory = glance.api:root_app_factory
/: api-caching
/healthcheck: healthcheck

[pipeline:api-caching]
pipeline = cors versionnegotiation gzip unauthenticated-context cache rootapp

[composite:glance-api-cachemanagement]
paste.composite_factory = glance.api:root_app_factory
/: api-cachemanagement
/healthcheck: healthcheck

[pipeline:api-cachemanagement]
pipeline =
    cors
    versionnegotiation
    gzip
    unauthenticated-context
    cache
    cache_manage
    rootapp

[composite:glance-api-fakeauth]
paste.composite_factory = glance.api:root_app_factory
/: api-fakeauth
/healthcheck: healthcheck

[pipeline:api-fakeauth]
pipeline = cors versionnegotiation gzip fakeauth context rootapp

[composite:glance-api-noauth]
paste.composite_factory = glance.api:root_app_factory
/: api-noauth
/healthcheck: healthcheck

[pipeline:api-noauth]
pipeline = cors versionnegotiation gzip context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v2: apiv2app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[app:healthcheck]
paste.app_factory = oslo_middleware:Healthcheck.app_factory
backends = disable_by_file
disable_by_file_path = %(disable_path)s

[filter:versionnegotiation]
paste.filter_factory = glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:gzip]
paste.filter_factory = glance.api.middleware.gzip:GzipMiddleware.factory

[filter:cache]
paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

[filter:cache_manage]
paste.filter_factory = glance.api.middleware.cache_manage:CacheManageFilter.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory = glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory

[filter:cors]
paste.filter_factory = oslo_middleware.cors:filter_factory
allowed_origin=http://valid.example.com
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

        default_sql_connection = SQLITE_CONN_TEMPLATE % self.test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.policy_file = policy_file
        self.policy_default_rule = 'default'

        self.conf_base = """[DEFAULT]
debug = %(debug)s
log_file = %(log_file)s
daemon = %(daemon)s
wakeup_time = 2
scrub_time = %(scrub_time)s
metadata_encryption_key = %(metadata_encryption_key)s
lock_path = %(lock_path)s
sql_idle_timeout = 3600
[database]
connection = %(sql_connection)s
[glance_store]
filesystem_store_datadir=%(image_dir)s
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
        # NOTE: Scrubber is enabled by default for the functional tests.
        # Please disable it by explicitly setting 'self.include_scrubber' to
        # False in the test SetUps that do not require Scrubber to run.
        self.include_scrubber = True

        # The clients will try to connect to this address. Let's make sure
        # we're not using the default '0.0.0.0'
        self.config(bind_host='127.0.0.1')
        self.config(image_cache_dir=self.test_dir)
        self.tracecmd = tracecmd_osmap.get(platform.system())

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('schema-image.json', conf_dir)
        self.copy_data_file('property-protections.conf', conf_dir)
        self.copy_data_file('property-protections-policies.conf', conf_dir)
        self.property_file_roles = os.path.join(conf_dir,
                                                'property-protections.conf')
        property_policies = 'property-protections-policies.conf'
        self.property_file_policies = os.path.join(conf_dir,
                                                   property_policies)
        self.policy_file = os.path.join(conf_dir, 'policy.yaml')

        self.api_server = ApiServer(self.test_dir,
                                    self.api_port,
                                    self.policy_file,
                                    sock=api_sock)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir, self.policy_file)

        self.pid_files = [self.api_server.pid_file,
                          self.scrubber_daemon.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []
        # Keep track of servers we've logged so we don't double-log them.
        self._attached_server_logs = []
        self.addOnException(self.add_log_details_on_exception)

        if not self.disabled:
            # We destroy the test data store between each test case,
            # and recreate it, which ensures that we have no side-effects
            # from the tests
            self.addCleanup(
                self._reset_database, self.api_server.sql_connection)
            self.addCleanup(self.cleanup)
            self._reset_database(self.api_server.sql_connection)

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

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
        ) on unused ports.  glance-control
        should be installed into the python path

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.cleanup()

        # Start up the API server

        self.start_with_retry(self.api_server, 'api_port', 3, **kwargs)

        if self.include_scrubber:
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
            return True
        except socket.error:
            return False
        finally:
            s.close()

    def ping_server_ipv6(self, port):
        """
        Simple ping on the port. If responsive, return True, else
        return False.

        :note We use raw sockets, not ping here, since ping uses ICMP and
        has no concept of ports...

        The function uses IPv6 (therefore AF_INET6 and ::1).
        """
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            s.connect(("::1", port))
            return True
        except socket.error:
            return False
        finally:
            s.close()

    def wait_for_servers(self, servers, expect_launch=True, timeout=30):
        """
        Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Glance server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 30 seconds
        :returns: None if launch expectation is met, otherwise an
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
                    try:
                        execute(cmd, raise_error=False, expect_exit=False)
                    except OSError as e:
                        if e.errno == errno.ENOENT:
                            raise RuntimeError('No executable found for "%s" '
                                               'command.' % self.tracecmd)
                        else:
                            raise
                    time.sleep(0.5)
                    if os.path.exists(trace):
                        msg += ('\n%s:\n%s\n' % (self.tracecmd,
                                                 open(trace).read()))

        self.add_log_details(failed)

        return msg if expect_launch else None

    def stop_server(self, server):
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

        # Spin down the API server
        self.stop_server(self.api_server)
        if self.include_scrubber:
            self.stop_server(self.scrubber_daemon)

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def add_log_details_on_exception(self, *args, **kwargs):
        self.add_log_details()

    def add_log_details(self, servers=None):
        for s in servers or self.launched_servers:
            if s.log_file not in self._attached_server_logs:
                self._attached_server_logs.append(s.log_file)
            self.addDetail(
                s.server_name, testtools.content.text_content(s.dump_log()))


class MultipleBackendFunctionalTest(test_utils.BaseTestCase):

    """
    Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    inited = False
    disabled = False
    launched_servers = []

    def setUp(self):
        super(MultipleBackendFunctionalTest, self).setUp()
        self.test_dir = self.useFixture(fixtures.TempDir()).path

        self.api_protocol = 'http'
        self.api_port, api_sock = test_utils.get_unused_port_and_socket()
        # NOTE: Scrubber is enabled by default for the functional tests.
        # Please disable it by explicitly setting 'self.include_scrubber' to
        # False in the test SetUps that do not require Scrubber to run.
        self.include_scrubber = True

        self.tracecmd = tracecmd_osmap.get(platform.system())

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('schema-image.json', conf_dir)
        self.copy_data_file('property-protections.conf', conf_dir)
        self.copy_data_file('property-protections-policies.conf', conf_dir)
        self.property_file_roles = os.path.join(conf_dir,
                                                'property-protections.conf')
        property_policies = 'property-protections-policies.conf'
        self.property_file_policies = os.path.join(conf_dir,
                                                   property_policies)
        self.policy_file = os.path.join(conf_dir, 'policy.yaml')

        self.api_server_multiple_backend = ApiServerForMultipleBackend(
            self.test_dir, self.api_port, self.policy_file, sock=api_sock)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir, self.policy_file)

        self.pid_files = [self.api_server_multiple_backend.pid_file,
                          self.scrubber_daemon.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []
        # Keep track of servers we've logged so we don't double-log them.
        self._attached_server_logs = []
        self.addOnException(self.add_log_details_on_exception)

        if not self.disabled:
            # We destroy the test data store between each test case,
            # and recreate it, which ensures that we have no side-effects
            # from the tests
            self.addCleanup(
                self._reset_database,
                self.api_server_multiple_backend.sql_connection)
            self.addCleanup(self.cleanup)
            self._reset_database(
                self.api_server_multiple_backend.sql_connection)

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

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
        servers = [self.api_server_multiple_backend,
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
        ) on unused ports.  glance-control
        should be installed into the python path

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.cleanup()

        # Start up the API server

        self.start_with_retry(self.api_server_multiple_backend,
                              'api_port', 3, **kwargs)

        if self.include_scrubber:
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
            return True
        except socket.error:
            return False
        finally:
            s.close()

    def ping_server_ipv6(self, port):
        """
        Simple ping on the port. If responsive, return True, else
        return False.

        :note We use raw sockets, not ping here, since ping uses ICMP and
        has no concept of ports...

        The function uses IPv6 (therefore AF_INET6 and ::1).
        """
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            s.connect(("::1", port))
            return True
        except socket.error:
            return False
        finally:
            s.close()

    def wait_for_servers(self, servers, expect_launch=True, timeout=30):
        """
        Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Glance server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 30 seconds
        :returns: None if launch expectation is met, otherwise an
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
                    try:
                        execute(cmd, raise_error=False, expect_exit=False)
                    except OSError as e:
                        if e.errno == errno.ENOENT:
                            raise RuntimeError('No executable found for "%s" '
                                               'command.' % self.tracecmd)
                        else:
                            raise
                    time.sleep(0.5)
                    if os.path.exists(trace):
                        msg += ('\n%s:\n%s\n' % (self.tracecmd,
                                                 open(trace).read()))

        self.add_log_details(failed)

        return msg if expect_launch else None

    def stop_server(self, server):
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

        # Spin down the API
        self.stop_server(self.api_server_multiple_backend)
        if self.include_scrubber:
            self.stop_server(self.scrubber_daemon)

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def add_log_details_on_exception(self, *args, **kwargs):
        self.add_log_details()

    def add_log_details(self, servers=None):
        for s in servers or self.launched_servers:
            if s.log_file not in self._attached_server_logs:
                self._attached_server_logs.append(s.log_file)
            self.addDetail(
                s.server_name, testtools.content.text_content(s.dump_log()))


class SynchronousAPIBase(test_utils.BaseTestCase):
    """A base class that provides synchronous calling into the API.

    This provides a way to directly call into the API WSGI stack
    without starting a separate server, and with a simple paste
    pipeline. Configured with multi-store and a real database.

    This differs from the FunctionalTest lineage above in that they
    start a full copy of the API server as a separate process, whereas
    this calls directly into the WSGI stack. This test base is
    appropriate for situations where you need to be able to mock the
    state of the world (i.e. warp time, or inject errors) but should
    not be used for happy-path testing where FunctionalTest provides
    more isolation.

    To use this, inherit and run start_server() before you are ready
    to make API calls (either in your setUp() or per-test if you need
    to change config or mocking).

    Once started, use the api_get(), api_put(), api_post(), and
    api_delete() methods to make calls to the API.

    """

    TENANT = str(uuid.uuid4())

    @mock.patch('oslo_db.sqlalchemy.enginefacade.writer.get_engine')
    def setup_database(self, mock_get_engine):
        """Configure and prepare a fresh sqlite database."""
        db_file = 'sqlite:///%s/test.db' % self.test_dir
        self.config(connection=db_file, group='database')

        # NOTE(danms): Make sure that we clear the current global
        # database configuration, provision a temporary database file,
        # and run migrations with our configuration to define the
        # schema there.
        db_api.clear_db_env()
        engine = db_api.get_engine()
        mock_get_engine.return_value = engine
        with mock.patch('logging.config'):
            # NOTE(danms): The alembic config in the env module will break our
            # BaseTestCase logging setup. So mock that out to prevent it while
            # we db_sync.
            test_utils.db_sync(engine=engine)

    def setup_simple_paste(self):
        """Setup a very simple no-auth paste pipeline.

        This configures the API to be very direct, including only the
        middleware absolutely required for consistent API calls.
        """
        self.paste_config = os.path.join(self.test_dir, 'glance-api-paste.ini')
        with open(self.paste_config, 'w') as f:
            f.write(textwrap.dedent("""
            [filter:context]
            paste.filter_factory = glance.api.middleware.context:\
                ContextMiddleware.factory
            [filter:fakeauth]
            paste.filter_factory = glance.tests.utils:\
                FakeAuthMiddleware.factory
            [filter:cache]
            paste.filter_factory = glance.api.middleware.cache:\
            CacheFilter.factory
            [filter:cachemanage]
            paste.filter_factory = glance.api.middleware.cache_manage:\
            CacheManageFilter.factory
            [pipeline:glance-api-cachemanagement]
            pipeline = context cache cachemanage rootapp
            [pipeline:glance-api-caching]
            pipeline = context cache rootapp
            [pipeline:glance-api]
            pipeline = context rootapp
            [composite:rootapp]
            paste.composite_factory = glance.api:root_app_factory
            /v2: apiv2app
            [app:apiv2app]
            paste.app_factory = glance.api.v2.router:API.factory
            """))

    def _store_dir(self, store):
        return os.path.join(self.test_dir, store)

    def setup_stores(self):
        """Configures multiple backend stores.

        This configures the API with three file-backed stores (store1,
        store2, and store3) as well as a os_glance_staging_store for
        imports.

        """
        self.config(enabled_backends={'store1': 'file', 'store2': 'file',
                                      'store3': 'file'})
        glance_store.register_store_opts(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        self.config(default_backend='store1',
                    group='glance_store')
        self.config(filesystem_store_datadir=self._store_dir('store1'),
                    group='store1')
        self.config(filesystem_store_datadir=self._store_dir('store2'),
                    group='store2')
        self.config(filesystem_store_datadir=self._store_dir('store3'),
                    group='store3')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')
        self.config(filesystem_store_datadir=self._store_dir('tasks'),
                    group='os_glance_tasks_store')

        glance_store.create_multi_stores(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        glance_store.verify_store()

    def setUp(self):
        super(SynchronousAPIBase, self).setUp()

        self.setup_database()
        self.setup_simple_paste()
        self.setup_stores()

    def start_server(self, enable_cache=True, set_worker_url=True):
        """Builds and "starts" the API server.

        Note that this doesn't actually "start" anything like
        FunctionalTest does above, but that terminology is used here
        to make it seem like the same sort of pattern.
        """
        config.set_config_defaults()
        root_app = 'glance-api'
        if enable_cache:
            root_app = 'glance-api-cachemanagement'
            self.config(image_cache_dir=self._store_dir('cache'))

        if set_worker_url:
            self.config(worker_self_reference_url='http://workerx')

        self.api = config.load_paste_app(root_app,
                                         conf_file=self.paste_config)
        self.config(enforce_new_defaults=True,
                    group='oslo_policy')
        self.config(enforce_scope=True,
                    group='oslo_policy')

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': self.TENANT,
            'Content-Type': 'application/json',
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def api_request(self, method, url, headers=None, data=None,
                    json=None, body_file=None):
        """Perform a request against the API.

        NOTE: Most code should use api_get(), api_post(), api_put(),
              or api_delete() instead!

        :param method: The HTTP method to use (i.e. GET, POST, etc)
        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        headers = self._headers(headers)
        req = webob.Request.blank(url, method=method,
                                  headers=headers)
        if json and not data:
            data = jsonutils.dumps(json).encode()
        if data and not body_file:
            req.body = data
        elif body_file:
            req.body_file = body_file
        return self.api(req)

    def api_get(self, url, headers=None):
        """Perform a GET request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :returns: A webob.Response object
        """
        return self.api_request('GET', url, headers=headers)

    def api_post(self, url, headers=None, data=None, json=None,
                 body_file=None):
        """Perform a POST request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        return self.api_request('POST', url, headers=headers,
                                data=data, json=json,
                                body_file=body_file)

    def api_put(self, url, headers=None, data=None, json=None, body_file=None):
        """Perform a PUT request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json,
                     mutually exclusive with body_file)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        return self.api_request('PUT', url, headers=headers,
                                data=data, json=json,
                                body_file=body_file)

    def api_delete(self, url, headers=None):
        """Perform a DELETE request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :returns: A webob.Response object
        """
        return self.api_request('DELETE', url, headers=headers)

    def api_patch(self, url, *patches, headers=None):
        """Perform a PATCH request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param patches: One or more patch dicts
        :param headers: Optional updates to the default set of headers
        :returns: A webob.Response object
        """
        if not headers:
            headers = {}
        headers['Content-Type'] = \
            'application/openstack-images-v2.1-json-patch'
        return self.api_request('PATCH', url, headers=headers,
                                json=list(patches))

    def _import_copy(self, image_id, stores, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'copy-image'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _import_direct(self, image_id, stores, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'glance-direct'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _import_web_download(self, image_id, stores, url, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'web-download',
                           'uri': url},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _create_and_upload(self, data_iter=None, expected_code=204,
                           visibility=None):
        data = {
            'name': 'foo',
            'container_format': 'bare',
            'disk_format': 'raw'
        }
        if visibility:
            data['visibility'] = visibility

        resp = self.api_post('/v2/images',
                             json=data)
        self.assertEqual(201, resp.status_code, resp.text)
        image = jsonutils.loads(resp.text)

        if data_iter:
            resp = self.api_put(
                '/v2/images/%s/file' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                body_file=data_iter)
        else:
            resp = self.api_put(
                '/v2/images/%s/file' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                data=b'IMAGEDATA')
        self.assertEqual(expected_code, resp.status_code)

        return image['id']

    def _create_and_stage(self, data_iter=None, expected_code=204,
                          visibility=None, extra={}):
        data = {
            'name': 'foo',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        if visibility:
            data['visibility'] = visibility

        data.update(extra)
        resp = self.api_post('/v2/images',
                             json=data)
        image = jsonutils.loads(resp.text)

        if data_iter:
            resp = self.api_put(
                '/v2/images/%s/stage' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                body_file=data_iter)
        else:
            resp = self.api_put(
                '/v2/images/%s/stage' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                data=b'IMAGEDATA')
        self.assertEqual(expected_code, resp.status_code)

        return image['id']

    def _wait_for_import(self, image_id, retries=10):
        for i in range(0, retries):
            image = self.api_get('/v2/images/%s' % image_id).json
            if not image.get('os_glance_import_task'):
                break
            self.addDetail('Create-Import task id',
                           ttc.text_content(image['os_glance_import_task']))
            time.sleep(1)

        self.assertIsNone(image.get('os_glance_import_task'),
                          'Timed out waiting for task to complete')

        return image

    def _create_and_import(self, stores=[], data_iter=None, expected_code=202,
                           visibility=None, extra={}):
        """Create an image, stage data, and import into the given stores.

        :returns: image_id
        """
        image_id = self._create_and_stage(data_iter=data_iter,
                                          visibility=visibility,
                                          extra=extra)

        resp = self._import_direct(image_id, stores)
        self.assertEqual(expected_code, resp.status_code)

        if expected_code >= 400:
            return image_id

        # Make sure it becomes active
        image = self._wait_for_import(image_id)
        self.assertEqual('active', image['status'])

        return image_id

    def _get_latest_task(self, image_id):
        tasks = self.api_get('/v2/images/%s/tasks' % image_id).json['tasks']
        tasks = sorted(tasks, key=lambda t: t['updated_at'])
        self.assertGreater(len(tasks), 0)
        return tasks[-1]

    def _create(self):
        return self.api_post('/v2/images',
                             json={'name': 'foo',
                                   'container_format': 'bare',
                                   'disk_format': 'raw'})

    def _create_metadef_resource(self, path=None, data=None,
                                 expected_code=201):
        resp = self.api_post(path,
                             json=data)
        md_resource = jsonutils.loads(resp.text)
        self.assertEqual(expected_code, resp.status_code)
        return md_resource
