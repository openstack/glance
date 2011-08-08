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

import functools
import os
import socket
import subprocess

import nose.plugins.skip


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


def skip_if_disabled(func):
    """Decorator that skips a test if test case is disabled."""
    @functools.wraps(func)
    def wrapped(*a, **kwargs):
        func.__test__ = False
        test_obj = a[0]
        message = getattr(test_obj, 'disabled_message',
                          'Test disabled')
        if test_obj.disabled:
            raise nose.SkipTest(message)
        func(*a, **kwargs)
    return wrapped


def execute(cmd, raise_error=True):
    """
    Executes a command in a subprocess. Returns a tuple
    of (exitcode, out, err), where out is the string output
    from stdout and err is the string output from stderr when
    executing the command.

    :param cmd: Command string to execute
    :param raise_error: If returncode is not 0 (success), then
                        raise a RuntimeError? Default: True)
    """

    env = os.environ.copy()

    # Make sure that we use the programs in the
    # current source directory's bin/ directory.
    env['PATH'] = os.path.join(os.getcwd(), 'bin') + ':' + env['PATH']
    process = subprocess.Popen(cmd,
                               shell=True,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env=env)
    result = process.communicate()
    (out, err) = result
    exitcode = process.returncode
    if process.returncode != 0 and raise_error:
        msg = "Command %(cmd)s did not succeed. Returned an exit "\
              "code of %(exitcode)d."\
              "\n\nSTDOUT: %(out)s"\
              "\n\nSTDERR: %(err)s" % locals()
        raise RuntimeError(msg)
    return exitcode, out, err


def get_unused_port():
    """
    Returns an unused port on localhost.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    addr, port = s.getsockname()
    s.close()
    return port
