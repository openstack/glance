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

from glance.api.v2 import image_members
from glance.api.v2 import images
from glance.api.v2 import metadef_namespaces
from glance.api.v2 import metadef_objects
from glance.api.v2 import metadef_properties
from glance.api.v2 import metadef_resource_types
from glance.api.v2 import metadef_tags
from glance.api.v2 import tasks
from glance.common import wsgi


class Controller(object):
    def __init__(self, custom_image_properties=None):
        self.image_schema = images.get_schema(custom_image_properties)
        self.image_collection_schema = images.get_collection_schema(
            custom_image_properties)
        self.member_schema = image_members.get_schema()
        self.member_collection_schema = image_members.get_collection_schema()
        self.task_schema = tasks.get_task_schema()
        self.task_collection_schema = tasks.get_collection_schema()

        # Metadef schemas
        self.metadef_namespace_schema = metadef_namespaces.get_schema()
        self.metadef_namespace_collection_schema = (
            metadef_namespaces.get_collection_schema())

        self.metadef_resource_type_schema = metadef_resource_types.get_schema()
        self.metadef_resource_type_collection_schema = (
            metadef_resource_types.get_collection_schema())

        self.metadef_property_schema = metadef_properties.get_schema()
        self.metadef_property_collection_schema = (
            metadef_properties.get_collection_schema())

        self.metadef_object_schema = metadef_objects.get_schema()
        self.metadef_object_collection_schema = (
            metadef_objects.get_collection_schema())

        self.metadef_tag_schema = metadef_tags.get_schema()
        self.metadef_tag_collection_schema = (
            metadef_tags.get_collection_schema())

    def image(self, req):
        return self.image_schema.raw()

    def images(self, req):
        return self.image_collection_schema.raw()

    def member(self, req):
        return self.member_schema.minimal()

    def members(self, req):
        return self.member_collection_schema.minimal()

    def task(self, req):
        return self.task_schema.minimal()

    def tasks(self, req):
        return self.task_collection_schema.minimal()

    def metadef_namespace(self, req):
        return self.metadef_namespace_schema.raw()

    def metadef_namespaces(self, req):
        return self.metadef_namespace_collection_schema.raw()

    def metadef_resource_type(self, req):
        return self.metadef_resource_type_schema.raw()

    def metadef_resource_types(self, req):
        return self.metadef_resource_type_collection_schema.raw()

    def metadef_property(self, req):
        return self.metadef_property_schema.raw()

    def metadef_properties(self, req):
        return self.metadef_property_collection_schema.raw()

    def metadef_object(self, req):
        return self.metadef_object_schema.raw()

    def metadef_objects(self, req):
        return self.metadef_object_collection_schema.raw()

    def metadef_tag(self, req):
        return self.metadef_tag_schema.raw()

    def metadef_tags(self, req):
        return self.metadef_tag_collection_schema.raw()


def create_resource(custom_image_properties=None):
    controller = Controller(custom_image_properties)
    return wsgi.Resource(controller)
