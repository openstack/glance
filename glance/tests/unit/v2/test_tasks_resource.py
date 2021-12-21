# Copyright 2013 IBM Corp.
# All Rights Reserved.
#
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
import http.client as http
from unittest import mock
import uuid

from oslo_config import cfg
from oslo_serialization import jsonutils
import webob

import glance.api.v2.tasks
from glance.common import timeutils
import glance.domain
import glance.gateway
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

DATETIME = datetime.datetime(2013, 9, 28, 15, 27, 36, 325355)
ISOTIME = '2013-09-28T15:27:36Z'


def _db_fixture(task_id, **kwargs):
    default_datetime = timeutils.utcnow()
    obj = {
        'id': task_id,
        'status': 'pending',
        'type': 'import',
        'input': {},
        'result': None,
        'owner': None,
        'image_id': 'fake_image_id',
        'user_id': 'fake_user',
        'request_id': 'fake_request_id',
        'message': None,
        'expires_at': default_datetime + datetime.timedelta(days=365),
        'created_at': default_datetime,
        'updated_at': default_datetime,
        'deleted_at': None,
        'deleted': False
    }
    obj.update(kwargs)
    return obj


def _domain_fixture(task_id, **kwargs):
    default_datetime = timeutils.utcnow()
    task_properties = {
        'task_id': task_id,
        'status': kwargs.get('status', 'pending'),
        'task_type': kwargs.get('type', 'import'),
        'owner': kwargs.get('owner'),
        'expires_at': kwargs.get('expires_at'),
        'created_at': kwargs.get('created_at', default_datetime),
        'updated_at': kwargs.get('updated_at', default_datetime),
        'task_input': kwargs.get('task_input', {}),
        'message': kwargs.get('message'),
        'result': kwargs.get('result'),
        'image_id': kwargs.get('image_id'),
        'user_id': kwargs.get('user_id'),
        'request_id': kwargs.get('request_id'),
    }
    task = glance.domain.Task(**task_properties)
    return task


CONF = cfg.CONF
CONF.import_opt('task_time_to_live', 'glance.common.config', group='task')


