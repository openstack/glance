# Copyright 2012 Red Hat Inc.
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

import webob.exc

from glance.common import exception


def update_image_read_acl(req, store_api, db_api, image):
    """Helper function to set ACL permissions on images in the image store"""
    location_uri = image['location']
    public = image['is_public']
    image_id = image['id']
    if location_uri:
        try:
            read_tenants = []
            write_tenants = []
            members = db_api.image_member_find(req.context,
                                               image_id=image_id)
            for member in members:
                if not member['deleted']:
                    if member['can_share']:
                        write_tenants.append(member['member'])
                    else:
                        read_tenants.append(member['member'])
            store_api.set_acls(req.context, location_uri, public=public,
                               read_tenants=read_tenants,
                               write_tenants=write_tenants)
        except exception.UnknownScheme:
            msg = _("Store for image_id not found: %s") % image_id
            raise webob.exc.HTTPBadRequest(explanation=msg,
                                           request=req,
                                           content_type='text/plain')
