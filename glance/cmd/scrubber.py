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

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)
import eventlet

import glance_store
from oslo_config import cfg
from oslo_log import log as logging

from glance.common import config
from glance import scrubber

eventlet.patcher.monkey_patch(all=False, socket=True, time=True, select=True,
                              thread=True, os=True)

CONF = cfg.CONF
logging.register_options(CONF)


def main():
    CONF.register_cli_opts(scrubber.scrubber_cmd_cli_opts)
    CONF.register_opts(scrubber.scrubber_cmd_opts)

    try:
        config.parse_args()
        logging.setup(CONF, 'glance')

        glance_store.register_opts(config.CONF)
        glance_store.create_stores(config.CONF)
        glance_store.verify_default_store()

        app = scrubber.Scrubber(glance_store)

        if CONF.daemon:
            server = scrubber.Daemon(CONF.wakeup_time)
            server.start(app)
            server.wait()
        else:
            app.run()
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


if __name__ == '__main__':
    main()
