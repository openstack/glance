# Copyright 2012 OpenStack Foundation.
# Copyright 2013 IBM Corp.
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
import uuid

import mock
from oslo.config import cfg

from glance.common import exception
from glance import domain
from glance.openstack.common import timeutils
import glance.tests.unit.utils as unittest_utils
import glance.tests.utils as test_utils


CONF = cfg.CONF


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
        self.assertIsNone(image.owner)
        self.assertIsNone(image.name)
        self.assertIsNone(image.size)
        self.assertEqual(image.min_disk, 0)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertIsNone(image.disk_format)
        self.assertIsNone(image.container_format)
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
        self.assertIsNone(image.size)
        self.assertEqual(image.min_disk, 256)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertIsNone(image.disk_format)
        self.assertIsNone(image.container_format)
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
        self.assertIsNone(image.owner)
        self.assertEqual(image.name, 'image-1')
        self.assertIsNone(image.size)
        self.assertEqual(image.min_disk, 0)
        self.assertEqual(image.min_ram, 0)
        self.assertEqual(image.protected, False)
        self.assertIsNone(image.disk_format)
        self.assertIsNone(image.container_format)
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

    def test_extra_properties(self):
        self.image.extra_properties = {'foo': 'bar'}
        self.assertEqual(self.image.extra_properties, {'foo': 'bar'})

    def test_extra_properties_assign(self):
        self.image.extra_properties['foo'] = 'bar'
        self.assertEqual(self.image.extra_properties, {'foo': 'bar'})

    def test_delete_extra_properties(self):
        self.image.extra_properties = {'foo': 'bar'}
        self.assertEqual(self.image.extra_properties, {'foo': 'bar'})
        del self.image.extra_properties['foo']
        self.assertEqual(self.image.extra_properties, {})

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

    def test_delayed_delete(self):
        self.config(delayed_delete=True)
        self.image.status = 'active'
        self.image.locations = [{'url': 'http://foo.bar/not.exists',
                                 'metadata': {}}]
        self.assertEqual(self.image.status, 'active')
        self.image.delete()
        self.assertEqual(self.image.status, 'pending_delete')


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


