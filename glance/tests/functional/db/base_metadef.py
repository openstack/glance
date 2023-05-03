# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import os
import os.path

from glance.common import config
from glance.common import exception
from glance import context
from glance.db.sqlalchemy import metadata
import glance.tests.functional.db as db_tests
from glance.tests import utils as test_utils


# root of repo
ROOT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir,
    os.pardir,
    os.pardir,
    os.pardir,
)
METADEFS_DIR = os.path.join(ROOT_DIR, 'etc', 'metadefs')


def build_namespace_fixture(**kwargs):
    namespace = {
        'namespace': 'MyTestNamespace',
        'display_name': 'test-display-name',
        'description': 'test-description',
        'visibility': 'public',
        'protected': 0,
        'owner': 'test-owner'
    }
    namespace.update(kwargs)
    return namespace


def build_resource_type_fixture(**kwargs):
    resource_type = {
        'name': 'MyTestResourceType',
        'protected': 0
    }
    resource_type.update(kwargs)
    return resource_type


def build_association_fixture(**kwargs):
    association = {
        'name': 'MyTestResourceType',
        'properties_target': 'test-properties-target',
        'prefix': 'test-prefix'
    }
    association.update(kwargs)
    return association


def build_object_fixture(**kwargs):
    # Full testing of required and schema done via rest api tests
    object = {
        'namespace_id': 1,
        'name': 'test-object-name',
        'description': 'test-object-description',
        'required': 'fake-required-properties-list',
        'json_schema': '{fake-schema}'
    }
    object.update(kwargs)
    return object


def build_property_fixture(**kwargs):
    # Full testing of required and schema done via rest api tests
    property = {
        'namespace_id': 1,
        'name': 'test-property-name',
        'json_schema': '{fake-schema}'
    }
    property.update(kwargs)
    return property


def build_tag_fixture(**kwargs):
    # Full testing of required and schema done via rest api tests
    tag = {
        'namespace_id': 1,
        'name': 'test-tag-name',
    }
    tag.update(kwargs)
    return tag


def build_tags_fixture(tag_name_list):
    tag_list = []
    for tag_name in tag_name_list:
        tag_list.append({'name': tag_name})
    return tag_list


class TestMetadefDriver(test_utils.BaseTestCase):

    """Test Driver class for Metadef tests."""

    def setUp(self):
        """Run before each test method to initialize test environment."""
        super(TestMetadefDriver, self).setUp()
        config.parse_args(args=[])
        self.config(metadata_source_path=METADEFS_DIR)
        context_cls = context.RequestContext
        self.adm_context = context_cls(is_admin=True,
                                       auth_token='user:user:admin')
        self.context = context_cls(is_admin=False,
                                   auth_token='user:user:user')
        self.db_api = db_tests.get_db(self.config)
        db_tests.reset_db(self.db_api)

    def _assert_saved_fields(self, expected, actual):
        for k in expected.keys():
            self.assertEqual(expected[k], actual[k])