class TestTasksController(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTasksController, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = unit_test_utils.FakeStoreAPI()
        self._create_tasks()
        self.controller = glance.api.v2.tasks.TasksController(self.db,
                                                              self.policy,
                                                              self.notifier,
                                                              self.store)
        self.gateway = glance.gateway.Gateway(self.db, self.store,
                                              self.notifier, self.policy)

    def _create_tasks(self):
        now = timeutils.utcnow()
        times = [now + datetime.timedelta(seconds=5 * i) for i in range(4)]
        self.tasks = [
            _db_fixture(UUID1, owner=TENANT1,
                        created_at=times[0], updated_at=times[0]),
            # FIXME(venkatesh): change the type to include clone and export
            # once they are included as a valid types under Task domain model.
            _db_fixture(UUID2, owner=TENANT2, type='import',
                        created_at=times[1], updated_at=times[1]),
            _db_fixture(UUID3, owner=TENANT3, type='import',
                        created_at=times[2], updated_at=times[2]),
            _db_fixture(UUID4, owner=TENANT4, type='import',
                        created_at=times[3], updated_at=times[3])]
        [self.db.task_create(None, task) for task in self.tasks]

    def test_index(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual(1, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID1])
        self.assertEqual(expected, actual)

    def test_index_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.controller.index(request)
        self.assertEqual(4, len(output['tasks']))

    def test_index_return_parameters(self):
        self.config(limit_param_default=1, api_limit_max=4)
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.controller.index(request, marker=UUID3, limit=1,
                                       sort_key='created_at', sort_dir='desc')
        self.assertEqual(1, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID2])
        self.assertEqual(expected, actual)
        self.assertEqual(UUID2, output['next_marker'])

    def test_index_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.controller.index(request, marker=UUID3, limit=2)
        self.assertEqual(2, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID2, UUID1])
        self.assertEqual(expected, actual)
        self.assertEqual(UUID1, output['next_marker'])

    def test_index_no_next_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        request = unit_test_utils.get_fake_request(is_admin=True)
        output = self.controller.index(request, marker=UUID1, limit=2)
        self.assertEqual(0, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([])
        self.assertEqual(expected, actual)
        self.assertNotIn('next_marker', output)

    def test_index_with_id_filter(self):
        request = unit_test_utils.get_fake_request('/tasks?id=%s' % UUID1)
        output = self.controller.index(request, filters={'id': UUID1})
        self.assertEqual(1, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID1])
        self.assertEqual(expected, actual)

    def test_index_with_filters_return_many(self):
        path = '/tasks?status=pending'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, filters={'status': 'pending'})
        self.assertEqual(4, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID1, UUID2, UUID3, UUID4])
        self.assertEqual(sorted(expected), sorted(actual))

    def test_index_with_many_filters(self):
        url = '/tasks?status=pending&type=import'
        request = unit_test_utils.get_fake_request(url, is_admin=True)
        output = self.controller.index(request,
                                       filters={
                                           'status': 'pending',
                                           'type': 'import',
                                           'owner': TENANT1,
                                       })
        self.assertEqual(1, len(output['tasks']))
        actual = set([task.task_id for task in output['tasks']])
        expected = set([UUID1])
        self.assertEqual(expected, actual)

    def test_index_with_marker(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, marker=UUID3)
        actual = set([task.task_id for task in output['tasks']])
        self.assertEqual(1, len(actual))
        self.assertIn(UUID2, actual)

    def test_index_with_limit(self):
        path = '/tasks'
        limit = 2
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, limit=limit)
        actual = set([task.task_id for task in output['tasks']])
        self.assertEqual(limit, len(actual))

    def test_index_greater_than_limit_max(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, limit=4)
        actual = set([task.task_id for task in output['tasks']])
        self.assertEqual(3, len(actual))
        self.assertNotIn(output['next_marker'], output)

    def test_index_default_limit(self):
        self.config(limit_param_default=1, api_limit_max=3)
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path)
        output = self.controller.index(request)
        actual = set([task.task_id for task in output['tasks']])
        self.assertEqual(1, len(actual))

    def test_index_with_sort_dir(self):
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, sort_dir='asc', limit=3)
        actual = [task.task_id for task in output['tasks']]
        self.assertEqual(3, len(actual))
        self.assertEqual([UUID1, UUID2, UUID3], actual)

    def test_index_with_sort_key(self):
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path, is_admin=True)
        output = self.controller.index(request, sort_key='created_at', limit=3)
        actual = [task.task_id for task in output['tasks']]
        self.assertEqual(3, len(actual))
        self.assertEqual(UUID4, actual[0])
        self.assertEqual(UUID3, actual[1])
        self.assertEqual(UUID2, actual[2])

    def test_index_with_marker_not_found(self):
        fake_uuid = str(uuid.uuid4())
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, marker=fake_uuid)

    def test_index_with_marker_is_not_like_uuid(self):
        marker = 'INVALID_UUID'
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, marker=marker)

    def test_index_invalid_sort_key(self):
        path = '/tasks'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, request, sort_key='foo')

    def test_index_zero_tasks(self):
        self.db.reset()
        request = unit_test_utils.get_fake_request()
        output = self.controller.index(request)
        self.assertEqual([], output['tasks'])

    def test_get(self):
        request = unit_test_utils.get_fake_request()
        task = self.controller.get(request, task_id=UUID1)
        self.assertEqual(UUID1, task.task_id)
        self.assertEqual('import', task.type)

    def test_get_non_existent(self):
        request = unit_test_utils.get_fake_request()
        task_id = str(uuid.uuid4())
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get, request, task_id)

    def test_get_not_allowed(self):
        request = unit_test_utils.get_fake_request()
        self.assertEqual(TENANT1, request.context.project_id)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get, request, UUID4)

    @mock.patch('glance.api.common.get_thread_pool')
    @mock.patch.object(glance.gateway.Gateway, 'get_task_factory')
    @mock.patch.object(glance.gateway.Gateway, 'get_task_executor_factory')
    @mock.patch.object(glance.gateway.Gateway, 'get_task_repo')
    def test_create(self, mock_get_task_repo, mock_get_task_executor_factory,
                    mock_get_task_factory, mock_get_thread_pool):
        # setup
        request = unit_test_utils.get_fake_request()
        task = {
            "type": "import",
            "input": {
                "import_from": "swift://cloud.foo/myaccount/mycontainer/path",
                "import_from_format": "qcow2",
                "image_properties": {}
            }
        }
        get_task_factory = mock.Mock()
        mock_get_task_factory.return_value = get_task_factory

        new_task = mock.Mock()
        get_task_factory.new_task.return_value = new_task

        new_task.run.return_value = mock.ANY

        get_task_executor_factory = mock.Mock()
        mock_get_task_executor_factory.return_value = get_task_executor_factory
        get_task_executor_factory.new_task_executor.return_value = mock.Mock()

        get_task_repo = mock.Mock()
        mock_get_task_repo.return_value = get_task_repo
        get_task_repo.add.return_value = mock.Mock()

        # call
        self.controller.create(request, task=task)

        # assert
        self.assertEqual(1, get_task_factory.new_task.call_count)
        self.assertEqual(1, get_task_repo.add.call_count)
        self.assertEqual(
            1, get_task_executor_factory.new_task_executor.call_count)

        # Make sure that we spawned the task's run method
        mock_get_thread_pool.assert_called_once_with('tasks_pool')
        mock_get_thread_pool.return_value.spawn.assert_called_once_with(
            new_task.run,
            get_task_executor_factory.new_task_executor.return_value)

    @mock.patch('glance.common.scripts.utils.get_image_data_iter')
    @mock.patch('glance.common.scripts.utils.validate_location_uri')
    def test_create_with_live_time(self, mock_validate_location_uri,
                                   mock_get_image_data_iter):
        self.skipTest("Something wrong, this test touches registry")
        request = unit_test_utils.get_fake_request()
        task = {
            "type": "import",
            "input": {
                "import_from": "http://download.cirros-cloud.net/0.3.4/"
                               "cirros-0.3.4-x86_64-disk.img",
                "import_from_format": "qcow2",
                "image_properties": {
                    "disk_format": "qcow2",
                    "container_format": "bare",
                    "name": "test-task"
                }
            }
        }

        new_task = self.controller.create(request, task=task)
        executor_factory = self.gateway.get_task_executor_factory(
            request.context)
        task_executor = executor_factory.new_task_executor(request.context)
        task_executor.begin_processing(new_task.task_id)
        success_task = self.controller.get(request, new_task.task_id)

        # ignore second and microsecond to avoid flaky runs
        task_live_time = (success_task.expires_at.replace(second=0,
                                                          microsecond=0) -
                          success_task.updated_at.replace(second=0,
                                                          microsecond=0))
        task_live_time_hour = (task_live_time.days * 24 +
                               task_live_time.seconds / 3600)
        self.assertEqual(CONF.task.task_time_to_live, task_live_time_hour)

    def test_create_with_wrong_import_form(self):
        request = unit_test_utils.get_fake_request()
        wrong_import_from = [
            "swift://cloud.foo/myaccount/mycontainer/path",
            "file:///path",
            "cinder://volume-id"
        ]
        executor_factory = self.gateway.get_task_executor_factory(
            request.context)
        task_repo = self.gateway.get_task_repo(request.context)

        for import_from in wrong_import_from:
            task = {
                "type": "import",
                "input": {
                    "import_from": import_from,
                    "import_from_format": "qcow2",
                    "image_properties": {
                        "disk_format": "qcow2",
                        "container_format": "bare",
                        "name": "test-task"
                    }
                }
            }
            new_task = self.controller.create(request, task=task)
            task_executor = executor_factory.new_task_executor(request.context)
            task_executor.begin_processing(new_task.task_id)
            final_task = task_repo.get(new_task.task_id)

            self.assertEqual('failure', final_task.status)
            if import_from.startswith("file:///"):
                msg = ("File based imports are not allowed. Please use a "
                       "non-local source of image data.")
            else:
                supported = ['http', ]
                msg = ("The given uri is not valid. Please specify a "
                       "valid uri from the following list of supported uri "
                       "%(supported)s") % {'supported': supported}
            self.assertEqual(msg, final_task.message)

    def test_create_with_properties_missed(self):
        request = unit_test_utils.get_fake_request()
        executor_factory = self.gateway.get_task_executor_factory(
            request.context)
        task_repo = self.gateway.get_task_repo(request.context)

        task = {
            "type": "import",
            "input": {
                "import_from": "swift://cloud.foo/myaccount/mycontainer/path",
                "import_from_format": "qcow2",
            }
        }
        new_task = self.controller.create(request, task=task)
        task_executor = executor_factory.new_task_executor(request.context)
        task_executor.begin_processing(new_task.task_id)
        final_task = task_repo.get(new_task.task_id)

        self.assertEqual('failure', final_task.status)
        msg = "Input does not contain 'image_properties' field"
        self.assertEqual(msg, final_task.message)

    @mock.patch.object(glance.gateway.Gateway, 'get_task_factory')
    def test_notifications_on_create(self, mock_get_task_factory):
        request = unit_test_utils.get_fake_request()

        new_task = mock.MagicMock(type='import')
        mock_get_task_factory.new_task.return_value = new_task
        new_task.run.return_value = mock.ANY

        task = {"type": "import", "input": {
            "import_from": "http://cloud.foo/myaccount/mycontainer/path",
            "import_from_format": "qcow2",
            "image_properties": {}
        }
        }
        task = self.controller.create(request, task=task)
        output_logs = [nlog for nlog in self.notifier.get_logs()
                       if nlog['event_type'] == 'task.create']
        self.assertEqual(1, len(output_logs))
        output_log = output_logs[0]
        self.assertEqual('INFO', output_log['notification_type'])
        self.assertEqual('task.create', output_log['event_type'])


