# Copyright 2010-2011 OpenStack Foundation
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

import atexit
import builtins
import logging

from glance.api import common as api_common
import glance.async_
# NOTE(akekane): Use native threading in tests, same as uWSGI production.
glance.async_.set_threadpool_model('native')


def _shutdown_cached_thread_pools():
    """Shut down cached thread pools at process exit.

    Replaces the futurist atexit hack removed in 992633. Functional tests use
    load_paste_app() rather than init_app(), so tasks_pool is not drained
    unless tearDown or this handler runs.
    """
    try:
        for name in list(api_common._CACHED_THREAD_POOL):
            pool_model = api_common._CACHED_THREAD_POOL.pop(name)
            pool = pool_model.pool
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
    except Exception:
        pass


atexit.register(_shutdown_cached_thread_pools)

# See http://code.google.com/p/python-nose/issues/detail?id=373
# The code below enables tests to work with i18n _() blocks
setattr(builtins, '_', lambda x: x)

# Set up logging to output debugging
logger = logging.getLogger()
hdlr = logging.FileHandler('run_tests.log', 'w')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.DEBUG)
