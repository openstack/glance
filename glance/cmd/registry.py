#!/usr/bin/env python

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 OpenStack Foundation
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
Reference implementation server for Glance Registry
"""

import os
import sys

import eventlet
# NOTE(jokke): As per the eventlet commit
# b756447bab51046dfc6f1e0e299cc997ab343701 there's circular import happening
# which can be solved making sure the hubs are properly and fully imported
# before calling monkey_patch(). This is solved in eventlet 0.22.0 but we
# need to address it before that is widely used around.
eventlet.hubs.get_hub()

if os.name == 'nt':
    # eventlet monkey patching the os module causes subprocess.Popen to fail
    # on Windows when using pipes due to missing non-blocking IO support.
    eventlet.patcher.monkey_patch(os=False)
else:
    eventlet.patcher.monkey_patch()

from oslo_reports import guru_meditation_report as gmr
from oslo_utils import encodeutils

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from oslo_config import cfg
from oslo_log import log as logging
import osprofiler.initializer

from glance.common import config
from glance.common import wsgi
from glance import notifier
from glance import version

CONF = cfg.CONF
CONF.import_group("profiler", "glance.common.wsgi")
logging.register_options(CONF)
wsgi.register_cli_opts()


def main():
    try:
        config.parse_args()
        config.set_config_defaults()
        wsgi.set_eventlet_hub()
        logging.setup(CONF, 'glance')
        gmr.TextGuruMeditation.setup_autorun(version)
        notifier.set_defaults()

        if CONF.profiler.enabled:
            osprofiler.initializer.init_from_conf(
                conf=CONF,
                context={},
                project="glance",
                service="registry",
                host=CONF.bind_host
            )

        server = wsgi.Server()
        server.start(config.load_paste_app('glance-registry'),
                     default_port=9191)
        server.wait()
    except RuntimeError as e:
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))


if __name__ == '__main__':
    main()
