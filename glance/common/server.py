# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Base functionality for nova daemons - gradually being replaced with twistd.py.
"""

import daemon
from daemon import pidlockfile
import logging
import logging.handlers
import os
import pprint
import signal
import sys
import time


def stop(pidfile):
    """
    Stop the daemon
    """
    # Get the pid from the pidfile
    try:
        pid = int(open(pidfile, 'r').read().strip())
    except IOError:
        message = "pidfile %s does not exist. Daemon not running?\n"
        sys.stderr.write(message % pidfile)
        return

    # Try killing the daemon process
    try:
        while 1:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.1)
    except OSError, err:
        err = str(err)
        if err.find("No such process") > 0:
            if os.path.exists(pidfile):
                os.remove(pidfile)
        else:
            print str(err)
            sys.exit(1)


def serve(name, main, options, args):
    """Controller for server"""

    pidfile = options['pidfile']
    if pidfile == 'None':
        options['pidfile'] = '%s.pid' % name

    action = 'start'
    if len(args) > 1:
        action = args.pop()

    if action == 'stop':
        stop(options['pidfile'])
        sys.exit()
    elif action == 'restart':
        stop(options['pidfile'])
    elif action == 'start':
        pass
    else:
        print 'usage: %s [options] [start|stop|restart]' % name
        sys.exit(1)
    daemonize(args, name, main, options)


def daemonize(args, name, main, options):
    """Does the work of daemonizing the process"""
    logging.getLogger('amqplib').setLevel(logging.WARN)
    pidfile = options['pidfile']
    logfile = options['logfile']
    if logfile == "None":
        logfile = None
    logdir = options['logdir']
    if logdir == "None":
        logdir = None
    files_to_keep = []
    if bool(options['daemonize']):
        logger = logging.getLogger()
        formatter = logging.Formatter(
                name + '(%(name)s): %(levelname)s %(message)s')
        if bool(options['use_syslog']) and not logfile:
            syslog = logging.handlers.SysLogHandler(address='/dev/log')
            syslog.setFormatter(formatter)
            logger.addHandler(syslog)
            files_to_keep.append(syslog.socket)
        else:
            if not logfile:
                logfile = '%s.log' % name
            if logdir:
                logfile = os.path.join(logdir, logfile)
            logfile = logging.FileHandler(logfile)
            logfile.setFormatter(formatter)
            logger.addHandler(logfile)
            files_to_keep.append(logfile.stream)
        stdin, stdout, stderr = None, None, None
    else:
        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr

    if bool(options['verbose']):
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    with daemon.DaemonContext(
            detach_process=bool(options['daemonize']),
            working_directory=options['working_directory'],
            pidfile=pidlockfile.TimeoutPIDLockFile(pidfile,
                                                   acquire_timeout=1,
                                                   threaded=False),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            uid=int(options['uid']),
            gid=int(options['gid']),
            files_preserve=files_to_keep):
        main(args)
