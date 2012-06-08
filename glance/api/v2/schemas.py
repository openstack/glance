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

from glance.common import wsgi
import glance.schema


class Controller(object):
    def __init__(self, schema_api):
        self.schema_api = schema_api

    def index(self, req):
        links = [
            {'rel': 'image', 'href': '/v2/schemas/image'},
            {'rel': 'access', 'href': '/v2/schemas/image/access'},
        ]
        return {'links': links}

    def image(self, req):
        return self.schema_api.get_schema('image')

    def access(self, req):
        return self.schema_api.get_schema('access')


def create_resource(schema_api):
    controller = Controller(schema_api)
    return wsgi.Resource(controller)
