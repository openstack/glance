# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import logging

import routes

from glance.api.v2 import image_access
from glance.api.v2 import image_data
from glance.api.v2 import image_tags
from glance.api.v2 import images
from glance.api.v2 import root
from glance.api.v2 import schemas
from glance.common import wsgi
import glance.schema

logger = logging.getLogger(__name__)


class API(wsgi.Router):

    """WSGI router for Glance v2 API requests."""

    def __init__(self, mapper):
        schema_api = glance.schema.API()
        glance.schema.load_custom_schema_properties(schema_api)

        root_resource = root.create_resource()
        mapper.connect('/', controller=root_resource, action='index')

        schemas_resource = schemas.create_resource(schema_api)
        mapper.connect('/schemas',
                       controller=schemas_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/image',
                       controller=schemas_resource,
                       action='image',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/image/access',
                       controller=schemas_resource,
                       action='access',
                       conditions={'method': ['GET']})

        images_resource = images.create_resource(schema_api)
        mapper.connect('/images',
                       controller=images_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images',
                       controller=images_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}',
                       controller=images_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}',
                       controller=images_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}',
                       controller=images_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        image_data_resource = image_data.create_resource()
        mapper.connect('/images/{image_id}/file',
                       controller=image_data_resource,
                       action='download',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/file',
                       controller=image_data_resource,
                       action='upload',
                       conditions={'method': ['PUT']})

        image_tags_resource = image_tags.create_resource()
        mapper.connect('/images/{image_id}/tags',
                       controller=image_tags_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        image_access_resource = image_access.create_resource(schema_api)
        mapper.connect('/images/{image_id}/access',
                       controller=image_access_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/access',
                       controller=image_access_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}/access/{tenant_id}',
                       controller=image_access_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/access/{tenant_id}',
                       controller=image_access_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        super(API, self).__init__(mapper)
