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

import futurist._thread as futurist_thread

import glance.async_
# NOTE(akekane): Use native threading in tests, same as uWSGI production.
# Standalone glance-api still uses eventlet but that is not common.
glance.async_.set_threadpool_model('native')


def _patched_clean_up():
    """Join futurist worker threads with timeout at test exit.

    Without timeout, join() can hang if workers are still running.
    """
    futurist_thread._dying = True
    threads_to_wait_for = []
    while futurist_thread._to_be_cleaned:
        worker, _ = futurist_thread._to_be_cleaned.popitem()
        worker.stop()
        threads_to_wait_for.append(worker)

    for worker in threads_to_wait_for:
        try:
            worker.join(timeout=0.1)
        except Exception:
            pass


# NOTE(akekane): Replace futurist atexit handler. Only needed for tests.
try:
    atexit.unregister(futurist_thread._clean_up)
except ValueError:
    pass

# Use patched version with join timeout to avoid hang
atexit.register(_patched_clean_up)

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
