# Copyright 2012 OpenStack Foundation.
# Copyright 2014 Intel Corporation
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

from oslo_utils import encodeutils

from glance.common import exception
import glance.context
import glance.db
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'

NAMESPACE1 = 'namespace1'
NAMESPACE2 = 'namespace2'
NAMESPACE3 = 'namespace3'
NAMESPACE4 = 'namespace4'

PROPERTY1 = 'Property1'
PROPERTY2 = 'Property2'
PROPERTY3 = 'Property3'

OBJECT1 = 'Object1'
OBJECT2 = 'Object2'
OBJECT3 = 'Object3'

TAG1 = 'Tag1'
TAG2 = 'Tag2'
TAG3 = 'Tag3'
TAG4 = 'Tag4'
TAG5 = 'Tag5'

RESOURCE_TYPE1 = 'ResourceType1'
RESOURCE_TYPE2 = 'ResourceType2'
RESOURCE_TYPE3 = 'ResourceType3'


def _db_namespace_fixture(**kwargs):
    namespace = {
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': True,
        'protected': False,
        'owner': None
    }
    namespace.update(kwargs)
    return namespace


def _db_property_fixture(name, **kwargs):
    property = {
        'name': name,
        'json_schema': {"type": "string", "title": "title"},
    }
    property.update(kwargs)
    return property


def _db_object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'json_schema': {},
        'required': '[]',
    }
    obj.update(kwargs)
    return obj


def _db_tag_fixture(name, **kwargs):
    obj = {
        'name': name
    }
    obj.update(kwargs)
    return obj


def _db_tags_fixture(names=None):
    tags = []
    if names:
        tag_name_list = names
    else:
        tag_name_list = [TAG1, TAG2, TAG3]

    for tag_name in tag_name_list:
        tags.append(_db_tag_fixture(tag_name))
    return tags


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


