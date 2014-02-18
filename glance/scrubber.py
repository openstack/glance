# Copyright 2010 OpenStack Foundation
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

import abc
import calendar
import eventlet
import os
import time

from oslo.config import cfg

from glance.common import crypt
from glance.common import exception
from glance.common import utils
from glance import context
from glance.openstack.common import lockutils
import glance.openstack.common.log as logging
import glance.registry.client.v1.api as registry

LOG = logging.getLogger(__name__)

scrubber_opts = [
    cfg.StrOpt('scrubber_datadir',
               default='/var/lib/glance/scrubber',
               help=_('Directory that the scrubber will use to track '
                      'information about what to delete. '
                      'Make sure this is set in glance-api.conf and '
                      'glance-scrubber.conf.')),
    cfg.IntOpt('scrub_time', default=0,
               help=_('The amount of time in seconds to delay before '
                      'performing a delete.')),
    cfg.BoolOpt('cleanup_scrubber', default=False,
                help=_('A boolean that determines if the scrubber should '
                       'clean up the files it uses for taking data. Only '
                       'one server in your deployment should be designated '
                       'the cleanup host.')),
    cfg.IntOpt('cleanup_scrubber_time', default=86400,
               help=_('Items must have a modified time that is older than '
                      'this value in order to be candidates for cleanup.'))
]

CONF = cfg.CONF
CONF.register_opts(scrubber_opts)
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


