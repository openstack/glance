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
from unittest import mock

from oslo_serialization import jsonutils
import webob

from glance.api.v2 import metadef_namespaces as namespaces
from glance.api.v2 import metadef_objects as objects
from glance.api.v2 import metadef_properties as properties
from glance.api.v2 import metadef_resource_types as resource_types
from glance.api.v2 import metadef_tags as tags
import glance.gateway
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

TAG1 = 'Tag1'
TAG2 = 'Tag2'
TAG3 = 'Tag3'
TAG4 = 'Tag4'
TAG5 = 'Tag5'

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


def _db_tag_fixture(name, **kwargs):
    obj = {
        'name': name
    }
    obj.update(kwargs)
    return obj


def _db_tags_fixture(tag_names=None):
    tag_list = []
    if not tag_names:
        tag_names = [TAG1, TAG2, TAG3]

    for tag_name in tag_names:
        tag = tags.MetadefTag()
        tag.name = tag_name
        tag_list.append(tag)
    return tag_list


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
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self._create_namespaces()
        self._create_properties()
        self._create_objects()
        self._create_resource_types()
        self._create_namespaces_resource_types()
        self._create_tags()
        self.namespace_controller = namespaces.NamespaceController(
            self.db, self.policy, self.notifier)
        self.property_controller = properties.NamespacePropertiesController(
            self.db, self.policy, self.notifier)
        self.object_controller = objects.MetadefObjectsController(
            self.db, self.policy, self.notifier)
        self.rt_controller = resource_types.ResourceTypeController(
            self.db, self.policy, self.notifier)
        self.tag_controller = tags.TagsController(
            self.db, self.policy, self.notifier)
        self.deserializer = objects.RequestDeserializer()
        self.property_deserializer = properties.RequestDeserializer()

    def _create_namespaces(self):
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

    def _create_tags(self):
        req = unit_test_utils.get_fake_request()
        self.tags = [
            (NAMESPACE3, _db_tag_fixture(TAG1)),
            (NAMESPACE3, _db_tag_fixture(TAG2)),
            (NAMESPACE1, _db_tag_fixture(TAG1)),
        ]
        [self.db.metadef_tag_create(req.context, namespace, tag)
         for namespace, tag in self.tags]

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

    def assertNotificationLog(self, expected_event_type, expected_payloads):
        events = [{'type': expected_event_type,
                   'payload': payload} for payload in expected_payloads]

        self.assertNotificationsLog(events)

    def assertNotificationsLog(self, expected_events):
        output_logs = self.notifier.get_logs()
        expected_logs_count = len(expected_events)
        self.assertEqual(expected_logs_count, len(output_logs))

        for output_log, event in zip(output_logs, expected_events):
            self.assertEqual('INFO', output_log['notification_type'])
            self.assertEqual(event['type'], output_log['event_type'])
            self.assertDictContainsSubset(event['payload'],
                                          output_log['payload'])
        self.notifier.log = []

    def test_namespace_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.index(request)
        output = output.to_dict()
        self.assertEqual(4, len(output['namespaces']))
        actual = set([namespace.namespace for
                      namespace in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE3, NAMESPACE5, NAMESPACE6])
        self.assertEqual(expected, actual)

    def test_namespace_index_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.namespace_controller.index(request)
        output = output.to_dict()
        self.assertEqual(5, len(output['namespaces']))
        actual = set([namespace.namespace for
                      namespace in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE2, NAMESPACE3, NAMESPACE5,
                        NAMESPACE6])
        self.assertEqual(expected, actual)

    def test_namespace_index_visibility_public(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        filters = {'visibility': 'public'}
        output = self.namespace_controller.index(request, filters=filters)
        output = output.to_dict()
        self.assertEqual(3, len(output['namespaces']))
        actual = set([namespace.namespace for namespace
                      in output['namespaces']])
        expected = set([NAMESPACE3, NAMESPACE5, NAMESPACE6])
        self.assertEqual(expected, actual)

    def test_namespace_index_resource_type(self):
        request = unit_test_utils.get_fake_request()
        filters = {'resource_types': [RESOURCE_TYPE1]}
        output = self.namespace_controller.index(request, filters=filters)
        output = output.to_dict()
        self.assertEqual(2, len(output['namespaces']))
        actual = set([namespace.namespace for namespace
                      in output['namespaces']])
        expected = set([NAMESPACE1, NAMESPACE3])
        self.assertEqual(expected, actual)

    def test_namespace_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.show(request, NAMESPACE1)
        output = output.to_dict()
        self.assertEqual(NAMESPACE1, output['namespace'])
        self.assertEqual(TENANT1, output['owner'])
        self.assertTrue(output['protected'])
        self.assertEqual('private', output['visibility'])

    def test_namespace_show_with_related_resources(self):
        request = unit_test_utils.get_fake_request()
        output = self.namespace_controller.show(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(NAMESPACE3, output['namespace'])
        self.assertEqual(TENANT3, output['owner'])
        self.assertFalse(output['protected'])
        self.assertEqual('public', output['visibility'])

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(expected, actual)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(expected, actual)

        self.assertEqual(1, len(output['resource_type_associations']))
        actual = set([rt.name for rt in output['resource_type_associations']])
        expected = set([RESOURCE_TYPE1])
        self.assertEqual(expected, actual)

    def test_namespace_show_with_property_prefix(self):
        request = unit_test_utils.get_fake_request()
        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE3)

        object = objects.MetadefObject()
        object.name = OBJECT3
        object.required = []

        property = properties.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        object.properties = {'prop1': property}
        object = self.object_controller.create(request, object, NAMESPACE3)

        self.assertNotificationsLog([
            {
                'type': 'metadef_resource_type.create',
                'payload': {
                    'namespace': NAMESPACE3,
                    'name': RESOURCE_TYPE2,
                    'prefix': 'pref',
                    'properties_target': None,
                }
            },
            {
                'type': 'metadef_object.create',
                'payload': {
                    'name': OBJECT3,
                    'namespace': NAMESPACE3,
                    'properties': [{
                        'name': 'prop1',
                        'additionalItems': None,
                        'confidential': None,
                        'title': u'title',
                        'default': None,
                        'pattern': None,
                        'enum': None,
                        'maximum': None,
                        'minItems': None,
                        'minimum': None,
                        'maxItems': None,
                        'minLength': None,
                        'uniqueItems': None,
                        'maxLength': None,
                        'items': None,
                        'type': u'string',
                        'description': None
                    }],
                    'required': [],
                    'description': None,
                }
            }
        ])

        filters = {'resource_type': RESOURCE_TYPE2}
        output = self.namespace_controller.show(request, NAMESPACE3, filters)
        output = output.to_dict()

        [self.assertTrue(property_name.startswith(rt.prefix)) for
         property_name in output['properties'].keys()]

        for object in output['objects']:
            [self.assertTrue(property_name.startswith(rt.prefix)) for
             property_name in object.properties.keys()]

    @mock.patch('glance.api.v2.metadef_namespaces.LOG')
    def test_cleanup_namespace_success(self, mock_log):
        fake_gateway = glance.gateway.Gateway(db_api=self.db,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)
        req = unit_test_utils.get_fake_request()
        ns_factory = fake_gateway.get_metadef_namespace_factory(
            req.context)
        ns_repo = fake_gateway.get_metadef_namespace_repo(req.context)
        namespace = namespaces.Namespace()
        namespace.namespace = 'FakeNamespace'
        new_namespace = ns_factory.new_namespace(**namespace.to_dict())
        ns_repo.add(new_namespace)

        self.namespace_controller._cleanup_namespace(ns_repo, namespace, True)

        mock_log.debug.assert_called_with(
            "Cleaned up namespace %(namespace)s ",
            {'namespace': namespace.namespace})

    @mock.patch('glance.api.v2.metadef_namespaces.LOG')
    @mock.patch('glance.api.authorization.MetadefNamespaceRepoProxy.remove')
    def test_cleanup_namespace_exception(self, mock_remove, mock_log):
        mock_remove.side_effect = Exception(u'Mock remove was called')

        fake_gateway = glance.gateway.Gateway(db_api=self.db,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)
        req = unit_test_utils.get_fake_request()
        ns_factory = fake_gateway.get_metadef_namespace_factory(
            req.context)
        ns_repo = fake_gateway.get_metadef_namespace_repo(req.context)
        namespace = namespaces.Namespace()
        namespace.namespace = 'FakeNamespace'
        new_namespace = ns_factory.new_namespace(**namespace.to_dict())
        ns_repo.add(new_namespace)

        self.namespace_controller._cleanup_namespace(ns_repo, namespace, True)

        called_msg = 'Failed to delete namespace %(namespace)s.' \
                     'Exception: %(exception)s'
        called_args = {'exception': u'Mock remove was called',
                       'namespace': u'FakeNamespace'}
        mock_log.error.assert_called_with((called_msg, called_args))
        mock_remove.assert_called_once_with(mock.ANY)

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
        self.assertNotificationLog("metadef_namespace.delete",
                                   [{'namespace': NAMESPACE2}])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_notification_disabled(self):
        self.config(disabled_notifications=["metadef_namespace.delete"])
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertNotificationsLog([])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_notification_group_disabled(self):
        self.config(disabled_notifications=["metadef_namespace"])
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertNotificationsLog([])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_notification_create_disabled(self):
        self.config(disabled_notifications=["metadef_namespace.create"])
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertNotificationLog("metadef_namespace.delete",
                                   [{'namespace': NAMESPACE2}])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete, request,
                          'FakeName')
        self.assertNotificationsLog([])

    def test_namespace_delete_non_visible(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete, request,
                          NAMESPACE2)
        self.assertNotificationsLog([])

    def test_namespace_delete_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.namespace_controller.delete(request, NAMESPACE2)
        self.assertNotificationLog("metadef_namespace.delete",
                                   [{'namespace': NAMESPACE2}])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE2)

    def test_namespace_delete_protected(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete, request,
                          NAMESPACE1)
        self.assertNotificationsLog([])

    def test_namespace_delete_protected_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete, request,
                          NAMESPACE1)
        self.assertNotificationsLog([])

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

    def test_namespace_delete_properties(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.namespace_controller.delete_properties(request, NAMESPACE3)

        output = self.property_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['properties']))

        self.assertNotificationLog("metadef_namespace.delete_properties",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_delete_properties_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete_properties,
                          request,
                          NAMESPACE3)
        self.assertNotificationsLog([])

    def test_namespace_delete_properties_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.namespace_controller.delete_properties(request, NAMESPACE3)

        output = self.property_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['properties']))
        self.assertNotificationLog("metadef_namespace.delete_properties",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_non_existing_delete_properties(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete_properties,
                          request,
                          NAMESPACE4)
        self.assertNotificationsLog([])

    def test_namespace_delete_objects(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.namespace_controller.delete_objects(request, NAMESPACE3)

        output = self.object_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['objects']))
        self.assertNotificationLog("metadef_namespace.delete_objects",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_delete_objects_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete_objects,
                          request,
                          NAMESPACE3)
        self.assertNotificationsLog([])

    def test_namespace_delete_objects_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.namespace_controller.delete_objects(request, NAMESPACE3)

        output = self.object_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['objects']))

        self.assertNotificationLog("metadef_namespace.delete_objects",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_non_existing_delete_objects(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete_objects,
                          request,
                          NAMESPACE4)
        self.assertNotificationsLog([])

    def test_namespace_delete_tags(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.namespace_controller.delete_tags(request, NAMESPACE3)

        output = self.tag_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['tags']))
        self.assertNotificationLog("metadef_namespace.delete_tags",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_delete_tags_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.delete_tags,
                          request,
                          NAMESPACE3)
        self.assertNotificationsLog([])

    def test_namespace_delete_tags_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.namespace_controller.delete_tags(request, NAMESPACE3)

        output = self.tag_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(0, len(output['tags']))
        self.assertNotificationLog("metadef_namespace.delete_tags",
                                   [{'namespace': NAMESPACE3}])

    def test_namespace_non_existing_delete_tags(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.delete_tags,
                          request,
                          NAMESPACE4)
        self.assertNotificationsLog([])

    def test_namespace_create(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE4
        namespace = self.namespace_controller.create(request, namespace)
        self.assertEqual(NAMESPACE4, namespace.namespace)

        self.assertNotificationLog("metadef_namespace.create",
                                   [{'namespace': NAMESPACE4}])
        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(NAMESPACE4, namespace.namespace)

    def test_namespace_create_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = u'\U0001f693'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.namespace_controller.create, request,
                          namespace)

    def test_namespace_create_duplicate(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = 'new-namespace'
        new_ns = self.namespace_controller.create(request, namespace)
        self.assertEqual('new-namespace', new_ns.namespace)
        self.assertRaises(webob.exc.HTTPConflict,
                          self.namespace_controller.create,
                          request, namespace)

    def test_namespace_create_different_owner(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE4
        namespace.owner = TENANT4
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.namespace_controller.create, request, namespace)
        self.assertNotificationsLog([])

    def test_namespace_create_different_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE4
        namespace.owner = TENANT4
        namespace = self.namespace_controller.create(request, namespace)
        self.assertEqual(NAMESPACE4, namespace.namespace)

        self.assertNotificationLog("metadef_namespace.create",
                                   [{'namespace': NAMESPACE4}])
        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(NAMESPACE4, namespace.namespace)

    def test_namespace_create_with_related_resources(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE4

        prop1 = properties.PropertyType()
        prop1.type = 'string'
        prop1.title = 'title'
        prop2 = properties.PropertyType()
        prop2.type = 'string'
        prop2.title = 'title'
        namespace.properties = {PROPERTY1: prop1, PROPERTY2: prop2}

        object1 = objects.MetadefObject()
        object1.name = OBJECT1
        object1.required = []
        object1.properties = {}
        object2 = objects.MetadefObject()
        object2.name = OBJECT2
        object2.required = []
        object2.properties = {}
        namespace.objects = [object1, object2]

        output = self.namespace_controller.create(request, namespace)
        self.assertEqual(NAMESPACE4, namespace.namespace)
        output = output.to_dict()

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(expected, actual)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(expected, actual)

        output = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(NAMESPACE4, namespace.namespace)
        output = output.to_dict()

        self.assertEqual(2, len(output['properties']))
        actual = set([property for property in output['properties']])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(expected, actual)

        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(expected, actual)

        self.assertNotificationsLog([
            {
                'type': 'metadef_namespace.create',
                'payload': {
                    'namespace': NAMESPACE4,
                    'owner': TENANT1,
                }
            },
            {
                'type': 'metadef_object.create',
                'payload': {
                    'namespace': NAMESPACE4,
                    'name': OBJECT1,
                    'properties': [],
                }
            },
            {
                'type': 'metadef_object.create',
                'payload': {
                    'namespace': NAMESPACE4,
                    'name': OBJECT2,
                    'properties': [],
                }
            },
            {
                'type': 'metadef_property.create',
                'payload': {
                    'namespace': NAMESPACE4,
                    'type': 'string',
                    'title': 'title',
                }
            },
            {
                'type': 'metadef_property.create',
                'payload': {
                    'namespace': NAMESPACE4,
                    'type': 'string',
                    'title': 'title',
                }
            }
        ])

    def test_namespace_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE1

        self.assertRaises(webob.exc.HTTPConflict,
                          self.namespace_controller.create, request, namespace)
        self.assertNotificationsLog([])

    def test_namespace_update(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)

        namespace.protected = False
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE1)
        self.assertFalse(namespace.protected)
        self.assertNotificationLog("metadef_namespace.update", [
            {'namespace': NAMESPACE1, 'protected': False}
        ])
        namespace = self.namespace_controller.show(request, NAMESPACE1)
        self.assertFalse(namespace.protected)

    def test_namespace_update_non_existing(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE4
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE4)
        self.assertNotificationsLog([])

    def test_namespace_update_non_visible(self):
        request = unit_test_utils.get_fake_request()

        namespace = namespaces.Namespace()
        namespace.namespace = NAMESPACE2
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE2)
        self.assertNotificationsLog([])

    def test_namespace_update_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        namespace = self.namespace_controller.show(request, NAMESPACE2)

        namespace.protected = False
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE2)
        self.assertFalse(namespace.protected)
        self.assertNotificationLog("metadef_namespace.update", [
            {'namespace': NAMESPACE2, 'protected': False}
        ])
        namespace = self.namespace_controller.show(request, NAMESPACE2)
        self.assertFalse(namespace.protected)

    def test_namespace_update_name(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)

        namespace.namespace = NAMESPACE4
        namespace = self.namespace_controller.update(request, namespace,
                                                     NAMESPACE1)
        self.assertEqual(NAMESPACE4, namespace.namespace)
        self.assertNotificationLog("metadef_namespace.update", [
            {'namespace': NAMESPACE4, 'namespace_old': NAMESPACE1}
        ])
        namespace = self.namespace_controller.show(request, NAMESPACE4)
        self.assertEqual(NAMESPACE4, namespace.namespace)

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.namespace_controller.show, request, NAMESPACE1)

    def test_namespace_update_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        namespace = self.namespace_controller.show(request, NAMESPACE1)
        namespace.namespace = u'\U0001f693'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.namespace_controller.update, request,
                          namespace, NAMESPACE1)

    def test_namespace_update_name_conflict(self):
        request = unit_test_utils.get_fake_request()
        namespace = self.namespace_controller.show(request, NAMESPACE1)
        namespace.namespace = NAMESPACE2
        self.assertRaises(webob.exc.HTTPConflict,
                          self.namespace_controller.update, request, namespace,
                          NAMESPACE1)
        self.assertNotificationsLog([])

    def test_property_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.property_controller.index(request, NAMESPACE3)
        self.assertEqual(2, len(output.properties))
        actual = set([property for property in output.properties])
        expected = set([PROPERTY1, PROPERTY2])
        self.assertEqual(expected, actual)

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
        self.assertEqual(PROPERTY1, output.name)

    def test_property_show_specific_resource_type(self):
        request = unit_test_utils.get_fake_request()
        output = self.property_controller.show(
            request, NAMESPACE6, ''.join([PREFIX1, PROPERTY4]),
            filters={'resource_type': RESOURCE_TYPE4})
        self.assertEqual(PROPERTY4, output.name)

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
        self.assertEqual(PROPERTY1, output.name)

    def test_property_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.property_controller.delete(request, NAMESPACE3, PROPERTY1)
        self.assertNotificationLog("metadef_property.delete",
                                   [{'name': PROPERTY1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_disabled_notification(self):
        self.config(disabled_notifications=["metadef_property.delete"])
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.property_controller.delete(request, NAMESPACE3, PROPERTY1)
        self.assertNotificationsLog([])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.delete, request, NAMESPACE3,
                          PROPERTY1)
        self.assertNotificationsLog([])

    def test_property_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.property_controller.delete(request, NAMESPACE3, PROPERTY1)
        self.assertNotificationLog("metadef_property.delete",
                                   [{'name': PROPERTY1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.show, request, NAMESPACE3,
                          PROPERTY1)

    def test_property_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE5,
                          PROPERTY2)
        self.assertNotificationsLog([])

    def test_property_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE4,
                          PROPERTY1)
        self.assertNotificationsLog([])

    def test_property_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.delete, request, NAMESPACE1,
                          PROPERTY1)
        self.assertNotificationsLog([])

    def test_property_delete_admin_protected(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.delete, request, NAMESPACE1,
                          PROPERTY1)
        self.assertNotificationsLog([])

    def test_property_create(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.create(request, NAMESPACE1,
                                                   property)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)
        self.assertNotificationLog("metadef_property.create",
                                   [{'name': PROPERTY2,
                                    'namespace': NAMESPACE1}])
        property = self.property_controller.show(request, NAMESPACE1,
                                                 PROPERTY2)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)

    def test_property_create_overlimit_name(self):
        request = unit_test_utils.get_fake_request('/metadefs/namespaces/'
                                                   'Namespace3/'
                                                   'properties')
        request.body = jsonutils.dump_as_bytes({
            'name': 'a' * 81, 'type': 'string', 'title': 'fake'})

        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.property_deserializer.create,
                                request)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_property_create_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = u'\U0001f693'
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.property_controller.create,
                          request, NAMESPACE1, property)

    def test_property_create_with_operators(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        property.operators = ['<or>']
        property = self.property_controller.create(request, NAMESPACE1,
                                                   property)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)
        self.assertEqual(['<or>'], property.operators)

        property = self.property_controller.show(request, NAMESPACE1,
                                                 PROPERTY2)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)
        self.assertEqual(['<or>'], property.operators)

    def test_property_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPConflict,
                          self.property_controller.create, request, NAMESPACE1,
                          property)
        self.assertNotificationsLog([])

    def test_property_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        property = properties.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.property_controller.create, request, NAMESPACE1,
                          property)
        self.assertNotificationsLog([])

    def test_property_create_non_visible_namespace_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        property = properties.PropertyType()
        property.name = PROPERTY2
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.create(request, NAMESPACE1,
                                                   property)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)

        self.assertNotificationLog("metadef_property.create",
                                   [{'name': PROPERTY2,
                                    'namespace': NAMESPACE1}])
        property = self.property_controller.show(request, NAMESPACE1,
                                                 PROPERTY2)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)

    def test_property_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.create, request, NAMESPACE4,
                          property)
        self.assertNotificationsLog([])

    def test_property_create_duplicate(self):
        request = unit_test_utils.get_fake_request()

        property = properties.PropertyType()
        property.name = 'new-property'
        property.type = 'string'
        property.title = 'title'
        new_property = self.property_controller.create(request, NAMESPACE1,
                                                       property)
        self.assertEqual('new-property', new_property.name)
        self.assertRaises(webob.exc.HTTPConflict,
                          self.property_controller.create, request,
                          NAMESPACE1, property)

    def test_property_update(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = PROPERTY1
        property.type = 'string123'
        property.title = 'title123'
        property = self.property_controller.update(request, NAMESPACE3,
                                                   PROPERTY1, property)
        self.assertEqual(PROPERTY1, property.name)
        self.assertEqual('string123', property.type)
        self.assertEqual('title123', property.title)
        self.assertNotificationLog("metadef_property.update", [
            {
                'name': PROPERTY1,
                'namespace': NAMESPACE3,
                'type': 'string123',
                'title': 'title123',
            }
        ])
        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        self.assertEqual(PROPERTY1, property.name)
        self.assertEqual('string123', property.type)
        self.assertEqual('title123', property.title)

    def test_property_update_name(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = PROPERTY3
        property.type = 'string'
        property.title = 'title'
        property = self.property_controller.update(request, NAMESPACE3,
                                                   PROPERTY1, property)
        self.assertEqual(PROPERTY3, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)

        self.assertNotificationLog("metadef_property.update", [
            {
                'name': PROPERTY3,
                'name_old': PROPERTY1,
                'namespace': NAMESPACE3,
                'type': 'string',
                'title': 'title',
            }
        ])
        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY2)
        self.assertEqual(PROPERTY2, property.name)
        self.assertEqual('string', property.type)
        self.assertEqual('title', property.title)

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
        self.assertNotificationsLog([])

    def test_property_update_with_overlimit_name(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'name': 'a' * 81, 'type': 'string', 'title': 'fake'})
        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.property_deserializer.create,
                                request)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_property_update_with_4byte_character(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = self.property_controller.show(request, NAMESPACE3,
                                                 PROPERTY1)
        property.name = u'\U0001f693'
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.property_controller.update, request,
                          NAMESPACE3, PROPERTY1, property)

    def test_property_update_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = properties.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.update, request, NAMESPACE5,
                          PROPERTY1, property)
        self.assertNotificationsLog([])

    def test_property_update_namespace_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        property = properties.PropertyType()
        property.name = PROPERTY1
        property.type = 'string'
        property.title = 'title'

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.property_controller.update, request, NAMESPACE4,
                          PROPERTY1, property)
        self.assertNotificationsLog([])

    def test_object_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.object_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(2, len(output['objects']))
        actual = set([object.name for object in output['objects']])
        expected = set([OBJECT1, OBJECT2])
        self.assertEqual(expected, actual)

    def test_object_index_zero_limit(self):
        request = unit_test_utils.get_fake_request('/metadefs/namespaces/'
                                                   'Namespace3/'
                                                   'objects?limit=0')
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

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
        self.assertEqual(OBJECT1, output.name)

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
        self.assertEqual(OBJECT1, output.name)

    def test_object_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.object_controller.delete(request, NAMESPACE3, OBJECT1)
        self.assertNotificationLog("metadef_object.delete",
                                   [{'name': OBJECT1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)

    def test_object_delete_disabled_notification(self):
        self.config(disabled_notifications=["metadef_object.delete"])
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.object_controller.delete(request, NAMESPACE3, OBJECT1)
        self.assertNotificationsLog([])
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)

    def test_object_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.delete, request, NAMESPACE3,
                          OBJECT1)
        self.assertNotificationsLog([])

    def test_object_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.object_controller.delete(request, NAMESPACE3, OBJECT1)
        self.assertNotificationLog("metadef_object.delete",
                                   [{'name': OBJECT1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound, self.object_controller.show,
                          request, NAMESPACE3, OBJECT1)

    def test_object_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE5,
                          OBJECT1)
        self.assertNotificationsLog([])

    def test_object_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE4,
                          OBJECT1)
        self.assertNotificationsLog([])

    def test_object_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.delete, request, NAMESPACE1,
                          OBJECT1)
        self.assertNotificationsLog([])

    def test_object_delete_admin_protected(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.delete, request, NAMESPACE1,
                          OBJECT1)
        self.assertNotificationsLog([])

    def test_object_create(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = OBJECT2
        object.required = []
        object.properties = {}
        object = self.object_controller.create(request, object, NAMESPACE1)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertEqual({}, object.properties)
        self.assertNotificationLog("metadef_object.create",
                                   [{'name': OBJECT2,
                                     'namespace': NAMESPACE1,
                                     'properties': []}])
        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertEqual({}, object.properties)

    def test_object_create_invalid_properties(self):
        request = unit_test_utils.get_fake_request('/metadefs/namespaces/'
                                                   'Namespace3/'
                                                   'objects')
        body = {
            "name": "My Object",
            "description": "object1 description.",
            "properties": {
                "property1": {
                    "type": "integer",
                    "title": "property",
                    "description": "property description",
                    "test-key": "test-value",
                }
            }
        }
        request.body = jsonutils.dump_as_bytes(body)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create,
                          request)

    def test_object_create_overlimit_name(self):
        request = unit_test_utils.get_fake_request('/metadefs/namespaces/'
                                                   'Namespace3/'
                                                   'objects')
        request.body = jsonutils.dump_as_bytes({'name': 'a' * 81})

        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.deserializer.create,
                                request)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_object_create_duplicate(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = 'New-Object'
        object.required = []
        object.properties = {}
        new_obj = self.object_controller.create(request, object, NAMESPACE3)
        self.assertEqual('New-Object', new_obj.name)
        self.assertRaises(webob.exc.HTTPConflict,
                          self.object_controller.create, request, object,
                          NAMESPACE3)

    def test_object_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPConflict,
                          self.object_controller.create, request, object,
                          NAMESPACE1)
        self.assertNotificationsLog([])

    def test_object_create_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = u'\U0001f693'
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.object_controller.create, request,
                          object, NAMESPACE1)

    def test_object_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = PROPERTY1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.create, request, object,
                          NAMESPACE4)
        self.assertNotificationsLog([])

    def test_object_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        object = objects.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.object_controller.create, request, object,
                          NAMESPACE1)
        self.assertNotificationsLog([])

    def test_object_create_non_visible_namespace_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        object = objects.MetadefObject()
        object.name = OBJECT2
        object.required = []
        object.properties = {}
        object = self.object_controller.create(request, object, NAMESPACE1)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertEqual({}, object.properties)
        self.assertNotificationLog("metadef_object.create",
                                   [{'name': OBJECT2,
                                    'namespace': NAMESPACE1}])
        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertEqual({}, object.properties)

    def test_object_create_missing_properties(self):
        request = unit_test_utils.get_fake_request()

        object = objects.MetadefObject()
        object.name = OBJECT2
        object.required = []
        object = self.object_controller.create(request, object, NAMESPACE1)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertNotificationLog("metadef_object.create",
                                   [{'name': OBJECT2,
                                     'namespace': NAMESPACE1,
                                     'properties': []}])
        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(OBJECT2, object.name)
        self.assertEqual([], object.required)
        self.assertEqual({}, object.properties)

    def test_object_update(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        object.name = OBJECT1
        object.description = 'description'
        object = self.object_controller.update(request, object, NAMESPACE3,
                                               OBJECT1)
        self.assertEqual(OBJECT1, object.name)
        self.assertEqual('description', object.description)
        self.assertNotificationLog("metadef_object.update", [
            {
                'name': OBJECT1,
                'namespace': NAMESPACE3,
                'description': 'description',
            }
        ])
        property = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        self.assertEqual(OBJECT1, property.name)
        self.assertEqual('description', object.description)

    def test_object_update_name(self):
        request = unit_test_utils.get_fake_request()

        object = self.object_controller.show(request, NAMESPACE1, OBJECT1)
        object.name = OBJECT2
        object = self.object_controller.update(request, object, NAMESPACE1,
                                               OBJECT1)
        self.assertEqual(OBJECT2, object.name)
        self.assertNotificationLog("metadef_object.update", [
            {
                'name': OBJECT2,
                'name_old': OBJECT1,
                'namespace': NAMESPACE1,
            }
        ])
        object = self.object_controller.show(request, NAMESPACE1, OBJECT2)
        self.assertEqual(OBJECT2, object.name)

    def test_object_update_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        object = self.object_controller.show(request, NAMESPACE1, OBJECT1)
        object.name = u'\U0001f693'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.object_controller.update, request,
                          object, NAMESPACE1, OBJECT1)

    def test_object_update_with_overlimit_name(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes(
            {"properties": {}, "name": "a" * 81, "required": []})
        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.deserializer.update, request)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_object_update_conflict(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = self.object_controller.show(request, NAMESPACE3, OBJECT1)
        object.name = OBJECT2
        self.assertRaises(webob.exc.HTTPConflict,
                          self.object_controller.update, request, object,
                          NAMESPACE3, OBJECT1)
        self.assertNotificationsLog([])

    def test_object_update_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = objects.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.update, request, object,
                          NAMESPACE5, OBJECT1)
        self.assertNotificationsLog([])

    def test_object_update_namespace_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        object = objects.MetadefObject()
        object.name = OBJECT1
        object.required = []
        object.properties = {}

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.object_controller.update, request, object,
                          NAMESPACE4, OBJECT1)
        self.assertNotificationsLog([])

    def test_resource_type_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.rt_controller.index(request)

        self.assertEqual(3, len(output.resource_types))
        actual = set([rtype.name for rtype in output.resource_types])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2, RESOURCE_TYPE4])
        self.assertEqual(expected, actual)

    def test_resource_type_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.rt_controller.show(request, NAMESPACE3)

        self.assertEqual(1, len(output.resource_type_associations))
        actual = set([rt.name for rt in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1])
        self.assertEqual(expected, actual)

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
        self.assertEqual(expected, actual)

    def test_resource_type_show_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.show,
                          request, NAMESPACE4)

    def test_resource_type_association_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.rt_controller.delete(request, NAMESPACE3, RESOURCE_TYPE1)
        self.assertNotificationLog("metadef_resource_type.delete",
                                   [{'name': RESOURCE_TYPE1,
                                    'namespace': NAMESPACE3}])
        output = self.rt_controller.show(request, NAMESPACE3)
        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_association_delete_disabled_notification(self):
        self.config(disabled_notifications=["metadef_resource_type.delete"])
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.rt_controller.delete(request, NAMESPACE3, RESOURCE_TYPE1)
        self.assertNotificationsLog([])
        output = self.rt_controller.show(request, NAMESPACE3)
        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_association_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.delete,
                          request, NAMESPACE3, RESOURCE_TYPE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.rt_controller.delete(request, NAMESPACE3, RESOURCE_TYPE1)
        self.assertNotificationLog("metadef_resource_type.delete",
                                   [{'name': RESOURCE_TYPE1,
                                    'namespace': NAMESPACE3}])
        output = self.rt_controller.show(request, NAMESPACE3)
        self.assertEqual(0, len(output.resource_type_associations))

    def test_resource_type_association_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE2)
        self.assertNotificationsLog([])

    def test_resource_type_association_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE4, RESOURCE_TYPE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_delete_protected_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.delete,
                          request, NAMESPACE1, RESOURCE_TYPE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_create(self):
        request = unit_test_utils.get_fake_request()

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE1)
        self.assertEqual(RESOURCE_TYPE2, rt.name)
        self.assertEqual('pref', rt.prefix)
        self.assertNotificationLog("metadef_resource_type.create",
                                   [{'name': RESOURCE_TYPE2,
                                    'namespace': NAMESPACE1}])
        output = self.rt_controller.show(request, NAMESPACE1)
        self.assertEqual(2, len(output.resource_type_associations))
        actual = set([x.name for x in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2])
        self.assertEqual(expected, actual)

    def test_resource_type_association_create_conflict(self):
        request = unit_test_utils.get_fake_request()

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE1
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPConflict, self.rt_controller.create,
                          request, rt, NAMESPACE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE1
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.create,
                          request, rt, NAMESPACE4)
        self.assertNotificationsLog([])

    def test_resource_type_association_create_non_existing_resource_type(self):
        request = unit_test_utils.get_fake_request()

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE3
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPNotFound, self.rt_controller.create,
                          request, rt, NAMESPACE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        self.assertRaises(webob.exc.HTTPForbidden, self.rt_controller.create,
                          request, rt, NAMESPACE1)
        self.assertNotificationsLog([])

    def test_resource_type_association_create_non_visible_namesp_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        rt = resource_types.ResourceTypeAssociation()
        rt.name = RESOURCE_TYPE2
        rt.prefix = 'pref'
        rt = self.rt_controller.create(request, rt, NAMESPACE1)
        self.assertEqual(RESOURCE_TYPE2, rt.name)
        self.assertEqual('pref', rt.prefix)
        self.assertNotificationLog("metadef_resource_type.create",
                                   [{'name': RESOURCE_TYPE2,
                                    'namespace': NAMESPACE1}])
        output = self.rt_controller.show(request, NAMESPACE1)
        self.assertEqual(2, len(output.resource_type_associations))
        actual = set([x.name for x in output.resource_type_associations])
        expected = set([RESOURCE_TYPE1, RESOURCE_TYPE2])
        self.assertEqual(expected, actual)

    def test_tag_index(self):
        request = unit_test_utils.get_fake_request()
        output = self.tag_controller.index(request, NAMESPACE3)
        output = output.to_dict()
        self.assertEqual(2, len(output['tags']))
        actual = set([tag.name for tag in output['tags']])
        expected = set([TAG1, TAG2])
        self.assertEqual(expected, actual)

    def test_tag_index_empty(self):
        request = unit_test_utils.get_fake_request()
        output = self.tag_controller.index(request, NAMESPACE5)
        output = output.to_dict()
        self.assertEqual(0, len(output['tags']))

    def test_tag_index_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.index,
                          request, NAMESPACE4)

    def test_tag_show(self):
        request = unit_test_utils.get_fake_request()
        output = self.tag_controller.show(request, NAMESPACE3, TAG1)
        self.assertEqual(TAG1, output.name)

    def test_tag_show_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.show,
                          request, NAMESPACE5, TAG1)

    def test_tag_show_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.show,
                          request, NAMESPACE1, TAG1)

    def test_tag_show_non_visible_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)

        output = self.tag_controller.show(request, NAMESPACE1, TAG1)
        self.assertEqual(TAG1, output.name)

    def test_tag_delete(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.tag_controller.delete(request, NAMESPACE3, TAG1)
        self.assertNotificationLog("metadef_tag.delete",
                                   [{'name': TAG1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.show,
                          request, NAMESPACE3, TAG1)

    def test_tag_delete_disabled_notification(self):
        self.config(disabled_notifications=["metadef_tag.delete"])
        request = unit_test_utils.get_fake_request(tenant=TENANT3)
        self.tag_controller.delete(request, NAMESPACE3, TAG1)
        self.assertNotificationsLog([])
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.show,
                          request, NAMESPACE3, TAG1)

    def test_tag_delete_other_owner(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.tag_controller.delete, request, NAMESPACE3,
                          TAG1)
        self.assertNotificationsLog([])

    def test_tag_delete_other_owner_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.tag_controller.delete(request, NAMESPACE3, TAG1)
        self.assertNotificationLog("metadef_tag.delete",
                                   [{'name': TAG1,
                                    'namespace': NAMESPACE3}])
        self.assertRaises(webob.exc.HTTPNotFound, self.tag_controller.show,
                          request, NAMESPACE3, TAG1)

    def test_tag_delete_non_existing(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.delete, request, NAMESPACE5,
                          TAG1)
        self.assertNotificationsLog([])

    def test_tag_delete_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.delete, request, NAMESPACE4,
                          TAG1)
        self.assertNotificationsLog([])

    def test_tag_delete_non_visible(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.delete, request, NAMESPACE1,
                          TAG1)
        self.assertNotificationsLog([])

    def test_tag_delete_admin_protected(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.tag_controller.delete, request, NAMESPACE1,
                          TAG1)
        self.assertNotificationsLog([])

    def test_tag_create(self):
        request = unit_test_utils.get_fake_request()
        tag = self.tag_controller.create(request, NAMESPACE1, TAG2)
        self.assertEqual(TAG2, tag.name)
        self.assertNotificationLog("metadef_tag.create",
                                   [{'name': TAG2,
                                    'namespace': NAMESPACE1}])

        tag = self.tag_controller.show(request, NAMESPACE1, TAG2)
        self.assertEqual(TAG2, tag.name)

    def test_tag_create_overlimit_name(self):
        request = unit_test_utils.get_fake_request()

        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.tag_controller.create,
                                request, NAMESPACE1, 'a' * 81)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_tag_create_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.tag_controller.create,
                          request, NAMESPACE1, u'\U0001f693')

    def test_tag_create_tags(self):
        request = unit_test_utils.get_fake_request()

        metadef_tags = tags.MetadefTags()
        metadef_tags.tags = _db_tags_fixture()
        output = self.tag_controller.create_tags(
            request, metadef_tags, NAMESPACE1)
        output = output.to_dict()
        self.assertEqual(3, len(output['tags']))
        actual = set([tag.name for tag in output['tags']])
        expected = set([TAG1, TAG2, TAG3])
        self.assertEqual(expected, actual)
        self.assertNotificationLog(
            "metadef_tag.create", [
                {'name': TAG1, 'namespace': NAMESPACE1},
                {'name': TAG2, 'namespace': NAMESPACE1},
                {'name': TAG3, 'namespace': NAMESPACE1},
            ]
        )

    def test_tag_create_duplicate_tags(self):
        request = unit_test_utils.get_fake_request()

        metadef_tags = tags.MetadefTags()
        metadef_tags.tags = _db_tags_fixture([TAG4, TAG5, TAG4])
        self.assertRaises(
            webob.exc.HTTPConflict,
            self.tag_controller.create_tags,
            request, metadef_tags, NAMESPACE1)
        self.assertNotificationsLog([])

    def test_tag_create_duplicate_with_pre_existing_tags(self):
        request = unit_test_utils.get_fake_request()

        metadef_tags = tags.MetadefTags()
        metadef_tags.tags = _db_tags_fixture([TAG1, TAG2, TAG3])
        output = self.tag_controller.create_tags(
            request, metadef_tags, NAMESPACE1)
        output = output.to_dict()
        self.assertEqual(3, len(output['tags']))
        actual = set([tag.name for tag in output['tags']])
        expected = set([TAG1, TAG2, TAG3])
        self.assertEqual(expected, actual)
        self.assertNotificationLog(
            "metadef_tag.create", [
                {'name': TAG1, 'namespace': NAMESPACE1},
                {'name': TAG2, 'namespace': NAMESPACE1},
                {'name': TAG3, 'namespace': NAMESPACE1},
            ]
        )

        metadef_tags = tags.MetadefTags()
        metadef_tags.tags = _db_tags_fixture([TAG4, TAG5, TAG4])
        self.assertRaises(
            webob.exc.HTTPConflict,
            self.tag_controller.create_tags,
            request, metadef_tags, NAMESPACE1)
        self.assertNotificationsLog([])

        output = self.tag_controller.index(request, NAMESPACE1)
        output = output.to_dict()
        self.assertEqual(3, len(output['tags']))
        actual = set([tag.name for tag in output['tags']])
        expected = set([TAG1, TAG2, TAG3])
        self.assertEqual(expected, actual)

    def test_tag_create_conflict(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPConflict,
                          self.tag_controller.create, request,
                          NAMESPACE1, TAG1)
        self.assertNotificationsLog([])

    def test_tag_create_non_existing_namespace(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.create, request,
                          NAMESPACE4, TAG1)
        self.assertNotificationsLog([])

    def test_tag_create_non_visible_namespace(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.tag_controller.create, request,
                          NAMESPACE1, TAG1)
        self.assertNotificationsLog([])

    def test_tag_create_non_visible_namespace_admin(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT2,
                                                   is_admin=True)
        tag = self.tag_controller.create(request, NAMESPACE1, TAG2)
        self.assertEqual(TAG2, tag.name)
        self.assertNotificationLog("metadef_tag.create",
                                   [{'name': TAG2,
                                    'namespace': NAMESPACE1}])

        tag = self.tag_controller.show(request, NAMESPACE1, TAG2)
        self.assertEqual(TAG2, tag.name)

    def test_tag_update(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        tag = self.tag_controller.show(request, NAMESPACE3, TAG1)
        tag.name = TAG3
        tag = self.tag_controller.update(request, tag, NAMESPACE3, TAG1)
        self.assertEqual(TAG3, tag.name)
        self.assertNotificationLog("metadef_tag.update", [
            {'name': TAG3, 'namespace': NAMESPACE3}
        ])

        property = self.tag_controller.show(request, NAMESPACE3, TAG3)
        self.assertEqual(TAG3, property.name)

    def test_tag_update_name(self):
        request = unit_test_utils.get_fake_request()

        tag = self.tag_controller.show(request, NAMESPACE1, TAG1)
        tag.name = TAG2
        tag = self.tag_controller.update(request, tag, NAMESPACE1, TAG1)
        self.assertEqual(TAG2, tag.name)
        self.assertNotificationLog("metadef_tag.update", [
            {'name': TAG2, 'name_old': TAG1, 'namespace': NAMESPACE1}
        ])

        tag = self.tag_controller.show(request, NAMESPACE1, TAG2)
        self.assertEqual(TAG2, tag.name)

    def test_tag_update_with_4byte_character(self):
        request = unit_test_utils.get_fake_request()

        tag = self.tag_controller.show(request, NAMESPACE1, TAG1)
        tag.name = u'\U0001f693'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.tag_controller.update, request, tag,
                          NAMESPACE1, TAG1)

    def test_tag_update_with_name_overlimit(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes(
            {"properties": {}, "name": "a" * 81, "required": []})
        exc = self.assertRaises(webob.exc.HTTPBadRequest,
                                self.deserializer.update, request)
        self.assertIn("Failed validating 'maxLength' in "
                      "schema['properties']['name']", exc.explanation)

    def test_tag_update_conflict(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        tag = self.tag_controller.show(request, NAMESPACE3, TAG1)
        tag.name = TAG2
        self.assertRaises(webob.exc.HTTPConflict,
                          self.tag_controller.update, request, tag,
                          NAMESPACE3, TAG1)
        self.assertNotificationsLog([])

    def test_tag_update_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        tag = tags.MetadefTag()
        tag.name = TAG1

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.update, request, tag,
                          NAMESPACE5, TAG1)
        self.assertNotificationsLog([])

    def test_tag_update_namespace_non_existing(self):
        request = unit_test_utils.get_fake_request(tenant=TENANT3)

        tag = tags.MetadefTag()
        tag.name = TAG1

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.tag_controller.update, request, tag,
                          NAMESPACE4, TAG1)
        self.assertNotificationsLog([])


class TestMetadefNamespaceResponseSerializers(base.IsolatedUnitTest):

    def setUp(self):
        super(TestMetadefNamespaceResponseSerializers, self).setUp()
        self.serializer = namespaces.ResponseSerializer(schema={})
        self.response = mock.Mock()
        self.result = mock.Mock()

    def test_delete_tags(self):
        self.serializer.delete_tags(self.response, self.result)
        self.assertEqual(204, self.response.status_int)
