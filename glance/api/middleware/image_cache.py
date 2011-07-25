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
Image Cache Management API
"""

import logging

from glance.api import cached_images
from glance.common import wsgi

logger = logging.getLogger('glance.api.middleware.image_cache')


class ImageCacheFilter(wsgi.Middleware):
    def __init__(self, app, options):
        super(ImageCacheFilter, self).__init__(app)

        map = app.map
        resource = cached_images.create_resource(options)
        map.resource("cached_image", "cached_images",
                     controller=resource,
                     collection={'reap_invalid': 'POST',
                                 'reap_stalled': 'POST'})

        map.connect("/cached_images",
                    controller=resource,
                    action="delete_collection",
                    conditions=dict(method=["DELETE"]))


def filter_factory(global_conf, **local_conf):
    """
    Factory method for paste.deploy
    """
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return ImageCacheFilter(app, conf)

    return filter
