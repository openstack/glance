# Copyright 2012 OpenStack LLC.
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

import glance.api.v2.base
from glance.common import exception
import glance.registry.db.api


class ImageAccessController(glance.api.v2.base.Controller):
    def __init__(self, conf, db=None):
        super(ImageAccessController, self).__init__(conf)
        self.db_api = db or glance.registry.db.api
        self.db_api.configure_db(conf)

    def _format_access_record(self, image_member):
        return {
            'image_id': image_member['image_id'],
            'tenant_id': image_member['member'],
            'can_share': image_member['can_share'],
            'links': self._get_access_record_links(image_member),
        }

    def _get_access_record_links(self, image_member):
        image_id = image_member['image_id']
        tenant_id = image_member['member']
        self_href = '/v2/images/%s/access/%s' % (image_id, tenant_id)
        return [
            {'rel': 'self', 'href': self_href},
            {'rel': 'describedby', 'href': '/v2/schemas/image/access'},
        ]

    def _get_container_links(self, image_id):
        return [{'rel': 'self', 'href': '/v2/images/%s/access' % image_id}]

    def index(self, req, image_id):
        try:
            members = self.db_api.get_image_members(req.context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        records = [self._format_access_record(m) for m in members]
        return {
            'access_records': records,
            'links': self._get_container_links(image_id),
        }
