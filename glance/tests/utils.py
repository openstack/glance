# Copyright 2010-2011 OpenStack Foundation
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

"""Common utilities used in testing"""

import errno
import functools
import os
import shlex
import shutil
import socket
import subprocess

import fixtures
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_log import log
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslotest import moxstubout
import six
from six.moves import BaseHTTPServer
import testtools
import webob

from glance.common import config
from glance.common import exception
from glance.common import property_utils
from glance.common import utils
from glance.common import wsgi
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models

CONF = cfg.CONF
try:
    CONF.debug
except cfg.NoSuchOptError:
    # NOTE(sigmavirus24): If we run the entire test suite, the logging options
    # will be registered appropriately and we do not need to re-register them.
    # However, when we run a test in isolation (or use --debug), those options
    # will not be registered for us. In order for a test in a class that
    # inherits from BaseTestCase to even run, we will need to register them
    # ourselves.  BaseTestCase.config will set the debug level if something
    # calls self.config(debug=True) so we need these options registered
    # appropriately.
    # See bug 1433785 for more details.
    log.register_options(CONF)


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()

        self._config_fixture = self.useFixture(cfg_fixture.Config())

        # NOTE(bcwaldon): parse_args has to be called to register certain
        # command-line options - specifically we need config_dir for
        # the following policy tests
        config.parse_args(args=[])
        self.addCleanup(CONF.reset)
        mox_fixture = self.useFixture(moxstubout.MoxStubout())
        self.stubs = mox_fixture.stubs
        self.stubs.Set(exception, '_FATAL_EXCEPTION_FORMAT_ERRORS', True)
        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self.conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(self.conf_dir)
        self.set_policy()

    def set_policy(self):
        conf_file = "policy.json"
        self.policy_file = self._copy_data_file(conf_file, self.conf_dir)
        self.config(policy_file=self.policy_file, group='oslo_policy')

    def set_property_protections(self, use_policies=False):
        self.unset_property_protections()
        conf_file = "property-protections.conf"
        if use_policies:
            conf_file = "property-protections-policies.conf"
            self.config(property_protection_rule_format="policies")
        self.property_file = self._copy_data_file(conf_file, self.test_dir)
        self.config(property_protection_file=self.property_file)

    def unset_property_protections(self):
        for section in property_utils.CONFIG.sections():
            property_utils.CONFIG.remove_section(section)

    def _copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def set_property_protection_rules(self, rules):
        with open(self.property_file, 'w') as f:
            for rule_key in rules.keys():
                f.write('[%s]\n' % rule_key)
                for operation in rules[rule_key].keys():
                    roles_str = ','.join(rules[rule_key][operation])
                    f.write('%s = %s\n' % (operation, roles_str))

    def config(self, **kw):
        """
        Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        self._config_fixture.config(**kw)


class requires(object):
    """Decorator that initiates additional test setup/teardown."""
    def __init__(self, setup=None, teardown=None):
        self.setup = setup
        self.teardown = teardown

    def __call__(self, func):
        def _runner(*args, **kw):
            if self.setup:
                self.setup(args[0])
            func(*args, **kw)
            if self.teardown:
                self.teardown(args[0])
        _runner.__name__ = func.__name__
        _runner.__doc__ = func.__doc__
        return _runner


class depends_on_exe(object):
    """Decorator to skip test if an executable is unavailable"""
    def __init__(self, exe):
        self.exe = exe

    def __call__(self, func):
        def _runner(*args, **kw):
            cmd = 'which %s' % self.exe
            exitcode, out, err = execute(cmd, raise_error=False)
            if exitcode != 0:
                args[0].disabled_message = 'test requires exe: %s' % self.exe
                args[0].disabled = True
            func(*args, **kw)
        _runner.__name__ = func.__name__
        _runner.__doc__ = func.__doc__
        return _runner


def skip_if_disabled(func):
    """Decorator that skips a test if test case is disabled."""
    @functools.wraps(func)
    def wrapped(*a, **kwargs):
        func.__test__ = False
        test_obj = a[0]
        message = getattr(test_obj, 'disabled_message',
                          'Test disabled')
        if getattr(test_obj, 'disabled', False):
            test_obj.skipTest(message)
        func(*a, **kwargs)
    return wrapped


def fork_exec(cmd,
              exec_env=None,
              logfile=None,
              pass_fds=None):
    """
    Execute a command using fork/exec.

    This is needed for programs system executions that need path
    searching but cannot have a shell as their parent process, for
    example: glance-api.  When glance-api starts it sets itself as
    the parent process for its own process group.  Thus the pid that
    a Popen process would have is not the right pid to use for killing
    the process group.  This patch gives the test env direct access
    to the actual pid.

    :param cmd: Command to execute as an array of arguments.
    :param exec_env: A dictionary representing the environment with
                     which to run the command.
    :param logile: A path to a file which will hold the stdout/err of
                   the child process.
    :param pass_fds: Sequence of file descriptors passed to the child.
    """
    env = os.environ.copy()
    if exec_env is not None:
        for env_name, env_val in exec_env.items():
            if callable(env_val):
                env[env_name] = env_val(env.get(env_name))
            else:
                env[env_name] = env_val

    pid = os.fork()
    if pid == 0:
        if logfile:
            fds = [1, 2]
            with open(logfile, 'r+b') as fptr:
                for desc in fds:  # close fds
                    try:
                        os.dup2(fptr.fileno(), desc)
                    except OSError:
                        pass
        if pass_fds and hasattr(os, 'set_inheritable'):
            # os.set_inheritable() is only available and needed
            # since Python 3.4. On Python 3.3 and older, file descriptors are
            # inheritable by default.
            for fd in pass_fds:
                os.set_inheritable(fd, True)

        args = shlex.split(cmd)
        os.execvpe(args[0], args, env)
    else:
        return pid


def wait_for_fork(pid,
                  raise_error=True,
                  expected_exitcode=0):
    """
    Wait for a process to complete

    This function will wait for the given pid to complete.  If the
    exit code does not match that of the expected_exitcode an error
    is raised.
    """

    rc = 0
    try:
        (pid, rc) = os.waitpid(pid, 0)
        rc = os.WEXITSTATUS(rc)
        if rc != expected_exitcode:
            raise RuntimeError('The exit code %d is not %d'
                               % (rc, expected_exitcode))
    except Exception:
        if raise_error:
            raise

    return rc


def execute(cmd,
            raise_error=True,
            no_venv=False,
            exec_env=None,
            expect_exit=True,
            expected_exitcode=0,
            context=None):
    """
    Executes a command in a subprocess. Returns a tuple
    of (exitcode, out, err), where out is the string output
    from stdout and err is the string output from stderr when
    executing the command.

    :param cmd: Command string to execute
    :param raise_error: If returncode is not 0 (success), then
                        raise a RuntimeError? Default: True)
    :param no_venv: Disable the virtual environment
    :param exec_env: Optional dictionary of additional environment
                     variables; values may be callables, which will
                     be passed the current value of the named
                     environment variable
    :param expect_exit: Optional flag true iff timely exit is expected
    :param expected_exitcode: expected exitcode from the launcher
    :param context: additional context for error message
    """

    env = os.environ.copy()
    if exec_env is not None:
        for env_name, env_val in exec_env.items():
            if callable(env_val):
                env[env_name] = env_val(env.get(env_name))
            else:
                env[env_name] = env_val

    # If we're asked to omit the virtualenv, and if one is set up,
    # restore the various environment variables
    if no_venv and 'VIRTUAL_ENV' in env:
        # Clip off the first element of PATH
        env['PATH'] = env['PATH'].split(os.pathsep, 1)[-1]
        del env['VIRTUAL_ENV']

    # Make sure that we use the programs in the
    # current source directory's bin/ directory.
    path_ext = [os.path.join(os.getcwd(), 'bin')]

    # Also jack in the path cmd comes from, if it's absolute
    args = shlex.split(cmd)
    executable = args[0]
    if os.path.isabs(executable):
        path_ext.append(os.path.dirname(executable))

    env['PATH'] = ':'.join(path_ext) + ':' + env['PATH']
    process = subprocess.Popen(args,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env=env)
    if expect_exit:
        result = process.communicate()
        (out, err) = result
        exitcode = process.returncode
    else:
        out = ''
        err = ''
        exitcode = 0

    if exitcode != expected_exitcode and raise_error:
        msg = ("Command %(cmd)s did not succeed. Returned an exit "
               "code of %(exitcode)d."
               "\n\nSTDOUT: %(out)s"
               "\n\nSTDERR: %(err)s" % {'cmd': cmd, 'exitcode': exitcode,
                                        'out': out, 'err': err})
        if context:
            msg += "\n\nCONTEXT: %s" % context
        raise RuntimeError(msg)
    return exitcode, out, err


def find_executable(cmdname):
    """
    Searches the path for a given cmdname.  Returns an absolute
    filename if an executable with the given name exists in the path,
    or None if one does not.

    :param cmdname: The bare name of the executable to search for
    """

    # Keep an eye out for the possibility of an absolute pathname
    if os.path.isabs(cmdname):
        return cmdname

    # Get a list of the directories to search
    path = ([os.path.join(os.getcwd(), 'bin')] +
            os.environ['PATH'].split(os.pathsep))

    # Search through each in turn
    for elem in path:
        full_path = os.path.join(elem, cmdname)
        if os.access(full_path, os.X_OK):
            return full_path

    # No dice...
    return None


def get_unused_port():
    """
    Returns an unused port on localhost.
    """
    port, s = get_unused_port_and_socket()
    s.close()
    return port


def get_unused_port_and_socket():
    """
    Returns an unused port on localhost and the open socket
    from which it was created.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    addr, port = s.getsockname()
    return (port, s)


