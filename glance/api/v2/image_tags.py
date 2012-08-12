# Copyright 2012 OpenStack, LLC
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


class Controller(object):
    def __init__(self, db=None):
        self.db_api = db or glance.db.get_api()
        self.db_api.configure_db()

    @utils.mutating
    def update(self, req, image_id, tag_value):
        context = req.context
        if tag_value not in self.db_api.image_tag_get_all(context, image_id):
            self.db_api.image_tag_create(context, image_id, tag_value)

    @utils.mutating
    def delete(self, req, image_id, tag_value):
        try:
            self.db_api.image_tag_delete(req.context, image_id, tag_value)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def update(self, response, result):
        response.status_int = 204

    def delete(self, response, result):
        response.status_int = 204


def create_resource():
    """Images resource factory method"""
    serializer = ResponseSerializer()
    controller = Controller()
    return wsgi.Resource(controller, serializer=serializer)
