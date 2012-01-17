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

"""Base test class for keystone-related tests"""

import datetime
import os
import shutil
import sys
import time

from glance.tests import functional
from glance.tests.utils import execute, find_executable


pattieblack_token = '887665443383'
pattieblack_id = '2'
froggy_token = '383344566788'
froggy_id = '3'
admin_token = '999888777666'
bacon_token = '111111111111'
bacon_id = '4'
prosciutto_token = '222222222222'


class KeystoneServer(functional.Server):
    """
    Class used to easily manage starting and stopping a keystone
    server during functional test runs.
    """
    def __init__(self, server_control, server_name, test_dir, port,
                 auth_port, admin_port):
        super(KeystoneServer, self).__init__(test_dir, port)
        self.no_venv = True

        self.server_control = server_control
        self.server_name = server_name
        self.auth_port = auth_port
        self.admin_port = admin_port

        default_sql_connection = 'sqlite:///%s/keystone.db' % test_dir
        self.sql_connection = os.environ.get('GLANCE_TEST_KEYSTONE_SQL',
                                             default_sql_connection)

        self.pid_file = os.path.join(self.test_dir, '%s.pid' % server_name)
        self.log_file = os.path.join(self.test_dir, '%s.log' % server_name)
        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
default_store = sqlite
log_file = %(log_file)s
backends = keystone.backends.sqlalchemy
service-header-mappings = {
        'nova' : 'X-Server-Management-Url',
        'swift' : 'X-Storage-Url',
        'cdn' : 'X-CDN-Management-Url'}
service_host = 0.0.0.0
service_port = %(auth_port)s
admin_host = 0.0.0.0
admin_port = %(admin_port)s
keystone-admin-role = Admin
keystone-service-admin-role = KeystoneServiceAdmin
service_ssl = False
admin_ssl = False

[keystone.backends.sqlalchemy]
sql_connection = %(sql_connection)s
backend_entities = ['UserRoleAssociation', 'Endpoints', 'Role', 'Tenant',
                    'User', 'Credentials', 'EndpointTemplates', 'Token',
                    'Service']
sql_idle_timeout = 30

[pipeline:admin]
pipeline = urlrewritefilter admin_api

[pipeline:keystone-legacy-auth]
pipeline = urlrewritefilter legacy_auth RAX-KEY-extension service_api

[app:service_api]
paste.app_factory = keystone.server:service_app_factory

[app:admin_api]
paste.app_factory = keystone.server:admin_app_factory

[filter:urlrewritefilter]
paste.filter_factory = keystone.middleware.url:filter_factory

[filter:legacy_auth]
paste.filter_factory = keystone.frontends.legacy_token_auth:filter_factory

[filter:RAX-KEY-extension]
paste.filter_factory =
        keystone.contrib.extensions.service.raxkey.frontend:filter_factory
"""


class AuthServer(KeystoneServer):
    """
    Server object that starts/stops/manages the keystone auth server
    """

    def __init__(self, server_control, test_dir, auth_port, admin_port):
        super(AuthServer, self).__init__(server_control, 'auth',
                                         test_dir, auth_port,
                                         auth_port, admin_port)


class AdminServer(KeystoneServer):
    """
    Server object that starts/stops/manages the keystone admin server
    """

    def __init__(self, server_control, test_dir, auth_port, admin_port):
        super(AdminServer, self).__init__(server_control, 'admin',
                                          test_dir, admin_port,
                                          auth_port, admin_port)


def patch_copy(base, src, offset, old, new):
    base.insert(src + offset, base[src].replace(old, new))


def conf_patch(server, **subs):
    # First, pull the configuration file
    paste_base = server.paste_conf_base.split('\n')

    # Need to find the pipeline
    for idx, text in enumerate(paste_base):
        if text.startswith('[pipeline:glance-'):
            # OK, the lines to repeat in modified form
            # are this and the next one...
            modidx = idx
            break

    # Now we need to add a new pipeline, replacing the default context field...
    server.deployment_flavor = 'tokenauth+keystoneshim'
    patch_copy(paste_base, modidx, 2, ']', '-tokenauth+keystoneshim]')
    patch_copy(paste_base, modidx + 1, 2, 'context', 'tokenauth keystone_shim')

    # Put the conf back together and append the keystone pieces
    server.paste_conf_base = '\n'.join(paste_base) + """
[filter:tokenauth]
paste.filter_factory = keystone.middleware.auth_token:filter_factory
service_protocol = http
service_host = 127.0.0.1
service_port = %%(bind_port)s
auth_host = 127.0.0.1
auth_port = %(admin_port)s
auth_protocol = http
auth_uri = http://127.0.0.1:%(admin_port)s/
admin_token = 999888777666
delay_auth_decision = 1