class MetadefNamespaceTests(object):

    def test_namespace_create(self):
        fixture = build_namespace_fixture()
        created = self.db_api.metadef_namespace_create(self.context, fixture)
        self.assertIsNotNone(created)
        self._assert_saved_fields(fixture, created)

    def test_namespace_create_duplicate(self):
        fixture = build_namespace_fixture()
        created = self.db_api.metadef_namespace_create(self.context, fixture)
        self.assertIsNotNone(created)
        self._assert_saved_fields(fixture, created)
        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_namespace_create,
                          self.context, fixture)

    def test_namespace_get(self):
        fixture = build_namespace_fixture()
        created = self.db_api.metadef_namespace_create(self.context, fixture)
        self.assertIsNotNone(created)
        self._assert_saved_fields(fixture, created)

        found = self.db_api.metadef_namespace_get(
            self.context, created['namespace'])
        self.assertIsNotNone(found, "Namespace not found.")

    def test_namespace_get_all_with_resource_types_filter(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture = build_association_fixture()
        created = self.db_api.metadef_resource_type_association_create(
            self.context, ns_created['namespace'], fixture)
        self.assertIsNotNone(created, "Could not create an association.")

        rt_filters = {'resource_types': fixture['name']}
        found = self.db_api.metadef_namespace_get_all(
            self.context, filters=rt_filters, sort_key='created_at')
        self.assertEqual(1, len(found))
        for item in found:
            self._assert_saved_fields(ns_fixture, item)

    def test_namespace_update(self):
        delta = {'owner': 'New Owner'}
        fixture = build_namespace_fixture()

        created = self.db_api.metadef_namespace_create(self.context, fixture)
        self.assertIsNotNone(created['namespace'])
        self.assertEqual(fixture['namespace'], created['namespace'])
        delta_dict = copy.deepcopy(created)
        delta_dict.update(delta.copy())

        updated = self.db_api.metadef_namespace_update(
            self.context, created['id'], delta_dict)
        self.assertEqual(delta['owner'], updated['owner'])

    def test_namespace_delete(self):
        fixture = build_namespace_fixture()
        created = self.db_api.metadef_namespace_create(self.context, fixture)
        self.assertIsNotNone(created, "Could not create a Namespace.")
        self.db_api.metadef_namespace_delete(
            self.context, created['namespace'])
        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_namespace_get,
                          self.context, created['namespace'])

    def test_namespace_delete_with_content(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self._assert_saved_fields(fixture_ns, created_ns)

        # Create object content for the namespace
        fixture_obj = build_object_fixture()
        created_obj = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], fixture_obj)
        self.assertIsNotNone(created_obj)

        # Create property content for the namespace
        fixture_prop = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], fixture_prop)
        self.assertIsNotNone(created_prop)

        # Create associations
        fixture_assn = build_association_fixture()
        created_assn = self.db_api.metadef_resource_type_association_create(
            self.context, created_ns['namespace'], fixture_assn)
        self.assertIsNotNone(created_assn)

        deleted_ns = self.db_api.metadef_namespace_delete(
            self.context, created_ns['namespace'])

        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_namespace_get,
                          self.context, deleted_ns['namespace'])


class MetadefPropertyTests(object):

    def test_property_create(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_prop = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], fixture_prop)
        self._assert_saved_fields(fixture_prop, created_prop)

    def test_property_create_duplicate(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_prop = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], fixture_prop)
        self._assert_saved_fields(fixture_prop, created_prop)

        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_property_create,
                          self.context, created_ns['namespace'], fixture_prop)

    def test_property_get(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture_ns, created_ns)

        fixture_prop = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], fixture_prop)

        found_prop = self.db_api.metadef_property_get(
            self.context, created_ns['namespace'], created_prop['name'])
        self._assert_saved_fields(fixture_prop, found_prop)

    def test_property_get_all(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture1 = build_property_fixture(namespace_id=ns_created['id'])
        created_p1 = self.db_api.metadef_property_create(
            self.context, ns_created['namespace'], fixture1)
        self.assertIsNotNone(created_p1, "Could not create a property.")

        fixture2 = build_property_fixture(namespace_id=ns_created['id'],
                                          name='test-prop-2')
        created_p2 = self.db_api.metadef_property_create(
            self.context, ns_created['namespace'], fixture2)
        self.assertIsNotNone(created_p2, "Could not create a property.")

        found = self.db_api.metadef_property_get_all(
            self.context, ns_created['namespace'])
        self.assertEqual(2, len(found))

    def test_property_update(self):
        delta = {'name': 'New-name', 'json_schema': 'new-schema'}

        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        prop_fixture = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], prop_fixture)
        self.assertIsNotNone(created_prop, "Could not create a property.")

        delta_dict = copy.deepcopy(created_prop)
        delta_dict.update(delta.copy())

        updated = self.db_api.metadef_property_update(
            self.context, created_ns['namespace'],
            created_prop['id'], delta_dict)
        self.assertEqual(delta['name'], updated['name'])
        self.assertEqual(delta['json_schema'], updated['json_schema'])

    def test_property_delete(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        prop_fixture = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], prop_fixture)
        self.assertIsNotNone(created_prop, "Could not create a property.")

        self.db_api.metadef_property_delete(
            self.context, created_ns['namespace'], created_prop['name'])
        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_property_get,
                          self.context, created_ns['namespace'],
                          created_prop['name'])

    def test_property_delete_namespace_content(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        prop_fixture = build_property_fixture(namespace_id=created_ns['id'])
        created_prop = self.db_api.metadef_property_create(
            self.context, created_ns['namespace'], prop_fixture)
        self.assertIsNotNone(created_prop, "Could not create a property.")

        self.db_api.metadef_property_delete_namespace_content(
            self.context, created_ns['namespace'])
        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_property_get,
                          self.context, created_ns['namespace'],
                          created_prop['name'])


