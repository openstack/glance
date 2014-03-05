# Copyright 2012 OpenStack Foundation.
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

from glance.api.v2 import image_data
from glance.api.v2 import image_members
from glance.api.v2 import image_tags
from glance.api.v2 import images
from glance.api.v2 import schemas
from glance.api.v2 import tasks
from glance.common import wsgi


class API(wsgi.Router):

    """WSGI router for Glance v2 API requests."""

    def __init__(self, mapper):
        custom_image_properties = images.load_custom_properties()

        schemas_resource = schemas.create_resource(custom_image_properties)
        mapper.connect('/schemas/image',
                       controller=schemas_resource,
                       action='image',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/images',
                       controller=schemas_resource,
                       action='images',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/member',
                       controller=schemas_resource,
                       action='member',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/members',
                       controller=schemas_resource,
                       action='members',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/task',
                       controller=schemas_resource,
                       action='task',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/tasks',
                       controller=schemas_resource,
                       action='tasks',
                       conditions={'method': ['GET']})

        images_resource = images.create_resource(custom_image_properties)
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
                       conditions={'method': ['PATCH']})
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
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        image_members_resource = image_members.create_resource()
        mapper.connect('/images/{image_id}/members',
                       controller=image_members_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/members',
                       controller=image_members_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        tasks_resource = tasks.create_resource()
        mapper.connect('/tasks',
                       controller=tasks_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/tasks',
                       controller=tasks_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/tasks/{task_id}',
                       controller=tasks_resource,
                       action='get',
                       conditions={'method': ['GET']})
        mapper.connect('/tasks/{task_id}',
                       controller=tasks_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})

        super(API, self).__init__(mapper)
