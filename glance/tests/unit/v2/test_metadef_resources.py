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

import datetime

import webob

from glance.api.v2 import metadef_namespaces as namespaces
from glance.api.v2 import metadef_objects as objects
from glance.api.v2 import metadef_properties as properties
from glance.api.v2 import metadef_resource_types as resource_types
import glance.api.v2.model.metadef_namespace
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils

DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
ISOTIME = '2012-05-16T15:27:36Z'

NAMESPACE1 = 'Namespace1'
NAMESPACE2 = 'Namespace2'
NAMESPACE3 = 'Namespace3'
NAMESPACE4 = 'Namespace4'
NAMESPACE5 = 'Namespace5'
NAMESPACE6 = 'Namespace6'

PROPERTY1 = 'Property1'
PROPERTY2 = 'Property2'
PROPERTY3 = 'Property3'
PROPERTY4 = 'Property4'

OBJECT1 = 'Object1'
OBJECT2 = 'Object2'
OBJECT3 = 'Object3'

RESOURCE_TYPE1 = 'ResourceType1'
RESOURCE_TYPE2 = 'ResourceType2'
RESOURCE_TYPE3 = 'ResourceType3'
RESOURCE_TYPE4 = 'ResourceType4'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

PREFIX1 = 'pref'


def _db_namespace_fixture(namespace, **kwargs):
    obj = {
        'namespace': namespace,
        'display_name': None,
        'description': None,
        'visibility': 'public',
        'protected': False,
        'owner': None,
    }
    obj.update(kwargs)
    return obj


def _db_property_fixture(name, **kwargs):
    obj = {
        'name': name,
        'json_schema': {"type": "string", "title": "title"},
    }
    obj.update(kwargs)
    return obj


def _db_object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'json_schema': {},
        'required': '[]',
    }
    obj.update(kwargs)
    return obj


def _db_resource_type_fixture(name, **kwargs):
    obj = {
        'name': name,
        'protected': False,
    }
    obj.update(kwargs)
    return obj


def _db_namespace_resource_type_fixture(name, **kwargs):
    obj = {
        'name': name,
        'properties_target': None,
        'prefix': None,
    }
    obj.update(kwargs)
    return obj


