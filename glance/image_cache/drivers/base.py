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
Base attribute driver class
"""

import os.path

from oslo_config import cfg
from oslo_log import log as logging

from glance.common import exception
from glance.common import utils
from glance.i18n import _

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class Driver(object):

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

    def set_paths(self):
        """
        Creates all necessary directories under the base cache directory
        """

        self.base_dir = CONF.image_cache_dir
        if self.base_dir is None:
            msg = _('Failed to read %s from config') % 'image_cache_dir'
            LOG.error(msg)
            driver = self.__class__.__module__
            raise exception.BadDriverConfiguration(driver_name=driver,
                                                   reason=msg)

        self.incomplete_dir = os.path.join(self.base_dir, 'incomplete')
        self.invalid_dir = os.path.join(self.base_dir, 'invalid')
        self.queue_dir = os.path.join(self.base_dir, 'queue')

        dirs = [self.incomplete_dir, self.invalid_dir, self.queue_dir]

        for path in dirs:
            utils.safe_mkdirs(path)

    def get_cache_size(self):
        """
        Returns the total size in bytes of the image cache.
        """
        raise NotImplementedError

    def get_cached_images(self):
        """
        Returns a list of records about cached images.

        The list of records shall be ordered by image ID and shall look like::

            [
                {
                'image_id': <IMAGE_ID>,
                'hits': INTEGER,
                'last_modified': ISO_TIMESTAMP,
                'last_accessed': ISO_TIMESTAMP,
                'size': INTEGER
                }, ...
            ]

        """
        return NotImplementedError

    def is_cached(self, image_id):
        """
        Returns True if the image with the supplied ID has its image
        file cached.

        :param image_id: Image ID
        """
        raise NotImplementedError

    def is_cacheable(self, image_id):
        """
        Returns True if the image with the supplied ID can have its
        image file cached, False otherwise.

        :param image_id: Image ID
        """
        raise NotImplementedError

    def is_queued(self, image_id):
        """
        Returns True if the image identifier is in our cache queue.

        :param image_id: Image ID
        """
        raise NotImplementedError

    def delete_all_cached_images(self):
        """
        Removes all cached image files and any attributes about the images
        and returns the number of cached image files that were deleted.
        """
        raise NotImplementedError

    def delete_cached_image(self, image_id):
        """
        Removes a specific cached image file and any attributes about the image

        :param image_id: Image ID
        """
        raise NotImplementedError

    def delete_all_queued_images(self):
        """
        Removes all queued image files and any attributes about the images
        and returns the number of queued image files that were deleted.
        """
        raise NotImplementedError

    def delete_queued_image(self, image_id):
        """
        Removes a specific queued image file and any attributes about the image

        :param image_id: Image ID
        """
        raise NotImplementedError

    def queue_image(self, image_id):
        """
        Puts an image identifier in a queue for caching. Return True
        on successful add to the queue, False otherwise...

        :param image_id: Image ID
        """

    def clean(self, stall_time=None):
        """
        Dependent on the driver, clean up and destroy any invalid or incomplete
        cached images
        """
        raise NotImplementedError

    def get_least_recently_accessed(self):
        """
        Return a tuple containing the image_id and size of the least recently
        accessed cached file, or None if no cached files.
        """
        raise NotImplementedError

    def open_for_write(self, image_id):
        """
        Open a file for writing the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        raise NotImplementedError

    def open_for_read(self, image_id):
        """
        Open and yield file for reading the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        raise NotImplementedError

    def get_image_filepath(self, image_id, cache_status='active'):
        """
        This crafts an absolute path to a specific entry

        :param image_id: Image ID
        :param cache_status: Status of the image in the cache
        """
        if cache_status == 'active':
            return os.path.join(self.base_dir, str(image_id))
        return os.path.join(self.base_dir, cache_status, str(image_id))

    def get_image_size(self, image_id):
        """
        Return the size of the image file for an image with supplied
        identifier.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id)
        return os.path.getsize(path)

    def get_queued_images(self):
        """
        Returns a list of image IDs that are in the queue. The
        list should be sorted by the time the image ID was inserted
        into the queue.
        """
        raise NotImplementedError
