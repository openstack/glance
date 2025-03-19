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

import http.client as http
import uuid

from oslo_serialization import jsonutils

from glance.tests import functional


TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


class TestTasks(functional.SynchronousAPIBase):

    def test_task_not_allowed_non_admin(self):
        self.start_server()
        roles = {'X-Roles': 'member'}
        # Task list should be empty
        path = '/v2/tasks'
        response = self.api_get(path, headers=self._headers(roles))
        self.assertEqual(http.FORBIDDEN, response.status_code)

    def test_task_lifecycle(self):
        self.start_server()
        # Task list should be empty
        path = '/v2/tasks'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(0, len(tasks))

        # Create a task
        path = '/v2/tasks'
        headers = self._headers({'content-type': 'application/json'})

        json = {
            "type": "import",
            "input": {
                "import_from": "http://example.com",
                "import_from_format": "qcow2",
                "image_properties": {
                    'disk_format': 'vhd',
                    'container_format': 'ovf'
                }
            }
        }
        response = self.api_post(path, headers=headers, json=json)
        self.assertEqual(http.CREATED, response.status_code)

        # Returned task entity should have a generated id and status
        task = jsonutils.loads(response.text)
        task_id = task['id']

        self.assertIn('Location', response.headers)
        path = f'http://localhost{path}'
        self.assertEqual(path + '/' + task_id, response.headers['Location'])

        checked_keys = set(['created_at',
                            'id',
                            'input',
                            'message',
                            'owner',
                            'schema',
                            'self',
                            'status',
                            'type',
                            'result',
                            'updated_at',
                            'request_id',
                            'user_id'
                            ])
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
        path = '/v2/tasks'
        response = self.api_get(path, headers=self._headers())
        self.assertEqual(http.OK, response.status_code)
        tasks = jsonutils.loads(response.text)['tasks']
        self.assertEqual(1, len(tasks))
        self.assertEqual(task_id, tasks[0]['id'])

        # Attempt to delete a task
        path = f'/v2/tasks/{tasks[0]["id"]}'
        response = self.api_delete(path, headers=self._headers())
        self.assertEqual(http.METHOD_NOT_ALLOWED, response.status_code)
        self.assertIsNotNone(response.headers.get('Allow'))
        self.assertEqual('GET', response.headers.get('Allow'))
