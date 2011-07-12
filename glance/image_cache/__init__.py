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
import logging
import os

from glance.common import config

logger = logging.getLogger('glance.image_cache')


class ImageCache(object):
    def __init__(self, options):
        self.options = options
        self._make_cache_directory_if_needed()

    def _make_cache_directory_if_needed(self):
        if self.enabled and not os.path.exists(self.path):
            logger.info("image cache directory doesn't exist, creating '%s'",
                        self.path)
            os.makedirs(self.path)

    @property
    def enabled(self):
        return config.get_option(
            self.options, 'image_cache_enabled', type='bool', default=False)

    @property
    def path(self):
        """This is the base path for the image cache"""
        datadir = self.options['image_cache_datadir']
        return datadir

    def path_for_image(self, image_meta):
        """This crafts an absolute path to a specific entry"""
        image_id = image_meta['id']
        return os.path.join(self.path, str(image_id))

    @contextmanager
    def open(self, image_meta, mode="r"):
        path = self.path_for_image(image_meta)
        with open(path, mode) as cache_file:
            yield cache_file

    def hit(self, image_meta):
        path = self.path_for_image(image_meta)
        return os.path.exists(path)

    def delete(self, image_meta):
        path = self.path_for_image(image_meta)
        logger.debug("deleting image cache entry '%s'", path)
        if os.path.exists(path):
            os.unlink(path)
