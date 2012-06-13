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

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.store


class ImageDataController(object):
    def __init__(self, db_api=None, store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.configure_db()
        self.store_api = store_api or glance.store
        self.store_api.create_stores()

    def _get_image(self, context, image_id):
        try:
            return self.db_api.image_get(context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound(_("Image does not exist"))

    @utils.mutating
    def upload(self, req, image_id, data, size):
        self._get_image(req.context, image_id)
        try:
            location, size, checksum = self.store_api.add_to_backend(
                    'file', image_id, data, size)
        except exception.Duplicate:
            raise webob.exc.HTTPConflict()

        values = {'location': location, 'size': size}
        self.db_api.image_update(req.context, image_id, values)

    def download(self, req, image_id):
        image = self._get_image(req.context, image_id)
        location = image['location']
        if location:
            image_data, image_size = self.store_api.get_from_backend(location)
            return {'data': image_data, 'size': image_size}
        else:
            raise webob.exc.HTTPNotFound(_("No image data could be found"))


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def upload(self, request):
        try:
            request.get_content_type('application/octet-stream')
        except exception.InvalidContentType:
            raise webob.exc.HTTPUnsupportedMediaType()

        image_size = request.content_length or None
        return {'size': image_size, 'data': request.body_file}


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def download(self, response, result):
        response.headers['Content-Length'] = result['size']
        response.headers['Content-Type'] = 'application/octet-stream'
        response.app_iter = result['data']


def create_resource():
    """Image data resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ImageDataController()
    return wsgi.Resource(controller, deserializer, serializer)
