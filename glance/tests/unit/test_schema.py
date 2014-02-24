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

from glance.common import exception
import glance.schema
from glance.tests import utils as test_utils


class TestBasicSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestBasicSchema, self).setUp()
        properties = {
            'ham': {'type': 'string'},
            'eggs': {'type': 'string'},
        }
        self.schema = glance.schema.Schema('basic', properties)

    def test_validate_passes(self):
        obj = {'ham': 'no', 'eggs': 'scrambled'}
        self.schema.validate(obj)  # No exception raised

    def test_validate_fails_on_extra_properties(self):
        obj = {'ham': 'virginia', 'eggs': 'scrambled', 'bacon': 'crispy'}
        self.assertRaises(exception.InvalidObject, self.schema.validate, obj)

    def test_validate_fails_on_bad_type(self):
        obj = {'eggs': 2}
        self.assertRaises(exception.InvalidObject, self.schema.validate, obj)

    def test_filter_strips_extra_properties(self):
        obj = {'ham': 'virginia', 'eggs': 'scrambled', 'bacon': 'crispy'}
        filtered = self.schema.filter(obj)
        expected = {'ham': 'virginia', 'eggs': 'scrambled'}
        self.assertEqual(expected, filtered)

    def test_merge_properties(self):
        self.schema.merge_properties({'bacon': {'type': 'string'}})
        expected = set(['ham', 'eggs', 'bacon'])
        actual = set(self.schema.raw()['properties'].keys())
        self.assertEqual(expected, actual)

    def test_merge_conflicting_properties(self):
        conflicts = {'eggs': {'type': 'integer'}}
        self.assertRaises(exception.SchemaLoadError,
                          self.schema.merge_properties, conflicts)

    def test_merge_conflicting_but_identical_properties(self):
        conflicts = {'ham': {'type': 'string'}}
        self.schema.merge_properties(conflicts)  # no exception raised
        expected = set(['ham', 'eggs'])
        actual = set(self.schema.raw()['properties'].keys())
        self.assertEqual(expected, actual)

    def test_raw_json_schema(self):
        expected = {
            'name': 'basic',
            'properties': {
                'ham': {'type': 'string'},
                'eggs': {'type': 'string'},
            },
            'additionalProperties': False,
        }
        self.assertEqual(expected, self.schema.raw())


class TestBasicSchemaLinks(test_utils.BaseTestCase):

    def setUp(self):
        super(TestBasicSchemaLinks, self).setUp()
        properties = {
            'ham': {'type': 'string'},
            'eggs': {'type': 'string'},
        }
        links = [
            {'rel': 'up', 'href': '/menu'},
        ]
        self.schema = glance.schema.Schema('basic', properties, links)

    def test_raw_json_schema(self):
        expected = {
            'name': 'basic',
            'properties': {
                'ham': {'type': 'string'},
                'eggs': {'type': 'string'},
            },
            'links': [
                {'rel': 'up', 'href': '/menu'},
            ],
            'additionalProperties': False,
        }
        self.assertEqual(expected, self.schema.raw())


class TestPermissiveSchema(test_utils.BaseTestCase):

    def setUp(self):
        super(TestPermissiveSchema, self).setUp()
        properties = {
            'ham': {'type': 'string'},
            'eggs': {'type': 'string'},
        }
        self.schema = glance.schema.PermissiveSchema('permissive', properties)

    def test_validate_with_additional_properties_allowed(self):
        obj = {'ham': 'virginia', 'eggs': 'scrambled', 'bacon': 'crispy'}
        self.schema.validate(obj)  # No exception raised

    def test_validate_rejects_non_string_extra_properties(self):
        obj = {'ham': 'virginia', 'eggs': 'scrambled', 'grits': 1000}
        self.assertRaises(exception.InvalidObject, self.schema.validate, obj)

    def test_filter_passes_extra_properties(self):
        obj = {'ham': 'virginia', 'eggs': 'scrambled', 'bacon': 'crispy'}
        filtered = self.schema.filter(obj)
        self.assertEqual(obj, filtered)

    def test_raw_json_schema(self):
        expected = {
            'name': 'permissive',
            'properties': {
                'ham': {'type': 'string'},
                'eggs': {'type': 'string'},
            },
            'additionalProperties': {'type': 'string'},
        }
        self.assertEqual(expected, self.schema.raw())


class TestCollectionSchema(test_utils.BaseTestCase):

    def test_raw_json_schema(self):
        item_properties = {'cheese': {'type': 'string'}}
        item_schema = glance.schema.Schema('mouse', item_properties)
        collection_schema = glance.schema.CollectionSchema('mice', item_schema)
        expected = {
            'name': 'mice',
            'properties': {
                'mice': {
                    'type': 'array',
                    'items': item_schema.raw(),
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
        self.assertEqual(expected, collection_schema.raw())
