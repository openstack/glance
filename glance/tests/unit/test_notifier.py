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

import mock
import webob

from glance.common import exception
import glance.context
from glance import domain
from glance import notifier
from glance.openstack.common import timeutils
import glance.tests.unit.utils as unit_test_utils
from glance.tests import utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'


class ImageStub(glance.domain.Image):
    def get_data(self):
        return ['01234', '56789']

    def set_data(self, data, size=None):
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


class TaskStub(glance.domain.Task):
    def run(self, executor):
        pass

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

    def get(self, *args, **kwargs):
        return 'task_from_get'

    def list(self, *args, **kwargs):
        return ['tasks_from_list']


class TestNotifier(utils.BaseTestCase):

    def test_load_rabbit(self):
        nfier = notifier.Notifier('rabbit')
        self.assertIsNotNone(nfier._transport)

    def test_load_qpid(self):
        nfier = notifier.Notifier('qpid')
        self.assertIsNotNone(nfier._transport)
        self.assertEqual(str(nfier._transport._driver._url),
                         'qpid:///')

    def test_notifier_strategy(self):
        self.config(notifier_strategy='qpid')
        nfier = notifier.Notifier()
        self.assertIsNotNone(nfier._transport)
        self.assertEqual(str(nfier._transport._driver._url),
                         'qpid:///')

    def test_transport_url(self):
        transport_url = "qpid://superhost:5672/"
        self.config(transport_url=transport_url)
        notify = notifier.Notifier()
        self.assertEqual(str(notify._transport._driver._url),
                         transport_url)

    def test_notification_driver_option(self):
        self.config(rpc_backend='qpid')
        self.config(notification_driver='messaging')
        self.config(notifier_strategy='rabbit')
        notify = notifier.Notifier()
        self.assertEqual(str(notify._transport._driver._url),
                         'rabbit:///')

        self.config(notifier_strategy='default')
        notify = notifier.Notifier()
        self.assertEqual(str(notify._transport._driver._url),
                         'qpid:///')


