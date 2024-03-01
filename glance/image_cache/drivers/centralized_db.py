# Copyright 2024 Red Hat, Inc.
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
Cache driver that uses Centralized database of glance to store information
about cached images
"""
from contextlib import contextmanager
import os
import stat
import time

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import fileutils

from glance.common import exception
from glance import context
import glance.db
from glance.i18n import _LI, _LW
from glance.image_cache.drivers import base

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class Driver(base.Driver):

    """
    Cache driver that uses centralized database to store cache
    information.
    """

    def __init__(self):
        self.context = context.get_admin_context()
        self.db_api = glance.db.get_api()

    def configure(self):
        """
        Configure the driver to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadDriverConfiguration`
        """
        super(Driver, self).configure()
        lockutils.set_defaults(self.base_dir)

        # NOTE(abhishekk): Record the node reference in the database for
        # future use.
        node_reference_url = CONF.worker_self_reference_url
        if node_reference_url:
            try:
                self.db_api.node_reference_create(
                    self.context, node_reference_url)
            except exception.Duplicate:
                LOG.debug("Node reference is already recorded, ignoring it")

    def get_cache_size(self):
        """
        Returns the total size in bytes of the image cache.
        """
        sizes = []
        for path in self.get_cache_files(self.base_dir):
            file_info = os.stat(path)
            sizes.append(file_info[stat.ST_SIZE])
        return sum(sizes)

    def get_hit_count(self, image_id):
        """
        Return the number of hits that an image has.

        :param image_id: Opaque image identifier
        """
        if not self.is_cached(image_id):
            return 0

        node_reference_url = CONF.worker_self_reference_url
        return self.db_api.get_hit_count(self.context, image_id,
                                         node_reference_url)

    def get_cached_images(self):
        """
        Returns a list of records about cached images.
        """
        LOG.debug("Gathering cached image entries.")
        node_reference_url = CONF.worker_self_reference_url
        return self.db_api.get_cached_images(
            self.context, node_reference_url)

    def is_cached(self, image_id):
        """
        Returns True if the image with the supplied ID has its image
        file cached.

        :param image_id: Image ID
        """
        return os.path.exists(self.get_image_filepath(image_id))

    def is_cacheable(self, image_id):
        """
        Returns True if the image with the supplied ID can have its
        image file cached, False otherwise.

        :param image_id: Image ID
        """
        # Make sure we're not already cached or caching the image
        return not (self.is_cached(image_id) or
                    self.is_being_cached(image_id))

    def is_being_cached(self, image_id):
        """
        Returns True if the image with supplied id is currently
        in the process of having its image file cached.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'incomplete')
        return os.path.exists(path)

    def is_queued(self, image_id):
        """
        Returns True if the image identifier is in our cache queue.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'queue')
        return os.path.exists(path)

    def delete_all_cached_images(self):
        """
        Removes all cached image files and any attributes about the images
        """
        deleted = 0
        for path in self.get_cache_files(self.base_dir):
            delete_cached_file(path)
            deleted += 1

        node_reference_url = CONF.worker_self_reference_url
        self.db_api.delete_all_cached_images(
            self.context, node_reference_url)

        return deleted

    def delete_cached_image(self, image_id):
        """
        Removes a specific cached image file and any attributes about the image

        :param image_id: Image ID
        """
        node_reference_url = CONF.worker_self_reference_url
        path = self.get_image_filepath(image_id)
        delete_cached_file(path)
        self.db_api.delete_cached_image(
            self.context, image_id, node_reference_url)

    def delete_all_queued_images(self):
        """
        Removes all queued image files and any attributes about the images
        """
        files_deleted = 0
        for file in self.get_cache_files(self.queue_dir):
            fileutils.delete_if_exists(file)
            files_deleted += 1
        return files_deleted

    def delete_queued_image(self, image_id):
        """
        Removes a specific queued image file and any attributes about the image

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'queue')
        fileutils.delete_if_exists(path)

    def clean(self, stall_time=None):
        """
        Delete any image files in the invalid directory and any
        files in the incomplete directory that are older than a
        configurable amount of time.
        """
        self.delete_invalid_files()

        if stall_time is None:
            stall_time = CONF.image_cache_stall_time

        now = time.time()
        older_than = now - stall_time
        self.delete_stalled_files(older_than)

    def get_least_recently_accessed(self):
        """
        Return a tuple containing the image_id and size of the least recently
        accessed cached file, or None if no cached files.
        """
        node_reference_url = CONF.worker_self_reference_url
        image_id = self.db_api.get_least_recently_accessed(
            self.context, node_reference_url)

        path = self.get_image_filepath(image_id)
        try:
            file_info = os.stat(path)
            size = file_info[stat.ST_SIZE]
        except OSError:
            size = 0
        return image_id, size

    @contextmanager
    def open_for_write(self, image_id):
        """
        Open a file for writing the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        incomplete_path = self.get_image_filepath(image_id, 'incomplete')
        node_reference_url = CONF.worker_self_reference_url

        def commit():
            final_path = self.get_image_filepath(image_id)
            LOG.debug("Fetch finished, moving "
                      "'%(incomplete_path)s' to '%(final_path)s'",
                      dict(incomplete_path=incomplete_path,
                           final_path=final_path))
            os.rename(incomplete_path, final_path)

            # Make sure that we "pop" the image from the queue...
            if self.is_queued(image_id):
                fileutils.delete_if_exists(
                    self.get_image_filepath(image_id, 'queue'))

            file_size = os.path.getsize(final_path)

            self.db_api.insert_cache_details(
                self.context, node_reference_url, image_id, file_size)
            LOG.debug("Image cached successfully.")

        def rollback(e):
            if os.path.exists(incomplete_path):
                invalid_path = self.get_image_filepath(image_id, 'invalid')

                msg = (_LW("Fetch of cache file failed (%(e)s), rolling "
                           "back by moving '%(incomplete_path)s' to "
                           "'%(invalid_path)s'"),
                       {'e': e,
                        'incomplete_path': incomplete_path,
                        'invalid_path': invalid_path})
                LOG.warning(msg)
                os.rename(incomplete_path, invalid_path)

            self.db_api.delete_cached_image(
                self.context, image_id, node_reference_url)

        try:
            with open(incomplete_path, 'wb') as cache_file:
                yield cache_file
        except Exception as e:
            with excutils.save_and_reraise_exception():
                rollback(e)
        else:
            commit()
        finally:
            # if the generator filling the cache file neither raises an
            # exception, nor completes fetching all data, neither rollback
            # nor commit will have been called, so the incomplete file
            # will persist - in that case remove it as it is unusable
            # example: ^c from client fetch
            if os.path.exists(incomplete_path):
                rollback('incomplete fetch')

    @contextmanager
    def open_for_read(self, image_id):
        """
        Open and yield file for reading the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id)
        try:
            with open(path, 'rb') as cache_file:
                yield cache_file
        finally:
            node_reference_url = CONF.worker_self_reference_url
            self.db_api.update_hit_count(
                self.context, image_id, node_reference_url)

    def queue_image(self, image_id):
        """
        This adds a image to be cache to the queue.

        If the image already exists in the queue or has already been
        cached, we return False, True otherwise

        :param image_id: Image ID
        """
        if self.is_cached(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already cached."), image_id)
            return False

        if self.is_being_cached(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already being "
                         "written to cache"), image_id)
            return False

        if self.is_queued(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already queued."), image_id)
            return False

        path = self.get_image_filepath(image_id, 'queue')

        # Touch the file to add it to the queue
        with open(path, "w"):
            pass

        return True

    def delete_invalid_files(self):
        """
        Removes any invalid cache entries
        """
        for path in self.get_cache_files(self.invalid_dir):
            fileutils.delete_if_exists(path)
            LOG.info(_LI("Removed invalid cache file %s"), path)

    def delete_stalled_files(self, older_than):
        """
        Removes any incomplete cache entries older than a
        supplied modified time.

        :param older_than: Files written to on or before this timestamp
                           will be deleted.
        """
        for path in self.get_cache_files(self.incomplete_dir):
            if os.path.getmtime(path) < older_than:
                try:
                    fileutils.delete_if_exists(path)
                    LOG.info(_LI("Removed stalled cache file %s"), path)
                except Exception as e:
                    msg = (_LW("Failed to delete file %(path)s. "
                               "Got error: %(e)s"),
                           dict(path=path, e=e))
                    LOG.warning(msg)

    def get_queued_images(self):
        """
        Returns a list of image IDs that are in the queue. The
        list should be sorted by the time the image ID was inserted
        into the queue.
        """
        files = [f for f in self.get_cache_files(self.queue_dir)]
        items = []
        for path in files:
            mtime = os.path.getmtime(path)
            items.append((mtime, os.path.basename(path)))

        items.sort()
        return [image_id for (modtime, image_id) in items]

    def get_cache_files(self, basepath):
        """
        Returns cache files in the supplied directory

        :param basepath: Directory to look in for cache files
        """
        for fname in os.listdir(basepath):
            path = os.path.join(basepath, fname)
            if os.path.isfile(path) and not path.endswith(".db"):
                yield path


def delete_cached_file(path):
    LOG.debug("Deleting image cache file '%s'", path)
    fileutils.delete_if_exists(path)
