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

logger = logging.getLogger(__name__)


class CacheManageFilter(wsgi.Middleware):
    def __init__(self, app, options):

        map = app.map
        resource = cached_images.create_resource(options)

        map.connect("/cached_images",
                    controller=resource,
                    action="get_cached_images",
                    conditions=dict(method=["GET"]))

        map.connect("/cached_images/{image_id}",
                    controller=resource,
                    action="delete_cached_image",
                    conditions=dict(method=["DELETE"]))

        map.connect("/cached_images",
                    controller=resource,
                    action="delete_cached_images",
                    conditions=dict(method=["DELETE"]))

        map.connect("/queued_images/{image_id}",
                    controller=resource,
                    action="queue_image",
                    conditions=dict(method=["PUT"]))

        map.connect("/queued_images",
                    controller=resource,
                    action="get_queued_images",
                    conditions=dict(method=["GET"]))

        map.connect("/queued_images/{image_id}",
                    controller=resource,
                    action="delete_queued_image",
                    conditions=dict(method=["DELETE"]))

        map.connect("/queued_images",
                    controller=resource,
                    action="delete_queued_images",
                    conditions=dict(method=["DELETE"]))

        logger.info(_("Initialized image cache management middleware"))
        super(CacheManageFilter, self).__init__(app)


def filter_factory(global_conf, **local_conf):
    """
    Factory method for paste.deploy
    """
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return CacheManageFilter(app, conf)

    return filter
