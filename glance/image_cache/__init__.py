# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
LRU Cache for Image Data
"""
from contextlib import contextmanager
import datetime
import itertools
import logging
import os
import sys
import time

from glance.common import config
from glance.common import exception
from glance import utils

logger = logging.getLogger('glance.image_cache')


class ImageCache(object):
    """Provides an LRU cache for image data.

    Data is cached on READ not on WRITE; meaning if the cache is enabled, we
    attempt to read from the cache first, if we don't find the data, we begin
    streaming the data from the 'store' while simultaneously tee'ing the data
    into the cache. Subsequent reads will generate cache HITs for this image.

    Assumptions
    ===========

        1. Cache data directory exists on a filesytem that updates atime on
           reads ('noatime' should NOT be set)

        2. Cache data directory exists on a filesystem that supports xattrs.
           This is optional, but highly recommended since it allows us to
           present ops with useful information pertaining to the cache, like
           human readable filenames and statistics.

        3. `glance-prune` is scheduled to run as a periodic job via cron. This
            is needed to run the LRU prune strategy to keep the cache size
            within the limits set by the config file.


    Cache Directory Notes
    =====================

    The image cache data directory contains the main cache path, where the
    active cache entries and subdirectories for handling partial downloads
    and errored-out cache images.

    The layout looks like:

        image-cache/
            entry1
            entry2
            ...
            incomplete/
            invalid/
            prefetch/
            prefetching/
    """
    def __init__(self, options):
        self.options = options
        self._make_cache_directory_if_needed()

    def _make_cache_directory_if_needed(self):
        """Creates main cache directory along with incomplete subdirectory"""
        if not self.enabled:
            return

        # NOTE(sirp): making the incomplete_path will have the effect of
        # creating the main cache path directory as well
        paths = [self.incomplete_path, self.invalid_path, self.prefetch_path,
                 self.prefetching_path]

        for path in paths:
            if os.path.exists(path):
                continue
            logger.info(_("image cache directory doesn't exist, "
                          "creating '%s'"), path)
            os.makedirs(path)

    @property
    def enabled(self):
        return config.get_option(
            self.options, 'image_cache_enabled', type='bool', default=False)

    @property
    def path(self):
        """This is the base path for the image cache"""
        datadir = self.options['image_cache_datadir']
        return datadir

    @property
    def incomplete_path(self):
        """This provides a temporary place to write our cache entries so that
        we we're not storing incomplete objects in the cache directly.

        When the file is finished writing to, it is moved from the incomplete
        path back out into the main cache directory.

        The incomplete_path is a subdirectory of the main cache path to ensure
        that they both reside on the same filesystem and thus making moves
        cheap.
        """
        return os.path.join(self.path, 'incomplete')

    @property
    def invalid_path(self):
        """Place to move corrupted images

        If an exception is raised while we're writing an image to the
        incomplete_path, we move the incomplete image to here.
        """
        return os.path.join(self.path, 'invalid')

    @property
    def prefetch_path(self):
        """This contains a list of image ids that should be pre-fetched into
        the cache
        """
        return os.path.join(self.path, 'prefetch')

    @property
    def prefetching_path(self):
        """This contains image ids that currently being prefetched"""
        return os.path.join(self.path, 'prefetching')

    def path_for_image(self, image_id):
        """This crafts an absolute path to a specific entry"""
        return os.path.join(self.path, str(image_id))

    def incomplete_path_for_image(self, image_id):
        """This crafts an absolute path to a specific entry in the incomplete
        directory
        """
        return os.path.join(self.incomplete_path, str(image_id))

    def invalid_path_for_image(self, image_id):
        """This crafts an absolute path to a specific entry in the invalid
        directory
        """
        return os.path.join(self.invalid_path, str(image_id))

    @contextmanager
    def open(self, image_meta, mode="rb"):
        """Open a cache image for reading or writing.

        We have two possible scenarios:

            1. READ: we should attempt to read the file from the cache's
               main directory

            2. WRITE: we should write to a file under the cache's incomplete
               directory, and when it's finished, move it out the main cache
               directory.
        """
        if mode == 'wb':
            with self._open_write(image_meta, mode) as cache_file:
                yield cache_file
        elif mode == 'rb':
            with self._open_read(image_meta, mode) as cache_file:
                yield cache_file
        else:
            # NOTE(sirp): `rw` and `a' modes are not supported since image
            # data is immutable, we `wb` it once, then `rb` multiple times.
            raise Exception(_("mode '%s' not supported") % mode)

    @contextmanager
    def _open_write(self, image_meta, mode):
        image_id = image_meta['id']
        incomplete_path = self.incomplete_path_for_image(image_id)

        def set_xattr(key, value):
            utils.set_xattr(incomplete_path, key, value)

        def commit():
            set_xattr('image_name', image_meta['name'])
            set_xattr('hits', 0)

            final_path = self.path_for_image(image_id)
            logger.debug(_("fetch finished, commiting by moving "
                         "'%(incomplete_path)s' to '%(final_path)s'"),
                         dict(incomplete_path=incomplete_path,
                              final_path=final_path))
            os.rename(incomplete_path, final_path)

        def rollback(e):
            set_xattr('image_name', image_meta['name'])
            set_xattr('error', "%s" % e)

            invalid_path = self.invalid_path_for_image(image_id)
            logger.debug(_("fetch errored, rolling back by moving "
                         "'%(incomplete_path)s' to '%(invalid_path)s'"),
                         dict(incomplete_path=incomplete_path,
                              invalid_path=invalid_path))
            os.rename(incomplete_path, invalid_path)

        try:
            with open(incomplete_path, mode) as cache_file:
                set_xattr('expected_size', image_meta['size'])
                yield cache_file
        except Exception as e:
            rollback(e)
            raise
        else:
            commit()

    @contextmanager
    def _open_read(self, image_meta, mode):
        image_id = image_meta['id']
        path = self.path_for_image(image_id)
        with open(path, mode) as cache_file:
            yield cache_file

        utils.inc_xattr(path, 'hits')  # bump the hit count

    def hit(self, image_id):
        return os.path.exists(self.path_for_image(image_id))

    @staticmethod
    def _delete_file(path):
        if os.path.exists(path):
            logger.debug(_("deleting image cache file '%s'"), path)
            os.unlink(path)
        else:
            logger.warn(_("image cache file '%s' doesn't exist, unable to"
                        " delete"), path)

    def purge(self, image_id):
        path = self.path_for_image(image_id)
        self._delete_file(path)

    def clear(self):
        purged = 0
        for path in self.get_all_regular_files(self.path):
            self._delete_file(path)
            purged += 1
        return purged

    def is_image_currently_being_written(self, image_id):
        """Returns true if we're currently downloading an image"""
        incomplete_path = self.incomplete_path_for_image(image_id)
        return os.path.exists(incomplete_path)

    def is_currently_prefetching_any_images(self):
        """True if we are currently prefetching an image.

        We only allow one prefetch to occur at a time.
        """
        return len(os.listdir(self.prefetching_path)) > 0

    def is_image_queued_for_prefetch(self, image_id):
        prefetch_path = os.path.join(self.prefetch_path, str(image_id))
        return os.path.exists(prefetch_path)

    def is_image_currently_prefetching(self, image_id):
        prefetching_path = os.path.join(self.prefetching_path, str(image_id))
        return os.path.exists(prefetching_path)

    def queue_prefetch(self, image_meta):
        """This adds a image to be prefetched to the queue directory.

        If the image already exists in the queue directory or the
        prefetching directory, we ignore it.
        """
        image_id = image_meta['id']

        if self.hit(image_id):
            msg = _("Skipping prefetch, image '%s' already cached") % image_id
            logger.warn(msg)
            raise exception.Invalid(msg)

        if self.is_image_currently_prefetching(image_id):
            msg = _("Skipping prefetch, already prefetching "
                    "image '%s'") % image_id
            logger.warn(msg)
            raise exception.Invalid(msg)

        if self.is_image_queued_for_prefetch(image_id):
            msg = _("Skipping prefetch, image '%s' already queued for"
                    " prefetching") % image_id
            logger.warn(msg)
            raise exception.Invalid(msg)

        prefetch_path = os.path.join(self.prefetch_path, str(image_id))

        # Touch the file to add it to the queue
        with open(prefetch_path, "w") as f:
            pass

        utils.set_xattr(prefetch_path, 'image_name', image_meta['name'])

    def delete_queued_prefetch_image(self, image_id):
        prefetch_path = os.path.join(self.prefetch_path, str(image_id))
        self._delete_file(prefetch_path)

    def delete_prefetching_image(self, image_id):
        prefetching_path = os.path.join(self.prefetching_path, str(image_id))
        self._delete_file(prefetching_path)

    def pop_prefetch_item(self):
        """This returns the next prefetch job.

        The prefetch directory is treated like a FIFO; so we sort by modified
        time and pick the oldest.
        """
        items = []
        for path in self.get_all_regular_files(self.prefetch_path):
            mtime = os.path.getmtime(path)
            items.append((mtime, path))

        if not items:
            raise IndexError

        # Sort oldest files to the end of the list
        items.sort(reverse=True)

        mtime, path = items.pop()
        image_id = os.path.basename(path)
        return image_id

    def do_prefetch(self, image_id):
        """This moves the file from the prefetch queue path to the in-progress
        prefetching path (so we don't try to prefetch something twice).
        """
        prefetch_path = os.path.join(self.prefetch_path, str(image_id))
        prefetching_path = os.path.join(self.prefetching_path, str(image_id))
        os.rename(prefetch_path, prefetching_path)

    @staticmethod
    def get_all_regular_files(basepath):
        for fname in os.listdir(basepath):
            path = os.path.join(basepath, fname)
            if os.path.isfile(path):
                yield path

    def _base_entries(self, basepath):
        def iso8601_from_timestamp(timestamp):
            return datetime.datetime.utcfromtimestamp(timestamp)\
                                    .isoformat()

        for path in self.get_all_regular_files(basepath):
            filename = os.path.basename(path)
            try:
                image_id = int(filename)
            except ValueError, TypeError:
                continue

            entry = {}
            entry['id'] = image_id
            entry['path'] = path
            entry['name'] = utils.get_xattr(path, 'image_name',
                                            default='UNKNOWN')

            mtime = os.path.getmtime(path)
            entry['last_modified'] = iso8601_from_timestamp(mtime)

            atime = os.path.getatime(path)
            entry['last_accessed'] = iso8601_from_timestamp(atime)

            entry['size'] = os.path.getsize(path)

            entry['expected_size'] = utils.get_xattr(
                    path, 'expected_size', default='UNKNOWN')

            yield entry

    def invalid_entries(self):
        """Cache info for invalid cached images"""
        for entry in self._base_entries(self.invalid_path):
            path = entry['path']
            entry['error'] = utils.get_xattr(path, 'error', default='UNKNOWN')
            yield entry

    def incomplete_entries(self):
        """Cache info for invalid cached images"""
        for entry in self._base_entries(self.incomplete_path):
            yield entry

    def prefetch_entries(self):
        """Cache info for both queued and in-progress prefetch jobs"""
        both_entries = itertools.chain(
                        self._base_entries(self.prefetch_path),
                        self._base_entries(self.prefetching_path))

        for entry in both_entries:
            path = entry['path']
            entry['status'] = 'in-progress' if 'prefetching' in path\
                                            else 'queued'
            yield entry

    def entries(self):
        """Cache info for currently cached images"""
        for entry in self._base_entries(self.path):
            path = entry['path']
            entry['hits'] = utils.get_xattr(path, 'hits', default='UNKNOWN')
            yield entry

    def _reap_old_files(self, dirpath, entry_type, grace=None):
        """
        """
        now = time.time()
        reaped = 0
        for path in self.get_all_regular_files(dirpath):
            mtime = os.path.getmtime(path)
            age = now - mtime
            if not grace:
                logger.debug(_("No grace period, reaping '%(path)s'"
                             " immediately"), locals())
                self._delete_file(path)
                reaped += 1
            elif age > grace:
                logger.debug(_("Cache entry '%(path)s' exceeds grace period, "
                             "(%(age)i s > %(grace)i s)"), locals())
                self._delete_file(path)
                reaped += 1

        logger.info(_("Reaped %(reaped)s %(entry_type)s cache entries"),
                    locals())
        return reaped

    def reap_invalid(self, grace=None):
        """Remove any invalid cache entries

        :param grace: Number of seconds to keep an invalid entry around for
                      debugging purposes. If None, then delete immediately.
        """
        return self._reap_old_files(self.invalid_path, 'invalid', grace=grace)

    def reap_stalled(self):
        """Remove any stalled cache entries"""
        stall_timeout = int(self.options.get('image_cache_stall_timeout',
                            86400))
        return self._reap_old_files(self.incomplete_path, 'stalled',
                                    grace=stall_timeout)