class TestTasksControllerPolicies(base.IsolatedUnitTest):

    def setUp(self):
        super(TestTasksControllerPolicies, self).setUp()
        self.db = unit_test_utils.FakeDB()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.controller = glance.api.v2.tasks.TasksController(self.db,
                                                              self.policy)

    def test_access_get_unauthorized(self):
        rules = {"tasks_api_access": False,
                 "get_task": True}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.get,
                          request, task_id=UUID2)

    def test_delete(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPMethodNotAllowed,
                          self.controller.delete,
                          request,
                          'fake_id')

    def test_access_delete_unauthorized(self):
        rules = {"tasks_api_access": False}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.delete,
                          request,
                          'fake_id')


class TestTasksDeserializerPolicies(test_utils.BaseTestCase):

    # NOTE(rosmaita): this is a bit weird, but we check the access
    # policy in the RequestDeserializer for calls that take bodies
    # or query strings because we want to make sure the failure is
    # a 403, not a 400 due to bad request format
    def setUp(self):
        super(TestTasksDeserializerPolicies, self).setUp()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.deserializer = glance.api.v2.tasks.RequestDeserializer(
            schema=None, policy_engine=self.policy)

    bad_path = '/tasks?limit=NaN'

    def test_access_index_authorized_bad_query_string(self):
        """Allow access, fail with 400"""
        rules = {"tasks_api_access": True,
                 "get_tasks": True}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request(self.bad_path)
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_access_index_unauthorized(self):
        """Disallow access with bad request, fail with 403"""
        rules = {"tasks_api_access": False,
                 "get_tasks": True}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request(self.bad_path)
        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.index,
                          request)

    bad_task = {'typo': 'import', 'input': {"import_from": "fake"}}

    def test_access_create_authorized_bad_format(self):
        """Allow access, fail with 400"""
        rules = {"tasks_api_access": True,
                 "add_task": True}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes(self.bad_task)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create,
                          request)

    def test_access_create_unauthorized(self):
        """Disallow access with bad request, fail with 403"""
        rules = {"tasks_api_access": False,
                 "add_task": True}
        self.policy.set_rules(rules)
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes(self.bad_task)
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.deserializer.create,
                          request)


class TestTasksDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTasksDeserializer, self).setUp()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.deserializer = glance.api.v2.tasks.RequestDeserializer(
            policy_engine=self.policy)

    def test_create_no_body(self):
        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.create, request)

    def test_create(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dump_as_bytes({
            'type': 'import',
            'input': {'import_from':
                      'swift://cloud.foo/myaccount/mycontainer/path',
                      'import_from_format': 'qcow2',
                      'image_properties': {'name': 'fake1'}},
        })
        output = self.deserializer.create(request)
        properties = {
            'type': 'import',
            'input': {'import_from':
                      'swift://cloud.foo/myaccount/mycontainer/path',
                      'import_from_format': 'qcow2',
                      'image_properties': {'name': 'fake1'}},
        }
        self.maxDiff = None
        expected = {'task': properties}
        self.assertEqual(expected, output)

    def test_index(self):
        marker = str(uuid.uuid4())
        path = '/tasks?limit=1&marker=%s' % marker
        request = unit_test_utils.get_fake_request(path)
        expected = {'limit': 1,
                    'marker': marker,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc',
                    'filters': {}}
        output = self.deserializer.index(request)
        self.assertEqual(expected, output)

    def test_index_strip_params_from_filters(self):
        type = 'import'
        path = '/tasks?type=%s' % type
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(type, output['filters']['type'])

    def test_index_with_many_filter(self):
        status = 'success'
        type = 'import'
        path = '/tasks?status=%(status)s&type=%(type)s' % {'status': status,
                                                           'type': type}
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(status, output['filters']['status'])
        self.assertEqual(type, output['filters']['type'])

    def test_index_with_filter_and_limit(self):
        status = 'success'
        path = '/tasks?status=%s&limit=1' % status
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(status, output['filters']['status'])
        self.assertEqual(1, output['limit'])

    def test_index_non_integer_limit(self):
        request = unit_test_utils.get_fake_request('/tasks?limit=blah')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_zero_limit(self):
        request = unit_test_utils.get_fake_request('/tasks?limit=0')
        expected = {'limit': 0,
                    'sort_key': 'created_at',
                    'sort_dir': 'desc',
                    'filters': {}}
        output = self.deserializer.index(request)
        self.assertEqual(expected, output)

    def test_index_negative_limit(self):
        path = '/tasks?limit=-1'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_fraction(self):
        request = unit_test_utils.get_fake_request('/tasks?limit=1.1')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_invalid_status(self):
        path = '/tasks?status=blah'
        request = unit_test_utils.get_fake_request(path)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.deserializer.index, request)

    def test_index_marker(self):
        marker = str(uuid.uuid4())
        path = '/tasks?marker=%s' % marker
        request = unit_test_utils.get_fake_request(path)
        output = self.deserializer.index(request)
        self.assertEqual(marker, output.get('marker'))

    def test_index_marker_not_specified(self):
        request = unit_test_utils.get_fake_request('/tasks')
        output = self.deserializer.index(request)
        self.assertNotIn('marker', output)

    def test_index_limit_not_specified(self):
        request = unit_test_utils.get_fake_request('/tasks')
        output = self.deserializer.index(request)
        self.assertNotIn('limit', output)

    def test_index_sort_key_id(self):
        request = unit_test_utils.get_fake_request('/tasks?sort_key=id')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': 'id',
            'sort_dir': 'desc',
            'filters': {}
        }
        self.assertEqual(expected, output)

    def test_index_sort_dir_asc(self):
        request = unit_test_utils.get_fake_request('/tasks?sort_dir=asc')
        output = self.deserializer.index(request)
        expected = {
            'sort_key': 'created_at',
            'sort_dir': 'asc',
            'filters': {}}
        self.assertEqual(expected, output)

    def test_index_sort_dir_bad_value(self):
        request = unit_test_utils.get_fake_request('/tasks?sort_dir=invalid')
        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)


class TestTasksSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestTasksSerializer, self).setUp()
        self.serializer = glance.api.v2.tasks.ResponseSerializer()
        self.fixtures = [
            _domain_fixture(UUID1, type='import', status='pending',
                            task_input={'loc': 'fake'}, result={},
                            owner=TENANT1, image_id='fake_image_id',
                            user_id='fake_user',
                            request_id='fake_request_id',
                            message='', created_at=DATETIME,
                            updated_at=DATETIME),
            _domain_fixture(UUID2, type='import', status='processing',
                            task_input={'loc': 'bake'}, owner=TENANT2,
                            image_id='fake_image_id',
                            user_id='fake_user',
                            request_id='fake_request_id',
                            message='', created_at=DATETIME,
                            updated_at=DATETIME, result={}),
            _domain_fixture(UUID3, type='import', status='success',
                            task_input={'loc': 'foo'}, owner=TENANT3,
                            image_id='fake_image_id',
                            user_id='fake_user',
                            request_id='fake_request_id',
                            message='', created_at=DATETIME,
                            updated_at=DATETIME, result={},
                            expires_at=DATETIME),
            _domain_fixture(UUID4, type='import', status='failure',
                            task_input={'loc': 'boo'}, owner=TENANT4,
                            image_id='fake_image_id',
                            user_id='fake_user',
                            request_id='fake_request_id',
                            message='', created_at=DATETIME,
                            updated_at=DATETIME, result={},
                            expires_at=DATETIME),
        ]

    def test_index(self):
        expected = {
            'tasks': [
                {
                    'id': UUID1,
                    'type': 'import',
                    'status': 'pending',
                    'owner': TENANT1,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/tasks/%s' % UUID1,
                    'schema': '/v2/schemas/task',
                },
                {
                    'id': UUID2,
                    'type': 'import',
                    'status': 'processing',
                    'owner': TENANT2,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/tasks/%s' % UUID2,
                    'schema': '/v2/schemas/task',
                },
                {
                    'id': UUID3,
                    'type': 'import',
                    'status': 'success',
                    'owner': TENANT3,
                    'expires_at': ISOTIME,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/tasks/%s' % UUID3,
                    'schema': '/v2/schemas/task',
                },
                {
                    'id': UUID4,
                    'type': 'import',
                    'status': 'failure',
                    'owner': TENANT4,
                    'expires_at': ISOTIME,
                    'created_at': ISOTIME,
                    'updated_at': ISOTIME,
                    'self': '/v2/tasks/%s' % UUID4,
                    'schema': '/v2/schemas/task',
                },
            ],
            'first': '/v2/tasks',
            'schema': '/v2/schemas/tasks',
        }
        request = webob.Request.blank('/v2/tasks')
        response = webob.Response(request=request)
        task_fixtures = [f for f in self.fixtures]
        result = {'tasks': task_fixtures}
        self.serializer.index(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_index_next_marker(self):
        request = webob.Request.blank('/v2/tasks')
        response = webob.Response(request=request)
        task_fixtures = [f for f in self.fixtures]
        result = {'tasks': task_fixtures, 'next_marker': UUID2}
        self.serializer.index(response, result)
        output = jsonutils.loads(response.body)
        self.assertEqual('/v2/tasks?marker=%s' % UUID2, output['next'])

    def test_index_carries_query_parameters(self):
        url = '/v2/tasks?limit=10&sort_key=id&sort_dir=asc'
        request = webob.Request.blank(url)
        response = webob.Response(request=request)
        task_fixtures = [f for f in self.fixtures]
        result = {'tasks': task_fixtures, 'next_marker': UUID2}
        self.serializer.index(response, result)
        output = jsonutils.loads(response.body)

        expected_url = '/v2/tasks?limit=10&sort_dir=asc&sort_key=id'
        self.assertEqual(unit_test_utils.sort_url_by_qs_keys(expected_url),
                         unit_test_utils.sort_url_by_qs_keys(output['first']))

        expect_next = '/v2/tasks?limit=10&marker=%s&sort_dir=asc&sort_key=id'
        self.assertEqual(unit_test_utils.sort_url_by_qs_keys(
                         expect_next % UUID2),
                         unit_test_utils.sort_url_by_qs_keys(output['next']))

    def test_get(self):
        expected = {
            'id': UUID4,
            'type': 'import',
            'status': 'failure',
            'input': {'loc': 'boo'},
            'result': {},
            'owner': TENANT4,
            'message': '',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'expires_at': ISOTIME,
            'self': '/v2/tasks/%s' % UUID4,
            'schema': '/v2/schemas/task',
            'image_id': 'fake_image_id',
            'user_id': 'fake_user',
            'request_id': 'fake_request_id',
        }
        response = webob.Response()
        self.serializer.get(response, self.fixtures[3])
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_get_ensure_expires_at_not_returned(self):
        expected = {
            'id': UUID1,
            'type': 'import',
            'status': 'pending',
            'input': {'loc': 'fake'},
            'result': {},
            'owner': TENANT1,
            'message': '',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/tasks/%s' % UUID1,
            'schema': '/v2/schemas/task',
            'image_id': 'fake_image_id',
            'user_id': 'fake_user',
            'request_id': 'fake_request_id',
        }
        response = webob.Response()
        self.serializer.get(response, self.fixtures[0])
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

        expected = {
            'id': UUID2,
            'type': 'import',
            'status': 'processing',
            'input': {'loc': 'bake'},
            'result': {},
            'owner': TENANT2,
            'message': '',
            'created_at': ISOTIME,
            'updated_at': ISOTIME,
            'self': '/v2/tasks/%s' % UUID2,
            'schema': '/v2/schemas/task',
            'image_id': 'fake_image_id',
            'user_id': 'fake_user',
            'request_id': 'fake_request_id',
        }
        response = webob.Response()

        self.serializer.get(response, self.fixtures[1])

        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_create(self):
        response = webob.Response()

        self.serializer.create(response, self.fixtures[3])

        serialized_task = jsonutils.loads(response.body)
        self.assertEqual(http.CREATED, response.status_int)
        self.assertEqual(self.fixtures[3].task_id,
                         serialized_task['id'])
        self.assertEqual(self.fixtures[3].task_input,
                         serialized_task['input'])
        self.assertIn('expires_at', serialized_task)
        self.assertEqual('application/json', response.content_type)

    def test_create_ensure_expires_at_is_not_returned(self):
        response = webob.Response()

        self.serializer.create(response, self.fixtures[0])

        serialized_task = jsonutils.loads(response.body)
        self.assertEqual(http.CREATED, response.status_int)
        self.assertEqual(self.fixtures[0].task_id,
                         serialized_task['id'])
        self.assertEqual(self.fixtures[0].task_input,
                         serialized_task['input'])
        self.assertNotIn('expires_at', serialized_task)
        self.assertEqual('application/json', response.content_type)

        response = webob.Response()

        self.serializer.create(response, self.fixtures[1])

        serialized_task = jsonutils.loads(response.body)
        self.assertEqual(http.CREATED, response.status_int)
        self.assertEqual(self.fixtures[1].task_id,
                         serialized_task['id'])
        self.assertEqual(self.fixtures[1].task_input,
                         serialized_task['input'])
        self.assertNotIn('expires_at', serialized_task)
        self.assertEqual('application/json', response.content_type)
