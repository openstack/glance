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

import httplib
import json

import webob.dec
import webob.exc

from glance.common import exception
from glance.common import wsgi
from glance import api
from glance import image_cache
from glance import registry


class Controller(api.BaseController):
    """
    A controller that produces information on the Glance API versions.
    """

    def __init__(self, options):
        self.options = options
        self.cache = image_cache.ImageCache(self.options)

    def index(self, req):
        status = req.str_params.get('status')
        if status == 'invalid':
            entries = list(self.cache.invalid_entries())
        elif status == 'incomplete':
            entries = list(self.cache.incomplete_entries())
        elif status == 'prefetching':
            entries = list(self.cache.prefetch_entries())
        else:
            entries = list(self.cache.entries())

        return dict(cached_images=entries)

    def delete(self, req, id):
        self.cache.purge(id)

    def delete_collection(self, req):
        """
        DELETE /cached_images - Clear all active cached images
        DELETE /cached_images?status=invalid - Reap invalid cached images
        DELETE /cached_images?status=incomplete - Reap stalled cached images
        """
        status = req.str_params.get('status')
        if status == 'invalid':
            num_reaped = self.cache.reap_invalid()
            return dict(num_reaped=num_reaped)
        elif status == 'incomplete':
            num_reaped = self.cache.reap_stalled()
            return dict(num_reaped=num_reaped)
        else:
            num_purged = self.cache.clear()
            return dict(num_purged=num_purged)

    def update(self, req, id):
        """PUT /cached_images/1 is used to prefetch an image into the cache"""
        image_meta = self.get_active_image_meta_or_404(req, id)
        try:
            self.cache.queue_prefetch(image_meta)
        except exception.Invalid, e:
            raise webob.exc.HTTPBadRequest(explanation="%s" % e)


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
