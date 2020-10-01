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
LRU Cache for Image Data
"""

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from oslo_utils import importutils
from oslo_utils.secretutils import md5
from oslo_utils import units

from glance.common import exception
from glance.common import utils
from glance.i18n import _, _LE, _LI, _LW

LOG = logging.getLogger(__name__)

image_cache_opts = [
    cfg.StrOpt('image_cache_driver', default='sqlite',
               choices=('sqlite', 'xattr'), ignore_case=True,
               help=_("""
The driver to use for image cache management.

This configuration option provides the flexibility to choose between the
different image-cache drivers available. An image-cache driver is responsible
for providing the essential functions of image-cache like write images to/read
images from cache, track age and usage of cached images, provide a list of
cached images, fetch size of the cache, queue images for caching and clean up
the cache, etc.

The essential functions of a driver are defined in the base class
``glance.image_cache.drivers.base.Driver``. All image-cache drivers (existing
and prospective) must implement this interface. Currently available drivers
are ``sqlite`` and ``xattr``. These drivers primarily differ in the way they
store the information about cached images:

* The ``sqlite`` driver uses a sqlite database (which sits on every glance
  node locally) to track the usage of cached images.
* The ``xattr`` driver uses the extended attributes of files to store this
  information. It also requires a filesystem that sets ``atime`` on the files
  when accessed.

Possible values:
    * sqlite
    * xattr

Related options:
    * None

""")),

    cfg.IntOpt('image_cache_max_size', default=10 * units.Gi,  # 10 GB
               min=0,
               help=_("""
The upper limit on cache size, in bytes, after which the cache-pruner cleans
up the image cache.

NOTE: This is just a threshold for cache-pruner to act upon. It is NOT a
hard limit beyond which the image cache would never grow. In fact, depending
on how often the cache-pruner runs and how quickly the cache fills, the image
cache can far exceed the size specified here very easily. Hence, care must be
taken to appropriately schedule the cache-pruner and in setting this limit.

Glance caches an image when it is downloaded. Consequently, the size of the
image cache grows over time as the number of downloads increases. To keep the
cache size from becoming unmanageable, it is recommended to run the
cache-pruner as a periodic task. When the cache pruner is kicked off, it
compares the current size of image cache and triggers a cleanup if the image
cache grew beyond the size specified here. After the cleanup, the size of
cache is less than or equal to size specified here.

Possible values:
    * Any non-negative integer

Related options:
    * None

""")),

    cfg.IntOpt('image_cache_stall_time', default=86400,  # 24 hours
               min=0,
               help=_("""
The amount of time, in seconds, an incomplete image remains in the cache.

Incomplete images are images for which download is in progress. Please see the
description of configuration option ``image_cache_dir`` for more detail.
Sometimes, due to various reasons, it is possible the download may hang and
the incompletely downloaded image remains in the ``incomplete`` directory.
This configuration option sets a time limit on how long the incomplete images
should remain in the ``incomplete`` directory before they are cleaned up.
Once an incomplete image spends more time than is specified here, it'll be
removed by cache-cleaner on its next run.

It is recommended to run cache-cleaner as a periodic task on the Glance API
nodes to keep the incomplete images from occupying disk space.

Possible values:
    * Any non-negative integer

Related options:
    * None

""")),

    cfg.StrOpt('image_cache_dir',
               help=_("""
Base directory for image cache.

This is the location where image data is cached and served out of. All cached
images are stored directly under this directory. This directory also contains
three subdirectories, namely, ``incomplete``, ``invalid`` and ``queue``.

The ``incomplete`` subdirectory is the staging area for downloading images. An
image is first downloaded to this directory. When the image download is
successful it is moved to the base directory. However, if the download fails,
the partially downloaded image file is moved to the ``invalid`` subdirectory.

The ``queue``subdirectory is used for queuing images for download. This is
used primarily by the cache-prefetcher, which can be scheduled as a periodic
task like cache-pruner and cache-cleaner, to cache images ahead of their usage.
Upon receiving the request to cache an image, Glance touches a file in the
``queue`` directory with the image id as the file name. The cache-prefetcher,
when running, polls for the files in ``queue`` directory and starts
downloading them in the order they were created. When the download is
successful, the zero-sized file is deleted from the ``queue`` directory.
If the download fails, the zero-sized file remains and it'll be retried the
next time cache-prefetcher runs.

