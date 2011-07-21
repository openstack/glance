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
Controller that returns information on the Glance API versions
"""

import httplib
import json

import webob.dec

from glance.common import exception
from glance.common import wsgi
from glance import image_cache
from glance import registry


class Controller(object):
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
        elif status == 'prefetching':
            entries = list(self.cache.prefetch_entries())
        else:
            entries = list(self.cache.entries())

        return dict(cached_images=entries)

    def delete(self, req, id):
        self.cache.purge(id)

    def purge_all(self, req):
        self.cache.purge_all()

    def update(self, req, id):
        """PUT /cached_images/1 is used to prefetch an image into the cache"""
        image_meta = self.get_image_meta_or_404(req, id)
        try:
            self.cache.queue_prefetch(image_meta)
        except exception.Invalid, e:
            raise HTTPBadRequest(explanation=str(e))

    # TODO(sirp): refactor this to common area?
    def get_image_meta_or_404(self, request, id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return registry.get_image_metadata(self.options, id)
        except exception.NotFound:
            msg = "Image with identifier %s not found" % id
            logger.debug(msg)
            raise HTTPNotFound(msg, request=request,
                               content_type='text/plain')


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