class TestMetadefsControllers(base.IsolatedUnitTest):

    def setUp(self):
        super(TestMetadefsControllers, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self._create_namespaces()
        self._create_properties()
        self._create_objects()
        self._create_resource_types()
        self._create_namespaces_resource_types()
        self.namespace_controller = namespaces.NamespaceController(self.db,
                                                                   self.policy)
        self.property_controller = \
            properties.NamespacePropertiesController(self.db, self.policy)
        self.object_controller = objects.MetadefObjectsController(self.db,
                                                                  self.policy)
        self.rt_controller = resource_types.ResourceTypeController(self.db,
                                                                   self.policy)

    def _create_namespaces(self):
        self.db.reset()
        req = unit_test_utils.get_fake_request()
        self.namespaces = [
            _db_namespace_fixture(NAMESPACE1, owner=TENANT1,
                                  visibility='private', protected=True),
            _db_namespace_fixture(NAMESPACE2, owner=TENANT2,
                                  visibility='private'),
            _db_namespace_fixture(NAMESPACE3, owner=TENANT3),
            _db_namespace_fixture(NAMESPACE5, owner=TENANT4),
            _db_namespace_fixture(NAMESPACE6, owner=TENANT4),
        ]
        [self.db.metadef_namespace_create(req.context, namespace)
         for namespace in self.namespaces]

    def _create_properties(self):
        req = unit_test_utils.get_fake_request()
        self.properties = [
            (NAMESPACE3, _db_property_fixture(PROPERTY1)),
            (NAMESPACE3, _db_property_fixture(PROPERTY2)),
            (NAMESPACE1, _db_property_fixture(PROPERTY1)),
            (NAMESPACE6, _db_property_fixture(PROPERTY4)),
        ]
        [self.db.metadef_property_create(req.context, namespace, property)
         for namespace, property in self.properties]

    def _create_objects(self):
        req = unit_test_utils.get_fake_request()
        self.objects = [
            (NAMESPACE3, _db_object_fixture(OBJECT1)),
            (NAMESPACE3, _db_object_fixture(OBJECT2)),
            (NAMESPACE1, _db_object_fixture(OBJECT1)),
        ]
        [self.db.metadef_object_create(req.context, namespace, object)
         for namespace, object in self.objects]

    def _create_resource_types(self):
        req = unit_test_utils.get_fake_request()
        self.resource_types = [
            _db_resource_type_fixture(RESOURCE_TYPE1),
            _db_resource_type_fixture(RESOURCE_TYPE2),
            _db_resource_type_fixture(RESOURCE_TYPE4),
        ]
        [self.db.metadef_resource_type_create(req.context, resource_type)
         for resource_type in self.resource_types]

    def _create_namespaces_resource_types(self):
        req = unit_test_utils.get_fake_request(is_admin=True)
        self.ns_resource_types = [
            (NAMESPACE1, _db_namespace_resource_type_fixture(RESOURCE_TYPE1)),
            (NAMESPACE3, _db_namespace_resource_type_fixture(RESOURCE_TYPE1)),
            (NAMESPACE2, _db_namespace_resource_type_fixture(RESOURCE_TYPE1)),
            (NAMESPACE2, _db_namespace_resource_type_fixture(RESOURCE_TYPE2)),
            (NAMESPACE6, _db_namespace_resource_type_fixture(RESOURCE_TYPE4,
                                                             prefix=PREFIX1)),
        ]
        [self.db.metadef_resource_type_association_create(req.context,
                                                          namespace,
                                                          ns_resource_type)
         for namespace, ns_resource_type in self.ns_resource_types]

    def test_namespace_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.index(request)
        output = output.to_dict()
        self.assertEqual(4, len(output['namespaces']))
        actual = set([namespace.namespace for
                      namespace in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE3, NAMESPACE5, NAMESPACE6])
        self.assertEqual(actual, expected)

    def test_namespace_index_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.namespace_controller.index(request)
        output = output.to_dict()
        self.assertEqual(5, len(output['namespaces']))
        actual = set([namespace.namespace for
                      namespace in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE2, NAMESPACE3, NAMESPACE5,
                        NAMESPACE6])
        self.assertEqual(actual, expected)

    def test_namespace_index_visibility_public(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        filters = {'visibility': 'public'}
        output = self.namespace_controller.index(request, filters=filters)
        output = output.to_dict()
        self.assertEqual(3, len(output['namespaces']))
        actual = set([namespace.namespace for namespace
                      in output['namespaces']])
        expected = set([NAMESPACE3, NAMESPACE5, NAMESPACE6])
        self.assertEqual(actual, expected)

    def test_namespace_index_resource_type(self):
        request = unit_test_utils.get_fake_request()
        filters = {'resource_types': [RESOURCE_TYPE1]}
        output = self.namespace_controller.index(request, filters=filters)
        output = output.to_dict()
        self.assertEqual(2, len(output['namespaces']))
        actual = set([namespace.namespace for namespace
                      in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE3])
        self.assertEqual(actual, expected)

    def test_namespace_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.show(request, NAMESPACE1)
        output = output.to_dict()
        self.assertEqual(output['namespace'], NAMESPACE1)
        self.assertEqual(output['owner'], TENANT1)
        self.assertTrue(output['protected'])
        self.assertEqual(output['visibility'], 'private')

    def test_namespace_show_with_related_resources(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.show(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(output['namespace'], NAMESPACE3)
        self.assertEqual(output['owner'], TENANT3)
        self.assertFalse(output['protected'])
        self.assertEqual(output['visibility'], 'public')

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(actual, expected)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(actual, expected)

        self.assertEqual(1, len(output['resource_type_associations']))
        actual = set([rt.name for rt in output['resource_type_associations']])
        expected = set([RESOURCE_TYPE1])
        self.assertEqual(actual, expected)

    def test_namespace_show_with_property_prefix(self):
        request = unit_test_utils.get_fake_request()
        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE3)

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT3
        object.required = []

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        object.properties = {'prop1': property}
        object = self.object_controller.create(request, object, NAMESPACE3)

        filters = {'resource_type': RESOURCE_TYPE2}
        output = self.namespace_controller.show(request, NAMESPACE3, filters)
        output = output.to_dict()

        [self.assertTrue(property_name.startswith(rt.prefix)) for
         property_name in output['properties'].keys()]

        for object in output['objects']:
            [self.assertTrue(property_name.startswith(rt.prefix)) for
             property_name in object.properties.keys()]

    def test_namespace_show_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, 'FakeName')

    def test_namespace_show_non_visible(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete, request,
                          'FakeName')

    def test_namespace_delete_non_visible(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete, request,
                          NAMESPACE2)

    def test_namespace_delete_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_protected(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete, request,
                          NAMESPACE1)

    def test_namespace_delete_protected_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete, request,
                          NAMESPACE1)

    def test_namespace_delete_with_contents(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.namespace_controller.delete(request, NAMESPACE3)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE3)
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          OBJECT1)

    def test_namespace_create(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE4
        namespace = self.namespace_controller.create(request, namespace)
        self.assertEqual(namespace.namespace, NAMESPACE4)

        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(namespace.namespace, NAMESPACE4)

    def test_namespace_create_different_owner(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE4
        namespace.owner = TENANT4
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.create, request, namespace)

    def test_namespace_create_different_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE4
        namespace.owner = TENANT4
        namespace = self.namespace_controller.create(request, namespace)
        self.assertEqual(namespace.namespace, NAMESPACE4)

        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(namespace.namespace, NAMESPACE4)

    def test_namespace_create_with_related_resources(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE4

        prop1 = glance.api.v2.model.metadef_property_type.PropertyType()
        prop1.type = 'string'
        prop1.title = 'title'
        prop2 = glance.api.v2.model.metadef_property_type.PropertyType()
        prop2.type = 'string'
        prop2.title = 'title'
        namespace.properties = {PROPERTY1: prop1, PROPERTY2: prop2}

        object1 = glance.api.v2.model.metadef_object.MetadefObject()
        object1.name = OBJECT1
        object1.required = []
        object1.properties = {}
        object2 = glance.api.v2.model.metadef_object.MetadefObject()
        object2.name = OBJECT2
        object2.required = []
        object2.properties = {}
        namespace.objects = [object1, object2]

        output = self.namespace_controller.create(request, namespace)
        self.assertEqual(namespace.namespace, NAMESPACE4)
        output = output.to_dict()

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(actual, expected)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(actual, expected)

        output = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(namespace.namespace, NAMESPACE4)
        output = output.to_dict()

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(actual, expected)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(actual, expected)

    def test_namespace_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE1

        self.assertRaises(webob.exc.HTTPConflict,
                          self.namespace_controller.create, request, namespace)

    def test_namespace_update(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)

        namespace.protected = False
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE1)
        self.assertFalse(namespace.protected)

        namespace = self.namespace_controller.show(request, NAMESPACE1)
        self.assertFalse(namespace.protected)

    def test_namespace_update_non_existing(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE4
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE4)

    def test_namespace_update_non_visible(self):
        request = unit_test_utils.get_fake_request()

        namespace = glance.api.v2.model.metadef_namespace.Namespace()
        namespace.namespace = NAMESPACE2
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE2)

    def test_namespace_update_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        namespace = self.namespace_controller.show(request, NAMESPACE2)

        namespace.protected = False
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE2)
        self.assertFalse(namespace.protected)

        namespace = self.namespace_controller.show(request, NAMESPACE2)
        self.assertFalse(namespace.protected)

    def test_namespace_update_name(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)

        namespace.namespace = NAMESPACE4
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE1)
        self.assertEqual(namespace.namespace, NAMESPACE4)

        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(namespace.namespace, NAMESPACE4)

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE1)

    def test_namespace_update_name_conflict(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)
        namespace.namespace = NAMESPACE2
        self.assertRaises(webob.exc.HTTPConflict,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE1)

    def test_property_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.property_controller.index(request, NAMESPACE3)
        self.assertEqual(2, len(output.properties))
        actual = set([property for property in output.properties])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(actual, expected)

    def test_property_index_empty(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        output = self.property_controller.index(request, NAMESPACE2)
        self.assertEqual(0, len(output.properties))

    def test_property_index_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.index, request, NAMESPACE4)

    def test_property_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.property_controller.show(request, NAMESPACE3, PROPERTY1)
        self.assertEqual(output.name, PROPERTY1)

    def test_property_show_specific_resource_type(self):
        request = unit_test_utils.get_fake_request()
        output = self.property_controller.show(
            request, NAMESPACE6, ''.join([PREFIX1, PROPERTY4]),
            filters={'resource_type': RESOURCE_TYPE4})
        self.assertEqual(output.name, PROPERTY4)

    def test_property_show_prefix_mismatch(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE6,
                          PROPERTY4, filters={'resource_type': RESOURCE_TYPE4})

    def test_property_show_non_existing_resource_type(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE2,
                          PROPERTY1, filters={'resource_type': 'test'})

    def test_property_show_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE2,
                          PROPERTY1)

    def test_property_show_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE1,
                          PROPERTY1)

    def test_property_show_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)
        output = self.property_controller.show(request, NAMESPACE1, PROPERTY1)
        self.assertEqual(output.name, PROPERTY1)

    def test_property_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.property_controller.delete(request, NAMESPACE3, PROPERTY1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.delete, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.property_controller.delete(request, NAMESPACE3, PROPERTY1)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE5,
                          PROPERTY2)

    def test_property_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE4,
                          PROPERTY1)

    def test_property_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE1,
                          PROPERTY1)

    def test_property_delete_admin_protected(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.delete, request, NAMESPACE1,
                          PROPERTY1)

    def test_property_create(self):
        request = unit_test_utils.get_fake_request()

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.create(request, NAMESPACE1,
                                                   property)
        self.assertEqual(property.name, PROPERTY2)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

        property = self.property_controller.show(request, NAMESPACE1,
                                                 PROPERTY2)
        self.assertEqual(property.name, PROPERTY2)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

    def test_property_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPConflict,
                          self.property_controller.create, request, NAMESPACE1,
                          property)

    def test_property_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.create, request, NAMESPACE1,
                          property)

    def test_property_create_non_visible_namespace_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.create(request, NAMESPACE1,
                                                   property)
        self.assertEqual(property.name, PROPERTY2)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

        property = self.property_controller.show(request, NAMESPACE1,
                                                 PROPERTY2)
        self.assertEqual(property.name, PROPERTY2)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

    def test_property_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.create, request, NAMESPACE4,
                          property)

    def test_property_update(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = PROPERTY1
        property.type = 'string123'
        property.title = 'title123'
        property = self.property_controller.update(request, NAMESPACE3,
                                                   PROPERTY1, property)
        self.assertEqual(property.name, PROPERTY1)
        self.assertEqual(property.type, 'string123')
        self.assertEqual(property.title, 'title123')

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        self.assertEqual(property.name, PROPERTY1)
        self.assertEqual(property.type, 'string123')
        self.assertEqual(property.title, 'title123')

    def test_property_update_name(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = PROPERTY3
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.update(request, NAMESPACE3,
                                                   PROPERTY1, property)
        self.assertEqual(property.name, PROPERTY3)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY2)
        self.assertEqual(property.name, PROPERTY2)
        self.assertEqual(property.type, 'string')
        self.assertEqual(property.title, 'title')

    def test_property_update_conflict(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        self.assertRaises(webob.exc.HTTPConflict,
                          self.property_controller.update, request, NAMESPACE3,
                          PROPERTY1, property)

    def test_property_update_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.update, request, NAMESPACE5,
                          PROPERTY1, property)

    def test_property_update_namespace_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = glance.api.v2.model.metadef_property_type.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.update, request, NAMESPACE4,
                          PROPERTY1, property)

    def test_object_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.object_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(actual, expected)

    def test_object_index_empty(self):
        request = unit_test_utils.get_fake_request()
        output = self.object_controller.index(request, NAMESPACE5)
        output = output.to_dict()
        self.assertEqual(0, len(output['objects']))

    def test_object_index_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.index,
                          request, NAMESPACE4)

    def test_object_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        self.assertEqual(output.name, OBJECT1)

    def test_object_show_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE5, OBJECT1)

    def test_object_show_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE1, OBJECT1)

    def test_object_show_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        output = self.object_controller.show(request, NAMESPACE1, OBJECT1)
        self.assertEqual(output.name, OBJECT1)

    def test_object_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.object_controller.delete(request, NAMESPACE3, OBJECT1)
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)

    def test_object_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.delete, request, NAMESPACE3,
                          OBJECT1)

    def test_object_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.object_controller.delete(request, NAMESPACE3, OBJECT1)
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)

    def test_object_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE5,
                          OBJECT1)

    def test_object_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE4,
                          OBJECT1)

    def test_object_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE1,
                          OBJECT1)

    def test_object_delete_admin_protected(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.delete, request, NAMESPACE1,
                          OBJECT1)

    def test_object_create(self):
        request = unit_test_utils.get_fake_request()

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT2
        object.required = []
        object.properties = {}
        object = self.object_controller.create(request, object, NAMESPACE1)
        self.assertEqual(object.name, OBJECT2)
        self.assertEqual(object.required, [])
        self.assertEqual(object.properties, {})

        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(object.name, OBJECT2)
        self.assertEqual(object.required, [])
        self.assertEqual(object.properties, {})

    def test_object_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPConflict,
                          self.object_controller.create, request, object,
                          NAMESPACE1)

    def test_object_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = PROPERTY1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.create, request, object,
                          NAMESPACE4)

    def test_object_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.create, request, object,
                          NAMESPACE1)

    def test_object_create_non_visible_namespace_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT2
        object.required = []
        object.properties = {}
        object = self.object_controller.create(request, object, NAMESPACE1)
        self.assertEqual(object.name, OBJECT2)
        self.assertEqual(object.required, [])
        self.assertEqual(object.properties, {})

        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(object.name, OBJECT2)
        self.assertEqual(object.required, [])
        self.assertEqual(object.properties, {})

    def test_object_update(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        object.name = OBJECT1
        object.description = 'description'
        object = self.object_controller.update(request, object, NAMESPACE3,
                                               OBJECT1)
        self.assertEqual(object.name, OBJECT1)
        self.assertEqual(object.description, 'description')

        property = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        self.assertEqual(property.name, OBJECT1)
        self.assertEqual(object.description, 'description')

    def test_object_update_name(self):
        request = unit_test_utils.get_fake_request()

        object = self.object_controller.show(request, NAMESPACE1, OBJECT1)
        object.name = OBJECT2
        object = self.object_controller.update(request, object, NAMESPACE1,
                                               OBJECT1)
        self.assertEqual(object.name, OBJECT2)

        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(object.name, OBJECT2)

    def test_object_update_conflict(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        object.name = OBJECT2
        self.assertRaises(webob.exc.HTTPConflict,
                          self.object_controller.update, request, object,
                          NAMESPACE3, OBJECT1)

    def test_object_update_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.update, request, object,
                          NAMESPACE5, OBJECT1)

    def test_object_update_namespace_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = glance.api.v2.model.metadef_object.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.update, request, object,
                          NAMESPACE4, OBJECT1)

    def test_resource_type_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.rt_controller.index(request)

        self.assertEqual(3, len(output.resource_types))
        actual = set([type.name for type in
                      output.resource_types])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2, RESOURCE_TYPE4])
        self.assertEqual(actual, expected)

    def test_resource_type_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.rt_controller.show(request, NAMESPACE3)

        self.assertEqual(1, len(output.resource_type_associations))
        actual = set([rt.name for rt in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1])
        self.assertEqual(actual, expected)

    def test_resource_type_show_empty(self):
        request = unit_test_utils.get_fake_request()
        output = self.rt_controller.show(request, NAMESPACE5)

        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_show_non_visible(self):
        request = unit_test_utils.get_fake_request()

        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.show,
                          request, NAMESPACE2)

    def test_resource_type_show_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        output = self.rt_controller.show(request, NAMESPACE2)
        self.assertEqual(2, len(output.resource_type_associations))
        actual = set([rt.name for rt in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2])
        self.assertEqual(actual, expected)

    def test_resource_type_show_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.show,
                          request, NAMESPACE4)

    def test_resource_type_association_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.rt_controller.delete(request, NAMESPACE3, RESOURCE_TYPE1)

        output = self.rt_controller.show(request, NAMESPACE3)
        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_association_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.delete,
                          request, NAMESPACE3, RESOURCE_TYPE1)

    def test_resource_type_association_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.rt_controller.delete(request, NAMESPACE3, RESOURCE_TYPE1)

        output = self.rt_controller.show(request, NAMESPACE3)
        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_association_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE2)

    def test_resource_type_association_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE4, RESOURCE_TYPE1)

    def test_resource_type_association_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE1)

    def test_resource_type_association_delete_protected_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE1)

    def test_resource_type_association_create(self):
        request = unit_test_utils.get_fake_request()

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE1)
        self.assertEqual(rt.name, RESOURCE_TYPE2)
        self.assertEqual(rt.prefix, 'pref')

        output = self.rt_controller.show(request, NAMESPACE1)
        self.assertEqual(2, len(output.resource_type_associations))
        actual = set([x.name for x in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2])
        self.assertEqual(actual, expected)

    def test_resource_type_association_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE1
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPConflict, self.rt_controller.create,
                          request, rt, NAMESPACE1)

    def test_resource_type_association_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE1
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.create,
                          request, rt, NAMESPACE4)

    def test_resource_type_association_create_non_existing_resource_type(self):
        request = unit_test_utils.get_fake_request()

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE3
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.create,
                          request, rt, NAMESPACE1)

    def test_resource_type_association_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.create,
                          request, rt, NAMESPACE1)

    def test_resource_type_association_create_non_visible_namesp_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        rt = glance.api.v2.model.metadef_resource_type.\
            ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE1)
        self.assertEqual(rt.name, RESOURCE_TYPE2)
        self.assertEqual(rt.prefix, 'pref')

        output = self.rt_controller.show(request, NAMESPACE1)
        self.assertEqual(2, len(output.resource_type_associations))
        actual = set([x.name for x in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2])
        self.assertEqual(actual, expected)