class TestExtraProperties(test_utils.BaseTestCase):

    def test_getitem(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        self.assertEqual(extra_properties['foo'], 'bar')
        self.assertEqual(extra_properties['snitch'], 'golden')

    def test_getitem_with_no_items(self):
        extra_properties = domain.ExtraProperties()
        self.assertRaises(KeyError, extra_properties.__getitem__, 'foo')

    def test_setitem(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        extra_properties['foo'] = 'baz'
        self.assertEqual(extra_properties['foo'], 'baz')

    def test_delitem(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        del extra_properties['foo']
        self.assertRaises(KeyError, extra_properties.__getitem__, 'foo')
        self.assertEqual(extra_properties['snitch'], 'golden')

    def test_len_with_zero_items(self):
        extra_properties = domain.ExtraProperties()
        self.assertEqual(len(extra_properties), 0)

    def test_len_with_non_zero_items(self):
        extra_properties = domain.ExtraProperties()
        extra_properties['foo'] = 'bar'
        extra_properties['snitch'] = 'golden'
        self.assertEqual(len(extra_properties), 2)

    def test_eq_with_a_dict(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        ref_extra_properties = {'foo': 'bar', 'snitch': 'golden'}
        self.assertEqual(extra_properties, ref_extra_properties)

    def test_eq_with_an_object_of_ExtraProperties(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        ref_extra_properties = domain.ExtraProperties()
        ref_extra_properties['snitch'] = 'golden'
        ref_extra_properties['foo'] = 'bar'
        self.assertEqual(extra_properties, ref_extra_properties)

    def test_eq_with_uneqal_dict(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        ref_extra_properties = {'boo': 'far', 'gnitch': 'solden'}
        self.assertFalse(extra_properties.__eq__(ref_extra_properties))

    def test_eq_with_unequal_ExtraProperties_object(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        ref_extra_properties = domain.ExtraProperties()
        ref_extra_properties['gnitch'] = 'solden'
        ref_extra_properties['boo'] = 'far'
        self.assertFalse(extra_properties.__eq__(ref_extra_properties))

    def test_eq_with_incompatible_object(self):
        a_dict = {'foo': 'bar', 'snitch': 'golden'}
        extra_properties = domain.ExtraProperties(a_dict)
        random_list = ['foo', 'bar']
        self.assertFalse(extra_properties.__eq__(random_list))


class TestTaskFactory(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTaskFactory, self).setUp()
        self.task_factory = domain.TaskFactory()

    def test_new_task(self):
        task_type = 'import'
        owner = TENANT1
        task = self.task_factory.new_task(task_type, owner)
        self.assertTrue(task.task_id is not None)
        self.assertTrue(task.created_at is not None)
        self.assertEqual(task.created_at, task.updated_at)
        self.assertEqual(task.status, 'pending')
        self.assertEqual(task.owner, TENANT1)

    def test_new_task_invalid_type(self):
        task_type = 'blah'
        owner = TENANT1
        self.assertRaises(
            exception.InvalidTaskType,
            self.task_factory.new_task,
            task_type,
            owner,
        )

    def test_new_task_details(self):
        task_id = 'fake_task_id'
        task_input = '{"import_from": "fake"}'
        result = '{"result": "success"}'
        message = 'fake message'
        task_details = self.task_factory.new_task_details(task_id,
                                                          task_input,
                                                          message,
                                                          result)
        self.assertEqual(task_details.task_id, task_id)
        self.assertEqual(task_details.input, task_input)
        self.assertEqual(task_details.result, result)
        self.assertEqual(task_details.message, message)


class TestTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTask, self).setUp()
        self.task_factory = domain.TaskFactory()
        task_type = 'import'
        owner = TENANT1
        task_ttl = CONF.task.task_time_to_live
        self.gateway = unittest_utils.FakeGateway()
        self.task = self.task_factory.new_task(task_type,
                                               owner,
                                               task_time_to_live=task_ttl)

    def test_task_invalid_status(self):
        task_id = str(uuid.uuid4())
        status = 'blah'
        self.assertRaises(
            exception.InvalidTaskStatus,
            domain.Task,
            task_id,
            task_type='import',
            status=status,
            owner=None,
            expires_at=None,
            created_at=timeutils.utcnow(),
            updated_at=timeutils.utcnow()
        )

    def test_validate_status_transition_from_pending(self):
        self.task.begin_processing()
        self.assertEqual(self.task.status, 'processing')

    def test_validate_status_transition_from_processing_to_success(self):
        self.task.begin_processing()
        self.task.succeed('')
        self.assertEqual(self.task.status, 'success')

    def test_validate_status_transition_from_processing_to_failure(self):
        self.task.begin_processing()
        self.task.fail('')
        self.assertEqual(self.task.status, 'failure')

    def test_invalid_status_transitions_from_pending(self):
        #test do not allow transition from pending to success
        self.assertRaises(
            exception.InvalidTaskStatusTransition,
            self.task.succeed,
            ''
        )

    def test_invalid_status_transitions_from_success(self):
        #test do not allow transition from success to processing
        self.task.begin_processing()
        self.task.succeed('')
        self.assertRaises(
            exception.InvalidTaskStatusTransition,
            self.task.begin_processing
        )
        #test do not allow transition from success to failure
        self.assertRaises(
            exception.InvalidTaskStatusTransition,
            self.task.fail,
            ''
        )

    def test_invalid_status_transitions_from_failure(self):
        #test do not allow transition from failure to processing
        self.task.begin_processing()
        self.task.fail('')
        self.assertRaises(
            exception.InvalidTaskStatusTransition,
            self.task.begin_processing
        )
        #test do not allow transition from failure to success
        self.assertRaises(
            exception.InvalidTaskStatusTransition,
            self.task.succeed,
            ''
        )

    def test_begin_processing(self):
        self.task.begin_processing()
        self.assertEqual(self.task.status, 'processing')

    @mock.patch.object(timeutils, 'utcnow')
    def test_succeed(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime.utcnow()
        self.task.begin_processing()
        self.task.succeed('{"location": "file://home"}')
        self.assertEqual(self.task.status, 'success')
        expected = (timeutils.utcnow() +
                    datetime.timedelta(hours=CONF.task.task_time_to_live))
        self.assertEqual(
            self.task.expires_at,
            expected
        )

    @mock.patch.object(timeutils, 'utcnow')
    def test_fail(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime.utcnow()
        self.task.begin_processing()
        self.task.fail('{"message": "connection failed"}')
        self.assertEqual(self.task.status, 'failure')
        expected = (timeutils.utcnow() +
                    datetime.timedelta(hours=CONF.task.task_time_to_live))
        self.assertEqual(
            self.task.expires_at,
            expected
        )


class TestTaskDetails(test_utils.BaseTestCase):
    def setUp(self):
        super(TestTaskDetails, self).setUp()
        self.task_input = ('{"import_from": "file:///home/a.img",'
                           ' "import_from_format": "qcow2"}')

    def test_task_details_init(self):
        task_details_values = ['task_id_1',
                               self.task_input,
                               'result',
                               'None']
        task_details = domain.TaskDetails(*task_details_values)
        self.assertIsNotNone(task_details)

    def test_task_details_with_no_task_id(self):
        task_id = None
        task_details_values = [task_id,
                               self.task_input,
                               'result',
                               'None']
        self.assertRaises(exception.TaskException,
                          domain.TaskDetails,
                          *task_details_values)
