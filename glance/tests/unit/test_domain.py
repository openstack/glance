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
from glance import domain
import glance.tests.utils as test_utils


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class TestImageFactory(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageFactory, self).setUp()
        self.image_factory = domain.ImageFactory()

    def test_minimal_new_image(self):
        image = self.image_factory.new_image()
        self.assertTrue(image.image_id is not None)
        self.assertTrue(image.created_at is not None)
        self.assertEqual(image.created_at, image.updated_at)
        self.assertEqual(image.status, 'queued')
        self.assertEqual(image.visibility, 'private')
        self.assertEqual(image.owner, None)
        self.assertEqual(image.name, None)
        self.assertEqual(image.size, None)
        self.assertEqual(image.min_disk, 0)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertEqual(image.disk_format, None)
        self.assertEqual(image.container_format, None)
        self.assertEqual(image.extra_properties, {})
        self.assertEqual(image.tags, set([]))

    def test_new_image(self):
        image = self.image_factory.new_image(
                image_id=UUID1, name='image-1', min_disk=256,
                owner=TENANT1)
        self.assertEqual(image.image_id, UUID1)
        self.assertTrue(image.created_at is not None)
        self.assertEqual(image.created_at, image.updated_at)
        self.assertEqual(image.status, 'queued')
        self.assertEqual(image.visibility, 'private')
        self.assertEqual(image.owner, TENANT1)
        self.assertEqual(image.name, 'image-1')
        self.assertEqual(image.size, None)
        self.assertEqual(image.min_disk, 256)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertEqual(image.disk_format, None)
        self.assertEqual(image.container_format, None)
        self.assertEqual(image.extra_properties, {})
        self.assertEqual(image.tags, set([]))

    def test_new_image_with_extra_properties_and_tags(self):
        extra_properties = {'foo': 'bar'}
        tags = ['one', 'two']
        image = self.image_factory.new_image(
                image_id=UUID1, name='image-1',
                extra_properties=extra_properties, tags=tags)

        self.assertEqual(image.image_id, UUID1)
        self.assertTrue(image.created_at is not None)
        self.assertEqual(image.created_at, image.updated_at)
        self.assertEqual(image.status, 'queued')
        self.assertEqual(image.visibility, 'private')
        self.assertEqual(image.owner, None)
        self.assertEqual(image.name, 'image-1')
        self.assertEqual(image.size, None)
        self.assertEqual(image.min_disk, 0)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertEqual(image.disk_format, None)
        self.assertEqual(image.container_format, None)
        self.assertEqual(image.extra_properties, {'foo': 'bar'})
        self.assertEqual(image.tags, set(['one', 'two']))

    def test_new_image_with_extra_properties_and_tags(self):
        extra_properties = {'foo': 'bar'}
        tags = ['one', 'two']
        image = self.image_factory.new_image(
                image_id=UUID1, name='image-1',
                extra_properties=extra_properties, tags=tags)

        self.assertEqual(image.image_id, UUID1)
        self.assertTrue(image.created_at is not None)
        self.assertEqual(image.created_at, image.updated_at)
        self.assertEqual(image.status, 'queued')
        self.assertEqual(image.visibility, 'private')
        self.assertEqual(image.owner, None)
        self.assertEqual(image.name, 'image-1')
        self.assertEqual(image.size, None)
        self.assertEqual(image.min_disk, 0)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertEqual(image.disk_format, None)
        self.assertEqual(image.container_format, None)
        self.assertEqual(image.extra_properties, {'foo': 'bar'})
        self.assertEqual(image.tags, set(['one', 'two']))

    def test_new_image_read_only_property(self):
        self.assertRaises(exception.ReadonlyProperty,
                          self.image_factory.new_image, image_id=UUID1,
                          name='image-1', size=256)

    def test_new_image_unexpected_property(self):
        self.assertRaises(TypeError,
                          self.image_factory.new_image, image_id=UUID1,
                          image_name='name-1')

    def test_new_image_reserved_property(self):
        extra_properties = {'deleted': True}
        self.assertRaises(exception.ReservedProperty,
                          self.image_factory.new_image, image_id=UUID1,
                          extra_properties=extra_properties)


class TestImage(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImage, self).setUp()
        self.image_factory = domain.ImageFactory()
        self.image = self.image_factory.new_image(
                container_format='bear', disk_format='rawr')

    def test_visibility_enumerated(self):
        self.image.visibility = 'public'
        self.image.visibility = 'private'
        self.assertRaises(ValueError, setattr,
                          self.image, 'visibility', 'ellison')

    def test_tags_always_a_set(self):
        self.image.tags = ['a', 'b', 'c']
        self.assertEqual(self.image.tags, set(['a', 'b', 'c']))

    def test_delete_protected_image(self):
        self.image.protected = True
        self.assertRaises(exception.ProtectedImageDelete, self.image.delete)

    def test_status_saving(self):
        self.image.status = 'saving'
        self.assertEqual(self.image.status, 'saving')

    def test_status_saving_without_disk_format(self):
        self.image.disk_format = None
        self.assertRaises(ValueError, setattr,
                          self.image, 'status', 'saving')

    def test_status_saving_without_container_format(self):
        self.image.container_format = None
        self.assertRaises(ValueError, setattr,
                          self.image, 'status', 'saving')

    def test_status_active_without_disk_format(self):
        self.image.disk_format = None
        self.assertRaises(ValueError, setattr,
                          self.image, 'status', 'active')

    def test_status_active_without_container_format(self):
        self.image.container_format = None
        self.assertRaises(ValueError, setattr,
                          self.image, 'status', 'active')


class TestImageMember(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageMember, self).setUp()
        self.image_member_factory = domain.ImageMemberFactory()
        self.image_factory = domain.ImageFactory()
        self.image = self.image_factory.new_image()
        self.image_member = self.image_member_factory\
                                .new_image_member(image=self.image,
                                                  member_id=TENANT1)

    def test_status_enumerated(self):
        self.image_member.status = 'pending'
        self.image_member.status = 'accepted'
        self.image_member.status = 'rejected'
        self.assertRaises(ValueError, setattr,
                          self.image_member, 'status', 'ellison')


class TestImageMemberFactory(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageMemberFactory, self).setUp()
        self.image_member_factory = domain.ImageMemberFactory()
        self.image_factory = domain.ImageFactory()

    def test_minimal_new_image_member(self):
        member_id = 'fake-member-id'
        image = self.image_factory.new_image(
                image_id=UUID1, name='image-1', min_disk=256,
                owner=TENANT1)
        image_member = self.image_member_factory.new_image_member(image,
                                                                  member_id)
        self.assertEqual(image_member.image_id, image.image_id)
        self.assertTrue(image_member.created_at is not None)
        self.assertEqual(image_member.created_at, image_member.updated_at)
        self.assertEqual(image_member.status, 'pending')
        self.assertTrue(image_member.member_id is not None)
