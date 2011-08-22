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
Prefetches images into the Image Cache
"""
import logging
import os
import stat
import time

from glance.common import config
from glance.common import context
from glance.image_cache import ImageCache
from glance import registry
from glance.store import get_from_backend


logger = logging.getLogger('glance.image_cache.prefetcher')


class Prefetcher(object):
    def __init__(self, options):
        self.options = options
        self.cache = ImageCache(options)

    def fetch_image_into_cache(self, image_id):
        ctx = context.RequestContext(is_admin=True, show_deleted=True)
        image_meta = registry.get_image_metadata(
                    self.options, ctx, image_id)
        with self.cache.open(image_meta, "wb") as cache_file:
            chunks = get_from_backend(image_meta['location'],
                                      expected_size=image_meta['size'],
                                      options=self.options)
            for chunk in chunks:
                cache_file.write(chunk)

    def run(self):
        if self.cache.is_currently_prefetching_any_images():
            logger.debug(_("Currently prefetching, going back to sleep..."))
            return

        try:
            image_id = self.cache.pop_prefetch_item()
        except IndexError:
            logger.debug(_("Nothing to prefetch, going back to sleep..."))
            return

        if self.cache.hit(image_id):
            logger.warn(_("Image %s is already in the cache, deleting "
                        "prefetch job and going back to sleep..."), image_id)
            self.cache.delete_queued_prefetch_image(image_id)
            return

        # NOTE(sirp): if someone is already downloading an image that is in
        # the prefetch queue, then go ahead and delete that item and try to
        # prefetch another
        if self.cache.is_image_currently_being_written(image_id):
            logger.warn(_("Image %s is already being cached, deleting "
                        "prefetch job and going back to sleep..."), image_id)
            self.cache.delete_queued_prefetch_image(image_id)
            return

        logger.debug(_("Prefetching '%s'"), image_id)
        self.cache.do_prefetch(image_id)

        try:
            self.fetch_image_into_cache(image_id)
        finally:
            self.cache.delete_prefetching_image(image_id)


def app_factory(global_config, **local_conf):
    conf = global_config.copy()
    conf.update(local_conf)
    return Prefetcher(conf)
