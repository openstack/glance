# Copyright (c) 2011 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Helper script for starting/stopping/reloading Glance server programs.
Thanks for some of the code, Swifties ;)
"""

import argparse
import fcntl
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from oslo_config import cfg
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.common import config
from glance.i18n import _

CONF = cfg.CONF

ALL_COMMANDS = ['start', 'status', 'stop', 'shutdown', 'restart',
                'reload', 'force-reload']
ALL_SERVERS = ['api', 'scrubber']
RELOAD_SERVERS = ['glance-api']
GRACEFUL_SHUTDOWN_SERVERS = ['glance-api', 'glance-scrubber']
MAX_DESCRIPTORS = 32768
MAX_MEMORY = 2 * units.Gi  # 2 GB
USAGE = """%(prog)s [options] <SERVER> <COMMAND> [CONFPATH]

Where <SERVER> is one of:

    all, {0}

And command is one of:

    {1}

And CONFPATH is the optional configuration file to use.""".format(
    ', '.join(ALL_SERVERS), ', '.join(ALL_COMMANDS))

exitcode = 0


def gated_by(predicate):
    def wrap(f):
        def wrapped_f(*args):
            if predicate:
                return f(*args)
            else:
                return None
        return wrapped_f
    return wrap


def pid_files(server, pid_file):
    pid_files = []
    if pid_file:
        if os.path.exists(os.path.abspath(pid_file)):
            pid_files = [os.path.abspath(pid_file)]
    else:
        if os.path.exists('/var/run/glance/%s.pid' % server):
            pid_files = ['/var/run/glance/%s.pid' % server]
    for pid_file in pid_files:
        pid = int(open(pid_file).read().strip())
        yield pid_file, pid


def do_start(verb, pid_file, server, args):
    if verb != 'Respawn' and pid_file == CONF.pid_file:
        for pid_file, pid in pid_files(server, pid_file):
            if os.path.exists('/proc/%s' % pid):
                print(_("%(serv)s appears to already be running: %(pid)s") %
                      {'serv': server, 'pid': pid_file})
                return
            else:
                print(_("Removing stale pid file %s") % pid_file)
                os.unlink(pid_file)

        try:
            resource.setrlimit(resource.RLIMIT_NOFILE,
                               (MAX_DESCRIPTORS, MAX_DESCRIPTORS))
            resource.setrlimit(resource.RLIMIT_DATA,
                               (MAX_MEMORY, MAX_MEMORY))
        except ValueError:
            print(_('Unable to increase file descriptor limit.  '
                    'Running as non-root?'))
        os.environ['PYTHON_EGG_CACHE'] = '/tmp'

    def write_pid_file(pid_file, pid):
        with open(pid_file, 'w') as fp:
            fp.write('%d\n' % pid)

    def redirect_to_null(fds):
        with open(os.devnull, 'r+b') as nullfile:
            for desc in fds:  # close fds
                try:
                    os.dup2(nullfile.fileno(), desc)
                except OSError:
                    pass

    def redirect_to_syslog(fds, server):
        log_cmd = 'logger'
        log_cmd_params = '-t "%s[%d]"' % (server, os.getpid())
        process = subprocess.Popen([log_cmd, log_cmd_params],
                                   stdin=subprocess.PIPE)
        for desc in fds:  # pipe to logger command
            try:
                os.dup2(process.stdin.fileno(), desc)
            except OSError:
                pass

    def redirect_stdio(server, capture_output):
        input = [sys.stdin.fileno()]
        output = [sys.stdout.fileno(), sys.stderr.fileno()]

        redirect_to_null(input)
        if capture_output:
            redirect_to_syslog(output, server)
        else:
            redirect_to_null(output)

    @gated_by(CONF.capture_output)
    def close_stdio_on_exec():
        fds = [sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()]
        for desc in fds:  # set close on exec flag
            fcntl.fcntl(desc, fcntl.F_SETFD, fcntl.FD_CLOEXEC)

    def launch(pid_file, conf_file=None, capture_output=False, await_time=0):
        args = [server]
        if conf_file:
            args += ['--config-file', conf_file]
            msg = (_('%(verb)sing %(serv)s with %(conf)s') %
                   {'verb': verb, 'serv': server, 'conf': conf_file})
        else:
            msg = (_('%(verb)sing %(serv)s') % {'verb': verb, 'serv': server})
        print(msg)

        close_stdio_on_exec()

        pid = os.fork()
        if pid == 0:
            os.setsid()
            redirect_stdio(server, capture_output)
            try:
                os.execlp('%s' % server, *args)
            except OSError as e:
                msg = (_('unable to launch %(serv)s. Got error: %(e)s') %
                       {'serv': server, 'e': e})
                sys.exit(msg)
            sys.exit(0)
        else:
            write_pid_file(pid_file, pid)
            await_child(pid, await_time)
            return pid

    @gated_by(CONF.await_child)
    def await_child(pid, await_time):
        bail_time = time.time() + await_time
        while time.time() < bail_time:
            reported_pid, status = os.waitpid(pid, os.WNOHANG)
            if reported_pid == pid:
                global exitcode
                exitcode = os.WEXITSTATUS(status)
                break
            time.sleep(0.05)

    conf_file = None
    if args and os.path.exists(args[0]):
        conf_file = os.path.abspath(os.path.expanduser(args[0]))

    return launch(pid_file, conf_file, CONF.capture_output, CONF.await_child)


def do_check_status(pid_file, server):
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as pidfile:
            pid = pidfile.read().strip()
        print(_("%(serv)s (pid %(pid)s) is running...") %
              {'serv': server, 'pid': pid})
    else:
        print(_("%s is stopped") % server)


def get_pid_file(server, pid_file):
    pid_file = (os.path.abspath(pid_file) if pid_file else
                '/var/run/glance/%s.pid' % server)
    dir, file = os.path.split(pid_file)

    if not os.path.exists(dir):
        try:
            os.makedirs(dir)
        except OSError:
            pass

    if not os.access(dir, os.W_OK):
        fallback = os.path.join(tempfile.mkdtemp(), '%s.pid' % server)
        msg = (_('Unable to create pid file %(pid)s.  Running as non-root?\n'
                 'Falling back to a temp file, you can stop %(service)s '
                 'service using:\n'
                 '  %(file)s %(server)s stop --pid-file %(fb)s') %
               {'pid': pid_file,
                'service': server,
                'file': __file__,
                'server': server,
                'fb': fallback})
        print(msg)
        pid_file = fallback

    return pid_file


def do_reload(pid_file, server):
    if server not in RELOAD_SERVERS:
        msg = (_('Reload of %(serv)s not supported') % {'serv': server})
        sys.exit(msg)

    pid = None
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as pidfile:
            pid = int(pidfile.read().strip())
    else:
        msg = (_('Server %(serv)s is stopped') % {'serv': server})
        sys.exit(msg)

    sig = signal.SIGHUP
    try:
        print(_('Reloading %(serv)s (pid %(pid)s) with signal(%(sig)s)')
              % {'serv': server, 'pid': pid, 'sig': sig})
        os.kill(pid, sig)
    except OSError:
        print(_("Process %d not running") % pid)


def do_stop(server, args, graceful=False):
    if graceful and server in GRACEFUL_SHUTDOWN_SERVERS:
        sig = signal.SIGHUP
    else:
        sig = signal.SIGTERM

    did_anything = False
    pfiles = pid_files(server, CONF.pid_file)
    for pid_file, pid in pfiles:
        did_anything = True
        try:
            os.unlink(pid_file)
        except OSError:
            pass
        try:
            print(_('Stopping %(serv)s (pid %(pid)s) with signal(%(sig)s)')
                  % {'serv': server, 'pid': pid, 'sig': sig})
            os.kill(pid, sig)
        except OSError:
            print(_("Process %d not running") % pid)
    for pid_file, pid in pfiles:
        for _junk in range(150):  # 15 seconds
            if not os.path.exists('/proc/%s' % pid):
                break
            time.sleep(0.1)
        else:
            print(_('Waited 15 seconds for pid %(pid)s (%(file)s) to die;'
                    ' giving up') % {'pid': pid, 'file': pid_file})
    if not did_anything:
        print(_('%s is already stopped') % server)


def add_command_parsers(subparsers):
    cmd_parser = argparse.ArgumentParser(add_help=False)
    cmd_subparsers = cmd_parser.add_subparsers(dest='command')
    for cmd in ALL_COMMANDS:
        parser = cmd_subparsers.add_parser(cmd)
        parser.add_argument('args', nargs=argparse.REMAINDER)

    for server in ALL_SERVERS:
        full_name = 'glance-' + server

        parser = subparsers.add_parser(server, parents=[cmd_parser])
        parser.set_defaults(servers=[full_name])

        parser = subparsers.add_parser(full_name, parents=[cmd_parser])
        parser.set_defaults(servers=[full_name])

    parser = subparsers.add_parser('all', parents=[cmd_parser])
    parser.set_defaults(servers=['glance-' + s for s in ALL_SERVERS])


def main():
    global exitcode

    opts = [
        cfg.SubCommandOpt('server',
                          title='Server types',
                          help='Available server types',
                          handler=add_command_parsers),
        cfg.StrOpt('pid-file',
                   metavar='PATH',
                   help='File to use as pid file. Default: '
                   '/var/run/glance/$server.pid.'),
        cfg.IntOpt('await-child',
                   metavar='DELAY',
                   default=0,
                   help='Period to wait for service death '
                        'in order to report exit code '
                        '(default is to not wait at all).'),
        cfg.BoolOpt('capture-output',
                    default=False,
                    help='Capture stdout/err in syslog '
                    'instead of discarding it.'),
        cfg.BoolOpt('respawn',
                    default=False,
                    help='Restart service on unexpected death.'),
    ]
    CONF.register_cli_opts(opts)

    config.parse_args(usage=USAGE)

    @gated_by(CONF.await_child)
    @gated_by(CONF.respawn)
    def mutually_exclusive():
        sys.stderr.write('--await-child and --respawn are mutually exclusive')
        sys.exit(1)

    mutually_exclusive()

    @gated_by(CONF.respawn)
    def anticipate_respawn(children):
        while children:
            pid, status = os.wait()
            if pid in children:
                (pid_file, server, args) = children.pop(pid)
                running = os.path.exists(pid_file)
                one_second_ago = time.time() - 1
                bouncing = (running and
                            os.path.getmtime(pid_file) >= one_second_ago)
                if running and not bouncing:
                    args = (pid_file, server, args)
                    new_pid = do_start('Respawn', *args)
                    children[new_pid] = args
                else:
                    rsn = 'bouncing' if bouncing else 'deliberately stopped'
                    print(_('Suppressed respawn as %(serv)s was %(rsn)s.')
                          % {'serv': server, 'rsn': rsn})

    if CONF.server.command == 'start':
        children = {}
        for server in CONF.server.servers:
            pid_file = get_pid_file(server, CONF.pid_file)
            args = (pid_file, server, CONF.server.args)
            pid = do_start('Start', *args)
            children[pid] = args

        anticipate_respawn(children)

    if CONF.server.command == 'status':
        for server in CONF.server.servers:
            pid_file = get_pid_file(server, CONF.pid_file)
            do_check_status(pid_file, server)

    if CONF.server.command == 'stop':
        for server in CONF.server.servers:
            do_stop(server, CONF.server.args)

    if CONF.server.command == 'shutdown':
        for server in CONF.server.servers:
            do_stop(server, CONF.server.args, graceful=True)

    if CONF.server.command == 'restart':
        for server in CONF.server.servers:
            do_stop(server, CONF.server.args)
        for server in CONF.server.servers:
            pid_file = get_pid_file(server, CONF.pid_file)
            do_start('Restart', pid_file, server, CONF.server.args)

    if CONF.server.command in ('reload', 'force-reload'):
        for server in CONF.server.servers:
            pid_file = get_pid_file(server, CONF.pid_file)
            do_reload(pid_file, server)

    sys.exit(exitcode)
