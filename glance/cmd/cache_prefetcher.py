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
Glance Image Cache Pre-fetcher

This is meant to be run from the command line after queueing
images to be pretched.
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

import glance_store
from oslo_log import log as logging

import glance.async_
from glance.common import config
from glance.image_cache import prefetcher

CONF = config.CONF
logging.register_options(CONF)
CONF.set_default(name='use_stderr', default=True)


def main():
    try:
        config.parse_cache_args()
        logging.setup(CONF, 'glance')
        CONF.import_opt('enabled_backends', 'glance.common.wsgi')
        glance.async_.set_threadpool_model('eventlet')

        if CONF.enabled_backends:
            glance_store.register_store_opts(CONF)
            glance_store.create_multi_stores(CONF)
            glance_store.verify_store()
        else:
            glance_store.register_opts(CONF)
            glance_store.create_stores(CONF)
            glance_store.verify_default_store()

        app = prefetcher.Prefetcher()
        app.run()
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


if __name__ == '__main__':
    main()
