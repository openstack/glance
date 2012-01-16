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

import logging
import os

from glance.common import cfg
from glance.common import exception
from glance.common import utils

logger = logging.getLogger(__name__)
DEFAULT_MAX_CACHE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB


class ImageCache(object):

    """Provides an LRU cache for image data."""

    opts = [
        cfg.StrOpt('image_cache_driver', default='sqlite'),
        cfg.IntOpt('image_cache_max_size', default=10 * (1024 ** 3)),  # 10 GB
        cfg.IntOpt('image_cache_stall_time', default=86400),  # 24 hours
        cfg.StrOpt('image_cache_dir'),
        ]

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(self.opts)
        self.init_driver()

    def init_driver(self):
        """
        Create the driver for the cache
        """
        driver_name = self.conf.image_cache_driver
        driver_module = (__name__ + '.drivers.' + driver_name + '.Driver')
        try:
            self.driver_class = utils.import_class(driver_module)
            logger.info(_("Image cache loaded driver '%s'.") %
                        driver_name)
        except exception.ImportFailure, import_err:
            logger.warn(_("Image cache driver "
                          "'%(driver_name)s' failed to load. "
                          "Got error: '%(import_err)s.") % locals())

            driver_module = __name__ + '.drivers.sqlite.Driver'
            logger.info(_("Defaulting to SQLite driver."))
            self.driver_class = utils.import_class(driver_module)
        self.configure_driver()

    def configure_driver(self):
        """
        Configure the driver for the cache and, if it fails to configure,
        fall back to using the SQLite driver which has no odd dependencies
        """
        try:
            self.driver = self.driver_class(self.conf)
            self.driver.configure()
        except exception.BadDriverConfiguration, config_err:
            driver_module = self.driver_class.__module__
            logger.warn(_("Image cache driver "
                          "'%(driver_module)s' failed to configure. "
                          "Got error: '%(config_err)s") % locals())
            logger.info(_("Defaulting to SQLite driver."))
            default_module = __name__ + '.drivers.sqlite.Driver'
            self.driver_class = utils.import_class(default_module)
            self.driver = self.driver_class(self.conf)
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
        max_size = self.conf.image_cache_max_size
        current_size = self.driver.get_cache_size()
        if max_size > current_size:
            logger.debug(_("Image cache has free space, skipping prune..."))
            return (0, 0)

        overage = current_size - max_size
        logger.debug(_("Image cache currently %(overage)d bytes over max "
                       "size. Starting prune to max size of %(max_size)d ") %
                     locals())

        total_bytes_pruned = 0
        total_files_pruned = 0
        entry = self.driver.get_least_recently_accessed()
        while entry and current_size > max_size:
            image_id, size = entry
            logger.debug(_("Pruning '%(image_id)s' to free %(size)d bytes"),
                         {'image_id': image_id, 'size': size})
            self.driver.delete_cached_image(image_id)
            total_bytes_pruned = total_bytes_pruned + size
            total_files_pruned = total_files_pruned + 1
            current_size = current_size - size
            entry = self.driver.get_least_recently_accessed()

        logger.debug(_("Pruning finished pruning. "
                       "Pruned %(total_files_pruned)d and "
                       "%(total_bytes_pruned)d.") % locals())
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

    def get_caching_iter(self, image_id, image_iter):
        """
        Returns an iterator that caches the contents of an image
        while the image contents are read through the supplied
        iterator.

        :param image_id: Image ID
        :param image_iter: Iterator that will read image contents
        """
        if not self.driver.is_cacheable(image_id):
            return image_iter

        logger.debug(_("Tee'ing image '%s' into cache"), image_id)

        def tee_iter(image_id):
            with self.driver.open_for_write(image_id) as cache_file:
                for chunk in image_iter:
                    cache_file.write(chunk)
                    yield chunk
                cache_file.flush()

        return tee_iter(image_id)

    def cache_image_iter(self, image_id, image_iter):
        """
        Cache an image with supplied iterator.

        :param image_id: Image ID
        :param image_file: Iterator retrieving image chunks

        :retval True if image file was cached, False otherwise
        """
        if not self.driver.is_cacheable(image_id):
            return False

        with self.driver.open_for_write(image_id) as cache_file:
            for chunk in image_iter:
                cache_file.write(chunk)
            cache_file.flush()
        return True

    def cache_image_file(self, image_id, image_file):
        """
        Cache an image file.

        :param image_id: Image ID
        :param image_file: Image file to cache

        :retval True if image file was cached, False otherwise
        """
        CHUNKSIZE = 64 * 1024 * 1024

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
