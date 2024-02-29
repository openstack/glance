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
import http.client
import http.server
import io
import os
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time
from unittest import mock

from alembic import command as alembic_command
import fixtures
from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_log.fixture import logging_error as log_fixture
from oslo_log import log
from oslo_utils import timeutils
from oslo_utils import units
import testtools
import webob

from glance.api.v2 import cached_images
from glance.common import config
from glance.common import exception
from glance.common import property_utils
from glance.common import utils
from glance.common import wsgi
from glance import context
from glance.db.sqlalchemy import alembic_migrations
from glance.db.sqlalchemy import api as db_api
from glance.tests.unit import fixtures as glance_fixtures

CONF = cfg.CONF
LOG = log.getLogger(__name__)
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
        self.mock_object(exception, '_FATAL_EXCEPTION_FORMAT_ERRORS', True)
        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self.test_dir2 = self.useFixture(fixtures.TempDir()).path
        self.conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(self.conf_dir)
        self.lock_dir = os.path.join(self.test_dir, 'locks')
        utils.safe_mkdirs(self.lock_dir)
        lockutils.set_defaults(self.lock_dir)
        self.set_policy()

        # Limit the amount of DeprecationWarning messages in the unit test logs
        self.useFixture(glance_fixtures.WarningsFixture())

        # Make sure logging output is limited but still test debug formatting
        self.useFixture(log_fixture.get_logging_handle_error_fixture())
        self.useFixture(glance_fixtures.StandardLogging())

        if cached_images.WORKER:
            cached_images.WORKER.terminate()
            cached_images.WORKER = None

    def set_policy(self):
        conf_file = "policy.yaml"
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

    def mock_object(self, obj, attr_name, *args, **kwargs):
        """"Use python mock to mock an object attribute

        Mocks the specified objects attribute with the given value.
        Automatically performs 'addCleanup' for the mock.
        """
        patcher = mock.patch.object(obj, attr_name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def delay_inaccurate_clock(self, duration=0.001):
        """Add a small delay to compensate for inaccurate system clocks.

        Some tests make assertions based on timestamps (e.g. comparing
        'created_at' and 'updated_at' fields). In some cases, subsequent
        time.time() calls may return identical values (python timestamps can
        have a lower resolution on Windows compared to Linux - 1e-7 as
        opposed to 1e-9).

        A small delay (a few ms should be negligeable) can prevent such
        issues. At the same time, it spares us from mocking the time
        module, which might be undesired.
        """

        # For now, we'll do this only for Windows. If really needed,
        # on Py3 we can get the clock resolution using time.get_clock_info,
        # but at that point we may as well just sleep 1ms all the time.
        if os.name == 'nt':
            time.sleep(duration)


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
            if os.name != 'nt':
                cmd = 'which %s' % self.exe
            else:
                cmd = 'where.exe', '%s' % self.exe

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
    :param logfile: A path to a file which will hold the stdout/err of
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
        if pass_fds:
            for fd in pass_fds:
                os.set_inheritable(fd, True)

        args = shlex.split(cmd)
        os.execvpe(args[0], args, env)
    else:
        return pid


def wait_for_fork(pid,
                  raise_error=True,
                  expected_exitcode=0,
                  force=True):
    """
    Wait for a process to complete

    This function will wait for the given pid to complete.  If the
    exit code does not match that of the expected_exitcode an error
    is raised.
    """

    # For the first period, we wait without being pushy, but after
    # this timer expires, we start sending SIGTERM
    term_timer = timeutils.StopWatch(5)
    term_timer.start()

    # After this timer expires we start sending SIGKILL
    nice_timer = timeutils.StopWatch(7)
    nice_timer.start()

    # Process gets a maximum amount of time to exit before we fail the
    # test
    total_timer = timeutils.StopWatch(10)
    total_timer.start()

    while not total_timer.expired():
        try:
            cpid, rc = os.waitpid(pid, force and os.WNOHANG or 0)
            if cpid == 0 and force:
                if not term_timer.expired():
                    # Waiting for exit on first signal
                    pass
                elif not nice_timer.expired():
                    # Politely ask the process to GTFO
                    LOG.warning('Killing child %i with SIGTERM', pid)
                    os.kill(pid, signal.SIGTERM)
                else:
                    # No more Mr. Nice Guy
                    LOG.warning('Killing child %i with SIGKILL', pid)
                    os.kill(pid, signal.SIGKILL)
                    expected_exitcode = signal.SIGKILL
                time.sleep(1)
                continue
            LOG.info('waitpid(%i) returned %i,%i', pid, cpid, rc)
            if rc != expected_exitcode:
                raise RuntimeError('The exit code %d is not %d'
                                   % (rc, expected_exitcode))
            return rc
        except ChildProcessError:
            # Nothing to wait for
            return 0
        except Exception as e:
            LOG.error('Got wait error: %s', e)
            if raise_error:
                raise

    raise RuntimeError('Gave up waiting for %i to exit!' % pid)


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
    if os.name != 'nt':
        args = shlex.split(cmd)
    else:
        args = cmd

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


def get_unused_port_ipv6():
    """
    Returns an unused port on localhost on IPv6 (uses ::1).
    """
    port, s = get_unused_port_and_socket_ipv6()
    s.close()
    return port


def get_unused_port_and_socket_ipv6():
    """
    Returns an unused port on localhost and the open socket
    from which it was created, but uses IPv6 (::1).
    """
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(('::1', 0))
    # Ignoring flowinfo and scopeid...
    addr, port, flowinfo, scopeid = s.getsockname()
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
        xattr.setxattr(path, "user.%s" % key, value)

    # We do a quick attempt to write a user xattr to a temporary file
    # to check that the filesystem is even enabled to support xattrs
    fake_filepath = os.path.join(path, 'testing-checkme')
    result = True
    with open(fake_filepath, 'wb') as fake_file:
        fake_file.write(b"XXX")
        fake_file.flush()
    try:
        set_xattr(fake_filepath, 'hits', b'1')
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
        class StaticHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(http.client.OK)
                self.send_header('Content-Length', str(len(fixture)))
                self.end_headers()
                self.wfile.write(fixture.encode('latin-1'))
                return

            def do_HEAD(self):
                # reserve non_existing_image_path for the cases where we expect
                # 404 from the server
                if 'non_existing_image_path' in self.path:
                    self.send_response(http.client.NOT_FOUND)
                else:
                    self.send_response(http.client.OK)
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
    httpd = http.server.HTTPServer(server_address, handler_class)
    port = httpd.socket.getsockname()[1]

    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()

    return thread, httpd, port


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
    def __init__(self, status=http.client.OK, headers=None, data=None,
                 *args, **kwargs):
        data = data or b'I am a teapot, short and stout\n'
        self.data = io.BytesIO(data)
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
        if isinstance(body, str):
            req.body = body.encode('utf-8')
        else:
            req.body = body
        resp = req.get_response(self.app)
        return Httplib2WebobResponse(resp), resp.body.decode('utf-8')


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


def db_sync(version='heads', engine=None):
    """Migrate the database to `version` or the most recent version."""
    if engine is None:
        engine = db_api.get_engine()

    alembic_config = alembic_migrations.get_alembic_config(engine=engine)
    alembic_command.upgrade(alembic_config, version)


def start_standalone_http_server():
    def _get_http_handler_class():
        class StaticHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                data = b"Hello World!!!"
                self.send_response(http.client.OK)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        return StaticHTTPRequestHandler

    server_address = ('127.0.0.1', 0)
    handler_class = _get_http_handler_class()
    httpd = http.server.HTTPServer(server_address, handler_class)
    port = httpd.socket.getsockname()[1]

    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()

    return thread, httpd, port


class FakeData(object):
    """Generate a bunch of data without storing it in memory.

    This acts like a read-only file object which generates fake data
    in chunks when read() is called or it is used as a generator. It
    can generate an arbitrary amount of data without storing it in
    memory.

    :param length: The number of bytes to generate
    :param chunk_size: The chunk size to return in iteration mode, or when
                       read() is called unbounded

    """
    def __init__(self, length, chunk_size=64 * units.Ki):
        self._max = length
        self._chunk_size = chunk_size
        self._len = 0

    def read(self, length=None):
        if length is None:
            length = self._chunk_size

        length = min(length, self._max - self._len)

        self._len += length
        if length == 0:
            return b''
        else:
            return b'0' * length

    def __iter__(self):
        return self

    def __next__(self):
        r = self.read()
        if len(r) == 0:
            raise StopIteration()
        else:
            return r
