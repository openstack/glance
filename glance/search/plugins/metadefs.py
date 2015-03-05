# Copyright 2015 Intel Corporation
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

import copy

import six

import glance.db
from glance.db.sqlalchemy import models_metadef as models
from glance.search.plugins import base
from glance.search.plugins import metadefs_notification_handler


class MetadefIndex(base.IndexBase):
    def __init__(self):
        super(MetadefIndex, self).__init__()

        self.db_api = glance.db.get_api()

    def get_index_name(self):
        return 'glance'

    def get_document_type(self):
        return 'metadef'

    def get_mapping(self):
        property_mapping = {
            'dynamic': True,
            'type': 'nested',
            'properties': {
                'property': {'type': 'string', 'index': 'not_analyzed'},
                'type': {'type': 'string'},
                'title': {'type': 'string'},
                'description': {'type': 'string'},
            }
        }
        mapping = {
            '_id': {
                'path': 'namespace',
            },
            'properties': {
                'display_name': {'type': 'string'},
                'description': {'type': 'string'},
                'namespace': {'type': 'string', 'index': 'not_analyzed'},
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'visibility': {'type': 'string', 'index': 'not_analyzed'},
                'resource_types': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'},
                        'prefix': {'type': 'string'},
                        'properties_target': {'type': 'string'},
                    },
                },
                'objects': {
                    'type': 'nested',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        'name': {'type': 'string'},
                        'description': {'type': 'string'},
                        'properties': property_mapping,
                    }
                },
                'properties': property_mapping,
                'tags': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'},
                    }
                }
            },
        }
        return mapping

    def get_rbac_filter(self, request_context):
        # TODO(krykowski): Define base get_rbac_filter in IndexBase class
        # which will provide some common subset of query pieces.
        # Something like:
        # def get_common_context_pieces(self, request_context):
        # return [{'term': {'owner': request_context.owner,
        #                  'type': {'value': self.get_document_type()}}]
        return [
            {
                "and": [
                    {
                        'or': [
                            {
                                'term': {
                                    'owner': request_context.owner
                                }
                            },
                            {
                                'term': {
                                    'visibility': 'public'
                                }
                            }
                        ]
                    },
                    {
                        'type': {
                            'value': self.get_document_type()
                        }
                    }
                ]
            }
        ]

    def get_objects(self):
        session = self.db_api.get_session()
        namespaces = session.query(models.MetadefNamespace).all()

        resource_types = session.query(models.MetadefResourceType).all()
        resource_types_map = {r.id: r.name for r in resource_types}

        for namespace in namespaces:
            namespace.resource_types = self.get_namespace_resource_types(
                namespace.id, resource_types_map)
            namespace.objects = self.get_namespace_objects(namespace.id)
            namespace.properties = self.get_namespace_properties(namespace.id)
            namespace.tags = self.get_namespace_tags(namespace.id)

        return namespaces

    def get_namespace_resource_types(self, namespace_id, resource_types):
        session = self.db_api.get_session()
        namespace_resource_types = session.query(
            models.MetadefNamespaceResourceType
        ).filter_by(namespace_id=namespace_id)

        resource_associations = [{
            'prefix': r.prefix,
            'properties_target': r.properties_target,
            'name': resource_types[r.resource_type_id],
        } for r in namespace_resource_types]
        return resource_associations

    def get_namespace_properties(self, namespace_id):
        session = self.db_api.get_session()
        properties = session.query(
            models.MetadefProperty
        ).filter_by(namespace_id=namespace_id)
        return list(properties)

    def get_namespace_objects(self, namespace_id):
        session = self.db_api.get_session()
        namespace_objects = session.query(
            models.MetadefObject
        ).filter_by(namespace_id=namespace_id)
        return list(namespace_objects)

    def get_namespace_tags(self, namespace_id):
        session = self.db_api.get_session()
        namespace_tags = session.query(
            models.MetadefTag
        ).filter_by(namespace_id=namespace_id)
        return list(namespace_tags)

    def serialize(self, obj):
        object_docs = [self.serialize_object(ns_obj) for ns_obj in obj.objects]
        property_docs = [self.serialize_property(prop.name, prop.json_schema)
                         for prop in obj.properties]
        resource_type_docs = [self.serialize_namespace_resource_type(rt)
                              for rt in obj.resource_types]
        tag_docs = [self.serialize_tag(tag) for tag in obj.tags]
        namespace_doc = self.serialize_namespace(obj)
        namespace_doc.update({
            'objects': object_docs,
            'properties': property_docs,
            'resource_types': resource_type_docs,
            'tags': tag_docs,
        })
        return namespace_doc

    def serialize_namespace(self, namespace):
        return {
            'namespace': namespace.namespace,
            'display_name': namespace.display_name,
            'description': namespace.description,
            'visibility': namespace.visibility,
            'protected': namespace.protected,
            'owner': namespace.owner,
        }

    def serialize_object(self, obj):
        obj_properties = obj.json_schema
        property_docs = []
        for name, schema in six.iteritems(obj_properties):
            property_doc = self.serialize_property(name, schema)
            property_docs.append(property_doc)

        document = {
            'name': obj.name,
            'description': obj.description,
            'properties': property_docs,
        }
        return document

    def serialize_property(self, name, schema):
        document = copy.deepcopy(schema)
        document['property'] = name

        if 'default' in document:
            document['default'] = str(document['default'])
        if 'enum' in document:
            document['enum'] = map(str, document['enum'])

        return document

    def serialize_namespace_resource_type(self, ns_resource_type):
        return {
            'name': ns_resource_type['name'],
            'prefix': ns_resource_type['prefix'],
            'properties_target': ns_resource_type['properties_target']
        }

    def serialize_tag(self, tag):
        return {
            'name': tag.name
        }

    def get_notification_handler(self):
        return metadefs_notification_handler.MetadefHandler(
            self.engine,
            self.get_index_name(),
            self.get_document_type()
        )

    def get_notification_supported_events(self):
        return [
            "metadef_namespace.create",
            "metadef_namespace.update",
            "metadef_namespace.delete",
            "metadef_object.create",
            "metadef_object.update",
            "metadef_object.delete",
            "metadef_property.create",
            "metadef_property.update",
            "metadef_property.delete",
            "metadef_tag.create",
            "metadef_tag.update",
            "metadef_tag.delete",
            "metadef_resource_type.create",
            "metadef_resource_type.delete",
            "metadef_namespace.delete_properties",
            "metadef_namespace.delete_objects",
            "metadef_namespace.delete_tags"
        ]
