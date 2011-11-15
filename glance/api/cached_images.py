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
Controller for Image Cache Management API
"""

import logging

import webob.exc

from glance.common import exception
from glance.common import wsgi
from glance.api.v1 import controller
from glance import image_cache
from glance import registry

logger = logging.getLogger(__name__)


class Controller(controller.BaseController):
    """
    A controller for managing cached images.
    """

    def __init__(self, options):
        self.options = options
        self.cache = image_cache.ImageCache(self.options)

    def get_cached_images(self, req):
        """
        GET /cached_images

        Returns a mapping of records about cached images.
        """
        images = self.cache.get_cached_images()
        return dict(cached_images=images)

    def delete_cached_image(self, req, image_id):
        """
        DELETE /cached_images/<IMAGE_ID>

        Removes an image from the cache.
        """
        self.cache.delete_cached_image(image_id)

    def delete_cached_images(self, req):
        """
        DELETE /cached_images - Clear all active cached images

        Removes all images from the cache.
        """
        return dict(num_deleted=self.cache.delete_all_cached_images())

    def get_queued_images(self, req):
        """
        GET /queued_images

        Returns a mapping of records about queued images.
        """
        images = self.cache.get_queued_images()
        return dict(queued_images=images)

    def queue_image(self, req, image_id):
        """
        PUT /queued_images/<IMAGE_ID>

        Queues an image for caching. We do not check to see if
        the image is in the registry here. That is done by the
        prefetcher...
        """
        self.cache.queue_image(image_id)

    def delete_queued_image(self, req, image_id):
        """
        DELETE /queued_images/<IMAGE_ID>

        Removes an image from the cache.
        """
        self.cache.delete_queued_image(image_id)

    def delete_queued_images(self, req):
        """
        DELETE /queued_images - Clear all active queued images

        Removes all images from the cache.
        """
        return dict(num_deleted=self.cache.delete_all_queued_images())


class CachedImageDeserializer(wsgi.JSONRequestDeserializer):
    pass


class CachedImageSerializer(wsgi.JSONResponseSerializer):
    pass


def create_resource(options):
    """Cached Images resource factory method"""
    deserializer = CachedImageDeserializer()
    serializer = CachedImageSerializer()
    return wsgi.Resource(Controller(options), deserializer, serializer)


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating Cached Images apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return Controller(conf)
