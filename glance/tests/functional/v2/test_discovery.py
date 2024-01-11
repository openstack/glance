# Copyright 2021 Red Hat, Inc.
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

import fixtures
import http.client as http

from oslo_utils import units

from glance.quota import keystone as ks_quota
from glance.tests import functional
from glance.tests.functional.v2.test_images import get_enforcer_class
from glance.tests import utils as test_utils


class TestDiscovery(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestDiscovery, self).setUp()
        self.config(endpoint_id='ENDPOINT_ID', group='oslo_limit')
        self.config(use_keystone_limits=True)

        self.enforcer_mock = self.useFixture(
            fixtures.MockPatchObject(ks_quota, 'limit')).mock

    def set_limit(self, limits):
        self.enforcer_mock.Enforcer = get_enforcer_class(limits)

    def _assert_usage(self, expected):
        usage = self.api_get('/v2/info/usage')
        usage = usage.json['usage']
        for item in ('count', 'size', 'stage'):
            key = 'image_%s_total' % item
            self.assertEqual(expected[key], usage[key],
                             'Mismatch in %s' % key)
        self.assertEqual(expected['image_count_uploading'],
                         usage['image_count_uploading'])

    def test_quota_with_usage(self):
        self.set_limit({'image_size_total': 5,
                        'image_count_total': 10,
                        'image_stage_total': 15,
                        'image_count_uploading': 20})

        self.start_server()

        # Initially we expect no usage, but our limits in place.
        expected = {
            'image_size_total': {'limit': 5, 'usage': 0},
            'image_count_total': {'limit': 10, 'usage': 0},
            'image_stage_total': {'limit': 15, 'usage': 0},
            'image_count_uploading': {'limit': 20, 'usage': 0},
        }
        self._assert_usage(expected)

        # Stage 1MiB and see our total count, uploading count, and
        # staging area usage increase.
        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_stage(data_iter=data)
        expected['image_count_uploading']['usage'] = 1
        expected['image_count_total']['usage'] = 1
        expected['image_stage_total']['usage'] = 1
        self._assert_usage(expected)

        # Doing the import does not change anything (since we are
        # synchronous and the task will not have run yet).
        self._import_direct(image_id, ['store1'])
        self._assert_usage(expected)

        # After the import is complete, our usage of the staging area
        # drops to zero, and our consumption of actual store space
        # reflects the new active image.
        self._wait_for_import(image_id)
        expected['image_count_uploading']['usage'] = 0
        expected['image_stage_total']['usage'] = 0
        expected['image_size_total']['usage'] = 1
        self._assert_usage(expected)

        # Upload also yields a new active image and store usage.
        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)
        expected['image_count_total']['usage'] = 2
        expected['image_size_total']['usage'] = 2
        self._assert_usage(expected)

        # Deleting an image drops the usage down.
        self.api_delete('/v2/images/%s' % image_id)
        expected['image_count_total']['usage'] = 1
        expected['image_size_total']['usage'] = 1
        self._assert_usage(expected)

    def test_stores(self):
        # NOTE(mrjoshi): As this is a functional test, we are
        # testing the functionality with file stores.

        self.start_server()

        # If user is admin or non-admin the store list will be
        # displayed.
        stores = self.api_get('/v2/info/stores').json['stores']
        expected = {
            "stores": [
                {
                    "id": "store1",
                    "default": "true"
                },
                {
                    "id": "store2"
                },
                {
                    "id": "store3"
                }]}

        self.assertEqual(expected['stores'], stores)

        # If user is admin the store list will be displayed
        # along with store properties.
        stores = self.api_get('/v2/info/stores/detail').json['stores']
        expected = {
            "stores": [
                {
                    "id": "store1",
                    "default": "true",
                    "type": "file",
                    "weight": 0,
                    "properties": {
                          "data_dir": self._store_dir('store1'),
                          "chunk_size": 65536,
                          "thin_provisioning": False
                    }
                },
                {
                    "id": "store2",
                    "type": "file",
                    "weight": 0,
                    "properties": {
                          "data_dir": self._store_dir('store2'),
                          "chunk_size": 65536,
                          "thin_provisioning": False
                    }
                },
                {
                    "id": "store3",
                    "type": "file",
                    "weight": 0,
                    "properties": {
                          "data_dir": self._store_dir('store3'),
                          "chunk_size": 65536,
                          "thin_provisioning": False
                    }
                }]}

        self.assertEqual(expected['stores'], stores)

        # If user is non-admin 403 Error response will be returned.
        response = self.api_get('/v2/info/stores/detail',
                                headers={'X-Roles': 'member'})
        self.assertEqual(http.FORBIDDEN, response.status_code)
