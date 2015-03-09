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
Image Cache Management API
"""

from oslo_log import log as logging
import routes

from glance.api import cached_images
from glance.common import wsgi
from glance import i18n

LOG = logging.getLogger(__name__)
_LI = i18n._LI


class CacheManageFilter(wsgi.Middleware):
    def __init__(self, app):
        mapper = routes.Mapper()
        resource = cached_images.create_resource()

        mapper.connect("/v1/cached_images",
                       controller=resource,
                       action="get_cached_images",
                       conditions=dict(method=["GET"]))

        mapper.connect("/v1/cached_images/{image_id}",
                       controller=resource,
                       action="delete_cached_image",
                       conditions=dict(method=["DELETE"]))

        mapper.connect("/v1/cached_images",
                       controller=resource,
                       action="delete_cached_images",
                       conditions=dict(method=["DELETE"]))

        mapper.connect("/v1/queued_images/{image_id}",
                       controller=resource,
                       action="queue_image",
                       conditions=dict(method=["PUT"]))

        mapper.connect("/v1/queued_images",
                       controller=resource,
                       action="get_queued_images",
                       conditions=dict(method=["GET"]))

        mapper.connect("/v1/queued_images/{image_id}",
                       controller=resource,
                       action="delete_queued_image",
                       conditions=dict(method=["DELETE"]))

        mapper.connect("/v1/queued_images",
                       controller=resource,
                       action="delete_queued_images",
                       conditions=dict(method=["DELETE"]))

        self._mapper = mapper
        self._resource = resource

        LOG.info(_LI("Initialized image cache management middleware"))
        super(CacheManageFilter, self).__init__(app)

    def process_request(self, request):
        # Map request to our resource object if we can handle it
        match = self._mapper.match(request.path_info, request.environ)
        if match:
            request.environ['wsgiorg.routing_args'] = (None, match)
            return self._resource(request)
        # Pass off downstream if we don't match the request path
        else:
            return None
