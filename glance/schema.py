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

import copy
import json
import logging

import jsonschema

from glance.common import exception
from glance.openstack.common import cfg

logger = logging.getLogger(__name__)

CONF = cfg.CONF

_BASE_SCHEMA_PROPERTIES = {
    'image': {
        'id': {
            'type': 'string',
            'description': 'An identifier for the image',
            'maxLength': 36,
        },
        'name': {
            'type': 'string',
            'description': 'Descriptive name for the image',
            'maxLength': 255,
        },
        'visibility': {
            'type': 'string',
            'description': 'Scope of image accessibility',
            'enum': ['public', 'private'],
        },
        'created_at': {
          'type': 'string',
          'description': 'Date and time of image registration',
          #TODO(bcwaldon): our jsonschema library doesn't seem to like the
          # format attribute, figure out why!
          #'format': 'date-time',
        },
        'updated_at': {
          'type': 'string',
          'description': 'Date and time of the last image modification',
          #'format': 'date-time',
        },
        'tags': {
            'type': 'array',
            'description': 'List of strings related to the image',
            'items': {
                'type': 'string',
                'maxLength': 255,
            },
        },
    },
    'access': {
        'tenant_id': {
          'type': 'string',
          'description': 'The tenant identifier',
        },
        'can_share': {
          'type': 'boolean',
          'description': 'Ability of tenant to share with others',
          'default': False,
        },
    },
}


class API(object):
    def __init__(self, base_properties=_BASE_SCHEMA_PROPERTIES):
        self.base_properties = base_properties
        self.schema_properties = copy.deepcopy(self.base_properties)

    def get_schema(self, name):
        if name == 'image' and CONF.allow_additional_image_properties:
            additional = {'type': 'string'}
        else:
            additional = False
        return {
            'name': name,
            'properties': self.schema_properties[name],
            'additionalProperties': additional
        }

    def set_custom_schema_properties(self, schema_name, custom_properties):
        """Update the custom properties of a schema with those provided."""
        schema_properties = copy.deepcopy(self.base_properties[schema_name])

        # Ensure custom props aren't attempting to override base props
        base_keys = set(schema_properties.keys())
        custom_keys = set(custom_properties.keys())
        intersecting_keys = base_keys.intersection(custom_keys)
        conflicting_keys = [k for k in intersecting_keys
                            if schema_properties[k] != custom_properties[k]]
        if len(conflicting_keys) > 0:
            props = ', '.join(conflicting_keys)
            reason = _("custom properties (%(props)s) conflict "
                       "with base properties")
            raise exception.SchemaLoadError(reason=reason % {'props': props})

        schema_properties.update(copy.deepcopy(custom_properties))
        self.schema_properties[schema_name] = schema_properties

    def validate(self, schema_name, obj):
        schema = self.get_schema(schema_name)
        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            raise exception.InvalidObject(schema=schema_name, reason=str(e))


def read_schema_properties_file(schema_name):
    """Find the schema properties files and load them into a dict."""
    schema_filename = 'schema-%s.json' % schema_name
    match = CONF.find_file(schema_filename)
    if match:
        schema_file = open(match)
        schema_data = schema_file.read()
        return json.loads(schema_data)
    else:
        msg = _('Could not find schema properties file %s. Continuing '
                'without custom properties')
        logger.warn(msg % schema_filename)
        return {}


def load_custom_schema_properties(api):
    """Extend base image and access schemas with custom properties."""
    for schema_name in ('image', 'access'):
        image_properties = read_schema_properties_file(schema_name)
        api.set_custom_schema_properties(schema_name, image_properties)
