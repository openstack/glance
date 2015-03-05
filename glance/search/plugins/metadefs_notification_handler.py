# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import six

from oslo_log import log as logging
import oslo_messaging

from glance.common import utils
from glance.search.plugins import base

LOG = logging.getLogger(__name__)


class MetadefHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(MetadefHandler, self).__init__(*args, **kwargs)
        self.namespace_delete_keys = ['deleted_at', 'deleted', 'created_at',
                                      'updated_at', 'namespace_old']
        self.property_delete_keys = ['deleted', 'deleted_at',
                                     'name_old', 'namespace', 'name']

    def process(self, ctxt, publisher_id, event_type, payload, metadata):
        try:
            actions = {
                "metadef_namespace.create": self.create_ns,
                "metadef_namespace.update": self.update_ns,
                "metadef_namespace.delete": self.delete_ns,
                "metadef_object.create": self.create_obj,
                "metadef_object.update": self.update_obj,
                "metadef_object.delete": self.delete_obj,
                "metadef_property.create": self.create_prop,
                "metadef_property.update": self.update_prop,
                "metadef_property.delete": self.delete_prop,
                "metadef_resource_type.create": self.create_rs,
                "metadef_resource_type.delete": self.delete_rs,
                "metadef_tag.create": self.create_tag,
                "metadef_tag.update": self.update_tag,
                "metadef_tag.delete": self.delete_tag,
                "metadef_namespace.delete_properties": self.delete_props,
                "metadef_namespace.delete_objects": self.delete_objects,
                "metadef_namespace.delete_tags": self.delete_tags
            }
            actions[event_type](payload)
            return oslo_messaging.NotificationResult.HANDLED
        except Exception as e:
            LOG.error(utils.exception_to_str(e))

    def run_create(self, id, payload):
        self.engine.create(
            index=self.index_name,
            doc_type=self.document_type,
            body=payload,
            id=id
        )

    def run_update(self, id, payload, script=False):
        if script:
            self.engine.update(
                index=self.index_name,
                doc_type=self.document_type,
                body=payload,
                id=id)
        else:
            doc = {"doc": payload}
            self.engine.update(
                index=self.index_name,
                doc_type=self.document_type,
                body=doc,
                id=id)

    def run_delete(self, id):
        self.engine.delete(
            index=self.index_name,
            doc_type=self.document_type,
            id=id
        )

    def create_ns(self, payload):
        id = payload['namespace']
        self.run_create(id, self.format_namespace(payload))

    def update_ns(self, payload):
        id = payload['namespace_old']
        self.run_update(id, self.format_namespace(payload))

    def delete_ns(self, payload):
        id = payload['namespace']
        self.run_delete(id)

    def create_obj(self, payload):
        id = payload['namespace']
        object = self.format_object(payload)
        self.create_entity(id, "objects", object)

    def update_obj(self, payload):
        id = payload['namespace']
        object = self.format_object(payload)
        self.update_entity(id, "objects", object,
                           payload['name_old'], "name")

    def delete_obj(self, payload):
        id = payload['namespace']
        self.delete_entity(id, "objects", payload['name'], "name")

    def create_prop(self, payload):
        id = payload['namespace']
        property = self.format_property(payload)
        self.create_entity(id, "properties", property)

    def update_prop(self, payload):
        id = payload['namespace']
        property = self.format_property(payload)
        self.update_entity(id, "properties", property,
                           payload['name_old'], "property")

    def delete_prop(self, payload):
        id = payload['namespace']
        self.delete_entity(id, "properties", payload['name'], "property")

    def create_rs(self, payload):
        id = payload['namespace']
        resource_type = dict()
        resource_type['name'] = payload['name']
        if payload['prefix']:
            resource_type['prefix'] = payload['prefix']
        if payload['properties_target']:
            resource_type['properties_target'] = payload['properties_target']

        self.create_entity(id, "resource_types", resource_type)

    def delete_rs(self, payload):
        id = payload['namespace']
        self.delete_entity(id, "resource_types", payload['name'], "name")

    def create_tag(self, payload):
        id = payload['namespace']
        tag = dict()
        tag['name'] = payload['name']

        self.create_entity(id, "tags", tag)

    def update_tag(self, payload):
        id = payload['namespace']
        tag = dict()
        tag['name'] = payload['name']

        self.update_entity(id, "tags", tag, payload['name_old'], "name")

    def delete_tag(self, payload):
        id = payload['namespace']
        self.delete_entity(id, "tags", payload['name'], "name")

    def delete_props(self, payload):
        self.delete_field(payload, "properties")

    def delete_objects(self, payload):
        self.delete_field(payload, "objects")

    def delete_tags(self, payload):
        self.delete_field(payload, "tags")

    def create_entity(self, id, entity, entity_data):
        script = ("if (ctx._source.containsKey('%(entity)s'))"
                  "{ctx._source.%(entity)s += entity_item }"
                  "else {ctx._source.%(entity)s=entity_list};" %
                  {"entity": entity})

        params = {
            "entity_item": entity_data,
            "entity_list": [entity_data]
        }
        payload = {"script": script, "params": params}
        self.run_update(id, payload=payload, script=True)

    def update_entity(self, id, entity, entity_data, entity_id, field_name):
        entity_id = entity_id.lower()
        script = ("obj=null; for(entity_item :ctx._source.%(entity)s)"
                  "{if(entity_item['%(field_name)s'].toLowerCase() "
                  " == entity_id ) obj=entity_item;};"
                  "if(obj!=null)ctx._source.%(entity)s.remove(obj);"
                  "if (ctx._source.containsKey('%(entity)s'))"
                  "{ctx._source.%(entity)s += entity_item; }"
                  "else {ctx._source.%(entity)s=entity_list;}" %
                  {"entity": entity, "field_name": field_name})
        params = {
            "entity_item": entity_data,
            "entity_list": [entity_data],
            "entity_id": entity_id
        }
        payload = {"script": script, "params": params}
        self.run_update(id, payload=payload, script=True)

    def delete_entity(self, id, entity, entity_id, field_name):
        entity_id = entity_id.lower()
        script = ("obj=null; for(entity_item :ctx._source.%(entity)s)"
                  "{if(entity_item['%(field_name)s'].toLowerCase() "
                  " == entity_id ) obj=entity_item;};"
                  "if(obj!=null)ctx._source.%(entity)s.remove(obj);" %
                  {"entity": entity, "field_name": field_name})
        params = {
            "entity_id": entity_id
        }
        payload = {"script": script, "params": params}
        self.run_update(id, payload=payload, script=True)

    def delete_field(self, payload, field):
        id = payload['namespace']
        script = ("if (ctx._source.containsKey('%(field)s'))"
                  "{ctx._source.remove('%(field)s')}") % {"field": field}
        payload = {"script": script}
        self.run_update(id, payload=payload, script=True)

    def format_namespace(self, payload):
        for key in self.namespace_delete_keys:
            if key in payload.keys():
                del payload[key]
        return payload

    def format_object(self, payload):
        formatted_object = dict()
        formatted_object['name'] = payload['name']
        formatted_object['description'] = payload['description']
        if payload['required']:
            formatted_object['required'] = payload['required']
        formatted_object['properties'] = []
        for property in payload['properties']:
            formatted_property = self.format_property(property)
            formatted_object['properties'].append(formatted_property)
        return formatted_object

    def format_property(self, payload):
        prop_data = dict()
        prop_data['property'] = payload['name']
        for key, value in six.iteritems(payload):
            if key not in self.property_delete_keys and value:
                prop_data[key] = value
        return prop_data
