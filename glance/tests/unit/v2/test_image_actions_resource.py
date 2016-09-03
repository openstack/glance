# Copyright 2015 OpenStack Foundation.
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
import glance_store as store
import webob

import glance.api.v2.image_actions as image_actions
import glance.context
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils


BASE_URI = unit_test_utils.BASE_URI

USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
CHKSUM = '93264c3edf5972c9f1cb309543d38a5c'


def _db_fixture(id, **kwargs):
    obj = {
        'id': id,
        'name': None,
        'visibility': 'shared',
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
    }
    obj.update(kwargs)
    return obj


class TestImageActionsController(base.IsolatedUnitTest):
    def setUp(self):
        super(TestImageActionsController, self).setUp()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = unit_test_utils.FakeStoreAPI()
        for i in range(1, 4):
            self.store.data['%s/fake_location_%i' % (BASE_URI, i)] = ('Z', 1)
        self.store_utils = unit_test_utils.FakeStoreUtils(self.store)
        self.controller = image_actions.ImageActionsController(
            self.db,
            self.policy,
            self.notifier,
            self.store)
        self.controller.gateway.store_utils = self.store_utils
        store.create_stores()

    def _get_fake_context(self, user=USER1, tenant=TENANT1, roles=None,
                          is_admin=False):
        if roles is None:
            roles = ['member']

        kwargs = {
            'user': user,
            'tenant': tenant,
            'roles': roles,
            'is_admin': is_admin,
        }

        context = glance.context.RequestContext(**kwargs)
        return context

    def _create_image(self, status):
        self.images = [
            _db_fixture(UUID1, owner=TENANT1, checksum=CHKSUM,
                        name='1', size=256, virtual_size=1024,
                        visibility='public',
                        locations=[{'url': '%s/%s' % (BASE_URI, UUID1),
                                    'metadata': {}, 'status': 'active'}],
                        disk_format='raw',
                        container_format='bare',
                        status=status),
        ]
        context = self._get_fake_context()
        [self.db.image_create(context, image) for image in self.images]

    def test_deactivate_from_active(self):
        self._create_image('active')

        request = unit_test_utils.get_fake_request()
        self.controller.deactivate(request, UUID1)

        image = self.db.image_get(request.context, UUID1)

        self.assertEqual('deactivated', image['status'])

    def test_deactivate_from_deactivated(self):
        self._create_image('deactivated')

        request = unit_test_utils.get_fake_request()
        self.controller.deactivate(request, UUID1)

        image = self.db.image_get(request.context, UUID1)

        self.assertEqual('deactivated', image['status'])

    def _test_deactivate_from_wrong_status(self, status):

        # deactivate will yield an error if the initial status is anything
        # other than 'active' or 'deactivated'
        self._create_image(status)

        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.deactivate,
                          request, UUID1)

    def test_deactivate_from_queued(self):
        self._test_deactivate_from_wrong_status('queued')

    def test_deactivate_from_saving(self):
        self._test_deactivate_from_wrong_status('saving')

    def test_deactivate_from_killed(self):
        self._test_deactivate_from_wrong_status('killed')

    def test_deactivate_from_pending_delete(self):
        self._test_deactivate_from_wrong_status('pending_delete')

    def test_deactivate_from_deleted(self):
        self._test_deactivate_from_wrong_status('deleted')

    def test_reactivate_from_active(self):
        self._create_image('active')

        request = unit_test_utils.get_fake_request()
        self.controller.reactivate(request, UUID1)

        image = self.db.image_get(request.context, UUID1)

        self.assertEqual('active', image['status'])

    def test_reactivate_from_deactivated(self):
        self._create_image('deactivated')

        request = unit_test_utils.get_fake_request()
        self.controller.reactivate(request, UUID1)

        image = self.db.image_get(request.context, UUID1)

        self.assertEqual('active', image['status'])

    def _test_reactivate_from_wrong_status(self, status):

        # reactivate will yield an error if the initial status is anything
        # other than 'active' or 'deactivated'
        self._create_image(status)

        request = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.reactivate,
                          request, UUID1)

    def test_reactivate_from_queued(self):
        self._test_reactivate_from_wrong_status('queued')

    def test_reactivate_from_saving(self):
        self._test_reactivate_from_wrong_status('saving')

    def test_reactivate_from_killed(self):
        self._test_reactivate_from_wrong_status('killed')

    def test_reactivate_from_pending_delete(self):
        self._test_reactivate_from_wrong_status('pending_delete')

    def test_reactivate_from_deleted(self):
        self._test_reactivate_from_wrong_status('deleted')
