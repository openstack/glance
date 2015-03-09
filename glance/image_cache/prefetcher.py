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
Prefetches images into the Image Cache
"""

import eventlet
import glance_store
from oslo_log import log as logging

from glance.common import exception
from glance import context
from glance import i18n
from glance.image_cache import base
import glance.registry.client.v1.api as registry

LOG = logging.getLogger(__name__)
_LI = i18n._LI
_LW = i18n._LW


class Prefetcher(base.CacheApp):

    def __init__(self):
        super(Prefetcher, self).__init__()
        registry.configure_registry_client()
        registry.configure_registry_admin_creds()

    def fetch_image_into_cache(self, image_id):
        ctx = context.RequestContext(is_admin=True, show_deleted=True)

        try:
            image_meta = registry.get_image_metadata(ctx, image_id)
            if image_meta['status'] != 'active':
                LOG.warn(_LW("Image '%s' is not active. Not caching.") %
                         image_id)
                return False

        except exception.NotFound:
            LOG.warn(_LW("No metadata found for image '%s'") % image_id)
            return False

        location = image_meta['location']
        image_data, image_size = glance_store.get_from_backend(location,
                                                               context=ctx)
        LOG.debug("Caching image '%s'", image_id)
        cache_tee_iter = self.cache.cache_tee_iter(image_id, image_data,
                                                   image_meta['checksum'])
        # Image is tee'd into cache and checksum verified
        # as we iterate
        list(cache_tee_iter)
        return True

    def run(self):

        images = self.cache.get_queued_images()
        if not images:
            LOG.debug("Nothing to prefetch.")
            return True

        num_images = len(images)
        LOG.debug("Found %d images to prefetch", num_images)

        pool = eventlet.GreenPool(num_images)
        results = pool.imap(self.fetch_image_into_cache, images)
        successes = sum([1 for r in results if r is True])
        if successes != num_images:
            LOG.warn(_LW("Failed to successfully cache all "
                         "images in queue."))
            return False

        LOG.info(_LI("Successfully cached all %d images") % num_images)
        return True
