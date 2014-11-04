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

from glance.api.v2 import image_actions
from glance.api.v2 import image_data
from glance.api.v2 import image_members
from glance.api.v2 import image_tags
from glance.api.v2 import images
from glance.api.v2 import metadef_namespaces
from glance.api.v2 import metadef_objects
from glance.api.v2 import metadef_properties
from glance.api.v2 import metadef_resource_types
from glance.api.v2 import metadef_tags
from glance.api.v2 import schemas
from glance.api.v2 import tasks
from glance.common import wsgi


class API(wsgi.Router):

    """WSGI router for Glance v2 API requests."""

    def __init__(self, mapper):
        custom_image_properties = images.load_custom_properties()
        reject_method_resource = wsgi.Resource(wsgi.RejectMethodController())

        schemas_resource = schemas.create_resource(custom_image_properties)
        mapper.connect('/schemas/image',
                       controller=schemas_resource,
                       action='image',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/image',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})
        mapper.connect('/schemas/images',
                       controller=schemas_resource,
                       action='images',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/images',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})
        mapper.connect('/schemas/member',
                       controller=schemas_resource,
                       action='member',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/member',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/members',
                       controller=schemas_resource,
                       action='members',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/members',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/task',
                       controller=schemas_resource,
                       action='task',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/task',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})
        mapper.connect('/schemas/tasks',
                       controller=schemas_resource,
                       action='tasks',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/tasks',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/namespace',
                       controller=schemas_resource,
                       action='metadef_namespace',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/namespace',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/namespaces',
                       controller=schemas_resource,
                       action='metadef_namespaces',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/namespaces',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/resource_type',
                       controller=schemas_resource,
                       action='metadef_resource_type',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/resource_type',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/resource_types',
                       controller=schemas_resource,
                       action='metadef_resource_types',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/resource_types',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/property',
                       controller=schemas_resource,
                       action='metadef_property',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/property',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/properties',
                       controller=schemas_resource,
                       action='metadef_properties',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/properties',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/object',
                       controller=schemas_resource,
                       action='metadef_object',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/object',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/objects',
                       controller=schemas_resource,
                       action='metadef_objects',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/objects',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/tag',
                       controller=schemas_resource,
                       action='metadef_tag',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/tag',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/schemas/metadefs/tags',
                       controller=schemas_resource,
                       action='metadef_tags',
                       conditions={'method': ['GET']})
        mapper.connect('/schemas/metadefs/tags',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        # Metadef resource types
        metadef_resource_types_resource = (
            metadef_resource_types.create_resource())

        mapper.connect('/metadefs/resource_types',
                       controller=metadef_resource_types_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/resource_types',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}/resource_types',
                       controller=metadef_resource_types_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/resource_types',
                       controller=metadef_resource_types_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces/{namespace}/resource_types',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}/resource_types/'
                       '{resource_type}',
                       controller=metadef_resource_types_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/resource_types/'
                       '{resource_type}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='DELETE',
                       conditions={'method': ['GET', 'POST', 'PUT',
                                              'PATCH', 'HEAD']})

        # Metadef Namespaces
        metadef_namespace_resource = metadef_namespaces.create_resource()
        mapper.connect('/metadefs/namespaces',
                       controller=metadef_namespace_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces',
                       controller=metadef_namespace_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}',
                       controller=metadef_namespace_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}',
                       controller=metadef_namespace_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/metadefs/namespaces/{namespace}',
                       controller=metadef_namespace_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT, DELETE',
                       conditions={'method': ['POST', 'PATCH', 'HEAD']})

        # Metadef namespace properties
        metadef_properties_resource = metadef_properties.create_resource()
        mapper.connect('/metadefs/namespaces/{namespace}/properties',
                       controller=metadef_properties_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties',
                       controller=metadef_properties_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties',
                       controller=metadef_namespace_resource,
                       action='delete_properties',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST, DELETE',
                       conditions={'method': ['PUT', 'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}/properties/{'
                       'property_name}',
                       controller=metadef_properties_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties/{'
                       'property_name}',
                       controller=metadef_properties_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties/{'
                       'property_name}',
                       controller=metadef_properties_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/properties/{'
                       'property_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT, DELETE',
                       conditions={'method': ['POST', 'PATCH', 'HEAD']})

        # Metadef objects
        metadef_objects_resource = metadef_objects.create_resource()
        mapper.connect('/metadefs/namespaces/{namespace}/objects',
                       controller=metadef_objects_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects',
                       controller=metadef_objects_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects',
                       controller=metadef_namespace_resource,
                       action='delete_objects',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST, DELETE',
                       conditions={'method': ['PUT', 'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}/objects/{'
                       'object_name}',
                       controller=metadef_objects_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects/{'
                       'object_name}',
                       controller=metadef_objects_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects/{'
                       'object_name}',
                       controller=metadef_objects_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/objects/{'
                       'object_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT, DELETE',
                       conditions={'method': ['POST', 'PATCH', 'HEAD']})

        # Metadef tags
        metadef_tags_resource = metadef_tags.create_resource()
        mapper.connect('/metadefs/namespaces/{namespace}/tags',
                       controller=metadef_tags_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags',
                       controller=metadef_tags_resource,
                       action='create_tags',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags',
                       controller=metadef_namespace_resource,
                       action='delete_tags',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST, DELETE',
                       conditions={'method': ['PUT', 'PATCH', 'HEAD']})

        mapper.connect('/metadefs/namespaces/{namespace}/tags/{tag_name}',
                       controller=metadef_tags_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags/{tag_name}',
                       controller=metadef_tags_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags/{tag_name}',
                       controller=metadef_tags_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags/{tag_name}',
                       controller=metadef_tags_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/metadefs/namespaces/{namespace}/tags/{tag_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST, PUT, DELETE',
                       conditions={'method': ['PATCH', 'HEAD']})

        images_resource = images.create_resource(custom_image_properties)
        mapper.connect('/images',
                       controller=images_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images',
                       controller=images_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/images',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE', 'PATCH',
                                              'HEAD']})

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
        mapper.connect('/images/{image_id}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PATCH, DELETE',
                       conditions={'method': ['POST', 'PUT', 'HEAD']})

        image_actions_resource = image_actions.create_resource()
        mapper.connect('/images/{image_id}/actions/deactivate',
                       controller=image_actions_resource,
                       action='deactivate',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}/actions/reactivate',
                       controller=image_actions_resource,
                       action='reactivate',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}/actions/deactivate',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='POST',
                       conditions={'method': ['GET', 'PUT', 'DELETE', 'PATCH',
                                              'HEAD']})
        mapper.connect('/images/{image_id}/actions/reactivate',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='POST',
                       conditions={'method': ['GET', 'PUT', 'DELETE', 'PATCH',
                                              'HEAD']})

        image_data_resource = image_data.create_resource()
        mapper.connect('/images/{image_id}/file',
                       controller=image_data_resource,
                       action='download',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/file',
                       controller=image_data_resource,
                       action='upload',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/file',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT',
                       conditions={'method': ['POST', 'DELETE', 'PATCH',
                                              'HEAD']})

        image_tags_resource = image_tags.create_resource()
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=image_tags_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/images/{image_id}/tags/{tag_value}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='PUT, DELETE',
                       conditions={'method': ['GET', 'POST', 'PATCH',
                                              'HEAD']})

        image_members_resource = image_members.create_resource()
        mapper.connect('/images/{image_id}/members',
                       controller=image_members_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/members',
                       controller=image_members_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/images/{image_id}/members',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE', 'PATCH',
                                              'HEAD']})

        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=image_members_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/images/{image_id}/members/{member_id}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT, DELETE',
                       conditions={'method': ['POST', 'PATCH', 'HEAD']})

        tasks_resource = tasks.create_resource()
        mapper.connect('/tasks',
                       controller=tasks_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/tasks',
                       controller=tasks_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/tasks',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE', 'PATCH',
                                              'HEAD']})

        mapper.connect('/tasks/{task_id}',
                       controller=tasks_resource,
                       action='get',
                       conditions={'method': ['GET']})
        mapper.connect('/tasks/{task_id}',
                       controller=tasks_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})
        mapper.connect('/tasks/{task_id}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, DELETE',
                       conditions={'method': ['POST', 'PUT', 'PATCH',
                                              'HEAD']})

        super(API, self).__init__(mapper)
