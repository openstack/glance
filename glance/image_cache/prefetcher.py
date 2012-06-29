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

import eventlet

from glance.common import exception
from glance import context
from glance.image_cache import base
import glance.openstack.common.log as logging
from glance import registry
import glance.store
import glance.store.filesystem
from glance.store import get_from_backend
import glance.store.http
import glance.store.rbd
import glance.store.s3
import glance.store.swift


LOG = logging.getLogger(__name__)


class Prefetcher(base.CacheApp):

    def __init__(self):
        glance.store.create_stores()
        super(Prefetcher, self).__init__()
        registry.configure_registry_client()
        registry.configure_registry_admin_creds()

    def fetch_image_into_cache(self, image_id):
        ctx = context.RequestContext(is_admin=True, show_deleted=True)

        try:
            image_meta = registry.get_image_metadata(ctx, image_id)
            if image_meta['status'] != 'active':
                LOG.warn(_("Image '%s' is not active. Not caching."),
                         image_id)
                return False

        except exception.NotFound:
            LOG.warn(_("No metadata found for image '%s'"), image_id)
            return False

        image_data, image_size = get_from_backend(ctx, image_meta['location'])
        LOG.debug(_("Caching image '%s'"), image_id)
        self.cache.cache_image_iter(image_id, image_data)
        return True

    def run(self):

        images = self.cache.get_queued_images()
        if not images:
            LOG.debug(_("Nothing to prefetch."))
            return True

        num_images = len(images)
        LOG.debug(_("Found %d images to prefetch"), num_images)

        pool = eventlet.GreenPool(num_images)
        results = pool.imap(self.fetch_image_into_cache, images)
        successes = sum([1 for r in results if r is True])
        if successes != num_images:
            LOG.error(_("Failed to successfully cache all "
                        "images in queue."))
            return False

        LOG.info(_("Successfully cached all %d images"), num_images)
        return True
