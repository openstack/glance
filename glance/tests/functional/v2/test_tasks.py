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

import uuid

from oslo_serialization import jsonutils
import requests

from glance.tests import functional


TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


class TestTasks(functional.FunctionalTest):

    def setUp(self):
        super(TestTasks, self).setUp()
        self.cleanup()
        self.api_server.deployment_flavor = 'noauth'

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.api_port, path)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_task_lifecycle(self):
        self.start_servers(**self.__dict__.copy())
        # Task list should be empty
        path = self._url('/v2/tasks')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(0, len(tasks))

        # Create a task
        path = self._url('/v2/tasks')
        headers = self._headers({'content-type': 'application/json'})

        data = jsonutils.dumps({
            "type": "import",
            "input": {
                "import_from": "http://example.com",
                "import_from_format": "qcow2",
                "image_properties": {
                    'disk_format': 'vhd',
                    'container_format': 'ovf'
                }
            }
        })
        response = requests.post(path, headers=headers, data=data)
        self.assertEqual(201, response.status_code)

        # Returned task entity should have a generated id and status
        task = jsonutils.loads(response.text)
        task_id = task['id']

        self.assertIn('Location', response.headers)
        self.assertEqual(path + '/' + task_id, response.headers['Location'])

        checked_keys = set([u'created_at',
                            u'id',
                            u'input',
                            u'message',
                            u'owner',
                            u'schema',
                            u'self',
                            u'status',
                            u'type',
                            u'result',
                            u'updated_at'])
        self.assertEqual(checked_keys, set(task.keys()))
        expected_task = {
            'status': 'pending',
            'type': 'import',
            'input': {
                "import_from": "http://example.com",
                "import_from_format": "qcow2",
                "image_properties": {
                    'disk_format': 'vhd',
                    'container_format': 'ovf'
                }},
            'schema': '/v2/schemas/task',
        }
        for key, value in expected_task.items():
            self.assertEqual(value, task[key], key)

        # Tasks list should now have one entry
        path = self._url('/v2/tasks')
        response = requests.get(path, headers=self._headers())
        self.assertEqual(200, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(1, len(tasks))
        self.assertEqual(task_id, tasks[0]['id'])

        # Attempt to delete a task
        path = self._url('/v2/tasks/%s' % tasks[0]['id'])
        response = requests.delete(path, headers=self._headers())
        self.assertEqual(405, response.status_code)
        self.assertIsNotNone(response.headers.get('Allow'))
        self.assertEqual('GET', response.headers.get('Allow'))

        self.stop_servers()


class TestTasksWithRegistry(TestTasks):
    def setUp(self):
        super(TestTasksWithRegistry, self).setUp()
        self.api_server.data_api = (
            'glance.tests.functional.v2.registry_data_api')
        self.registry_server.deployment_flavor = 'trusted-auth'
