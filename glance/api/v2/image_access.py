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

import json

import jsonschema

from glance.api.v2 import base
from glance.api.v2 import schemas
from glance.common import wsgi
import glance.registry.db.api


class ImageAccessController(base.Controller):
    def __init__(self, conf, db=None):
        super(ImageAccessController, self).__init__(conf)
        self.db_api = db or glance.registry.db.api
        self.db_api.configure_db(conf)

    def index(self, req, image_id):
        image = self.db_api.image_get(req.context, image_id)
        return image['members']

    def show(self, req, image_id, tenant_id):
        return self.db_api.image_member_find(req.context, image_id, tenant_id)

    def create(self, req, access):
        return self.db_api.image_member_create(req.context, access)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def __init__(self, conf):
        super(RequestDeserializer, self).__init__()
        self.conf = conf

    def _validate(self, request, obj):
        schema = schemas.SchemasController(self.conf).access(request)
        jsonschema.validate(obj, schema)

    def create(self, request):
        output = super(RequestDeserializer, self).default(request)
        body = output.pop('body')
        self._validate(request, body)
        body['member'] = body.pop('tenant_id')
        output['access'] = body
        return output


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def _get_access_href(self, image_member):
        image_id = image_member['image_id']
        tenant_id = image_member['member']
        return '/v2/images/%s/access/%s' % (image_id, tenant_id)

    def _get_access_links(self, access):
        return [
            {'rel': 'self', 'href': self._get_access_href(access)},
            {'rel': 'describedby', 'href': '/v2/schemas/image/access'},
        ]

    def _format_access(self, access):
        return {
            'image_id': access['image_id'],
            'tenant_id': access['member'],
            'can_share': access['can_share'],
            'links': self._get_access_links(access),
        }

    def _get_container_links(self, image_id):
        return [{'rel': 'self', 'href': '/v2/images/%s/access' % image_id}]

    def show(self, response, access):
        response.body = json.dumps({'access': self._format_access(access)})

    def index(self, response, access_records):
        body = {
            'access_records': [self._format_access(a) for a in access_records],
            'links': [],
        }
        response.body = json.dumps(body)

    def create(self, response, access):
        response.body = json.dumps({'access': self._format_access(access)})
        response.location = self._get_access_href(access)
