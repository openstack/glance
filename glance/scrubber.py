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
import os
import time

import eventlet
from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging
import six

from glance.common import crypt
from glance.common import exception
from glance.common import utils
from glance import context
import glance.db as db_api
from glance import i18n
import glance.registry.client.v1.api as registry

LOG = logging.getLogger(__name__)

_ = i18n._
_LI = i18n._LI
_LW = i18n._LW
_LE = i18n._LE

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
    cfg.BoolOpt('delayed_delete', default=False,
                help=_('Turn on/off delayed delete.')),
    cfg.IntOpt('cleanup_scrubber_time', default=86400,
               help=_('Items must have a modified time that is older than '
                      'this value in order to be candidates for cleanup.'))
]

scrubber_cmd_opts = [
    cfg.IntOpt('wakeup_time', default=300,
               help=_('Loop time between checking for new '
                      'items to schedule for delete.'))
]

scrubber_cmd_cli_opts = [
    cfg.BoolOpt('daemon',
                short='D',
                default=False,
                help=_('Run as a long-running process. When not '
                       'specified (the default) run the scrub operation '
                       'once and then exits. When specified do not exit '
                       'and run scrub on wakeup_time interval as '
                       'specified in the config.'))
]

CONF = cfg.CONF
CONF.register_opts(scrubber_opts)
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


