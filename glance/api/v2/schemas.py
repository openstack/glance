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

import glance.api.v2.base
from glance.common import wsgi


class SchemasController(glance.api.v2.base.Controller):
    def index(self, req):
        links = [
            {'rel': 'image', 'href': '/schemas/image'},
            {'rel': 'access', 'href': '/schemas/image/access'},
        ]
        return {'links': links}

    def image(self, req):
        return {
            "name": "image",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "An identifier for the image",
                    "required": True,
                    "maxLength": 32,
                    "readonly": True
                },
                "name": {
                    "type": "string",
                    "description": "Descriptive name for the image",
                    "required": True,
                },
            },
        }

    def access(self, req):
        return {
            'name': 'access',
            'properties': {
                "image_id": {
                  "type": "string",
                  "description": "The image identifier",
                  "required": True,
                  "maxLength": 32,
                },
                "tenant_id": {
                  "type": "string",
                  "description": "The tenant identifier",
                  "required": True,
                },
                "can_share": {
                  "type": "boolean",
                  "description": "Ability of tenant to share with others",
                  "required": True,
                  "default": False,
                },
            },
        }


def create_resource(conf):
    controller = SchemasController(conf)
    return wsgi.Resource(controller)