def xattr_writes_supported(path):
    """
    Returns True if the we can write a file to the supplied
    path and subsequently write a xattr to that file.
    """
    try:
        import xattr
    except ImportError:
        return False

    def set_xattr(path, key, value):
        xattr.setxattr(path, "user.%s" % key, str(value))

    # We do a quick attempt to write a user xattr to a temporary file
    # to check that the filesystem is even enabled to support xattrs
    fake_filepath = os.path.join(path, 'testing-checkme')
    result = True
    with open(fake_filepath, 'wb') as fake_file:
        fake_file.write("XXX")
        fake_file.flush()
    try:
        set_xattr(fake_filepath, 'hits', '1')
    except IOError as e:
        if e.errno == errno.EOPNOTSUPP:
            result = False
    else:
        # Cleanup after ourselves...
        if os.path.exists(fake_filepath):
            os.unlink(fake_filepath)

    return result


def minimal_headers(name, public=True):
    headers = {
        'Content-Type': 'application/octet-stream',
        'X-Image-Meta-Name': name,
        'X-Image-Meta-disk_format': 'raw',
        'X-Image-Meta-container_format': 'ovf',
    }
    if public:
        headers['X-Image-Meta-Is-Public'] = 'True'
    return headers


def minimal_add_command(port, name, suffix='', public=True):
    visibility = 'is_public=True' if public else ''
    return ("bin/glance --port=%d add %s"
            " disk_format=raw container_format=ovf"
            " name=%s %s" % (port, visibility, name, suffix))


