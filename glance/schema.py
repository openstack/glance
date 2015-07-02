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

import jsonschema
from oslo_utils import encodeutils
import six

from glance.common import exception
from glance import i18n

_ = i18n._


class Schema(object):

    def __init__(self, name, properties=None, links=None, required=None,
                 definitions=None):
        self.name = name
        if properties is None:
            properties = {}
        self.properties = properties
        self.links = links
        self.required = required
        self.definitions = definitions

    def validate(self, obj):
        try:
            jsonschema.validate(obj, self.raw())
        except jsonschema.ValidationError as e:
            reason = encodeutils.exception_to_unicode(e)
            raise exception.InvalidObject(schema=self.name, reason=reason)

    def filter(self, obj):
        filtered = {}
        for key, value in six.iteritems(obj):
            if self._filter_func(self.properties, key):
                filtered[key] = value

            # NOTE(flaper87): This exists to allow for v1, null properties,
            # to be used with the V2 API. During Kilo, it was allowed for the
            # later to return None values without considering that V1 allowed
            # for custom properties to be None, which is something V2 doesn't
            # allow for. This small hack here will set V1 custom `None` pro-
            # perties to an empty string so that they will be updated along
            # with the image (if an update happens).
            #
            # We could skip the properties that are `None` but that would bring
            # back the behavior we moved away from. Note that we can't consider
            # doing a schema migration because we don't know which properties
            # are "custom" and which came from `schema-image` if those custom
            # properties were created with v1.
            if key not in self.properties and value is None:
                filtered[key] = ''
        return filtered

    @staticmethod
    def _filter_func(properties, key):
        return key in properties

    def merge_properties(self, properties):
        # Ensure custom props aren't attempting to override base props
        original_keys = set(self.properties.keys())
        new_keys = set(properties.keys())
        intersecting_keys = original_keys.intersection(new_keys)
        conflicting_keys = [k for k in intersecting_keys
                            if self.properties[k] != properties[k]]
        if conflicting_keys:
            props = ', '.join(conflicting_keys)
            reason = _("custom properties (%(props)s) conflict "
                       "with base properties")
            raise exception.SchemaLoadError(reason=reason % {'props': props})

        self.properties.update(properties)

    def raw(self):
        raw = {
            'name': self.name,
            'properties': self.properties,
            'additionalProperties': False,
        }
        if self.definitions:
            raw['definitions'] = self.definitions
        if self.required:
            raw['required'] = self.required
        if self.links:
            raw['links'] = self.links
        return raw

    def minimal(self):
        minimal = {
            'name': self.name,
            'properties': self.properties
        }
        if self.definitions:
            minimal['definitions'] = self.definitions
        if self.required:
            minimal['required'] = self.required
        return minimal


class PermissiveSchema(Schema):
    @staticmethod
    def _filter_func(properties, key):
        return True

    def raw(self):
        raw = super(PermissiveSchema, self).raw()
        raw['additionalProperties'] = {'type': 'string'}
        return raw

    def minimal(self):
        minimal = super(PermissiveSchema, self).raw()
        return minimal


class CollectionSchema(object):

    def __init__(self, name, item_schema):
        self.name = name
        self.item_schema = item_schema

    def raw(self):
        definitions = None
        if self.item_schema.definitions:
            definitions = self.item_schema.definitions
            self.item_schema.definitions = None
        raw = {
            'name': self.name,
            'properties': {
                self.name: {
                    'type': 'array',
                    'items': self.item_schema.raw(),
                },
                'first': {'type': 'string'},
                'next': {'type': 'string'},
                'schema': {'type': 'string'},
            },
            'links': [
                {'rel': 'first', 'href': '{first}'},
                {'rel': 'next', 'href': '{next}'},
                {'rel': 'describedby', 'href': '{schema}'},
            ],
        }
        if definitions:
            raw['definitions'] = definitions
            self.item_schema.definitions = definitions

        return raw

    def minimal(self):
        definitions = None
        if self.item_schema.definitions:
            definitions = self.item_schema.definitions
            self.item_schema.definitions = None
        minimal = {
            'name': self.name,
            'properties': {
                self.name: {
                    'type': 'array',
                    'items': self.item_schema.minimal(),
                },
                'schema': {'type': 'string'},
            },
            'links': [
                {'rel': 'describedby', 'href': '{schema}'},
            ],
        }
        if definitions:
            minimal['definitions'] = definitions
            self.item_schema.definitions = definitions

        return minimal


class DictCollectionSchema(Schema):
    def __init__(self, name, item_schema):
        self.name = name
        self.item_schema = item_schema

    def raw(self):
        definitions = None
        if self.item_schema.definitions:
            definitions = self.item_schema.definitions
            self.item_schema.definitions = None
        raw = {
            'name': self.name,
            'properties': {
                self.name: {
                    'type': 'object',
                    'additionalProperties': self.item_schema.raw(),
                },
                'first': {'type': 'string'},
                'next': {'type': 'string'},
                'schema': {'type': 'string'},
            },
            'links': [
                {'rel': 'first', 'href': '{first}'},
                {'rel': 'next', 'href': '{next}'},
                {'rel': 'describedby', 'href': '{schema}'},
            ],
        }
        if definitions:
            raw['definitions'] = definitions
            self.item_schema.definitions = definitions

        return raw

    def minimal(self):
        definitions = None
        if self.item_schema.definitions:
            definitions = self.item_schema.definitions
            self.item_schema.definitions = None
        minimal = {
            'name': self.name,
            'properties': {
                self.name: {
                    'type': 'object',
                    'additionalProperties': self.item_schema.minimal(),
                },
                'schema': {'type': 'string'},
            },
            'links': [
                {'rel': 'describedby', 'href': '{schema}'},
            ],
        }
        if definitions:
            minimal['definitions'] = definitions
            self.item_schema.definitions = definitions

        return minimal
