# Copyright 2012 OpenStack Foundation
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
import glance.store
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils


BASE_URI = 'swift+http://storeurl.com/container'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '228c6da5-29cd-4d67-9457-ed632e083fc0'


class ImageRepoStub(object):
    def add(self, image):
        return image

    def save(self, image):
        return image


class ImageStub(object):
    def __init__(self, image_id, status=None, locations=None,
                 visibility=None):
        self.image_id = image_id
        self.status = status
        self.locations = locations or []
        self.visibility = visibility

    def delete(self):
        self.status = 'deleted'

    def get_member_repo(self):
        return FakeMemberRepo(self, [TENANT1, TENANT2])


class FakeMemberRepo(object):
    def __init__(self, image, tenants=None):
        self.image = image
        self.factory = glance.domain.ImageMemberFactory()
        self.tenants = tenants or []

    def list(self, *args, **kwargs):
        return [self.factory.new_image_member(self.image, tenant)
                for tenant in self.tenants]

    def add(self, member):
        self.tenants.append(member.member_id)

    def remove(self, member):
        self.tenants.remove(member.member_id)


class TestStoreImage(utils.BaseTestCase):
    def setUp(self):
        locations = ['%s/%s' % (BASE_URI, UUID1)]
        self.image_stub = ImageStub(UUID1, 'active', locations)
        self.store_api = unit_test_utils.FakeStoreAPI()
        super(TestStoreImage, self).setUp()

    def test_image_delete(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        location = image.locations[0]
        self.assertEquals(image.status, 'active')
        self.store_api.get_from_backend({}, location)
        image.delete()
        self.assertEquals(image.status, 'deleted')
        self.assertRaises(exception.NotFound,
                          self.store_api.get_from_backend, {}, location)

    def test_image_delayed_delete(self):
        self.config(delayed_delete=True)
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEquals(image.status, 'active')
        image.delete()
        self.assertEquals(image.status, 'pending_delete')
        self.store_api.get_from_backend({}, image.locations[0])  # no exception

    def test_image_get_data(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEquals(image.get_data(), 'XXX')

    def test_image_set_data(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', 4)
        self.assertEquals(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEquals(image.locations, [UUID2])
        self.assertEquals(image.checksum, 'Z')
        self.assertEquals(image.status, 'active')

    def test_image_set_data_unknown_size(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', None)
        self.assertEquals(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEquals(image.locations, [UUID2])
        self.assertEquals(image.checksum, 'Z')
        self.assertEquals(image.status, 'active')


class TestStoreImageRepo(utils.BaseTestCase):
    def setUp(self):
        super(TestStoreImageRepo, self).setUp()
        self.store_api = unit_test_utils.FakeStoreAPI()
        self.image_stub = ImageStub(UUID1)
        self.image = glance.store.ImageProxy(self.image_stub,
                                             {}, self.store_api)
        self.image_repo_stub = ImageRepoStub()
        self.image_repo = glance.store.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.store_api)

    def test_add_updates_acls(self):
        self.image_stub.locations = ['foo', 'bar']
        self.image_stub.visibility = 'public'
        self.image_repo.add(self.image)
        self.assertTrue(self.store_api.acls['foo']['public'])
        self.assertEqual(self.store_api.acls['foo']['read'], [])
        self.assertEqual(self.store_api.acls['foo']['write'], [])
        self.assertTrue(self.store_api.acls['bar']['public'])
        self.assertEqual(self.store_api.acls['bar']['read'], [])
        self.assertEqual(self.store_api.acls['bar']['write'], [])

    def test_add_ignores_acls_if_no_locations(self):
        self.image_stub.locations = []
        self.image_stub.visibility = 'public'
        self.image_repo.add(self.image)
        self.assertEqual(len(self.store_api.acls), 0)

    def test_save_updates_acls(self):
        self.image_stub.locations = ['foo']
        self.image_repo.save(self.image)
        self.assertIn('foo', self.store_api.acls)

    def test_add_fetches_members_if_private(self):
        self.image_stub.locations = ['glue']
        self.image_stub.visibility = 'private'
        self.image_repo.add(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEquals(acls['write'], [])
        self.assertEquals(acls['read'], [TENANT1, TENANT2])

    def test_save_fetches_members_if_private(self):
        self.image_stub.locations = ['glue']
        self.image_stub.visibility = 'private'
        self.image_repo.save(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEquals(acls['write'], [])
        self.assertEquals(acls['read'], [TENANT1, TENANT2])

    def test_member_addition_updates_acls(self):
        self.image_stub.locations = ['glug']
        self.image_stub.visibility = 'private'
        member_repo = self.image.get_member_repo()
        membership = glance.domain.ImageMembership(
                UUID1, TENANT3, None, None, status='accepted')
        member_repo.add(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEquals(acls['write'], [])
        self.assertEquals(acls['read'], [TENANT1, TENANT2, TENANT3])

    def test_member_removal_updates_acls(self):
        self.image_stub.locations = ['glug']
        self.image_stub.visibility = 'private'
        member_repo = self.image.get_member_repo()
        membership = glance.domain.ImageMembership(
                UUID1, TENANT1, None, None, status='accepted')
        member_repo.remove(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEquals(acls['write'], [])
        self.assertEquals(acls['read'], [TENANT2])