class TestImageNotifications(utils.BaseTestCase):
    """Test Image Notifications work"""

    def setUp(self):
        super(TestImageNotifications, self).setUp()
        self.image = ImageStub(
            image_id=UUID1, name='image-1', status='active', size=1024,
            created_at=DATETIME, updated_at=DATETIME, owner=TENANT1,
            visibility='public', container_format='ami',
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
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.update')
        self.assertEqual(output_log['payload']['id'], self.image.image_id)
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_add_notification(self):
        self.image_repo_proxy.add(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.create')
        self.assertEqual(output_log['payload']['id'], self.image.image_id)
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_delete_notification(self):
        self.image_repo_proxy.remove(self.image_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.delete')
        self.assertEqual(output_log['payload']['id'], self.image.image_id)
        self.assertTrue(output_log['payload']['deleted'])
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_image_get(self):
        image = self.image_repo_proxy.get(UUID1)
        self.assertIsInstance(image, glance.notifier.ImageProxy)
        self.assertEqual(image.image, 'image_from_get')

    def test_image_list(self):
        images = self.image_repo_proxy.list()
        self.assertIsInstance(images[0], glance.notifier.ImageProxy)
        self.assertEqual(images[0].image, 'images_from_list')

    def test_image_get_data_notification(self):
        self.image_proxy.size = 10
        data = ''.join(self.image_proxy.get_data())
        self.assertEqual(data, '0123456789')
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.send')
        self.assertEqual(output_log['payload']['image_id'],
                         self.image.image_id)
        self.assertEqual(output_log['payload']['receiver_tenant_id'], TENANT2)
        self.assertEqual(output_log['payload']['receiver_user_id'], USER1)
        self.assertEqual(output_log['payload']['bytes_sent'], 10)
        self.assertEqual(output_log['payload']['owner_id'], TENANT1)

    def test_image_get_data_size_mismatch(self):
        self.image_proxy.size = 11
        list(self.image_proxy.get_data())
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.send')
        self.assertEqual(output_log['payload']['image_id'],
                         self.image.image_id)

    def test_image_set_data_prepare_notification(self):
        insurance = {'called': False}

        def data_iterator():
            output_logs = self.notifier.get_logs()
            self.assertEqual(len(output_logs), 1)
            output_log = output_logs[0]
            self.assertEqual(output_log['notification_type'], 'INFO')
            self.assertEqual(output_log['event_type'], 'image.prepare')
            self.assertEqual(output_log['payload']['id'], self.image.image_id)
            yield 'abcd'
            yield 'efgh'
            insurance['called'] = True

        self.image_proxy.set_data(data_iterator(), 8)
        self.assertTrue(insurance['called'])

    def test_image_set_data_upload_and_activate_notification(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            yield 'fghij'

        self.image_proxy.set_data(data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 2)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertEqual(output_log['payload']['id'], self.image.image_id)

        output_log = output_logs[1]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'image.activate')
        self.assertEqual(output_log['payload']['id'], self.image.image_id)

    def test_image_set_data_storage_full(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.StorageFull('Modern Major General')

        self.assertRaises(webob.exc.HTTPRequestEntityTooLarge,
                          self.image_proxy.set_data, data_iterator(), 10)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Modern Major General' in output_log['payload'])

    def test_image_set_data_value_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise ValueError('value wrong')

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('value wrong' in output_log['payload'])

    def test_image_set_data_duplicate(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.Duplicate('Cant have duplicates')

        self.assertRaises(webob.exc.HTTPConflict,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Cant have duplicates' in output_log['payload'])

    def test_image_set_data_storage_write_denied(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.StorageWriteDenied('The Very Model')

        self.assertRaises(webob.exc.HTTPServiceUnavailable,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('The Very Model' in output_log['payload'])

    def test_image_set_data_forbidden(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.Forbidden('Not allowed')

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Not allowed' in output_log['payload'])

    def test_image_set_data_not_found(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.NotFound('Not found')

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Not found' in output_log['payload'])

    def test_image_set_data_HTTP_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise webob.exc.HTTPError('Http issue')

        self.assertRaises(webob.exc.HTTPError,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Http issue' in output_log['payload'])

    def test_image_set_data_error(self):
        def data_iterator():
            self.notifier.log = []
            yield 'abcde'
            raise exception.GlanceException('Failed')

        self.assertRaises(exception.GlanceException,
                          self.image_proxy.set_data, data_iterator(), 10)

        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)

        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'ERROR')
        self.assertEqual(output_log['event_type'], 'image.upload')
        self.assertTrue('Failed' in output_log['payload'])


class TestTaskNotifications(utils.BaseTestCase):
    """Test Task Notifications work"""

    def setUp(self):
        super(TestTaskNotifications, self).setUp()
        self.task = TaskStub(
            task_id='aaa',
            task_type='import',
            status='pending',
            owner=TENANT2,
            expires_at=None,
            created_at=DATETIME,
            updated_at=DATETIME
        )
        self.task_details = domain.TaskDetails(task_id=self.task.task_id,
                                               task_input={"loc": "fake"},
                                               result='',
                                               message='')
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
        self.task_details_proxy = notifier.TaskDetailsProxy(self.task_details,
                                                            self.context,
                                                            self.notifier)
        self.patcher = mock.patch.object(timeutils, 'utcnow')
        mock_utcnow = self.patcher.start()
        mock_utcnow.return_value = datetime.datetime.utcnow()

    def tearDown(self):
        super(TestTaskNotifications, self).tearDown()
        self.patcher.stop()

    def test_task_create_notification(self):
        self.task_repo_proxy.add(self.task_proxy, self.task_details_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.create')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)
        self.assertEqual(
            output_log['payload']['updated_at'],
            timeutils.isotime(self.task.updated_at)
        )
        self.assertEqual(
            output_log['payload']['created_at'],
            timeutils.isotime(self.task.created_at)
        )
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_task_delete_notification(self):
        now = timeutils.isotime()
        self.task_repo_proxy.remove(self.task_proxy)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.delete')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)
        self.assertEqual(
            output_log['payload']['updated_at'],
            timeutils.isotime(self.task.updated_at)
        )
        self.assertEqual(
            output_log['payload']['created_at'],
            timeutils.isotime(self.task.created_at)
        )
        self.assertEqual(
            output_log['payload']['deleted_at'],
            now
        )
        if 'location' in output_log['payload']:
            self.fail('Notification contained location field.')

    def test_task_run_notification(self):
        self.task_proxy.run(executor=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.run')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)

    def test_task_processing_notification(self):
        self.task_proxy.begin_processing()
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.processing')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)

    def test_task_success_notification(self):
        self.task_proxy.begin_processing()
        self.task_proxy.succeed(result=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 2)
        output_log = output_logs[1]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.success')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)

    def test_task_failure_notification(self):
        self.task_proxy.fail(message=None)
        output_logs = self.notifier.get_logs()
        self.assertEqual(len(output_logs), 1)
        output_log = output_logs[0]
        self.assertEqual(output_log['notification_type'], 'INFO')
        self.assertEqual(output_log['event_type'], 'task.failure')
        self.assertEqual(output_log['payload']['id'], self.task.task_id)
