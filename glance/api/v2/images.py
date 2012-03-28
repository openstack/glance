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
from glance.common import wsgi
import glance.registry.db.api


class ImagesController(glance.api.v2.base.Controller):
    """WSGI controller for images resource in Glance v2 API."""

    def __init__(self, conf, db=None):
        super(ImagesController, self).__init__(conf)
        self.db_api = db or glance.registry.db.api
        self.db_api.configure_db(conf)

    def _format_image(self, image):
        props = ['id', 'name']
        items = filter(lambda item: item[0] in props, image.iteritems())
        obj = dict(items)
        obj['links'] = self._get_image_links(image)
        return obj

    def _get_image_links(self, image):
        image_id = image['id']
        return [
            {'rel': 'self', 'href': '/v2/images/%s' % image_id},
            {'rel': 'access', 'href': '/v2/images/%s/access' % image_id},
            {'rel': 'describedby', 'href': '/v2/schemas/image'},
        ]

    def _get_container_links(self, images):
        return []

    def index(self, req):
        images = self.db_api.image_get_all(req.context)
        return {
            'images': [self._format_image(i) for i in images],
            'links': self._get_container_links(images),
        }

    def show(self, req, id):
        try:
            image = self.db_api.image_get(req.context, id)
        except exception.ImageNotFound:
            raise webob.exc.HTTPNotFound()
        return self._format_image(image)


def create_resource(conf):
    """Images resource factory method"""
    controller = ImagesController(conf)
    return wsgi.Resource(controller)
