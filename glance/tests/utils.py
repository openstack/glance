# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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
import random
import socket
import subprocess
import tempfile

import nose.plugins.skip

from glance.common import config
from glance.common import utils
from glance.common import wsgi


def get_isolated_test_env():
    """
    Returns a tuple of (test_id, test_dir) that is unique
    for an isolated test environment. Also ensure the test_dir
    is created.
    """
    test_id = random.randint(0, 100000)
    test_dir = os.path.join("/", "tmp", "test.%d" % test_id)
    utils.safe_mkdirs(test_dir)
    return test_id, test_dir


class TestConfigOpts(config.GlanceConfigOpts):
    """
    Support easily controllable config for unit tests, avoiding the
    need to manipulate config files directly.

    Configuration values are provided as a dictionary of key-value pairs,
    in the simplest case feeding into the DEFAULT group only.

    Non-default groups may also populated via nested dictionaries, e.g.

      {'snafu': {'foo': 'bar', 'bells': 'whistles'}}

    equates to config of form:

      [snafu]
      foo = bar
      bells = whistles

    The config so provided is dumped to a temporary file, with its path
    exposed via the temp_file property.

    :param test_values: dictionary of key-value pairs for the
                        DEFAULT group
    :param groups:      nested dictionary of key-value pairs for
                        non-default groups
    :param clean:       flag to trigger clean up of temporary directory
    """

    def __init__(self, test_values={}, groups={}, clean=True):
        super(TestConfigOpts, self).__init__()
        self._test_values = test_values
        self._test_groups = groups
        self.clean = clean

        self.temp_file = os.path.join(tempfile.mkdtemp(), 'testcfg.conf')

        self()

    def __call__(self):
        self._write_tmp_config_file()
        try:
            super(TestConfigOpts, self).\
                __call__(['--config-file', self.temp_file])
        finally:
            if self.clean:
                os.remove(self.temp_file)
                os.rmdir(os.path.dirname(self.temp_file))

    def _write_tmp_config_file(self):
        contents = '[DEFAULT]\n'
        for key, value in self._test_values.items():
            contents += '%s = %s\n' % (key, value)

        for group, settings in self._test_groups.items():
            contents += '[%s]\n' % group
            for key, value in settings.items():
                contents += '%s = %s\n' % (key, value)

        try:
            with open(self.temp_file, 'wb') as f:
                f.write(contents)
                f.flush()
        except Exception, e:
            if self.clean:
                os.remove(self.temp_file)
                os.rmdir(os.path.dirname(self.temp_file))
            raise e


class skip_test(object):
    """Decorator that skips a test."""
    def __init__(self, msg):
        self.message = msg

    def __call__(self, func):
        def _skipper(*args, **kw):
            """Wrapped skipper function."""
            raise nose.SkipTest(self.message)
        _skipper.__name__ = func.__name__
        _skipper.__doc__ = func.__doc__
        return _skipper


class skip_if(object):
    """Decorator that skips a test if condition is true."""
    def __init__(self, condition, msg):
        self.condition = condition
        self.message = msg

    def __call__(self, func):
        def _skipper(*args, **kw):
            """Wrapped skipper function."""
            if self.condition:
                raise nose.SkipTest(self.message)
            func(*args, **kw)
        _skipper.__name__ = func.__name__
        _skipper.__doc__ = func.__doc__
        return _skipper


class skip_unless(object):
    """Decorator that skips a test if condition is not true."""
    def __init__(self, condition, msg):
        self.condition = condition
        self.message = msg

    def __call__(self, func):
        def _skipper(*args, **kw):
            """Wrapped skipper function."""
            if not self.condition:
                raise nose.SkipTest(self.message)
            func(*args, **kw)
        _skipper.__name__ = func.__name__
        _skipper.__doc__ = func.__doc__
        return _skipper


class requires(object):
    """Decorator that initiates additional test setup/teardown."""
    def __init__(self, setup, teardown=None):
        self.setup = setup
        self.teardown = teardown

    def __call__(self, func):
        def _runner(*args, **kw):
            self.setup(args[0])
            func(*args, **kw)
            if self.teardown:
                self.teardown(args[0])
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
            raise nose.SkipTest(message)
        func(*a, **kwargs)
    return wrapped


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
    executable = cmd.split()[0]
    if os.path.isabs(executable):
        path_ext.append(os.path.dirname(executable))

    env['PATH'] = ':'.join(path_ext) + ':' + env['PATH']
    process = subprocess.Popen(cmd,
                               shell=True,
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
        msg = "Command %(cmd)s did not succeed. Returned an exit "\
              "code of %(exitcode)d."\
              "\n\nSTDOUT: %(out)s"\
              "\n\nSTDERR: %(err)s" % locals()
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
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    addr, port = s.getsockname()
    s.close()
    return port


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
    except IOError, e:
        if e.errno == errno.EOPNOTSUPP:
            result = False
    else:
        # Cleanup after ourselves...
        if os.path.exists(fake_filepath):
            os.unlink(fake_filepath)

    return result


def minimal_headers(name, public=True):
    headers = {'Content-Type': 'application/octet-stream',
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


class FakeAuthMiddleware(wsgi.Middleware):

    def __init__(self, app, conf, **local_conf):
        super(FakeAuthMiddleware, self).__init__(app)

    def process_request(self, req):
        auth_tok = req.headers.get('X-Auth-Token')
        if auth_tok:
            status, user, tenant, role = auth_tok.split(':')
            req.headers['X-Identity-Status'] = status
            req.headers['X-User-Id'] = user
            req.headers['X-Tenant-Id'] = tenant
            req.headers['X-Role'] = role