class ScrubQueue(object):
    """Image scrub queue base class.

    The queue contains image's location which need to delete from backend.
    """
    def __init__(self):
        self.scrub_time = CONF.scrub_time
        self.metadata_encryption_key = CONF.metadata_encryption_key
        registry.configure_registry_client()
        registry.configure_registry_admin_creds()
        self.registry = registry.get_registry_client(context.RequestContext())

    @abc.abstractmethod
    def add_location(self, image_id, location, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param location: The opaque image location
        :param user_context: The user's request context

        :retval A boolean value to indicate success or not
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

    def _read_queue_file(self, file_path):
        """Reading queue file to loading deleted location and timestamp out.

        :param file_path: Queue file full path

        :retval a list of image location id, uri and timestamp tuple
        """
        loc_ids = []
        uris = []
        delete_times = []

        try:
            with open(file_path, 'r') as f:
                while True:
                    loc_id = f.readline().strip()
                    if loc_id:
                        lid = six.text_type(loc_id)
                        loc_ids.append(int(lid) if lid.isdigit() else lid)
                        uris.append(unicode(f.readline().strip()))
                        delete_times.append(int(f.readline().strip()))
                    else:
                        break
            return loc_ids, uris, delete_times
        except Exception:
            LOG.error(_LE("%s file can not be read.") % file_path)

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
                # Each record has three lines:
                # location id, uri and delete time.
                line_no = (record_idx + 1) * 3 - 1
                del lines[line_no:line_no + 3]
            with open(file_path, 'w') as f:
                f.write(''.join(lines))
            os.chmod(file_path, 0o600)
        except Exception:
            LOG.error(_LE("%s file can not be wrote.") % file_path)

    def add_location(self, image_id, location, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param location: The opaque image location
        :param user_context: The user's request context

        :retval A boolean value to indicate success or not
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
                    return True
            except exception.NotFound as e:
                LOG.warn(_LW("Failed to find image to delete: %s"),
                         utils.exception_to_str(e))
                return False

            loc_id = location.get('id', '-')
            if self.metadata_encryption_key:
                uri = crypt.urlsafe_encrypt(self.metadata_encryption_key,
                                            location['url'], 64)
            else:
                uri = location['url']
            delete_time = time.time() + self.scrub_time
            file_path = os.path.join(self.scrubber_datadir, str(image_id))

            if os.path.exists(file_path):
                # Append the uri of location to the queue file
                with open(file_path, 'a') as f:
                    f.write('\n')
                    f.write('\n'.join([str(loc_id),
                                       uri,
                                       str(int(delete_time))]))
            else:
                # NOTE(zhiyan): Protect the file before we write any data.
                open(file_path, 'w').close()
                os.chmod(file_path, 0o600)
                with open(file_path, 'w') as f:
                    f.write('\n'.join([str(loc_id),
                                       uri,
                                       str(int(delete_time))]))
            os.utime(file_path, (delete_time, delete_time))

            return True

    def _walk_all_locations(self, remove=False):
        """Returns a list of image id and location tuple from scrub queue.

        :param remove: Whether remove location from queue or not after walk

        :retval a list of image id, location id and uri tuple from scrub queue
        """
        if not os.path.exists(self.scrubber_datadir):
            LOG.warn(_LW("%s directory does not exist.") %
                     self.scrubber_datadir)
            return []

        ret = []
        for root, dirs, files in os.walk(self.scrubber_datadir):
            for image_id in files:
                if not utils.is_uuid_like(image_id):
                    continue
                with lockutils.lock("scrubber-%s" % image_id,
                                    lock_file_prefix='glance-', external=True):
                    file_path = os.path.join(self.scrubber_datadir, image_id)
                    records = self._read_queue_file(file_path)
                    loc_ids, uris, delete_times = records

                    remove_record_idxs = []
                    skipped = False
                    for (record_idx, delete_time) in enumerate(delete_times):
                        if delete_time > time.time():
                            skipped = True
                            continue
                        else:
                            ret.append((image_id,
                                        loc_ids[record_idx],
                                        uris[record_idx]))
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
        admin_tenant_name = CONF.admin_tenant_name
        admin_token = self.registry.auth_token
        self.admin_context = context.RequestContext(user=CONF.admin_user,
                                                    tenant=admin_tenant_name,
                                                    auth_token=admin_token)

    def add_location(self, image_id, location, user_context=None):
        """Adding image location to scrub queue.

        :param image_id: The opaque image identifier
        :param location: The opaque image location
        :param user_context: The user's request context

        :retval A boolean value to indicate success or not
        """
        loc_id = location.get('id')
        if loc_id:
            db_api.get_api().image_location_delete(self.admin_context,
                                                   image_id, loc_id,
                                                   'pending_delete')
            return True
        else:
            return False

    def _get_images_page(self, marker):
        filters = {'deleted': True,
                   'is_public': 'none',
                   'status': 'pending_delete'}

        if marker:
            return self.registry.get_images_detailed(filters=filters,
                                                     marker=marker)
        else:
            return self.registry.get_images_detailed(filters=filters)

    def _get_all_images(self):
        """Generator to fetch all appropriate images, paging as needed."""

        marker = None
        while True:
            images = self._get_images_page(marker)
            if len(images) == 0:
                break
            marker = images[-1]['id']

            for image in images:
                yield image

    def _walk_all_locations(self, remove=False):
        """Returns a list of image id and location tuple from scrub queue.

        :param remove: Whether remove location from queue or not after walk

        :retval a list of image id, location id and uri tuple from scrub queue
        """
        ret = []

        for image in self._get_all_images():
            deleted_at = image.get('deleted_at')
            if not deleted_at:
                continue

            # NOTE: Strip off microseconds which may occur after the last '.,'
            # Example: 2012-07-07T19:14:34.974216
            date_str = deleted_at.rsplit('.', 1)[0].rsplit(',', 1)[0]
            delete_time = calendar.timegm(time.strptime(date_str,
                                                        "%Y-%m-%dT%H:%M:%S"))

            if delete_time + self.scrub_time > time.time():
                continue

            for loc in image['location_data']:
                if loc['status'] != 'pending_delete':
                    continue

                if self.metadata_encryption_key:
                    uri = crypt.urlsafe_encrypt(self.metadata_encryption_key,
                                                loc['url'], 64)
                else:
                    uri = loc['url']

                ret.append((image['id'], loc['id'], uri))

                if remove:
                    db_api.get_api().image_location_delete(self.admin_context,
                                                           image['id'],
                                                           loc['id'],
                                                           'deleted')
                    self.registry.update_image(image['id'],
                                               {'status': 'deleted'})
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
        LOG.info(_LI("Starting Daemon: wakeup_time=%(wakeup_time)s "
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
            msg = _LI("Daemon Shutdown on KeyboardInterrupt")
            LOG.info(msg)

    def _run(self, application):
        LOG.debug("Running application")
        self.pool.spawn_n(application.run, self.pool, self.event)
        eventlet.spawn_after(self.wakeup_time, self._run, application)
        LOG.debug("Next run scheduled in %s seconds" % self.wakeup_time)


class Scrubber(object):
    def __init__(self, store_api):
        LOG.info(_LI("Initializing scrubber with configuration: %s") %
                 six.text_type({'scrubber_datadir': CONF.scrubber_datadir,
                                'cleanup': CONF.cleanup_scrubber,
                                'cleanup_time': CONF.cleanup_scrubber_time,
                                'registry_host': CONF.registry_host,
                                'registry_port': CONF.registry_port}))

        utils.safe_mkdirs(CONF.scrubber_datadir)

        self.store_api = store_api

        registry.configure_registry_client()
        registry.configure_registry_admin_creds()
        self.registry = registry.get_registry_client(context.RequestContext())

        # Here we create a request context with credentials to support
        # delayed delete when using multi-tenant backend storage
        admin_tenant = CONF.admin_tenant_name
        auth_token = self.registry.auth_token
        self.admin_context = context.RequestContext(user=CONF.admin_user,
                                                    tenant=admin_tenant,
                                                    auth_token=auth_token)

        (self.file_queue, self.db_queue) = get_scrub_queues()

    def _get_delete_jobs(self, queue, pop):
        try:
            if pop:
                records = queue.pop_all_locations()
            else:
                records = queue.get_all_locations()
        except Exception as err:
            LOG.error(_LE("Can not %(op)s scrub jobs from queue: %(err)s") %
                      {'op': 'pop' if pop else 'get',
                       'err': utils.exception_to_str(err)})
            return {}

        delete_jobs = {}
        for image_id, loc_id, loc_uri in records:
            if image_id not in delete_jobs:
                delete_jobs[image_id] = []
            delete_jobs[image_id].append((image_id, loc_id, loc_uri))
        return delete_jobs

    def _merge_delete_jobs(self, file_jobs, db_jobs):
        ret = {}
        for image_id, file_job_items in file_jobs.iteritems():
            ret[image_id] = file_job_items
            db_job_items = db_jobs.get(image_id, [])
            for db_item in db_job_items:
                if db_item not in file_job_items:
                    ret[image_id].append(db_item)
        for image_id, db_job_items in db_jobs.iteritems():
            if image_id not in ret:
                ret[image_id] = db_job_items
        return ret

    def run(self, pool, event=None):
        file_jobs = self._get_delete_jobs(self.file_queue, True)
        db_jobs = self._get_delete_jobs(self.db_queue, False)
        delete_jobs = self._merge_delete_jobs(file_jobs, db_jobs)

        if delete_jobs:
            for image_id, jobs in six.iteritems(delete_jobs):
                self._scrub_image(pool, image_id, jobs)

        if CONF.cleanup_scrubber:
            self._cleanup(pool)

    def _scrub_image(self, pool, image_id, delete_jobs):
        if len(delete_jobs) == 0:
            return

        LOG.info(_LI("Scrubbing image %(id)s from %(count)d locations.") %
                 {'id': image_id, 'count': len(delete_jobs)})
        # NOTE(bourke): The starmap must be iterated to do work
        list(pool.starmap(self._delete_image_location_from_backend,
                          delete_jobs))

        image = self.registry.get_image(image_id)
        if (image['status'] == 'pending_delete' and
                not self.file_queue.has_image(image_id)):
            self.registry.update_image(image_id, {'status': 'deleted'})

    def _delete_image_location_from_backend(self, image_id, loc_id, uri):
        if CONF.metadata_encryption_key:
            uri = crypt.urlsafe_decrypt(CONF.metadata_encryption_key, uri)

        try:
            LOG.debug("Deleting URI from image %s." % image_id)
            self.store_api.delete_from_backend(uri, self.admin_context)
            if loc_id != '-':
                db_api.get_api().image_location_delete(self.admin_context,
                                                       image_id,
                                                       int(loc_id),
                                                       'deleted')
            LOG.info(_LI("Image %s has been deleted.") % image_id)
        except Exception:
            LOG.warn(_LW("Unable to delete URI from image %s.") % image_id)

    def _read_cleanup_file(self, file_path):
        """Reading cleanup to get latest cleanup timestamp.

        :param file_path: Cleanup status file full path

        :retval latest cleanup timestamp
        """
        try:
            if not os.path.exists(file_path):
                msg = _("%s file is not exists.") % six.text_type(file_path)
                raise Exception(msg)
            atime = int(os.path.getatime(file_path))
            mtime = int(os.path.getmtime(file_path))
            if atime != mtime:
                msg = _("%s file contains conflicting cleanup "
                        "timestamp.") % six.text_type(file_path)
                raise Exception(msg)
            return atime
        except Exception as e:
            LOG.error(utils.exception_to_str(e))
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
            LOG.error(_LE("%s file can not be created.") %
                      six.text_type(file_path))

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

        LOG.info(_LI("Getting images deleted before %s") %
                 CONF.cleanup_scrubber_time)
        self._update_cleanup_file(cleanup_file, now)

        delete_jobs = self._get_delete_jobs(self.db_queue, False)
        if not delete_jobs:
            return

        for image_id, jobs in six.iteritems(delete_jobs):
            with lockutils.lock("scrubber-%s" % image_id,
                                lock_file_prefix='glance-', external=True):
                if not self.file_queue.has_image(image_id):
                    # NOTE(zhiyan): scrubber should not cleanup this image
                    # since a queue file be created for this 'pending_delete'
                    # image concurrently before the code get lock and
                    # reach here. The checking only be worth if glance-api and
                    # glance-scrubber service be deployed on a same host.
                    self._scrub_image(pool, image_id, jobs)