class MetadefObjectTests(object):

    def test_object_create(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_object = build_object_fixture(namespace_id=created_ns['id'])
        created_object = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], fixture_object)
        self._assert_saved_fields(fixture_object, created_object)

    def test_object_create_duplicate(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_object = build_object_fixture(namespace_id=created_ns['id'])
        created_object = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], fixture_object)
        self._assert_saved_fields(fixture_object, created_object)

        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_object_create,
                          self.context, created_ns['namespace'],
                          fixture_object)

    def test_object_get(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture_ns)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture_ns, created_ns)

        fixture_object = build_object_fixture(namespace_id=created_ns['id'])
        created_object = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], fixture_object)

        found_object = self.db_api.metadef_object_get(
            self.context, created_ns['namespace'], created_object['name'])
        self._assert_saved_fields(fixture_object, found_object)

    def test_object_get_all(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(self.context,
                                                          ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture1 = build_object_fixture(namespace_id=ns_created['id'])
        created_o1 = self.db_api.metadef_object_create(
            self.context, ns_created['namespace'], fixture1)
        self.assertIsNotNone(created_o1, "Could not create an object.")

        fixture2 = build_object_fixture(namespace_id=ns_created['id'],
                                        name='test-object-2')
        created_o2 = self.db_api.metadef_object_create(
            self.context, ns_created['namespace'], fixture2)
        self.assertIsNotNone(created_o2, "Could not create an object.")

        found = self.db_api.metadef_object_get_all(
            self.context, ns_created['namespace'])
        self.assertEqual(2, len(found))

    def test_object_update(self):
        delta = {'name': 'New-name', 'json_schema': 'new-schema',
                 'required': 'new-required'}

        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        object_fixture = build_object_fixture(namespace_id=created_ns['id'])
        created_object = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], object_fixture)
        self.assertIsNotNone(created_object, "Could not create an object.")

        delta_dict = {}
        delta_dict.update(delta.copy())

        updated = self.db_api.metadef_object_update(
            self.context, created_ns['namespace'],
            created_object['id'], delta_dict)
        self.assertEqual(delta['name'], updated['name'])
        self.assertEqual(delta['json_schema'], updated['json_schema'])

    def test_object_delete(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        object_fixture = build_object_fixture(namespace_id=created_ns['id'])
        created_object = self.db_api.metadef_object_create(
            self.context, created_ns['namespace'], object_fixture)
        self.assertIsNotNone(created_object, "Could not create an object.")

        self.db_api.metadef_object_delete(
            self.context, created_ns['namespace'], created_object['name'])
        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_object_get,
                          self.context, created_ns['namespace'],
                          created_object['name'])


class MetadefResourceTypeTests(object):

    def test_resource_type_get_all(self):
        resource_types_orig = self.db_api.metadef_resource_type_get_all(
            self.context)

        fixture = build_resource_type_fixture()
        self.db_api.metadef_resource_type_create(self.context, fixture)

        resource_types = self.db_api.metadef_resource_type_get_all(
            self.context)

        test_len = len(resource_types_orig) + 1
        self.assertEqual(test_len, len(resource_types))


