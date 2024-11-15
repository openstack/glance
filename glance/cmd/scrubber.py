#!/usr/bin/env python

# Copyright 2011-2012 OpenStack Foundation
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
Glance Scrub Service
"""

import os
import sys

import eventlet
eventlet.patcher.monkey_patch()

import subprocess

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

import glance_store
from oslo_config import cfg
from oslo_log import log as logging

from glance.common import config
from glance.common import exception
from glance import scrubber


CONF = cfg.CONF
logging.register_options(CONF)
CONF.set_default(name='use_stderr', default=True)


def main():
    try:
        CONF.register_cli_opts(scrubber.scrubber_cmd_cli_opts)
        CONF.register_opts(scrubber.scrubber_cmd_opts)

        config.parse_args()
        logging.setup(CONF, 'glance')
        CONF.import_opt('enabled_backends', 'glance.common.wsgi')

        if CONF.enabled_backends:
            glance_store.register_store_opts(CONF)
            glance_store.create_multi_stores(CONF)
            glance_store.verify_store()
        else:
            glance_store.register_opts(CONF)
            glance_store.create_stores(CONF)
            glance_store.verify_default_store()

        if CONF.restore and CONF.daemon:
            sys.exit("ERROR: The restore and daemon options should not be set "
                     "together. Please use either of them in one request.")

        app = scrubber.Scrubber(glance_store)

        if CONF.restore:
            if scrubber_already_running():
                already_running_msg = (
                    "ERROR: glance-scrubber is already running. "
                    "Please ensure that the daemon is stopped.")
                sys.exit(already_running_msg)

            app.revert_image_status(CONF.restore)
        elif CONF.daemon:
            server = scrubber.Daemon(CONF.wakeup_time)
            server.start(app)
            server.wait()
        else:
            app.run()
    except (exception.ImageNotFound, exception.Conflict) as e:
        sys.exit("ERROR: %s" % e)
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


def scrubber_already_running():
    # Try to check the glance-scrubber is running or not.
    # 1. Try to find the pid file if scrubber is controlled by
    #    glance-control
    # 2. Try to check the process name.
    pid_file = '/var/run/glance/glance-scrubber.pid'
    if os.path.exists(os.path.abspath(pid_file)):
        return True

    for glance_scrubber_name in ['glance-scrubber',
                                 'glance.cmd.scrubber']:
        cmd = subprocess.Popen(
            ['/usr/bin/pgrep', '-f', glance_scrubber_name],
            stdout=subprocess.PIPE, shell=False)
        pids, _ = cmd.communicate()

        # The response format of subprocess.Popen.communicate() is
        # diffderent between py2 and py3. It's "string" in py2, but
        # "bytes" in py3.
        if isinstance(pids, bytes):
            pids = pids.decode()
        self_pid = os.getpid()

        if pids.count('\n') > 1 and str(self_pid) in pids:
            # One process is self, so if the process number is > 1, it
            # means that another glance-scrubber process is running.
            return True
        elif pids.count('\n') > 0 and str(self_pid) not in pids:
            # If self is not in result and the pids number is still
            # > 0, it means that the another glance-scrubber process is
            # running.
            return True

    return False


if __name__ == '__main__':
    main()
