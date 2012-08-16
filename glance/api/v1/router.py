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


from glance.api.v1 import images
from glance.api.v1 import members
from glance.common import wsgi


class API(wsgi.Router):

    """WSGI router for Glance v1 API requests."""

    def __init__(self, mapper):
        images_resource = images.create_resource()

        mapper.resource("image", "images", controller=images_resource,
                        collection={'detail': 'GET'})
        mapper.connect("/", controller=images_resource, action="index")
        mapper.connect("/images/{id}", controller=images_resource,
                       action="meta", conditions=dict(method=["HEAD"]))

        members_resource = members.create_resource()

        mapper.resource("member", "members", controller=members_resource,
                        parent_resource=dict(member_name='image',
                                             collection_name='images'))
        mapper.connect("/shared-images/{id}",
                       controller=members_resource,
                       action="index_shared_images")
        mapper.connect("/images/{image_id}/members",
                       controller=members_resource,
                       action="update_all",
                       conditions=dict(method=["PUT"]))

        super(API, self).__init__(mapper)
