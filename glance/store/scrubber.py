# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

import datetime
import eventlet
import logging

from glance import registry
from glance import store
from glance.common import config
from glance.common import exception
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.store.scrubber')


class Daemon(object):
    def __init__(self, wakeup_time=300, threads=1000):
        logger.info("Starting Daemon: " +
                    "wakeup_time=%s threads=%s" % (wakeup_time, threads))
        self.wakeup_time = wakeup_time
        self.event = eventlet.event.Event()
        self.pool = eventlet.greenpool.GreenPool(threads)

    def start(self, application):
        self._run(application)

    def wait(self):
        try:
            self.event.wait()
        except KeyboardInterrupt:
            logger.info("Daemon Shutdown on KeyboardInterrupt")

    def _run(self, application):
        logger.debug("Runing application")
        self.pool.spawn_n(application.run, self.event, self.pool)
        eventlet.spawn_after(self.wakeup_time, self._run, application)
        logger.debug("Next run scheduled in %s seconds" % self.wakeup_time)


class Scrubber(object):
    def __init__(self, options):
        logger.info("Initializing scrubber with options: %s" % options)
        self.options = options
        scrub_time = config.get_option(options, 'scrub_time', type='int',
                                       default=0)
        scrub_time = int(self.options.get('scrub_time', 0))
        logger.info("Scrub interval set to %s seconds" % scrub_time)
        self.scrub_time = datetime.timedelta(seconds=scrub_time)
        db_api.configure_db(options)

    def run(self, event, pool):
        delete_time = datetime.datetime.utcnow() - self.scrub_time
        logger.info("Getting images deleted before %s" % delete_time)
        pending = db_api.image_get_all_pending_delete(None, delete_time)
        logger.info("Deleting %s images" % len(pending))
        delete_work = [(p['id'], p['location']) for p in pending]
        pool.starmap(self._delete, delete_work)

    def _delete(self, id, location):
        try:
            logger.debug("Deleting %s" % location)
            store.delete_from_backend(location)
        except (store.UnsupportedBackend, exception.NotFound):
            msg = "Failed to delete image from store (%s). "
            logger.error(msg % uri)

        context = {'deleted': True}
        db_api.image_update(context, id, {'status': 'deleted'})


def app_factory(global_config, **local_conf):
    conf = global_config.copy()
    conf.update(local_conf)
    return Scrubber(conf)