class ScrubQueue(object):
    """Image scrub queue base class.

    The queue contains image's location which need to delete from backend.
    """
    def __init__(self):
        registry.configure_registry_client()
        registry.configure_registry_admin_creds()
        self.registry = registry.get_registry_client(context.RequestContext())

    @abc.abstractmethod
    def add_location(self, image_id, uri, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param uri: The opaque image location uri
        :param user_context: The user's request context
        """
        pass

    @abc.abstractmethod
    def get_all_locations(self):
        """Returns a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        pass

    @abc.abstractmethod
    def pop_all_locations(self):
        """Pop out a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        pass

    @abc.abstractmethod
    def has_image(self, image_id):
        """Returns whether the queue contains an image or not.
        :param image_id: The opaque image identifier

        :retval a boolean value to inform including or not
        """
        pass


class ScrubFileQueue(ScrubQueue):
    """File-based image scrub queue class."""
    def __init__(self):
        super(ScrubFileQueue, self).__init__()
        self.scrubber_datadir = CONF.scrubber_datadir
        utils.safe_mkdirs(self.scrubber_datadir)
        self.scrub_time = CONF.scrub_time
        self.metadata_encryption_key = CONF.metadata_encryption_key

    def _read_queue_file(self, file_path):
        """Reading queue file to loading deleted location and timestamp out.

        :param file_path: Queue file full path

        :retval a list of image location timestamp tuple from queue file
        """
        uris = []
        delete_times = []

        try:
            with open(file_path, 'r') as f:
                while True:
                    uri = f.readline().strip()
                    if uri:
                        uris.append(uri)
                        delete_times.append(int(f.readline().strip()))
                    else:
                        break
        except Exception:
            LOG.error(_("%s file can not be read.") % file_path)

        return uris, delete_times

    def _update_queue_file(self, file_path, remove_record_idxs):
        """Updating queue file to remove such queue records.

        :param file_path: Queue file full path
        :param remove_record_idxs: A list of record index those want to remove
        """
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            # NOTE(zhiyan) we need bottom up removing to
            # keep record index be valid.
            remove_record_idxs.sort(reverse=True)
            for record_idx in remove_record_idxs:
                # Each record has two lines
                line_no = (record_idx + 1) * 2 - 1
                del lines[line_no:line_no + 2]
            with open(file_path, 'w') as f:
                f.write(''.join(lines))
            os.chmod(file_path, 0o600)
        except Exception:
            LOG.error(_("%s file can not be wrote.") % file_path)

    def add_location(self, image_id, uri, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param uri: The opaque image location uri
        :param user_context: The user's request context
        """
        if user_context is not None:
            registry_client = registry.get_registry_client(user_context)
        else:
            registry_client = self.registry

        with lockutils.lock("scrubber-%s" % image_id,
                            lock_file_prefix='glance-', external=True):

            # NOTE(zhiyan): make sure scrubber does not cleanup
            # 'pending_delete' images concurrently before the code
            # get lock and reach here.
            try:
                image = registry_client.get_image(image_id)
                if image['status'] == 'deleted':
                    return
            except exception.NotFound as e:
                LOG.error(_("Failed to find image to delete: "
                            "%(e)s"), {'e': e})
                return

            delete_time = time.time() + self.scrub_time
            file_path = os.path.join(self.scrubber_datadir, str(image_id))

            if self.metadata_encryption_key is not None:
                uri = crypt.urlsafe_encrypt(self.metadata_encryption_key,
                                            uri, 64)

            if os.path.exists(file_path):
                # Append the uri of location to the queue file
                with open(file_path, 'a') as f:
                    f.write('\n')
                    f.write('\n'.join([uri, str(int(delete_time))]))
            else:
                # NOTE(zhiyan): Protect the file before we write any data.
                open(file_path, 'w').close()
                os.chmod(file_path, 0o600)
                with open(file_path, 'w') as f:
                    f.write('\n'.join([uri, str(int(delete_time))]))
            os.utime(file_path, (delete_time, delete_time))

    def _walk_all_locations(self, remove=False):
        """Returns a list of image id and location tuple from scrub queue.

        :param remove: Whether remove location from queue or not after walk

        :retval a list of image image_id and location tuple from scrub queue
        """
        if not os.path.exists(self.scrubber_datadir):
            LOG.info(_("%s directory does not exist.") % self.scrubber_datadir)
            return []

        ret = []
        for root, dirs, files in os.walk(self.scrubber_datadir):
            for image_id in files:
                if not utils.is_uuid_like(image_id):
                    continue
                with lockutils.lock("scrubber-%s" % image_id,
                                    lock_file_prefix='glance-', external=True):
                    file_path = os.path.join(self.scrubber_datadir, image_id)
                    uris, delete_times = self._read_queue_file(file_path)

                    remove_record_idxs = []
                    skipped = False
                    for (record_idx, delete_time) in enumerate(delete_times):
                        if delete_time > time.time():
                            skipped = True
                            continue
                        else:
                            ret.append((image_id, uris[record_idx]))
                            remove_record_idxs.append(record_idx)
                    if remove:
                        if skipped:
                            # NOTE(zhiyan): remove location records from
                            # the queue file.
                            self._update_queue_file(file_path,
                                                    remove_record_idxs)
                        else:
                            utils.safe_remove(file_path)
        return ret

    def get_all_locations(self):
        """Returns a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        return self._walk_all_locations()

    def pop_all_locations(self):
        """Pop out a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        return self._walk_all_locations(remove=True)

    def has_image(self, image_id):
        """Returns whether the queue contains an image or not.

        :param image_id: The opaque image identifier

        :retval a boolean value to inform including or not
        """
        return os.path.exists(os.path.join(self.scrubber_datadir,
                                           str(image_id)))


class ScrubDBQueue(ScrubQueue):
    """Database-based image scrub queue class."""
    def __init__(self):
        super(ScrubDBQueue, self).__init__()
        self.cleanup_scrubber_time = CONF.cleanup_scrubber_time

    def add_location(self, image_id, uri, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param uri: The opaque image location uri
        :param user_context: The user's request context
        """
        raise NotImplementedError

    def _walk_all_locations(self, remove=False):
        """Returns a list of image id and location tuple from scrub queue.

        :param remove: Whether remove location from queue or not after walk

        :retval a list of image id and location tuple from scrub queue
        """
        filters = {'deleted': True,
                   'is_public': 'none',
                   'status': 'pending_delete'}
        ret = []
        for image in self.registry.get_images_detailed(filters=filters):
            deleted_at = image.get('deleted_at')
            if not deleted_at:
                continue

            # NOTE: Strip off microseconds which may occur after the last '.,'
            # Example: 2012-07-07T19:14:34.974216
            date_str = deleted_at.rsplit('.', 1)[0].rsplit(',', 1)[0]
            delete_time = calendar.timegm(time.strptime(date_str,
                                                        "%Y-%m-%dT%H:%M:%S"))

            if delete_time + self.cleanup_scrubber_time > time.time():
                continue

            ret.extend([(image['id'], location['uri'])
                        for location in image['location_data']])

            if remove:
                self.registry.update_image(image['id'], {'status': 'deleted'})
        return ret

    def get_all_locations(self):
        """Returns a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        return self._walk_all_locations()

    def pop_all_locations(self):
        """Pop out a list of image id and location tuple from scrub queue.

        :retval a list of image id and location tuple from scrub queue
        """
        return self._walk_all_locations(remove=True)

    def has_image(self, image_id):
        """Returns whether the queue contains an image or not.

        :param image_id: The opaque image identifier

        :retval a boolean value to inform including or not
        """
        try:
            image = self.registry.get_image(image_id)
            return image['status'] == 'pending_delete'
        except exception.NotFound:
            return False


_file_queue = None
_db_queue = None


def get_scrub_queues():
    global _file_queue, _db_queue
    if not _file_queue:
        _file_queue = ScrubFileQueue()
    if not _db_queue:
        _db_queue = ScrubDBQueue()
    return (_file_queue, _db_queue)


class Daemon(object):
    def __init__(self, wakeup_time=300, threads=1000):
        LOG.info(_("Starting Daemon: wakeup_time=%(wakeup_time)s "
                   "threads=%(threads)s"),
                 {'wakeup_time': wakeup_time, 'threads': threads})
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
    def __init__(self, store_api):
        LOG.info(_("Initializing scrubber with configuration: %s") %
                 unicode({'scrubber_datadir': CONF.scrubber_datadir,
                          'cleanup': CONF.cleanup_scrubber,
                          'cleanup_time': CONF.cleanup_scrubber_time,
                          'registry_host': CONF.registry_host,
                          'registry_port': CONF.registry_port}))

        utils.safe_mkdirs(CONF.scrubber_datadir)

        self.store_api = store_api

        registry.configure_registry_client()
        registry.configure_registry_admin_creds()
        self.registry = registry.get_registry_client(context.RequestContext())

        (self.file_queue, self.db_queue) = get_scrub_queues()

    def _get_delete_jobs(self, queue, pop):
        try:
            if pop:
                image_id_uri_list = queue.pop_all_locations()
            else:
                image_id_uri_list = queue.get_all_locations()
        except Exception:
            LOG.error(_("Can not %s scrub jobs from queue.") %
                      'pop' if pop else 'get')
            return None

        delete_jobs = {}
        for image_id, image_uri in image_id_uri_list:
            if image_id not in delete_jobs:
                delete_jobs[image_id] = []
            delete_jobs[image_id].append((image_id, image_uri))
        return delete_jobs

    def run(self, pool, event=None):
        delete_jobs = self._get_delete_jobs(self.file_queue, True)
        if delete_jobs:
            for image_id, jobs in delete_jobs.iteritems():
                self._scrub_image(pool, image_id, jobs)

        if CONF.cleanup_scrubber:
            self._cleanup(pool)

    def _scrub_image(self, pool, image_id, delete_jobs):
        if len(delete_jobs) == 0:
            return

        LOG.info(_("Scrubbing image %(id)s from %(count)d locations.") %
                 {'id': image_id, 'count': len(delete_jobs)})
        # NOTE(bourke): The starmap must be iterated to do work
        list(pool.starmap(self._delete_image_from_backend, delete_jobs))

        image = self.registry.get_image(image_id)
        if (image['status'] == 'pending_delete' and
                not self.file_queue.has_image(image_id)):
            self.registry.update_image(image_id, {'status': 'deleted'})

    def _delete_image_from_backend(self, image_id, uri):
        if CONF.metadata_encryption_key is not None:
            uri = crypt.urlsafe_decrypt(CONF.metadata_encryption_key, uri)

        try:
            LOG.debug(_("Deleting URI from image %(image_id)s.") %
                      {'image_id': image_id})

            # Here we create a request context with credentials to support
            # delayed delete when using multi-tenant backend storage
            admin_tenant = CONF.admin_tenant_name
            auth_token = self.registry.auth_tok
            admin_context = context.RequestContext(user=CONF.admin_user,
                                                   tenant=admin_tenant,
                                                   auth_tok=auth_token)

            self.store_api.delete_from_backend(admin_context, uri)
        except Exception:
            msg = _("Failed to delete URI from image %(image_id)s")
            LOG.error(msg % {'image_id': image_id})

    def _read_cleanup_file(self, file_path):
        """Reading cleanup to get latest cleanup timestamp.

        :param file_path: Cleanup status file full path

        :retval latest cleanup timestamp
        """
        try:
            if not os.path.exists(file_path):
                msg = _("%s file is not exists.") % unicode(file_path)
                raise Exception(msg)
            atime = int(os.path.getatime(file_path))
            mtime = int(os.path.getmtime(file_path))
            if atime != mtime:
                msg = _("%s file contains conflicting cleanup "
                        "timestamp.") % unicode(file_path)
                raise Exception(msg)
            return atime
        except Exception as e:
            LOG.error(e)
        return None

    def _update_cleanup_file(self, file_path, cleanup_time):
        """Update latest cleanup timestamp to cleanup file.

        :param file_path: Cleanup status file full path
        :param cleanup_time: The Latest cleanup timestamp
        """
        try:
            open(file_path, 'w').close()
            os.chmod(file_path, 0o600)
            os.utime(file_path, (cleanup_time, cleanup_time))
        except Exception:
            LOG.error(_("%s file can not be created.") % unicode(file_path))

    def _cleanup(self, pool):
        now = time.time()
        cleanup_file = os.path.join(CONF.scrubber_datadir, ".cleanup")
        if not os.path.exists(cleanup_file):
            self._update_cleanup_file(cleanup_file, now)
            return

        last_cleanup_time = self._read_cleanup_file(cleanup_file)
        cleanup_time = last_cleanup_time + CONF.cleanup_scrubber_time
        if cleanup_time > now:
            return

        LOG.info(_("Getting images deleted before "
                   "%s") % CONF.cleanup_scrubber_time)
        self._update_cleanup_file(cleanup_file, now)

        delete_jobs = self._get_delete_jobs(self.db_queue, False)
        if not delete_jobs:
            return

        for image_id, jobs in delete_jobs.iteritems():
            with lockutils.lock("scrubber-%s" % image_id,
                                lock_file_prefix='glance-', external=True):
                if not self.file_queue.has_image(image_id):
                    # NOTE(zhiyan): scrubber should not cleanup this image
                    # since a queue file be created for this 'pending_delete'
                    # image concurrently before the code get lock and
                    # reach here. The checking only be worth if glance-api and
                    # glance-scrubber service be deployed on a same host.
                    self._scrub_image(pool, image_id, jobs)