def start_http_server(image_id, image_data):
    def _get_http_handler_class(fixture):
        class StaticHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(fixture)))
                self.end_headers()
                self.wfile.write(fixture)
                return

            def do_HEAD(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(fixture)))
                self.end_headers()
                return

            def log_message(self, *args, **kwargs):
                # Override this method to prevent debug output from going
                # to stderr during testing
                return

        return StaticHTTPRequestHandler

    server_address = ('127.0.0.1', 0)
    handler_class = _get_http_handler_class(image_data)
    httpd = BaseHTTPServer.HTTPServer(server_address, handler_class)
    port = httpd.socket.getsockname()[1]

    pid = os.fork()
    if pid == 0:
        httpd.serve_forever()
    else:
        return pid, port


class RegistryAPIMixIn(object):

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)
            with open(os.path.join(self.test_dir, fixture['id']),
                      'wb') as image:
                image.write("chunk00000remainder")

    def destroy_fixtures(self):
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def get_fixture(self, **kwargs):
        fixture = {'name': 'fake public image',
                   'status': 'active',
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'is_public': True,
                   'size': 20,
                   'checksum': None}
        fixture.update(kwargs)
        return fixture

    def get_minimal_fixture(self, **kwargs):
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}
        fixture.update(kwargs)
        return fixture

    def get_extra_fixture(self, id, name, **kwargs):
        created_at = kwargs.pop('created_at', timeutils.utcnow())
        updated_at = kwargs.pop('updated_at', created_at)
        return self.get_fixture(
            id=id, name=name, deleted=False, deleted_at=None,
            created_at=created_at, updated_at=updated_at,
            **kwargs)

    def get_api_response_ext(self, http_resp, url='/images', headers=None,
                             body=None, method=None, api=None,
                             content_type=None):
        if api is None:
            api = self.api
        if headers is None:
            headers = {}
        req = webob.Request.blank(url)
        for k, v in six.iteritems(headers):
            req.headers[k] = v
        if method:
            req.method = method
        if body:
            req.body = body
        if content_type == 'json':
            req.content_type = 'application/json'
        elif content_type == 'octet':
            req.content_type = 'application/octet-stream'
        res = req.get_response(api)
        self.assertEqual(res.status_int, http_resp)
        return res

    def assertEqualImages(self, res, uuids, key='images', unjsonify=True):
        images = jsonutils.loads(res.body)[key] if unjsonify else res
        self.assertEqual(len(images), len(uuids))
        for i, value in enumerate(uuids):
            self.assertEqual(images[i]['id'], value)