[filter:keystone_shim]
paste.filter_factory = glance.common.wsgi:filter_factory
glance.filter_factory =
 keystone.middleware.glance_auth_token:KeystoneContextMiddleware
""" % subs


class KeystoneTests(functional.FunctionalTest):
    """
    Base test class for keystone-related tests.
    """

    KEYSTONE = None

    def setUp(self):
        """
        Look up keystone-control.
        """

        if not self.inited:
            KeystoneTests.inited = True

            # Try looking up the keystone executable
            cmdname = 'keystone-control'
            KeystoneTests.KEYSTONE = find_executable(cmdname)

            # If we don't have keystone-control, disable ourself
            if self.KEYSTONE is None:
                KeystoneTests.disabled = True
                KeystoneTests.disabled_message = "Keystone not installed"

        # Make sure to call superclass
        super(KeystoneTests, self).setUp()

        if self.disabled:
            return

        # Also need keystone auth and admin ports...
        self.auth_port = functional.get_unused_port()
        self.admin_port = functional.get_unused_port()

        # Set up the servers
        self.auth_server = AuthServer(self.KEYSTONE, self.test_dir,
                                      self.auth_port, self.admin_port)
        self.admin_server = AdminServer(self.KEYSTONE, self.test_dir,
                                        self.auth_port, self.admin_port)

        # Include their pid files, too
        self.pid_files.extend([self.auth_server.pid_file,
                               self.admin_server.pid_file])

        # Have to patch the api and registry config files for keystone
        # integration
        conf_patch(self.api_server, auth_port=self.auth_port,
                   admin_port=self.admin_port)
        conf_patch(self.registry_server, auth_port=self.auth_port,
                   admin_port=self.admin_port)
        self.registry_server.paste_conf_base += (
            'context_class = glance.registry.context.RequestContext\n')

    def tearDown(self):
        super(KeystoneTests, self).tearDown()
        if not self.disabled:
            self._reset_database(self.auth_server.sql_connection)

    def start_servers(self, **kwargs):
        """
        Starts the authentication and admin servers (keystone-auth and
        keystone-admin) on unused ports, in addition to the Glance API
        and Registry servers.

        Any kwargs passed to this method will override the
        configuration value in the conf file used in starting the
        servers.
        """
        # Start with the Glance servers
        super(KeystoneTests, self).start_servers(**kwargs)

        # Set up the data store
        keystone_conf = self.auth_server.write_conf(**kwargs)
        datafile = os.path.join(os.path.dirname(__file__), 'data',
                                'keystone_data.py')
        execute("python %s -c %s" % (datafile, keystone_conf))

        # Start keystone-auth
        exitcode, out, err = self.auth_server.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Auth server. "
                         "Got: %s" % err)
        self.assertTrue("Starting keystone-auth with" in out)

        # Now keystone-admin
        exitcode, out, err = self.admin_server.start(**kwargs)

        self.assertEqual(0, exitcode,
                         "Failed to spin up the Admin server. "
                         "Got: %s" % err)
        self.assertTrue("Starting keystone-admin with" in out)

        self.wait_for_keystone_servers()

    def wait_for_keystone_servers(self, timeout=3):
        """
        Tight loop, waiting for both Auth and Admin server to be
        available on the ports.  Returns when both are pingable.
        There is a timeout on waiting for the servers to come up.

        :param timeout: Optional, defaults to 3 seconds
        """
        now = datetime.datetime.now()
        timeout_time = now + datetime.timedelta(seconds=timeout)
        while (timeout_time > now):
            if (self.ping_server(self.auth_port) and
                self.ping_server(self.admin_port)):
                return
            now = datetime.datetime.now()
            time.sleep(0.05)
        self.assertFalse(True, "Failed to start keystone servers.")

    def stop_servers(self):
        """
        Called to stop the started servers in a normal fashion.  Note
        that cleanup() will stop the servers using a fairly draconian
        method of sending a SIGTERM signal to the servers.  Here, we
        use the glance-control and keystone-control stop method to
        gracefully shut the servers down.  This method also asserts
        that the shutdown was clean, and so it is meant to be called
        during a normal test case sequence.
        """

        # Spin down the auth server...
        exitcode, out, err = self.auth_server.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the Auth server. "
                         "Got: %s" % err)

        # ...and the admin server...
        exitcode, out, err = self.admin_server.stop()
        self.assertEqual(0, exitcode,
                         "Failed to spin down the Admin server. "
                         "Got: %s" % err)

        # Now on to everything else...
        super(KeystoneTests, self).stop_servers()
