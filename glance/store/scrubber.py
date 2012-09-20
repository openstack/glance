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

import calendar
import eventlet
import os
import time

from glance import context
from glance.common import utils
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
from glance import registry
from glance import store
import glance.store.filesystem
import glance.store.http
import glance.store.s3
import glance.store.swift

LOG = logging.getLogger(__name__)

scrubber_opts = [
    cfg.BoolOpt('cleanup_scrubber', default=False),
    cfg.IntOpt('cleanup_scrubber_time', default=86400)
    ]

CONF = cfg.CONF
CONF.register_opts(scrubber_opts)


class Daemon(object):
    def __init__(self, wakeup_time=300, threads=1000):
        LOG.info(_("Starting Daemon: wakeup_time=%(wakeup_time)s "
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
            LOG.info(msg)

    def _run(self, application):
        LOG.debug(_("Running application"))
        self.pool.spawn_n(application.run, self.pool, self.event)
        eventlet.spawn_after(self.wakeup_time, self._run, application)
        LOG.debug(_("Next run scheduled in %s seconds") % self.wakeup_time)


class Scrubber(object):
    CLEANUP_FILE = ".cleanup"

    def __init__(self):
        self.datadir = CONF.scrubber_datadir
        self.cleanup = CONF.cleanup_scrubber
        self.cleanup_time = CONF.cleanup_scrubber_time
        # configs for registry API store auth
        self.admin_user = CONF.admin_user
        self.admin_tenant = CONF.admin_tenant_name

        host, port = CONF.registry_host, CONF.registry_port

        LOG.info(_("Initializing scrubber with conf: %s") %
                 {'datadir': self.datadir, 'cleanup': self.cleanup,
                  'cleanup_time': self.cleanup_time,
                  'registry_host': host, 'registry_port': port})

        registry.configure_registry_client()
        registry.configure_registry_admin_creds()
        ctx = context.RequestContext()
        self.registry = registry.get_registry_client(ctx)

        utils.safe_mkdirs(self.datadir)

        store.create_stores()

    def run(self, pool, event=None):
        now = time.time()

        if not os.path.exists(self.datadir):
            LOG.info(_("%s does not exist") % self.datadir)
            return

        delete_work = []
        for root, dirs, files in os.walk(self.datadir):
            for id in files:
                if id == self.CLEANUP_FILE:
                    continue

                file_name = os.path.join(root, id)
                delete_time = os.stat(file_name).st_mtime

                if delete_time > now:
                    continue

                uri, delete_time = read_queue_file(file_name)

                if delete_time > now:
                    continue

                delete_work.append((id, uri, now))

        LOG.info(_("Deleting %s images") % len(delete_work))
        pool.starmap(self._delete, delete_work)
        # NOTE(bourke): When not running as a daemon, a slight pause is needed
        # to allow the starmap to begin it's work.
        eventlet.sleep(0.1)

        if self.cleanup:
            self._cleanup(pool)

    def _delete(self, id, uri, now):
        file_path = os.path.join(self.datadir, str(id))
        try:
            LOG.debug(_("Deleting %(uri)s") % {'uri': uri})
            # Here we create a request context with credentials to support
            # delayed delete when using multi-tenant backend storage
            ctx = context.RequestContext(auth_tok=self.registry.auth_tok,
                                         user=self.admin_user,
                                         tenant=self.admin_tenant)
            store.delete_from_backend(ctx, uri)
        except store.UnsupportedBackend:
            msg = _("Failed to delete image from store (%(uri)s).")
            LOG.error(msg % {'uri': uri})
            write_queue_file(file_path, uri, now)

        self.registry.update_image(id, {'status': 'deleted'})
        utils.safe_remove(file_path)

    def _cleanup(self, pool):
        now = time.time()
        cleanup_file = os.path.join(self.datadir, self.CLEANUP_FILE)
        if not os.path.exists(cleanup_file):
            write_queue_file(cleanup_file, 'cleanup', now)
            return

        _uri, last_run_time = read_queue_file(cleanup_file)
        cleanup_time = last_run_time + self.cleanup_time
        if cleanup_time > now:
            return

        LOG.info(_("Getting images deleted before %s") % self.cleanup_time)
        write_queue_file(cleanup_file, 'cleanup', now)

        filters = {'deleted': True, 'is_public': 'none',
                   'status': 'pending_delete'}
        pending_deletes = self.registry.get_images_detailed(filters=filters)

        delete_work = []
        for pending_delete in pending_deletes:
            deleted_at = pending_delete.get('deleted_at')
            if not deleted_at:
                continue

            time_fmt = "%Y-%m-%dT%H:%M:%S"
            # NOTE: Strip off microseconds which may occur after the last '.,'
            # Example: 2012-07-07T19:14:34.974216
            date_str = deleted_at.rsplit('.', 1)[0].rsplit(',', 1)[0]
            delete_time = calendar.timegm(time.strptime(date_str,
                                                        time_fmt))

            if delete_time + self.cleanup_time > now:
                continue

            delete_work.append((pending_delete['id'],
                                pending_delete['location'],
                                now))

        LOG.info(_("Deleting %s images") % len(delete_work))
        pool.starmap(self._delete, delete_work)


def read_queue_file(file_path):
    with open(file_path) as f:
        uri = f.readline().strip()
        delete_time = int(f.readline().strip())
    return uri, delete_time


def write_queue_file(file_path, uri, delete_time):
    with open(file_path, 'w') as f:
        f.write('\n'.join([uri, str(int(delete_time))]))
    os.chmod(file_path, 0600)
    os.utime(file_path, (delete_time, delete_time))