class TestMetadefRepo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestMetadefRepo, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.context = glance.context.RequestContext(user=USER1,
                                                     tenant=TENANT1)
        self.namespace_repo = glance.db.MetadefNamespaceRepo(self.context,
                                                             self.db)
        self.property_repo = glance.db.MetadefPropertyRepo(self.context,
                                                           self.db)
        self.object_repo = glance.db.MetadefObjectRepo(self.context,
                                                       self.db)
        self.tag_repo = glance.db.MetadefTagRepo(self.context,
                                                 self.db)
        self.resource_type_repo = glance.db.MetadefResourceTypeRepo(
            self.context, self.db)
        self.namespace_factory = glance.domain.MetadefNamespaceFactory()
        self.property_factory = glance.domain.MetadefPropertyFactory()
        self.object_factory = glance.domain.MetadefObjectFactory()
        self.tag_factory = glance.domain.MetadefTagFactory()
        self.resource_type_factory = glance.domain.MetadefResourceTypeFactory()
        self._create_namespaces()
        self._create_properties()
        self._create_objects()
        self._create_tags()
        self._create_resource_types()

    def _create_namespaces(self):
        self.namespaces = [
            _db_namespace_fixture(namespace=NAMESPACE1,
                                  display_name='1',
                                  description='desc1',
                                  visibility='private',
                                  protected=True,
                                  owner=TENANT1),
            _db_namespace_fixture(namespace=NAMESPACE2,
                                  display_name='2',
                                  description='desc2',
                                  visibility='public',
                                  protected=False,
                                  owner=TENANT1),
            _db_namespace_fixture(namespace=NAMESPACE3,
                                  display_name='3',
                                  description='desc3',
                                  visibility='private',
                                  protected=True,
                                  owner=TENANT3),
            _db_namespace_fixture(namespace=NAMESPACE4,
                                  display_name='4',
                                  description='desc4',
                                  visibility='public',
                                  protected=True,
                                  owner=TENANT3)
        ]
        [self.db.metadef_namespace_create(None, namespace)
         for namespace in self.namespaces]

    def _create_properties(self):
        self.properties = [
            _db_property_fixture(name=PROPERTY1),
            _db_property_fixture(name=PROPERTY2),
            _db_property_fixture(name=PROPERTY3)
        ]
        [self.db.metadef_property_create(self.context, NAMESPACE1, property)
         for property in self.properties]
        [self.db.metadef_property_create(self.context, NAMESPACE4, property)
         for property in self.properties]

    def _create_objects(self):
        self.objects = [
            _db_object_fixture(name=OBJECT1,
                               description='desc1'),
            _db_object_fixture(name=OBJECT2,
                               description='desc2'),
            _db_object_fixture(name=OBJECT3,
                               description='desc3'),
        ]
        [self.db.metadef_object_create(self.context, NAMESPACE1, object)
         for object in self.objects]
        [self.db.metadef_object_create(self.context, NAMESPACE4, object)
         for object in self.objects]

    def _create_tags(self):
        self.tags = [
            _db_tag_fixture(name=TAG1),
            _db_tag_fixture(name=TAG2),
            _db_tag_fixture(name=TAG3),
        ]
        [self.db.metadef_tag_create(self.context, NAMESPACE1, tag)
         for tag in self.tags]
        [self.db.metadef_tag_create(self.context, NAMESPACE4, tag)
         for tag in self.tags]

    def _create_resource_types(self):
        self.resource_types = [
            _db_resource_type_fixture(name=RESOURCE_TYPE1,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE2,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE3,
                                      protected=True),
        ]
        [self.db.metadef_resource_type_create(self.context, resource_type)
         for resource_type in self.resource_types]

    def test_get_namespace(self):
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.assertEqual(NAMESPACE1, namespace.namespace)
        self.assertEqual('desc1', namespace.description)
        self.assertEqual('1', namespace.display_name)
        self.assertEqual(TENANT1, namespace.owner)
        self.assertTrue(namespace.protected)
        self.assertEqual('private', namespace.visibility)

    def test_get_namespace_not_found(self):
        fake_namespace = "fake_namespace"
        exc = self.assertRaises(exception.NotFound,
                                self.namespace_repo.get,
                                fake_namespace)
        self.assertIn(fake_namespace, encodeutils.exception_to_unicode(exc))

    def test_get_namespace_forbidden(self):
        self.assertRaises(exception.NotFound,
                          self.namespace_repo.get,
                          NAMESPACE3)

    def test_list_namespace(self):
        namespaces = self.namespace_repo.list()
        namespace_names = set([n.namespace for n in namespaces])
        self.assertEqual(set([NAMESPACE1, NAMESPACE2, NAMESPACE4]),
                         namespace_names)

    def test_list_private_namespaces(self):
        filters = {'visibility': 'private'}
        namespaces = self.namespace_repo.list(filters=filters)
        namespace_names = set([n.namespace for n in namespaces])
        self.assertEqual(set([NAMESPACE1]), namespace_names)

    def test_add_namespace(self):
        # NOTE(pawel-koniszewski): Change db_namespace_fixture to
        # namespace_factory when namespace primary key in DB
        # will be changed from Integer to UUID
        namespace = _db_namespace_fixture(namespace='added_namespace',
                                          display_name='fake',
                                          description='fake_desc',
                                          visibility='public',
                                          protected=True,
                                          owner=TENANT1)
        self.assertEqual('added_namespace', namespace['namespace'])
        self.db.metadef_namespace_create(None, namespace)
        retrieved_namespace = self.namespace_repo.get(namespace['namespace'])
        self.assertEqual('added_namespace', retrieved_namespace.namespace)

    def test_save_namespace(self):
        namespace = self.namespace_repo.get(NAMESPACE1)
        namespace.display_name = 'save_name'
        namespace.description = 'save_desc'
        self.namespace_repo.save(namespace)
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.assertEqual('save_name', namespace.display_name)
        self.assertEqual('save_desc', namespace.description)

    def test_remove_namespace(self):
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.namespace_repo.remove(namespace)
        self.assertRaises(exception.NotFound, self.namespace_repo.get,
                          NAMESPACE1)

    def test_remove_namespace_not_found(self):
        fake_name = 'fake_name'
        namespace = self.namespace_repo.get(NAMESPACE1)
        namespace.namespace = fake_name
        exc = self.assertRaises(exception.NotFound, self.namespace_repo.remove,
                                namespace)
        self.assertIn(fake_name, encodeutils.exception_to_unicode(exc))

    def test_get_property(self):
        property = self.property_repo.get(NAMESPACE1, PROPERTY1)
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.assertEqual(PROPERTY1, property.name)
        self.assertEqual(namespace.namespace, property.namespace.namespace)

    def test_get_property_not_found(self):
        exc = self.assertRaises(exception.NotFound,
                                self.property_repo.get,
                                NAMESPACE2, PROPERTY1)
        self.assertIn(PROPERTY1, encodeutils.exception_to_unicode(exc))

    def test_list_property(self):
        properties = self.property_repo.list(filters={'namespace': NAMESPACE1})
        property_names = set([p.name for p in properties])
        self.assertEqual(set([PROPERTY1, PROPERTY2, PROPERTY3]),
                         property_names)

    def test_list_property_empty_result(self):
        properties = self.property_repo.list(filters={'namespace': NAMESPACE2})
        property_names = set([p.name for p in properties])
        self.assertEqual(set([]),
                         property_names)

    def test_list_property_namespace_not_found(self):
        exc = self.assertRaises(exception.NotFound, self.property_repo.list,
                                filters={'namespace': 'not-a-namespace'})
        self.assertIn('not-a-namespace', encodeutils.exception_to_unicode(exc))

    def test_add_property(self):
        # NOTE(pawel-koniszewski): Change db_property_fixture to
        # property_factory when property primary key in DB
        # will be changed from Integer to UUID
        property = _db_property_fixture(name='added_property')
        self.assertEqual('added_property', property['name'])
        self.db.metadef_property_create(self.context, NAMESPACE1, property)
        retrieved_property = self.property_repo.get(NAMESPACE1,
                                                    'added_property')
        self.assertEqual('added_property', retrieved_property.name)

    def test_add_property_namespace_forbidden(self):
        # NOTE(pawel-koniszewski): Change db_property_fixture to
        # property_factory when property primary key in DB
        # will be changed from Integer to UUID
        property = _db_property_fixture(name='added_property')
        self.assertEqual('added_property', property['name'])
        self.assertRaises(exception.Forbidden, self.db.metadef_property_create,
                          self.context, NAMESPACE3, property)

    def test_add_property_namespace_not_found(self):
        # NOTE(pawel-koniszewski): Change db_property_fixture to
        # property_factory when property primary key in DB
        # will be changed from Integer to UUID
        property = _db_property_fixture(name='added_property')
        self.assertEqual('added_property', property['name'])
        self.assertRaises(exception.NotFound, self.db.metadef_property_create,
                          self.context, 'not_a_namespace', property)

    def test_save_property(self):
        property = self.property_repo.get(NAMESPACE1, PROPERTY1)
        property.schema = '{"save": "schema"}'
        self.property_repo.save(property)
        property = self.property_repo.get(NAMESPACE1, PROPERTY1)
        self.assertEqual(PROPERTY1, property.name)
        self.assertEqual('{"save": "schema"}', property.schema)

    def test_remove_property(self):
        property = self.property_repo.get(NAMESPACE1, PROPERTY1)
        self.property_repo.remove(property)
        self.assertRaises(exception.NotFound, self.property_repo.get,
                          NAMESPACE1, PROPERTY1)

    def test_remove_property_not_found(self):
        fake_name = 'fake_name'
        property = self.property_repo.get(NAMESPACE1, PROPERTY1)
        property.name = fake_name
        self.assertRaises(exception.NotFound, self.property_repo.remove,
                          property)

    def test_get_object(self):
        object = self.object_repo.get(NAMESPACE1, OBJECT1)
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.assertEqual(OBJECT1, object.name)
        self.assertEqual('desc1', object.description)
        self.assertEqual(['[]'], object.required)
        self.assertEqual({}, object.properties)
        self.assertEqual(namespace.namespace, object.namespace.namespace)

    def test_get_object_not_found(self):
        exc = self.assertRaises(exception.NotFound, self.object_repo.get,
                                NAMESPACE2, OBJECT1)
        self.assertIn(OBJECT1, encodeutils.exception_to_unicode(exc))

    def test_list_object(self):
        objects = self.object_repo.list(filters={'namespace': NAMESPACE1})
        object_names = set([o.name for o in objects])
        self.assertEqual(set([OBJECT1, OBJECT2, OBJECT3]), object_names)

    def test_list_object_empty_result(self):
        objects = self.object_repo.list(filters={'namespace': NAMESPACE2})
        object_names = set([o.name for o in objects])
        self.assertEqual(set([]), object_names)

    def test_list_object_namespace_not_found(self):
        exc = self.assertRaises(exception.NotFound, self.object_repo.list,
                                filters={'namespace': 'not-a-namespace'})
        self.assertIn('not-a-namespace', encodeutils.exception_to_unicode(exc))

    def test_add_object(self):
        # NOTE(pawel-koniszewski): Change db_object_fixture to
        # object_factory when object primary key in DB
        # will be changed from Integer to UUID
        object = _db_object_fixture(name='added_object')
        self.assertEqual('added_object', object['name'])
        self.db.metadef_object_create(self.context, NAMESPACE1, object)
        retrieved_object = self.object_repo.get(NAMESPACE1,
                                                'added_object')
        self.assertEqual('added_object', retrieved_object.name)

    def test_add_object_namespace_forbidden(self):
        # NOTE(pawel-koniszewski): Change db_object_fixture to
        # object_factory when object primary key in DB
        # will be changed from Integer to UUID
        object = _db_object_fixture(name='added_object')
        self.assertEqual('added_object', object['name'])
        self.assertRaises(exception.Forbidden, self.db.metadef_object_create,
                          self.context, NAMESPACE3, object)

    def test_add_object_namespace_not_found(self):
        # NOTE(pawel-koniszewski): Change db_object_fixture to
        # object_factory when object primary key in DB
        # will be changed from Integer to UUID
        object = _db_object_fixture(name='added_object')
        self.assertEqual('added_object', object['name'])
        self.assertRaises(exception.NotFound, self.db.metadef_object_create,
                          self.context, 'not-a-namespace', object)

    def test_save_object(self):
        object = self.object_repo.get(NAMESPACE1, OBJECT1)
        object.required = ['save_req']
        object.description = 'save_desc'
        self.object_repo.save(object)
        object = self.object_repo.get(NAMESPACE1, OBJECT1)
        self.assertEqual(OBJECT1, object.name)
        self.assertEqual(['save_req'], object.required)
        self.assertEqual('save_desc', object.description)

    def test_remove_object(self):
        object = self.object_repo.get(NAMESPACE1, OBJECT1)
        self.object_repo.remove(object)
        self.assertRaises(exception.NotFound, self.object_repo.get,
                          NAMESPACE1, OBJECT1)

    def test_remove_object_not_found(self):
        fake_name = 'fake_name'
        object = self.object_repo.get(NAMESPACE1, OBJECT1)
        object.name = fake_name
        self.assertRaises(exception.NotFound, self.object_repo.remove,
                          object)

    def test_list_resource_type(self):
        resource_type = self.resource_type_repo.list(
            filters={'namespace': NAMESPACE1})
        self.assertEqual(0, len(resource_type))

    def test_get_tag(self):
        tag = self.tag_repo.get(NAMESPACE1, TAG1)
        namespace = self.namespace_repo.get(NAMESPACE1)
        self.assertEqual(TAG1, tag.name)
        self.assertEqual(namespace.namespace, tag.namespace.namespace)

    def test_get_tag_not_found(self):
        exc = self.assertRaises(exception.NotFound, self.tag_repo.get,
                                NAMESPACE2, TAG1)
        self.assertIn(TAG1, encodeutils.exception_to_unicode(exc))

    def test_list_tag(self):
        tags = self.tag_repo.list(filters={'namespace': NAMESPACE1})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([TAG1, TAG2, TAG3]), tag_names)

    def test_list_tag_empty_result(self):
        tags = self.tag_repo.list(filters={'namespace': NAMESPACE2})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([]), tag_names)

    def test_list_tag_namespace_not_found(self):
        exc = self.assertRaises(exception.NotFound, self.tag_repo.list,
                                filters={'namespace': 'not-a-namespace'})
        self.assertIn('not-a-namespace', encodeutils.exception_to_unicode(exc))

    def test_add_tag(self):
        # NOTE(pawel-koniszewski): Change db_tag_fixture to
        # tag_factory when tag primary key in DB
        # will be changed from Integer to UUID
        tag = _db_tag_fixture(name='added_tag')
        self.assertEqual('added_tag', tag['name'])
        self.db.metadef_tag_create(self.context, NAMESPACE1, tag)
        retrieved_tag = self.tag_repo.get(NAMESPACE1, 'added_tag')
        self.assertEqual('added_tag', retrieved_tag.name)

    def test_add_tags(self):
        tags = self.tag_repo.list(filters={'namespace': NAMESPACE1})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([TAG1, TAG2, TAG3]), tag_names)

        tags = _db_tags_fixture([TAG3, TAG4, TAG5])
        self.db.metadef_tag_create_tags(self.context, NAMESPACE1, tags)

        tags = self.tag_repo.list(filters={'namespace': NAMESPACE1})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([TAG3, TAG4, TAG5]), tag_names)

    def test_add_duplicate_tags_with_pre_existing_tags(self):
        tags = self.tag_repo.list(filters={'namespace': NAMESPACE1})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([TAG1, TAG2, TAG3]), tag_names)

        tags = _db_tags_fixture([TAG5, TAG4, TAG5])
        self.assertRaises(exception.Duplicate,
                          self.db.metadef_tag_create_tags,
                          self.context, NAMESPACE1, tags)

        tags = self.tag_repo.list(filters={'namespace': NAMESPACE1})
        tag_names = set([t.name for t in tags])
        self.assertEqual(set([TAG1, TAG2, TAG3]), tag_names)

    def test_add_tag_namespace_forbidden(self):
        # NOTE(pawel-koniszewski): Change db_tag_fixture to
        # tag_factory when tag primary key in DB
        # will be changed from Integer to UUID
        tag = _db_tag_fixture(name='added_tag')
        self.assertEqual('added_tag', tag['name'])
        self.assertRaises(exception.Forbidden, self.db.metadef_tag_create,
                          self.context, NAMESPACE3, tag)

    def test_add_tag_namespace_not_found(self):
        # NOTE(pawel-koniszewski): Change db_tag_fixture to
        # tag_factory when tag primary key in DB
        # will be changed from Integer to UUID
        tag = _db_tag_fixture(name='added_tag')
        self.assertEqual('added_tag', tag['name'])
        self.assertRaises(exception.NotFound, self.db.metadef_tag_create,
                          self.context, 'not-a-namespace', tag)

    def test_save_tag(self):
        tag = self.tag_repo.get(NAMESPACE1, TAG1)
        self.tag_repo.save(tag)
        tag = self.tag_repo.get(NAMESPACE1, TAG1)
        self.assertEqual(TAG1, tag.name)

    def test_remove_tag(self):
        tag = self.tag_repo.get(NAMESPACE1, TAG1)
        self.tag_repo.remove(tag)
        self.assertRaises(exception.NotFound, self.tag_repo.get,
                          NAMESPACE1, TAG1)

    def test_remove_tag_not_found(self):
        fake_name = 'fake_name'
        tag = self.tag_repo.get(NAMESPACE1, TAG1)
        tag.name = fake_name
        self.assertRaises(exception.NotFound, self.tag_repo.remove, tag)
