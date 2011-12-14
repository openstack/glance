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
Queues images for prefetching into the image cache
"""

import logging

import eventlet

from glance.common import exception
from glance.image_cache import ImageCache
from glance import registry


logger = logging.getLogger(__name__)


class Queuer(object):

    def __init__(self, conf, **local_conf):
        self.conf = conf
        self.cache = ImageCache(conf)
        registry.configure_registry_client(conf)

    def queue_image(self, image_id):
        ctx = \
            registry.get_client_context(conf, is_admin=True, show_deleted=True)
        try:
            image_meta = registry.get_image_metadata(ctx, image_id)
            if image_meta['status'] != 'active':
                logger.warn(_("Image '%s' is not active. Not queueing."),
                            image_id)
                return False

        except exception.NotFound:
            logger.warn(_("No metadata found for image '%s'"), image_id)
            return False

        logger.debug(_("Queueing image '%s'"), image_id)
        self.cache.queue_image(image_id)
        return True

    def run(self, images):

        num_images = len(images)
        if num_images == 0:
            logger.debug(_("No images to queue!"))
            return True

        logger.debug(_("Received %d images to queue"), num_images)

        pool = eventlet.GreenPool(num_images)
        results = pool.imap(self.queue_image, images)
        successes = sum([1 for r in results if r is True])
        if successes != num_images:
            logger.error(_("Failed to successfully queue all "
                           "images in queue."))
            return False

        logger.info(_("Successfully queued all %d images"), num_images)
        return True
