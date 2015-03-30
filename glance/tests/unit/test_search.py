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

import datetime

import mock

from oslo_utils import timeutils

from glance.search.plugins import images as images_plugin
from glance.search.plugins import metadefs as metadefs_plugin
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
DATE1 = timeutils.isotime(DATETIME)

# General
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

# Images
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

CHECKSUM = '93264c3edf5972c9f1cb309543d38a5c'

# Metadefinitions
NAMESPACE1 = 'namespace1'
NAMESPACE2 = 'namespace2'

PROPERTY1 = 'Property1'
PROPERTY2 = 'Property2'
PROPERTY3 = 'Property3'

OBJECT1 = 'Object1'
OBJECT2 = 'Object2'
OBJECT3 = 'Object3'

RESOURCE_TYPE1 = 'ResourceType1'
RESOURCE_TYPE2 = 'ResourceType2'
RESOURCE_TYPE3 = 'ResourceType3'

TAG1 = 'Tag1'
TAG2 = 'Tag2'
TAG3 = 'Tag3'


class DictObj(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)


def _image_fixture(image_id, **kwargs):
    image_members = kwargs.pop('members', [])
    extra_properties = kwargs.pop('extra_properties', {})

    obj = {
        'id': image_id,
        'name': None,
        'is_public': False,
        'properties': {},
        'checksum': None,
        'owner': None,
        'status': 'queued',
        'tags': [],
        'size': None,
        'virtual_size': None,
        'locations': [],
        'protected': False,
        'disk_format': None,
        'container_format': None,
        'deleted': False,
        'min_ram': None,
        'min_disk': None,
        'created_at': DATETIME,
        'updated_at': DATETIME,
    }
    obj.update(kwargs)
    image = DictObj(**obj)
    image.tags = set(image.tags)
    image.properties = [DictObj(name=k, value=v)
                        for k, v in extra_properties.items()]
    image.members = [DictObj(**m) for m in image_members]
    return image


def _db_namespace_fixture(**kwargs):
    obj = {
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': True,
        'protected': False,
        'owner': None
    }
    obj.update(kwargs)
    return DictObj(**obj)


def _db_property_fixture(name, **kwargs):
    obj = {
        'name': name,
        'json_schema': {"type": "string", "title": "title"},
    }
    obj.update(kwargs)
    return DictObj(**obj)


def _db_object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'json_schema': {},
        'required': '[]',
    }
    obj.update(kwargs)
    return DictObj(**obj)


def _db_resource_type_fixture(name, **kwargs):
    obj = {
        'name': name,
        'protected': False,
    }
    obj.update(kwargs)
    return DictObj(**obj)


def _db_namespace_resource_type_fixture(name, prefix, **kwargs):
    obj = {
        'properties_target': None,
        'prefix': prefix,
        'name': name,
    }
    obj.update(kwargs)
    return obj


def _db_tag_fixture(name, **kwargs):
    obj = {
        'name': name,
    }
    obj.update(**kwargs)
    return DictObj(**obj)


class TestImageLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageLoaderPlugin, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.db.reset()

        self._create_images()

        self.plugin = images_plugin.ImageIndex()

    def _create_images(self):
        self.simple_image = _image_fixture(
            UUID1, owner=TENANT1, checksum=CHECKSUM, name='simple', size=256,
            is_public=True, status='active'
        )
        self.tagged_image = _image_fixture(
            UUID2, owner=TENANT1, checksum=CHECKSUM, name='tagged', size=512,
            is_public=True, status='active', tags=['ping', 'pong'],
        )
        self.complex_image = _image_fixture(
            UUID3, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            is_public=True, status='active',
            extra_properties={'mysql_version': '5.6', 'hypervisor': 'lxc'}
        )
        self.members_image = _image_fixture(
            UUID3, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            is_public=True, status='active',
            members=[
                {'member': TENANT1, 'deleted': False, 'status': 'accepted'},
                {'member': TENANT2, 'deleted': False, 'status': 'accepted'},
                {'member': TENANT3, 'deleted': True, 'status': 'accepted'},
                {'member': TENANT4, 'deleted': False, 'status': 'pending'},
            ]
        )

        self.images = [self.simple_image, self.tagged_image,
                       self.complex_image, self.members_image]

    def test_index_name(self):
        self.assertEqual('glance', self.plugin.get_index_name())

    def test_document_type(self):
        self.assertEqual('image', self.plugin.get_document_type())

    def test_image_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': set([]),
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.simple_image)
        self.assertEqual(expected, serialized)

    def test_image_with_tags_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'tagged',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 512,
            'status': 'active',
            'tags': set(['ping', 'pong']),
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.tagged_image)
        self.assertEqual(expected, serialized)

    def test_image_with_properties_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'hypervisor': 'lxc',
            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'mysql_version': '5.6',
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': set([]),
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.complex_image)
        self.assertEqual(expected, serialized)

    def test_image_with_members_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
            'members': ['6838eb7b-6ded-434a-882c-b344c77fe8df',
                        '2c014f32-55eb-467d-8fcb-4bd706012f81'],
            'min_disk': None,
            'min_ram': None,
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': set([]),
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.members_image)
        self.assertEqual(expected, serialized)

    def test_setup_data(self):
        with mock.patch.object(self.plugin, 'get_objects',
                               return_value=self.images) as mock_get:
            with mock.patch.object(self.plugin, 'save_documents') as mock_save:
                self.plugin.setup_data()

                mock_get.assert_called_once_with()
                mock_save.assert_called_once_with([
                    {
                        'status': 'active',
                        'tags': set([]),
                        'container_format': None,
                        'min_ram': None,
                        'visibility': 'public',
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'members': [],
                        'min_disk': None,
                        'virtual_size': None,
                        'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
                        'size': 256,
                        'name': 'simple',
                        'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                        'disk_format': None,
                        'protected': False,
                        'created_at': DATE1,
                        'updated_at': DATE1
                    },
                    {
                        'status': 'active',
                        'tags': set(['pong', 'ping']),
                        'container_format': None,
                        'min_ram': None,
                        'visibility': 'public',
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'members': [],
                        'min_disk': None,
                        'virtual_size': None,
                        'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
                        'size': 512,
                        'name': 'tagged',
                        'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                        'disk_format': None,
                        'protected': False,
                        'created_at': DATE1,
                        'updated_at': DATE1
                    },
                    {
                        'status': 'active',
                        'tags': set([]),
                        'container_format': None,
                        'min_ram': None,
                        'visibility': 'public',
                        'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
                        'members': [],
                        'min_disk': None,
                        'virtual_size': None,
                        'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                        'size': 256,
                        'name': 'complex',
                        'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                        'mysql_version': '5.6',
                        'disk_format': None,
                        'protected': False,
                        'hypervisor': 'lxc',
                        'created_at': DATE1,
                        'updated_at': DATE1
                    },
                    {
                        'status': 'active',
                        'tags': set([]),
                        'container_format': None,
                        'min_ram': None,
                        'visibility': 'public',
                        'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
                        'members': ['6838eb7b-6ded-434a-882c-b344c77fe8df',
                                    '2c014f32-55eb-467d-8fcb-4bd706012f81'],
                        'min_disk': None,
                        'virtual_size': None,
                        'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                        'size': 256,
                        'name': 'complex',
                        'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                        'disk_format': None,
                        'protected': False,
                        'created_at': DATE1,
                        'updated_at': DATE1
                    }
                ])


class TestMetadefLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestMetadefLoaderPlugin, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.db.reset()

        self._create_resource_types()
        self._create_namespaces()
        self._create_namespace_resource_types()
        self._create_properties()
        self._create_tags()
        self._create_objects()

        self.plugin = metadefs_plugin.MetadefIndex()

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
        ]

    def _create_properties(self):
        self.properties = [
            _db_property_fixture(name=PROPERTY1),
            _db_property_fixture(name=PROPERTY2),
            _db_property_fixture(name=PROPERTY3)
        ]

        self.namespaces[0].properties = [self.properties[0]]
        self.namespaces[1].properties = self.properties[1:]

    def _create_objects(self):
        self.objects = [
            _db_object_fixture(name=OBJECT1,
                               description='desc1',
                               json_schema={'property1': {
                                   'type': 'string',
                                   'default': 'value1',
                                   'enum': ['value1', 'value2']
                               }}),
            _db_object_fixture(name=OBJECT2,
                               description='desc2'),
            _db_object_fixture(name=OBJECT3,
                               description='desc3'),
        ]

        self.namespaces[0].objects = [self.objects[0]]
        self.namespaces[1].objects = self.objects[1:]

    def _create_resource_types(self):
        self.resource_types = [
            _db_resource_type_fixture(name=RESOURCE_TYPE1,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE2,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE3,
                                      protected=True),
        ]

    def _create_namespace_resource_types(self):
        self.namespace_resource_types = [
            _db_namespace_resource_type_fixture(
                prefix='p1',
                name=self.resource_types[0].name),
            _db_namespace_resource_type_fixture(
                prefix='p2',
                name=self.resource_types[1].name),
            _db_namespace_resource_type_fixture(
                prefix='p2',
                name=self.resource_types[2].name),
        ]
        self.namespaces[0].resource_types = self.namespace_resource_types[:1]
        self.namespaces[1].resource_types = self.namespace_resource_types[1:]

    def _create_tags(self):
        self.tags = [
            _db_resource_type_fixture(name=TAG1),
            _db_resource_type_fixture(name=TAG2),
            _db_resource_type_fixture(name=TAG3),
        ]
        self.namespaces[0].tags = self.tags[:1]
        self.namespaces[1].tags = self.tags[1:]

    def test_index_name(self):
        self.assertEqual('glance', self.plugin.get_index_name())

    def test_document_type(self):
        self.assertEqual('metadef', self.plugin.get_document_type())

    def test_namespace_serialize(self):
        metadef_namespace = self.namespaces[0]
        expected = {
            'namespace': 'namespace1',
            'display_name': '1',
            'description': 'desc1',
            'visibility': 'private',
            'protected': True,
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df'
        }
        serialized = self.plugin.serialize_namespace(metadef_namespace)
        self.assertEqual(expected, serialized)

    def test_object_serialize(self):
        metadef_object = self.objects[0]
        expected = {
            'name': 'Object1',
            'description': 'desc1',
            'properties': [{
                'default': 'value1',
                'enum': ['value1', 'value2'],
                'property': 'property1',
                'type': 'string'
            }]
        }
        serialized = self.plugin.serialize_object(metadef_object)
        self.assertEqual(expected, serialized)

    def test_property_serialize(self):
        metadef_property = self.properties[0]
        expected = {
            'property': 'Property1',
            'type': 'string',
            'title': 'title',
        }
        serialized = self.plugin.serialize_property(
            metadef_property.name, metadef_property.json_schema)
        self.assertEqual(expected, serialized)

    def test_complex_serialize(self):
        metadef_namespace = self.namespaces[0]
        expected = {
            'namespace': 'namespace1',
            'display_name': '1',
            'description': 'desc1',
            'visibility': 'private',
            'protected': True,
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'objects': [{
                'description': 'desc1',
                'name': 'Object1',
                'properties': [{
                    'default': 'value1',
                    'enum': ['value1', 'value2'],
                    'property': 'property1',
                    'type': 'string'
                }]
            }],
            'resource_types': [{
                'prefix': 'p1',
                'name': 'ResourceType1',
                'properties_target': None
            }],
            'properties': [{
                'property': 'Property1',
                'title': 'title',
                'type': 'string'
            }],
            'tags': [{'name': 'Tag1'}],
        }
        serialized = self.plugin.serialize(metadef_namespace)
        self.assertEqual(expected, serialized)

    def test_setup_data(self):
        with mock.patch.object(self.plugin, 'get_objects',
                               return_value=self.namespaces) as mock_get:
            with mock.patch.object(self.plugin, 'save_documents') as mock_save:
                self.plugin.setup_data()

                mock_get.assert_called_once_with()
                mock_save.assert_called_once_with([
                    {
                        'display_name': '1',
                        'description': 'desc1',
                        'objects': [
                            {
                                'name': 'Object1',
                                'description': 'desc1',
                                'properties': [{
                                    'default': 'value1',
                                    'property': 'property1',
                                    'enum': ['value1', 'value2'],
                                    'type': 'string'
                                }],
                            }
                        ],
                        'namespace': 'namespace1',
                        'visibility': 'private',
                        'protected': True,
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [{
                            'property': 'Property1',
                            'type': 'string',
                            'title': 'title'
                        }],
                        'resource_types': [{
                            'prefix': 'p1',
                            'name': 'ResourceType1',
                            'properties_target': None
                        }],
                        'tags': [{'name': 'Tag1'}],
                    },
                    {
                        'display_name': '2',
                        'description': 'desc2',
                        'objects': [
                            {
                                'properties': [],
                                'name': 'Object2',
                                'description': 'desc2'
                            },
                            {
                                'properties': [],
                                'name': 'Object3',
                                'description': 'desc3'
                            }
                        ],
                        'namespace': 'namespace2',
                        'visibility': 'public',
                        'protected': False,
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [
                            {
                                'property': 'Property2',
                                'type': 'string',
                                'title': 'title'
                            },
                            {
                                'property': 'Property3',
                                'type': 'string',
                                'title': 'title'
                            }
                        ],
                        'resource_types': [
                            {
                                'name': 'ResourceType2',
                                'prefix': 'p2',
                                'properties_target': None,
                            },
                            {
                                'name': 'ResourceType3',
                                'prefix': 'p2',
                                'properties_target': None,
                            }
                        ],
                        'tags': [
                            {'name': 'Tag2'},
                            {'name': 'Tag3'},
                        ],
                    }
                ])