class FakeAuthMiddleware(wsgi.Middleware):

    def __init__(self, app, is_admin=False):
        super(FakeAuthMiddleware, self).__init__(app)
        self.is_admin = is_admin

    def process_request(self, req):
        auth_token = req.headers.get('X-Auth-Token')
        user = None
        tenant = None
        roles = []
        if auth_token:
            user, tenant, role = auth_token.split(':')
            if tenant.lower() == 'none':
                tenant = None
            roles = [role]
            req.headers['X-User-Id'] = user
            req.headers['X-Tenant-Id'] = tenant
            req.headers['X-Roles'] = role
            req.headers['X-Identity-Status'] = 'Confirmed'
        kwargs = {
            'user': user,
            'tenant': tenant,
            'roles': roles,
            'is_admin': self.is_admin,
            'auth_token': auth_token,
        }

        req.context = context.RequestContext(**kwargs)


class FakeHTTPResponse(object):
    def __init__(self, status=200, headers=None, data=None, *args, **kwargs):
        data = data or 'I am a teapot, short and stout\n'
        self.data = six.StringIO(data)
        self.read = self.data.read
        self.status = status
        self.headers = headers or {'content-length': len(data)}

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def getheaders(self):
        return self.headers or {}

    def read(self, amt):
        self.data.read(amt)


class Httplib2WsgiAdapter(object):
    def __init__(self, app):
        self.app = app

    def request(self, uri, method="GET", body=None, headers=None):
        req = webob.Request.blank(uri, method=method, headers=headers)
        req.body = body
        resp = req.get_response(self.app)
        return Httplib2WebobResponse(resp), resp.body


class Httplib2WebobResponse(object):
    def __init__(self, webob_resp):
        self.webob_resp = webob_resp

    @property
    def status(self):
        return self.webob_resp.status_code

    def __getitem__(self, key):
        return self.webob_resp.headers[key]

    def get(self, key):
        return self.webob_resp.headers[key]

    @property
    def allow(self):
        return self.webob_resp.allow

    @allow.setter
    def allow(self, allowed):
        if type(allowed) is not str:
            raise TypeError('Allow header should be a str')

        self.webob_resp.allow = allowed


class HttplibWsgiAdapter(object):
    def __init__(self, app):
        self.app = app
        self.req = None

    def request(self, method, url, body=None, headers=None):
        if headers is None:
            headers = {}
        self.req = webob.Request.blank(url, method=method, headers=headers)
        self.req.body = body

    def getresponse(self):
        response = self.req.get_response(self.app)
        return FakeHTTPResponse(response.status_code, response.headers,
                                response.body)
