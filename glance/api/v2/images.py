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


class ImagesController(base.Controller):
    def __init__(self, conf, db=None):
        super(ImagesController, self).__init__(conf)
        self.db_api = db or glance.registry.db.api
        self.db_api.configure_db(conf)

    def index(self, req):
        return self.db_api.image_get_all(req.context)

    def show(self, req, id):
        return self.db_api.image_get(req.context, id)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def __init__(self, conf):
        super(RequestDeserializer, self).__init__()
        self.conf = conf

    def _validate(self, request, obj):
        schema = schemas.SchemasController(self.conf).image(request)
        jsonschema.validate(obj, schema)

    def create(self, request):
        output = super(RequestDeserializer, self).default(request)
        body = output.pop('body')
        self._validate(request, body)
        output['image'] = body
        return output


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def _get_image_href(self, image):
        return '/v2/images/%s' % image['id']

    def _get_image_links(self, image):
        return [
            {'rel': 'self', 'href': self._get_image_href(image)},
            {'rel': 'describedby', 'href': '/v2/schemas/image'},
        ]

    def _format_image(self, image):
        props = ['id', 'name']
        items = filter(lambda item: item[0] in props, image.iteritems())
        obj = dict(items)
        obj['links'] = self._get_image_links(image)
        return obj

    def create(self, response, image):
        response.body = json.dumps({'image': self._format_image(image)})
        response.location = self._get_image_href(image)

    def show(self, response, image):
        response.body = json.dumps({'image': self._format_image(image)})

    def index(self, response, images):
        body = {
            'images': [self._format_image(i) for i in images],
            'links': [],
        }
        response.body = json.dumps(body)


def create_resource(conf):
    """Images resource factory method"""
    controller = ImagesController(conf)
    return wsgi.Resource(controller)
