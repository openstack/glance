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

from glance.common import wsgi
from glance import image_cache


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

    def purge_all(self, req):
        self.cache.purge_all()


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
