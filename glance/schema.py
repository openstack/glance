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

import jsonschema

from glance.common import exception


class Schema(object):

    def __init__(self, name, properties=None):
        self.name = name
        if properties is None:
            properties = {}
        self.properties = properties

    def validate(self, obj):
        try:
            jsonschema.validate(obj, self.raw())
        except jsonschema.ValidationError as e:
            raise exception.InvalidObject(schema=self.name, reason=str(e))

    def filter(self, obj):
        filtered = {}
        for key, value in obj.iteritems():
            if key in self.properties:
                filtered[key] = value
        return filtered

    def merge_properties(self, properties):
        # Ensure custom props aren't attempting to override base props
        original_keys = set(self.properties.keys())
        new_keys = set(properties.keys())
        intersecting_keys = original_keys.intersection(new_keys)
        conflicting_keys = [k for k in intersecting_keys
                            if self.properties[k] != properties[k]]
        if len(conflicting_keys) > 0:
            props = ', '.join(conflicting_keys)
            reason = _("custom properties (%(props)s) conflict "
                       "with base properties")
            raise exception.SchemaLoadError(reason=reason % {'props': props})

        self.properties.update(properties)

    def raw(self):
        return {
            'name': self.name,
            'properties': self.properties,
            'additionalProperties': False,
        }


class PermissiveSchema(Schema):
    def filter(self, obj):
        return obj

    def raw(self):
        raw = super(PermissiveSchema, self).raw()
        raw['additionalProperties'] = {'type': 'string'}
        return raw