class MetadefResourceTypeAssociationTests(object):

    def test_association_create(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created)
        self._assert_saved_fields(ns_fixture, ns_created)

        assn_fixture = build_association_fixture()
        assn_created = self.db_api.metadef_resource_type_association_create(
            self.context, ns_created['namespace'], assn_fixture)
        self.assertIsNotNone(assn_created)
        self._assert_saved_fields(assn_fixture, assn_created)

    def test_association_create_duplicate(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created)
        self._assert_saved_fields(ns_fixture, ns_created)

        assn_fixture = build_association_fixture()
        assn_created = self.db_api.metadef_resource_type_association_create(
            self.context, ns_created['namespace'], assn_fixture)
        self.assertIsNotNone(assn_created)
        self._assert_saved_fields(assn_fixture, assn_created)

        self.assertRaises(exception.Duplicate,
                          self.db_api.
                          metadef_resource_type_association_create,
                          self.context, ns_created['namespace'], assn_fixture)

    def test_association_delete(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture = build_association_fixture()
        created = self.db_api.metadef_resource_type_association_create(
            self.context, ns_created['namespace'], fixture)
        self.assertIsNotNone(created, "Could not create an association.")

        created_resource = self.db_api.metadef_resource_type_get(
            self.context, fixture['name'])
        self.assertIsNotNone(created_resource, "resource_type not created")

        self.db_api.metadef_resource_type_association_delete(
            self.context, ns_created['namespace'], created_resource['name'])
        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_resource_type_association_get,
                          self.context, ns_created['namespace'],
                          created_resource['name'])

    def test_association_get_all_by_namespace(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(
            self.context, ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture = build_association_fixture()
        created = self.db_api.metadef_resource_type_association_create(
            self.context, ns_created['namespace'], fixture)
        self.assertIsNotNone(created, "Could not create an association.")

        found = (
            self.db_api.metadef_resource_type_association_get_all_by_namespace(
                self.context, ns_created['namespace']))
        self.assertEqual(1, len(found))
        for item in found:
            self._assert_saved_fields(fixture, item)


class MetadefTagTests(object):

    def test_tag_create(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_tag = build_tag_fixture(namespace_id=created_ns['id'])
        created_tag = self.db_api.metadef_tag_create(
            self.context, created_ns['namespace'], fixture_tag)
        self._assert_saved_fields(fixture_tag, created_tag)

    def test_tag_create_duplicate(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        fixture_tag = build_tag_fixture(namespace_id=created_ns['id'])
        created_tag = self.db_api.metadef_tag_create(
            self.context, created_ns['namespace'], fixture_tag)
        self._assert_saved_fields(fixture_tag, created_tag)

        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_tag_create,
                          self.context, created_ns['namespace'],
                          fixture_tag)

    def test_tag_create_tags(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        tags = build_tags_fixture(['Tag1', 'Tag2', 'Tag3'])
        created_tags = self.db_api.metadef_tag_create_tags(
            self.context, created_ns['namespace'], tags)
        actual = set([tag['name'] for tag in created_tags])
        expected = set(['Tag1', 'Tag2', 'Tag3'])
        self.assertEqual(expected, actual)

    def test_tag_create_tags_with_append(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        tags = build_tags_fixture(['Tag1', 'Tag2', 'Tag3'])
        created_tags = self.db_api.metadef_tag_create_tags(
            self.context, created_ns['namespace'], tags)
        actual = set([tag['name'] for tag in created_tags])
        expected = set(['Tag1', 'Tag2', 'Tag3'])
        self.assertEqual(expected, actual)

        new_tags = build_tags_fixture(['Tag4', 'Tag5', 'Tag6'])
        new_created_tags = self.db_api.metadef_tag_create_tags(
            self.context, created_ns['namespace'], new_tags, can_append=True)
        actual = set([tag['name'] for tag in new_created_tags])
        expected = set(['Tag4', 'Tag5', 'Tag6'])
        self.assertEqual(expected, actual)

        tags = self.db_api.metadef_tag_get_all(self.context,
                                               created_ns['namespace'],
                                               sort_key='created_at')
        actual = set([tag['name'] for tag in tags])
        expected = set(['Tag1', 'Tag2', 'Tag3', 'Tag4', 'Tag5', 'Tag6'])
        self.assertEqual(expected, actual)

    def test_tag_create_duplicate_tags_1(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        tags = build_tags_fixture(['Tag1', 'Tag2', 'Tag3', 'Tag2'])
        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_tag_create_tags,
                          self.context, created_ns['namespace'],
                          tags)

    def test_tag_create_duplicate_tags_2(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        tags = build_tags_fixture(['Tag1', 'Tag2', 'Tag3'])
        self.db_api.metadef_tag_create_tags(self.context,
                                            created_ns['namespace'], tags)
        dup_tag = build_tag_fixture(namespace_id=created_ns['id'],
                                    name='Tag3')
        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_tag_create,
                          self.context, created_ns['namespace'], dup_tag)

    def test_tag_create_duplicate_tags_3(self):
        fixture = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture, created_ns)

        tags = build_tags_fixture(['Tag1', 'Tag2', 'Tag3'])
        self.db_api.metadef_tag_create_tags(self.context,
                                            created_ns['namespace'], tags)
        dup_tags = build_tags_fixture(['Tag3', 'Tag4', 'Tag5'])
        self.assertRaises(exception.Duplicate,
                          self.db_api.metadef_tag_create_tags,
                          self.context, created_ns['namespace'],
                          dup_tags, can_append=True)

    def test_tag_get(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture_ns)
        self.assertIsNotNone(created_ns)
        self._assert_saved_fields(fixture_ns, created_ns)

        fixture_tag = build_tag_fixture(namespace_id=created_ns['id'])
        created_tag = self.db_api.metadef_tag_create(
            self.context, created_ns['namespace'], fixture_tag)

        found_tag = self.db_api.metadef_tag_get(
            self.context, created_ns['namespace'], created_tag['name'])
        self._assert_saved_fields(fixture_tag, found_tag)

    def test_tag_get_all(self):
        ns_fixture = build_namespace_fixture()
        ns_created = self.db_api.metadef_namespace_create(self.context,
                                                          ns_fixture)
        self.assertIsNotNone(ns_created, "Could not create a namespace.")
        self._assert_saved_fields(ns_fixture, ns_created)

        fixture1 = build_tag_fixture(namespace_id=ns_created['id'])
        created_tag1 = self.db_api.metadef_tag_create(
            self.context, ns_created['namespace'], fixture1)
        self.assertIsNotNone(created_tag1, "Could not create tag 1.")

        fixture2 = build_tag_fixture(namespace_id=ns_created['id'],
                                     name='test-tag-2')
        created_tag2 = self.db_api.metadef_tag_create(
            self.context, ns_created['namespace'], fixture2)
        self.assertIsNotNone(created_tag2, "Could not create tag 2.")

        found = self.db_api.metadef_tag_get_all(
            self.context, ns_created['namespace'], sort_key='created_at')
        self.assertEqual(2, len(found))

    def test_tag_update(self):
        delta = {'name': 'New-name'}

        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(self.context,
                                                          fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        tag_fixture = build_tag_fixture(namespace_id=created_ns['id'])
        created_tag = self.db_api.metadef_tag_create(
            self.context, created_ns['namespace'], tag_fixture)
        self.assertIsNotNone(created_tag, "Could not create a tag.")

        delta_dict = {}
        delta_dict.update(delta.copy())

        updated = self.db_api.metadef_tag_update(
            self.context, created_ns['namespace'],
            created_tag['id'], delta_dict)
        self.assertEqual(delta['name'], updated['name'])

    def test_tag_delete(self):
        fixture_ns = build_namespace_fixture()
        created_ns = self.db_api.metadef_namespace_create(
            self.context, fixture_ns)
        self.assertIsNotNone(created_ns['namespace'])

        tag_fixture = build_tag_fixture(namespace_id=created_ns['id'])
        created_tag = self.db_api.metadef_tag_create(
            self.context, created_ns['namespace'], tag_fixture)
        self.assertIsNotNone(created_tag, "Could not create a tag.")

        self.db_api.metadef_tag_delete(
            self.context, created_ns['namespace'], created_tag['name'])

        self.assertRaises(exception.NotFound,
                          self.db_api.metadef_tag_get,
                          self.context, created_ns['namespace'],
                          created_tag['name'])


class MetadefLoadUnloadTests:

    # if additional default schemas are added, you need to update this
    _namespace_count = 33
    _namespace_object_counts = {
        'OS::Compute::Quota': 3,
        'OS::Software::WebServers': 3,
        'OS::Software::DBMS': 12,
        'OS::Software::Runtimes': 5,
    }
    _namespace_property_counts = {
        'CIM::ProcessorAllocationSettingData': 3,
        'CIM::ResourceAllocationSettingData': 19,
        'CIM::StorageAllocationSettingData': 13,
        'CIM::VirtualSystemSettingData': 17,
        'OS::Compute::XenAPI': 1,
        'OS::Compute::InstanceData': 2,
        'OS::Compute::Libvirt': 4,
        'OS::Compute::VMwareQuotaFlavor': 2,
        'OS::Cinder::Volumetype': 1,
        'OS::Glance::Signatures': 4,
        'OS::Compute::AggregateIoOpsFilter': 1,
        'OS::Compute::RandomNumberGenerator': 3,
        'OS::Compute::VTPM': 2,
        'OS::Compute::Hypervisor': 2,
        'OS::Compute::CPUPinning': 2,
        'OS::OperatingSystem': 3,
        'OS::Compute::AggregateDiskFilter': 1,
        'OS::Compute::AggregateNumInstancesFilter': 1,
        'OS::Compute::CPUMode': 1,
        'OS::Compute::HostCapabilities': 7,
        'OS::Compute::VirtCPUTopology': 6,
        'OS::Glance::CommonImageProperties': 10,
        'OS::Compute::GuestShutdownBehavior': 1,
        'OS::Compute::VMwareFlavor': 2,
        'OS::Compute::TPM': 1,
        'OS::Compute::GuestMemoryBacking': 1,
        'OS::Compute::LibvirtImage': 16,
        'OS::Compute::VMware': 6,
        'OS::Compute::Watchdog': 1,
    }

    def test_metadef_load_unload(self):
        # load the metadata definitions
        metadata.db_load_metadefs(self.db_api.get_engine())

        # trust but verify
        expected = self._namespace_count
        namespaces = self.db_api.metadef_namespace_get_all(self.adm_context)
        actual = len(namespaces)
        self.assertEqual(
            expected,
            actual,
            f"expected {expected} namespaces but got {actual}"
        )

        for namespace in namespaces:
            expected = self._namespace_object_counts.get(
                namespace['namespace'],
                0,
            )
            objects = self.db_api.metadef_object_get_all(
                self.adm_context,
                namespace['namespace'],
            )
            actual = len(objects)
            self.assertEqual(
                expected,
                actual,
                f"expected {expected} objects in {namespace['namespace']} "
                f"namespace but got {actual}: "
                f"{', '.join(o['name'] for o in objects)}"
            )

        for namespace in namespaces:
            expected = self._namespace_property_counts.get(
                namespace['namespace'],
                0,
            )
            properties = self.db_api.metadef_property_get_all(
                self.adm_context,
                namespace['namespace'],
            )
            actual = len(properties)
            self.assertEqual(
                expected,
                actual,
                f"expected {expected} properties in {namespace['namespace']} "
                f"namespace but got {actual}: "
                f"{', '.join(p['name'] for p in properties)}"
            )

        # unload the definitions
        metadata.db_unload_metadefs(self.db_api.get_engine())


class MetadefDriverTests(MetadefNamespaceTests,
                         MetadefResourceTypeTests,
                         MetadefResourceTypeAssociationTests,
                         MetadefPropertyTests,
                         MetadefObjectTests,
                         MetadefTagTests,
                         MetadefLoadUnloadTests):
    # collection class
    pass
