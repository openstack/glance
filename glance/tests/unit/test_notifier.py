# Copyright 2011 OpenStack Foundation
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
from unittest import mock

import glance_store
from oslo_config import cfg
import oslo_messaging
import webob

import glance.async_
from glance.common import exception
from glance.common import timeutils
import glance.context
from glance import notifier
import glance.tests.unit.utils as unit_test_utils
from glance.tests import utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'


class ImageStub(glance.domain.Image):
    def get_data(self, offset=0, chunk_size=None):
        return ['01234', '56789']

    def set_data(self, data, size, backend=None, set_active=True):
        for chunk in data:
            pass


class ImageRepoStub(object):
    def remove(self, *args, **kwargs):
        return 'image_from_get'

    def save(self, *args, **kwargs):
        return 'image_from_save'

    def add(self, *args, **kwargs):
        return 'image_from_add'

    def get(self, *args, **kwargs):
        return 'image_from_get'

    def list(self, *args, **kwargs):
        return ['images_from_list']


class ImageMemberRepoStub(object):
    def remove(self, *args, **kwargs):
        return 'image_member_from_remove'

    def save(self, *args, **kwargs):
        return 'image_member_from_save'

    def add(self, *args, **kwargs):
        return 'image_member_from_add'

    def get(self, *args, **kwargs):
        return 'image_member_from_get'

    def list(self, *args, **kwargs):
        return ['image_members_from_list']


class TaskStub(glance.domain.TaskStub):
    def run(self, executor):
        pass


class Task(glance.domain.Task):
    def succeed(self, result):
        pass

    def fail(self, message):
        pass


class TaskRepoStub(object):
    def remove(self, *args, **kwargs):
        return 'task_from_remove'

    def save(self, *args, **kwargs):
        return 'task_from_save'

    def add(self, *args, **kwargs):
        return 'task_from_add'

    def get_task(self, *args, **kwargs):
        return 'task_from_get'

    def list(self, *args, **kwargs):
        return ['tasks_from_list']


class TestNotifier(utils.BaseTestCase):

    @mock.patch.object(oslo_messaging, 'Notifier')
    @mock.patch.object(oslo_messaging, 'get_notification_transport')
    def _test_load_strategy(self,
                            mock_get_transport, mock_notifier,
                            url, driver):
        nfier = notifier.Notifier()
        mock_get_transport.assert_called_with(cfg.CONF)
        self.assertIsNotNone(nfier._transport)
        mock_notifier.assert_called_with(nfier._transport,
                                         publisher_id='image.localhost')
        self.assertIsNotNone(nfier._notifier)

    def test_notifier_load(self):
        self._test_load_strategy(url=None, driver=None)

    @mock.patch.object(oslo_messaging, 'set_transport_defaults')
    def test_set_defaults(self, mock_set_trans_defaults):
        notifier.set_defaults(control_exchange='foo')
        mock_set_trans_defaults.assert_called_with('foo')
        notifier.set_defaults()
        mock_set_trans_defaults.assert_called_with('glance')