Possible values:
    * A valid path

Related options:
    * ``image_cache_sqlite_db``

""")),
]

CONF = cfg.CONF
CONF.register_opts(image_cache_opts)


class ImageCache(object):

    """Provides an LRU cache for image data."""

    def __init__(self):
        self.init_driver()

    def init_driver(self):
        """
        Create the driver for the cache
        """
        driver_name = CONF.image_cache_driver
        driver_module = (__name__ + '.drivers.' + driver_name + '.Driver')
        try:
            self.driver_class = importutils.import_class(driver_module)
            LOG.info(_LI("Image cache loaded driver '%s'."), driver_name)
        except ImportError as import_err:
            LOG.warn(_LW("Image cache driver "
                         "'%(driver_name)s' failed to load. "
                         "Got error: '%(import_err)s."),
                     {'driver_name': driver_name,
                      'import_err': import_err})

            driver_module = __name__ + '.drivers.sqlite.Driver'
            LOG.info(_LI("Defaulting to SQLite driver."))
            self.driver_class = importutils.import_class(driver_module)
        self.configure_driver()

    def configure_driver(self):
        """
        Configure the driver for the cache and, if it fails to configure,
        fall back to using the SQLite driver which has no odd dependencies
        """
        try:
            self.driver = self.driver_class()
            self.driver.configure()
        except exception.BadDriverConfiguration as config_err:
            driver_module = self.driver_class.__module__
            LOG.warn(_LW("Image cache driver "
                         "'%(driver_module)s' failed to configure. "
                         "Got error: '%(config_err)s"),
                     {'driver_module': driver_module,
                      'config_err': config_err})
            LOG.info(_LI("Defaulting to SQLite driver."))
            default_module = __name__ + '.drivers.sqlite.Driver'
            self.driver_class = importutils.import_class(default_module)
            self.driver = self.driver_class()
            self.driver.configure()

    def is_cached(self, image_id):
        """
        Returns True if the image with the supplied ID has its image
        file cached.

        :param image_id: Image ID
        """
        return self.driver.is_cached(image_id)

    def is_queued(self, image_id):
        """
        Returns True if the image identifier is in our cache queue.

        :param image_id: Image ID
        """
        return self.driver.is_queued(image_id)

    def get_cache_size(self):
        """
        Returns the total size in bytes of the image cache.
        """
        return self.driver.get_cache_size()

    def get_hit_count(self, image_id):
        """
        Return the number of hits that an image has

        :param image_id: Opaque image identifier
        """
        return self.driver.get_hit_count(image_id)

    def get_cached_images(self):
        """
        Returns a list of records about cached images.
        """
        return self.driver.get_cached_images()

    def delete_all_cached_images(self):
        """
        Removes all cached image files and any attributes about the images
        and returns the number of cached image files that were deleted.
        """
        return self.driver.delete_all_cached_images()

    def delete_cached_image(self, image_id):
        """
        Removes a specific cached image file and any attributes about the image

        :param image_id: Image ID
        """
        self.driver.delete_cached_image(image_id)

    def delete_all_queued_images(self):
        """
        Removes all queued image files and any attributes about the images
        and returns the number of queued image files that were deleted.
        """
        return self.driver.delete_all_queued_images()

    def delete_queued_image(self, image_id):
        """
        Removes a specific queued image file and any attributes about the image

        :param image_id: Image ID
        """
        self.driver.delete_queued_image(image_id)

    def prune(self):
        """
        Removes all cached image files above the cache's maximum
        size. Returns a tuple containing the total number of cached
        files removed and the total size of all pruned image files.
        """
        max_size = CONF.image_cache_max_size
        current_size = self.driver.get_cache_size()
        if max_size > current_size:
            LOG.debug("Image cache has free space, skipping prune...")
            return (0, 0)

        overage = current_size - max_size
        LOG.debug("Image cache currently %(overage)d bytes over max "
                  "size. Starting prune to max size of %(max_size)d ",
                  {'overage': overage, 'max_size': max_size})

        total_bytes_pruned = 0
        total_files_pruned = 0
        entry = self.driver.get_least_recently_accessed()
        while entry and current_size > max_size:
            image_id, size = entry
            LOG.debug("Pruning '%(image_id)s' to free %(size)d bytes",
                      {'image_id': image_id, 'size': size})
            self.driver.delete_cached_image(image_id)
            total_bytes_pruned = total_bytes_pruned + size
            total_files_pruned = total_files_pruned + 1
            current_size = current_size - size
            entry = self.driver.get_least_recently_accessed()

        LOG.debug("Pruning finished pruning. "
                  "Pruned %(total_files_pruned)d and "
                  "%(total_bytes_pruned)d.",
                  {'total_files_pruned': total_files_pruned,
                   'total_bytes_pruned': total_bytes_pruned})
        return total_files_pruned, total_bytes_pruned

    def clean(self, stall_time=None):
        """
        Cleans up any invalid or incomplete cached images. The cache driver
        decides what that means...
        """
        self.driver.clean(stall_time)

    def queue_image(self, image_id):
        """
        This adds a image to be cache to the queue.

        If the image already exists in the queue or has already been
        cached, we return False, True otherwise

        :param image_id: Image ID
        """
        return self.driver.queue_image(image_id)

    def get_caching_iter(self, image_id, image_checksum, image_iter):
        """
        Returns an iterator that caches the contents of an image
        while the image contents are read through the supplied
        iterator.

        :param image_id: Image ID
        :param image_checksum: checksum expected to be generated while
                               iterating over image data
        :param image_iter: Iterator that will read image contents
        """
        if not self.driver.is_cacheable(image_id):
            return image_iter

        LOG.debug("Tee'ing image '%s' into cache", image_id)

        return self.cache_tee_iter(image_id, image_iter, image_checksum)

    def cache_tee_iter(self, image_id, image_iter, image_checksum):
        try:
            current_checksum = md5(usedforsecurity=False)

            with self.driver.open_for_write(image_id) as cache_file:
                for chunk in image_iter:
                    try:
                        cache_file.write(chunk)
                    finally:
                        current_checksum.update(chunk)
                        yield chunk
                cache_file.flush()

                if (image_checksum and
                        image_checksum != current_checksum.hexdigest()):
                    msg = _("Checksum verification failed. Aborted "
                            "caching of image '%s'.") % image_id
                    raise exception.GlanceException(msg)

        except exception.GlanceException as e:
            with excutils.save_and_reraise_exception():
                # image_iter has given us bad, (size_checked_iter has found a
                # bad length), or corrupt data (checksum is wrong).
                LOG.exception(encodeutils.exception_to_unicode(e))
        except Exception as e:
            LOG.exception(_LE("Exception encountered while tee'ing "
                              "image '%(image_id)s' into cache: %(error)s. "
                              "Continuing with response.") %
                          {'image_id': image_id,
                           'error': encodeutils.exception_to_unicode(e)})

            # If no checksum provided continue responding even if
            # caching failed.
            for chunk in image_iter:
                yield chunk

    def cache_image_iter(self, image_id, image_iter, image_checksum=None):
        """
        Cache an image with supplied iterator.

        :param image_id: Image ID
        :param image_file: Iterator retrieving image chunks
        :param image_checksum: Checksum of image

        :returns: True if image file was cached, False otherwise
        """
        if not self.driver.is_cacheable(image_id):
            return False

        for chunk in self.get_caching_iter(image_id, image_checksum,
                                           image_iter):
            pass
        return True

    def cache_image_file(self, image_id, image_file):
        """
        Cache an image file.

        :param image_id: Image ID
        :param image_file: Image file to cache

        :returns: True if image file was cached, False otherwise
        """
        CHUNKSIZE = 64 * units.Mi

        return self.cache_image_iter(image_id,
                                     utils.chunkiter(image_file, CHUNKSIZE))

    def open_for_read(self, image_id):
        """
        Open and yield file for reading the image file for an image
        with supplied identifier.

        :note Upon successful reading of the image file, the image's
              hit count will be incremented.

        :param image_id: Image ID
        """
        return self.driver.open_for_read(image_id)

    def get_image_size(self, image_id):
        """
        Return the size of the image file for an image with supplied
        identifier.

        :param image_id: Image ID
        """
        return self.driver.get_image_size(image_id)

    def get_queued_images(self):
        """
        Returns a list of image IDs that are in the queue. The
        list should be sorted by the time the image ID was inserted
        into the queue.
        """
        return self.driver.get_queued_images()
