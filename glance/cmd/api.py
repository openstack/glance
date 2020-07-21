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
Glance API Server
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

# Monkey patch the original current_thread to use the up-to-date _active
# global variable. See https://bugs.launchpad.net/bugs/1863021 and
# https://github.com/eventlet/eventlet/issues/592
import __original_module_threading as orig_threading
import threading
orig_threading.current_thread.__globals__['_active'] = threading._active

from oslo_reports import guru_meditation_report as gmr
from oslo_utils import encodeutils

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
import osprofiler.initializer

import glance.async_
from glance.common import config
from glance.common import exception
from glance.common import wsgi
from glance import notifier
from glance import version

CONF = cfg.CONF
CONF.import_group("profiler", "glance.common.wsgi")
logging.register_options(CONF)
wsgi.register_cli_opts()

# NOTE(rosmaita): Any new exceptions added should preserve the current
# error codes for backward compatibility.  The value 99 is returned
# for errors not listed in this map.
ERROR_CODE_MAP = {RuntimeError: 1,
                  exception.WorkerCreationFailure: 2,
                  glance_store.exceptions.BadStoreConfiguration: 3,
                  ValueError: 4,
                  cfg.ConfigFileValueError: 5}


def fail(e):
    sys.stderr.write("ERROR: %s\n" % encodeutils.exception_to_unicode(e))
    return_code = ERROR_CODE_MAP.get(type(e), 99)
    sys.exit(return_code)


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
                service="api",
                host=CONF.bind_host
            )

        # NOTE(danms): Configure system-wide threading model to use eventlet
        glance.async_.set_threadpool_model('eventlet')

        # NOTE(abhishekk): Added initialize_prefetcher KW argument to Server
        # object so that prefetcher object should only be initialized in case
        # of API service and ignored in case of registry. Once registry is
        # removed this parameter should be removed as well.
        initialize_prefetcher = False
        if CONF.paste_deploy.flavor == 'keystone+cachemanagement':
            initialize_prefetcher = True
        server = wsgi.Server(initialize_glance_store=True,
                             initialize_prefetcher=initialize_prefetcher)
        server.start(config.load_paste_app('glance-api'), default_port=9292)
        server.wait()
    except Exception as e:
        fail(e)


if __name__ == '__main__':
    main()