class TestImageNotifications(utils.BaseTestCase):
    """Test Image Notifications work"""

    def setUp(self):
        super(TestImageNotifications, self).setUp()
        self.image = ImageStub(
            image_id=UUID1, name='image-1', status='active', size=1024,
            created_at=DATETIME, updated_at=DATETIME, owner=TENANT1,
            visibility='public', container_format='ami', virtual_size=2048,
            tags=['one', 'two'], disk_format='ami', min_ram=128,
            min_disk=10, checksum='ca425b88f047ce8ec45ee90e813ada91',
            locations=['http://127.0.0.1'])
        self.context = glance.context.RequestContext(tenant=TENANT2,
                                                     user=USER1)
        self.image_repo_stub = ImageRepoStub()
        self.notifier = unit_test_utils.FakeNotifier()
        self.image_repo_proxy = glance.notifier.ImageRepoProxy(
            self.image_repo_stub, self.context, self.notifier)
        self.image_proxy = glance.notifier.ImageProxy(
            self.image, self.context, self.notifier)

    def test_image_save_notification(self):
        self.image_repo_proxy.save(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.update', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_save_notification_disabled(self):
        self.config(disabled_notifications=["image.update"])
        self.image_repo_proxy.save(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_add_notification(self):
        self.image_repo_proxy.add(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.create', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_add_notification_disabled(self):
        self.config(disabled_notifications=["image.create"])
        self.image_repo_proxy.add(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_delete_notification(self):
        self.image_repo_proxy.remove(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.delete', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])
        self.assertTrue(output_log['payload']['deleted'])
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_delete_notification_disabled(self):
        self.config(disabled_notifications=['image.delete'])
        self.image_repo_proxy.remove(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_get(self):
        image = self.image_repo_proxy.get(UUID1)
        self.assertIsInstance(image, glance.notifier.ImageProxy)
        self.assertEqual('image_from_get', image.repo)

    def test_image_list(self):
        images = self.image_repo_proxy.list()
        self.assertIsInstance(images[0], glance.notifier.ImageProxy)
        self.assertEqual('images_from_list', images[0].repo)

    def test_image_get_data_should_call_next_image_get_data(self):
        with mock.patch.object(self.image, 'get_data') as get_data_mock:
            self.image_proxy.get_data()

            self.assertTrue(get_data_mock.called)

    def test_image_get_data_notification(self):
        self.image_proxy.size = 10
        data = ''.join(self.image_proxy.get_data())
        self.assertEqual('0123456789', data)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.send', output_log['event_type'])
        self.assertEqual(self.image.image_id,
                         output_log['payload']['image_id'])
        self.assertEqual(TENANT2, output_log['payload']['receiver_tenant_id'])
        self.assertEqual(USER1, output_log['payload']['receiver_user_id'])
        self.assertEqual(10, output_log['payload']['bytes_sent'])
        self.assertEqual(TENANT1, output_log['payload']['owner_id'])

    def test_image_get_data_notification_disabled(self):
        self.config(disabled_notifications=['image.send'])
        self.image_proxy.size = 10
        data = ''.join(self.image_proxy.get_data())
        self.assertEqual('0123456789', data)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_get_data_size_mismatch(self):
        self.image_proxy.size = 11
        list(self.image_proxy.get_data())
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.send', output_log['event_type'])
        self.assertEqual(self.image.image_id,
                         output_log['payload']['image_id'])

    def test_image_set_data_prepare_notification(self):
        insurance = {'called': False}

        def data_iterator():
            output_logs = self.notifier.get_logs()
            self.assertEqual(1, len(output_logs))
            output_log = output_logs[0]
            self.assertEqual('INFO', output_log['notification_type'])
            self.assertEqual('image.prepare', output_log['event_type'])
            self.assertEqual(self.image.image_id, output_log['payload']['id'])
            self.assertEqual(['store1', 'store2'], output_log['payload'][
                'os_glance_importing_to_stores'])
            self.assertEqual([],
                             output_log['payload']['os_glance_failed_import'])
            yield 'abcd'
            yield 'efgh'
            insurance['called'] = True

        self.image_proxy.extra_properties[
            'os_glance_importing_to_stores'] = 'store1,store2'
        self.image_proxy.extra_properties['os_glance_failed_import'] = ''
        self.image_proxy.set_data(data_iterator(), 8)
        self.assertTrue(insurance['called'])

    def test_image_set_data_prepare_notification_disabled(self):
        insurance = {'called': False}

        def data_iterator():
            output_logs = self.notifier.get_logs()
            self.assertEqual(0, len(output_logs))
            yield 'abcd'
            yield 'efgh'
            insurance['called'] = True

        self.config(disabled_notifications=['image.prepare'])
        self.image_proxy.set_data(data_iterator(), 8)
        self.assertTrue(insurance['called'])

    def test_image_set_data_upload_and_activate_notification(self):
        image = ImageStub(image_id=UUID1, name='image-1', status='queued',
                          created_at=DATETIME, updated_at=DATETIME,
                          owner=TENANT1, visibility='public')
        context = glance.context.RequestContext(tenant=TENANT2, user=USER1)
        fake_notifier = unit_test_utils.FakeNotifier()
        image_proxy = glance.notifier.ImageProxy(image, context, fake_notifier)

        def data_iterator():
            fake_notifier.log = []
            yield 'abcde'
            yield 'fghij'
            image_proxy.extra_properties[
                'os_glance_importing_to_stores'] = 'store2'

        image_proxy.extra_properties[
            'os_glance_importing_to_stores'] = 'store1,store2'
        image_proxy.extra_properties['os_glance_failed_import'] = ''
        image_proxy.set_data(data_iterator(), 10)

        output_logs = fake_notifier.get_logs()
        self.assertEqual(2, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])
        self.assertEqual(['store2'], output_log['payload'][
            'os_glance_importing_to_stores'])
        self.assertEqual([],
                         output_log['payload']['os_glance_failed_import'])

        output_log = output_logs[1]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.activate', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])

    def test_image_set_data_upload_and_not_activate_notification(self):
        insurance = {'called': False}

        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            yield 'fghij'
            self.image_proxy.extra_properties[
                'os_glance_importing_to_stores'] = 'store2'
            insurance['called'] = True

        self.image_proxy.set_data(data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertEqual(self.image.image_id, output_log['payload']['id'])
        self.assertTrue(insurance['called'])

    def test_image_set_data_upload_and_activate_notification_disabled(self):
        insurance = {'called': False}
        image = ImageStub(image_id=UUID1, name='image-1', status='queued',
                          created_at=DATETIME, updated_at=DATETIME,
                          owner=TENANT1, visibility='public')
        context = glance.context.RequestContext(tenant=TENANT2, user=USER1)
        fake_notifier = unit_test_utils.FakeNotifier()
        image_proxy = glance.notifier.ImageProxy(image, context, fake_notifier)

        def data_iterator():
            fake_notifier.log = []
            yield 'abcde'
            yield 'fghij'
            insurance['called'] = True

        self.config(disabled_notifications=['image.activate', 'image.upload'])
        image_proxy.set_data(data_iterator(), 10)
        self.assertTrue(insurance['called'])
        output_logs = fake_notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_set_data_storage_full(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise glance_store.StorageFull(message='Modern Major General')

        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.image_proxy.set_data, data_iterator(), 10)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Modern Major General', output_log['payload'])

    def test_image_set_data_value_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise ValueError('value wrong')

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('value wrong', output_log['payload'])

    def test_image_set_data_duplicate(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.Duplicate('Cant have duplicates')

        self.assertRaises(webob.exc.HTTPConflict,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Cant have duplicates', output_log['payload'])

    def test_image_set_data_storage_write_denied(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise glance_store.StorageWriteDenied(message='The Very Model')

        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('The Very Model', output_log['payload'])

    def test_image_set_data_forbidden(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.Forbidden('Not allowed')

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Not allowed', output_log['payload'])

    def test_image_set_data_not_found(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.NotFound('Not found')

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Not found', output_log['payload'])

    def test_image_set_data_HTTP_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise webob.exc.HTTPError('Http issue')

        self.assertRaises(webob.exc.HTTPError,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Http issue', output_log['payload'])

    def test_image_set_data_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.GlanceException('Failed')

        self.assertRaises(exception.GlanceException,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))

        output_log = output_logs[0]
        self.assertEqual('ERROR', output_log['notification_type'])
        self.assertEqual('image.upload', output_log['event_type'])
        self.assertIn('Failed', output_log['payload'])


class TestImageMemberNotifications(utils.BaseTestCase):
    """Test Image Member Notifications work"""

    def setUp(self):
        super(TestImageMemberNotifications, self).setUp()
        self.context = glance.context.RequestContext(tenant=TENANT2,
                                                     user=USER1)
        self.notifier = unit_test_utils.FakeNotifier()

        self.image = ImageStub(
            image_id=UUID1, name='image-1', status='active', size=1024,
            created_at=DATETIME, updated_at=DATETIME, owner=TENANT1,
            visibility='public', container_format='ami',
            tags=['one', 'two'], disk_format='ami', min_ram=128,
            min_disk=10, checksum='ca425b88f047ce8ec45ee90e813ada91',
            locations=['http://127.0.0.1'])
        self.image_member = glance.domain.ImageMembership(
            id=1, image_id=UUID1, member_id=TENANT1, created_at=DATETIME,
            updated_at=DATETIME, status='accepted')

        self.image_member_repo_stub = ImageMemberRepoStub()
        self.image_member_repo_proxy = glance.notifier.ImageMemberRepoProxy(
            self.image_member_repo_stub, self.image,
            self.context, self.notifier)
        self.image_member_proxy = glance.notifier.ImageMemberProxy(
            self.image_member, self.context, self.notifier)

    def _assert_image_member_with_notifier(self, output_log, deleted=False):
        self.assertEqual(self.image_member.member_id,
                         output_log['payload']['member_id'])
        self.assertEqual(self.image_member.image_id,
                         output_log['payload']['image_id'])
        self.assertEqual(self.image_member.status,
                         output_log['payload']['status'])
        self.assertEqual(timeutils.isotime(self.image_member.created_at),
                         output_log['payload']['created_at'])
        self.assertEqual(timeutils.isotime(self.image_member.updated_at),
                         output_log['payload']['updated_at'])

        if deleted:
            self.assertTrue(output_log['payload']['deleted'])
            self.assertIsNotNone(output_log['payload']['deleted_at'])
        else:
            self.assertFalse(output_log['payload']['deleted'])
            self.assertIsNone(output_log['payload']['deleted_at'])

    def test_image_member_add_notification(self):
        self.image_member_repo_proxy.add(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.member.create', output_log['event_type'])
        self._assert_image_member_with_notifier(output_log)

    def test_image_member_add_notification_disabled(self):
        self.config(disabled_notifications=['image.member.create'])
        self.image_member_repo_proxy.add(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_member_save_notification(self):
        self.image_member_repo_proxy.save(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.member.update', output_log['event_type'])
        self._assert_image_member_with_notifier(output_log)

    def test_image_member_save_notification_disabled(self):
        self.config(disabled_notifications=['image.member.update'])
        self.image_member_repo_proxy.save(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_member_delete_notification(self):
        self.image_member_repo_proxy.remove(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('image.member.delete', output_log['event_type'])
        self._assert_image_member_with_notifier(output_log, deleted=True)

    def test_image_member_delete_notification_disabled(self):
        self.config(disabled_notifications=['image.member.delete'])
        self.image_member_repo_proxy.remove(self.image_member_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_image_member_get(self):
        image_member = self.image_member_repo_proxy.get(TENANT1)
        self.assertIsInstance(image_member, glance.notifier.ImageMemberProxy)
        self.assertEqual('image_member_from_get', image_member.repo)

    def test_image_member_list(self):
        image_members = self.image_member_repo_proxy.list()
        self.assertIsInstance(image_members[0],
                              glance.notifier.ImageMemberProxy)
        self.assertEqual('image_members_from_list', image_members[0].repo)


class TestTaskNotifications(utils.BaseTestCase):
    """Test Task Notifications work"""

    def setUp(self):
        super(TestTaskNotifications, self).setUp()
        task_input = {"loc": "fake"}
        self.task_stub = TaskStub(
            task_id='aaa',
            task_type='import',
            status='pending',
            owner=TENANT2,
            expires_at=None,
            created_at=DATETIME,
            updated_at=DATETIME,
            image_id='fake_image_id',
            user_id='fake_user',
            request_id='fake_request_id',
        )

        self.task = Task(
            task_id='aaa',
            task_type='import',
            status='pending',
            owner=TENANT2,
            expires_at=None,
            created_at=DATETIME,
            updated_at=DATETIME,
            task_input=task_input,
            result='res',
            message='blah',
            image_id='fake_image_id',
            user_id='fake_user',
            request_id='fake_request_id',
        )
        self.context = glance.context.RequestContext(
            tenant=TENANT2,
            user=USER1
        )
        self.task_repo_stub = TaskRepoStub()
        self.notifier = unit_test_utils.FakeNotifier()
        self.task_repo_proxy = glance.notifier.TaskRepoProxy(
            self.task_repo_stub,
            self.context,
            self.notifier
        )
        self.task_proxy = glance.notifier.TaskProxy(
            self.task,
            self.context,
            self.notifier
        )
        self.task_stub_proxy = glance.notifier.TaskStubProxy(
            self.task_stub,
            self.context,
            self.notifier
        )
        self.patcher = mock.patch.object(timeutils, 'utcnow')
        mock_utcnow = self.patcher.start()
        mock_utcnow.return_value = datetime.datetime.utcnow()

    def tearDown(self):
        super(TestTaskNotifications, self).tearDown()
        self.patcher.stop()

    def test_task_create_notification(self):
        self.task_repo_proxy.add(self.task_stub_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.create', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        self.assertEqual(
            timeutils.isotime(self.task.updated_at),
            output_log['payload']['updated_at']
        )
        self.assertEqual(
            timeutils.isotime(self.task.created_at),
            output_log['payload']['created_at']
        )
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')
        # Verify newly added fields 'image_id', 'user_id' and
        # 'request_id' are not part of notification yet
        self.assertNotIn('image_id', output_log['payload'])
        self.assertNotIn('user_id', output_log['payload'])
        self.assertNotIn('request_id', output_log['payload'])

    def test_task_create_notification_disabled(self):
        self.config(disabled_notifications=['task.create'])
        self.task_repo_proxy.add(self.task_stub_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_task_delete_notification(self):
        now = timeutils.isotime()
        self.task_repo_proxy.remove(self.task_stub_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.delete', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        self.assertEqual(
            timeutils.isotime(self.task.updated_at),
            output_log['payload']['updated_at']
        )
        self.assertEqual(
            timeutils.isotime(self.task.created_at),
            output_log['payload']['created_at']
        )
        self.assertEqual(
            now,
            output_log['payload']['deleted_at']
        )
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')
        # Verify newly added fields 'image_id', 'user_id' and
        # 'request_id' are not part of notification yet
        self.assertNotIn('image_id', output_log['payload'])
        self.assertNotIn('user_id', output_log['payload'])
        self.assertNotIn('request_id', output_log['payload'])

    def test_task_delete_notification_disabled(self):
        self.config(disabled_notifications=['task.delete'])
        self.task_repo_proxy.remove(self.task_stub_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_task_run_notification(self):
        with mock.patch('glance.async_.TaskExecutor') as mock_executor:
            executor = mock_executor.return_value
            executor._run.return_value = mock.Mock()
            self.task_proxy.run(executor=mock_executor)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.run', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        self.assertNotIn(self.task.image_id, output_log['payload'])
        self.assertNotIn(self.task.user_id, output_log['payload'])
        self.assertNotIn(self.task.request_id, output_log['payload'])

    def test_task_run_notification_disabled(self):
        self.config(disabled_notifications=['task.run'])
        with mock.patch('glance.async_.TaskExecutor') as mock_executor:
            executor = mock_executor.return_value
            executor._run.return_value = mock.Mock()
            self.task_proxy.run(executor=mock_executor)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_task_processing_notification(self):
        self.task_proxy.begin_processing()
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.processing', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        # Verify newly added fields 'image_id', 'user_id' and
        # 'request_id' are not part of notification yet
        self.assertNotIn('image_id', output_log['payload'])
        self.assertNotIn('user_id', output_log['payload'])
        self.assertNotIn('request_id', output_log['payload'])

    def test_task_processing_notification_disabled(self):
        self.config(disabled_notifications=['task.processing'])
        self.task_proxy.begin_processing()
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_task_success_notification(self):
        self.task_proxy.begin_processing()
        self.task_proxy.succeed(result=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(2, len(output_logs))
        output_log = output_logs[1]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.success', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        # Verify newly added fields 'image_id', 'user_id' and
        # 'request_id' are not part of notification yet
        self.assertNotIn('image_id', output_log['payload'])
        self.assertNotIn('user_id', output_log['payload'])
        self.assertNotIn('request_id', output_log['payload'])

    def test_task_success_notification_disabled(self):
        self.config(disabled_notifications=['task.processing', 'task.success'])
        self.task_proxy.begin_processing()
        self.task_proxy.succeed(result=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))

    def test_task_failure_notification(self):
        self.task_proxy.fail(message=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.failure', output_log['event_type'])
        self.assertEqual(self.task.task_id, output_log['payload']['id'])
        # Verify newly added fields 'image_id', 'user_id' and
        # 'request_id' are not part of notification yet
        self.assertNotIn('image_id', output_log['payload'])
        self.assertNotIn('user_id', output_log['payload'])
        self.assertNotIn('request_id', output_log['payload'])

    def test_task_failure_notification_disabled(self):
        self.config(disabled_notifications=['task.failure'])
        self.task_proxy.fail(message=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(0, len(output_logs))
