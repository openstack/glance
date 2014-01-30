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

from oslo.config import cfg

from glance.common import config
from glance.openstack.common import log
from glance import scrubber
import glance.store

CONF = cfg.CONF


def main():
    CONF.register_cli_opt(
        cfg.BoolOpt('daemon',
                    short='D',
                    default=False,
                    help='Run as a long-running process. When not '
                         'specified (the default) run the scrub operation '
                         'once and then exits. When specified do not exit '
                         'and run scrub on wakeup_time interval as '
                         'specified in the config.'))
    CONF.register_opt(cfg.IntOpt('wakeup_time', default=300))

    try:

        config.parse_args()
        log.setup('glance')

        glance.store.create_stores()
        glance.store.verify_default_store()

        app = scrubber.Scrubber(glance.store)

        if CONF.daemon:
            server = scrubber.Daemon(CONF.wakeup_time)
            server.start(app)
            server.wait()
        else:
            import eventlet
            pool = eventlet.greenpool.GreenPool(1000)
            app.run(pool)
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


if __name__ == '__main__':
    main()
