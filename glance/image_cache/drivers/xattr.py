# Copyright 2011 OpenStack Foundation
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
Cache driver that uses xattr file tags and requires a filesystem
that has atimes set.

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

$image_cache_dir/
  entry1
  entry2
  ...
  incomplete/
  invalid/
  queue/
"""
from contextlib import contextmanager
import errno
import os
import stat
import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from oslo_utils import fileutils
import six
import xattr

from glance.common import exception
from glance.i18n import _, _LI
from glance.image_cache.drivers import base

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class Driver(base.Driver):

    """
    Cache driver that uses xattr file tags and requires a filesystem
    that has atimes set.
    """

    def configure(self):
        """
        Configure the driver to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadDriverConfiguration`
        """
        # Here we set up the various file-based image cache paths
        # that we need in order to find the files in different states
        # of cache management.
        self.set_paths()

        # We do a quick attempt to write a user xattr to a temporary file
        # to check that the filesystem is even enabled to support xattrs
        image_cache_dir = self.base_dir
        fake_image_filepath = os.path.join(image_cache_dir, 'checkme')
        with open(fake_image_filepath, 'wb') as fake_file:
            fake_file.write(b"XXX")
            fake_file.flush()
        try:
            set_xattr(fake_image_filepath, 'hits', '1')
        except IOError as e:
            if e.errno == errno.EOPNOTSUPP:
                msg = (_("The device housing the image cache directory "
                         "%(image_cache_dir)s does not support xattr. It is"
                         " likely you need to edit your fstab and add the "
                         "user_xattr option to the appropriate line for the"
                         " device housing the cache directory.") %
                       {'image_cache_dir': image_cache_dir})
                LOG.error(msg)
                raise exception.BadDriverConfiguration(driver_name="xattr",
                                                       reason=msg)
        else:
            # Cleanup after ourselves...
            fileutils.delete_if_exists(fake_image_filepath)

    def get_cache_size(self):
        """
        Returns the total size in bytes of the image cache.
        """
        sizes = []
        for path in get_all_regular_files(self.base_dir):
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

        path = self.get_image_filepath(image_id)
        return int(get_xattr(path, 'hits', default=0))

    def get_cached_images(self):
        """
        Returns a list of records about cached images.
        """
        LOG.debug("Gathering cached image entries.")
        entries = []
        for path in get_all_regular_files(self.base_dir):
            image_id = os.path.basename(path)

            entry = {'image_id': image_id}
            file_info = os.stat(path)
            entry['last_modified'] = file_info[stat.ST_MTIME]
            entry['last_accessed'] = file_info[stat.ST_ATIME]
            entry['size'] = file_info[stat.ST_SIZE]
            entry['hits'] = self.get_hit_count(image_id)

            entries.append(entry)
        return entries

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
        """
        path = self.get_image_filepath(image_id, 'queue')
        return os.path.exists(path)

    def delete_all_cached_images(self):
        """
        Removes all cached image files and any attributes about the images
        """
        deleted = 0
        for path in get_all_regular_files(self.base_dir):
            delete_cached_file(path)
            deleted += 1
        return deleted

    def delete_cached_image(self, image_id):
        """
        Removes a specific cached image file and any attributes about the image

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id)
        delete_cached_file(path)

    def delete_all_queued_images(self):
        """
        Removes all queued image files and any attributes about the images
        """
        files = [f for f in get_all_regular_files(self.queue_dir)]
        for file in files:
            fileutils.delete_if_exists(file)
        return len(files)

    def delete_queued_image(self, image_id):
        """
        Removes a specific queued image file and any attributes about the image

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'queue')
        fileutils.delete_if_exists(path)

    def get_least_recently_accessed(self):
        """
        Return a tuple containing the image_id and size of the least recently
        accessed cached file, or None if no cached files.
        """
        stats = []
        for path in get_all_regular_files(self.base_dir):
            file_info = os.stat(path)
            stats.append((file_info[stat.ST_ATIME],  # access time
                          file_info[stat.ST_SIZE],   # size in bytes
                          path))                     # absolute path

        if not stats:
            return None

        stats.sort()
        return os.path.basename(stats[0][2]), stats[0][1]

    @contextmanager
    def open_for_write(self, image_id):
        """
        Open a file for writing the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        incomplete_path = self.get_image_filepath(image_id, 'incomplete')

        def set_attr(key, value):
            set_xattr(incomplete_path, key, value)

        def commit():
            set_attr('hits', 0)

            final_path = self.get_image_filepath(image_id)
            LOG.debug("Fetch finished, moving "
                      "'%(incomplete_path)s' to '%(final_path)s'",
                      dict(incomplete_path=incomplete_path,
                           final_path=final_path))
            os.rename(incomplete_path, final_path)

            # Make sure that we "pop" the image from the queue...
            if self.is_queued(image_id):
                LOG.debug("Removing image '%s' from queue after "
                          "caching it.", image_id)
                fileutils.delete_if_exists(
                    self.get_image_filepath(image_id, 'queue'))

        def rollback(e):
            set_attr('error', encodeutils.exception_to_unicode(e))

            invalid_path = self.get_image_filepath(image_id, 'invalid')
            LOG.debug("Fetch of cache file failed (%(e)s), rolling back by "
                      "moving '%(incomplete_path)s' to "
                      "'%(invalid_path)s'",
                      {'e': encodeutils.exception_to_unicode(e),
                       'incomplete_path': incomplete_path,
                       'invalid_path': invalid_path})
            os.rename(incomplete_path, invalid_path)

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
        with open(path, 'rb') as cache_file:
            yield cache_file
        path = self.get_image_filepath(image_id)
        inc_xattr(path, 'hits', 1)

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
        LOG.debug("Queueing image '%s'.", image_id)

        # Touch the file to add it to the queue
        with open(path, "w"):
            pass

        return True

    def get_queued_images(self):
        """
        Returns a list of image IDs that are in the queue. The
        list should be sorted by the time the image ID was inserted
        into the queue.
        """
        files = [f for f in get_all_regular_files(self.queue_dir)]
        items = []
        for path in files:
            mtime = os.path.getmtime(path)
            items.append((mtime, os.path.basename(path)))

        items.sort()
        return [image_id for (modtime, image_id) in items]

    def _reap_old_files(self, dirpath, entry_type, grace=None):
        now = time.time()
        reaped = 0
        for path in get_all_regular_files(dirpath):
            mtime = os.path.getmtime(path)
            age = now - mtime
            if not grace:
                LOG.debug("No grace period, reaping '%(path)s'"
                          " immediately", {'path': path})
                delete_cached_file(path)
                reaped += 1
            elif age > grace:
                LOG.debug("Cache entry '%(path)s' exceeds grace period, "
                          "(%(age)i s > %(grace)i s)",
                          {'path': path, 'age': age, 'grace': grace})
                delete_cached_file(path)
                reaped += 1

        LOG.info(_LI("Reaped %(reaped)s %(entry_type)s cache entries"),
                 {'reaped': reaped, 'entry_type': entry_type})
        return reaped

    def reap_invalid(self, grace=None):
        """Remove any invalid cache entries

        :param grace: Number of seconds to keep an invalid entry around for
                      debugging purposes. If None, then delete immediately.
        """
        return self._reap_old_files(self.invalid_dir, 'invalid', grace=grace)

    def reap_stalled(self, grace=None):
        """Remove any stalled cache entries

        :param grace: Number of seconds to keep an invalid entry around for
                      debugging purposes. If None, then delete immediately.
        """
        return self._reap_old_files(self.incomplete_dir, 'stalled',
                                    grace=grace)

    def clean(self, stall_time=None):
        """
        Delete any image files in the invalid directory and any
        files in the incomplete directory that are older than a
        configurable amount of time.
        """
        self.reap_invalid()

        if stall_time is None:
            stall_time = CONF.image_cache_stall_time

        self.reap_stalled(stall_time)


def get_all_regular_files(basepath):
    for fname in os.listdir(basepath):
        path = os.path.join(basepath, fname)
        if os.path.isfile(path):
            yield path


def delete_cached_file(path):
    LOG.debug("Deleting image cache file '%s'", path)
    fileutils.delete_if_exists(path)


def _make_namespaced_xattr_key(key, namespace='user'):
    """
    Create a fully-qualified xattr-key by including the intended namespace.

    Namespacing differs among OSes[1]:

        FreeBSD: user, system
        Linux: user, system, trusted, security
        MacOS X: not needed

    Mac OS X won't break if we include a namespace qualifier, so, for
    simplicity, we always include it.

    --
    [1] http://en.wikipedia.org/wiki/Extended_file_attributes
    """
    namespaced_key = ".".join([namespace, key])
    return namespaced_key


def get_xattr(path, key, **kwargs):
    """Return the value for a particular xattr

    If the key doesn't not exist, or xattrs aren't supported by the file
    system then a KeyError will be raised, that is, unless you specify a
    default using kwargs.
    """
    namespaced_key = _make_namespaced_xattr_key(key)
    try:
        return xattr.getxattr(path, namespaced_key)
    except IOError:
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise


def set_xattr(path, key, value):
    """Set the value of a specified xattr.

    If xattrs aren't supported by the file-system, we skip setting the value.
    """
    namespaced_key = _make_namespaced_xattr_key(key)
    if not isinstance(value, six.binary_type):
        value = str(value)
        if six.PY3:
            value = value.encode('utf-8')
    xattr.setxattr(path, namespaced_key, value)


def inc_xattr(path, key, n=1):
    """
    Increment the value of an xattr (assuming it is an integer).

    BEWARE, this code *does* have a RACE CONDITION, since the
    read/update/write sequence is not atomic.

    Since the use-case for this function is collecting stats--not critical--
    the benefits of simple, lock-free code out-weighs the possibility of an
    occasional hit not being counted.
    """
    count = int(get_xattr(path, key))
    count += n
    set_xattr(path, key, str(count))
