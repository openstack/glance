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
import glance.store.filesystem
import glance.store.http
import glance.store.s3
import glance.store.swift
from glance.common import config
from glance.registry import context
from glance.common import exception
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.store.scrubber')


class Daemon(object):
    def __init__(self, wakeup_time=300, threads=1000):
        logger.info(_("Starting Daemon: wakeup_time=%(wakeup_time)s "
                      "threads=%(threads)s") % locals())
        self.wakeup_time = wakeup_time
        self.event = eventlet.event.Event()
        self.pool = eventlet.greenpool.GreenPool(threads)

    def start(self, application):
        self._run(application)

    def wait(self):
        try:
            self.event.wait()
        except KeyboardInterrupt:
            msg = _("Daemon Shutdown on KeyboardInterrupt")
            logger.info(msg)

    def _run(self, application):
        logger.debug(_("Runing application"))
        self.pool.spawn_n(application.run, self.pool, self.event)
        eventlet.spawn_after(self.wakeup_time, self._run, application)
        logger.debug(_("Next run scheduled in %s seconds") % self.wakeup_time)


class Scrubber(object):
    def __init__(self, options):
        logger.info(_("Initializing scrubber with options: %s") % options)
        self.options = options
        scrub_time = config.get_option(options, 'scrub_time', type='int',
                                       default=0)
        logger.info(_("Scrub interval set to %s seconds") % scrub_time)
        self.scrub_time = datetime.timedelta(seconds=scrub_time)
        db_api.configure_db(options)
        store.create_stores(options)

    def run(self, pool, event=None):
        delete_time = datetime.datetime.utcnow() - self.scrub_time
        logger.info(_("Getting images deleted before %s") % delete_time)
        pending = db_api.image_get_all_pending_delete(None, delete_time)
        num_pending = len(pending)
        logger.info(_("Deleting %(num_pending)s images") % locals())
        delete_work = [(p['id'], p['location']) for p in pending]
        pool.starmap(self._delete, delete_work)

    def _delete(self, image_id, location):
        try:
            logger.debug(_("Deleting %(location)s") % locals())
            store.delete_from_backend(location)
        except (store.UnsupportedBackend, exception.NotFound):
            msg = _("Failed to delete image from store (%(uri)s).") % locals()
            logger.error(msg)

        ctx = context.RequestContext(is_admin=True, show_deleted=True)
        db_api.image_update(ctx, image_id, {'status': 'deleted'})


def app_factory(global_config, **local_conf):
    conf = global_config.copy()
    conf.update(local_conf)
    return Scrubber(conf)
