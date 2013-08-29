# Copyright 2013, Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the 'License'); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mox

from glance.common import exception
import glance.quota
import glance.store
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils as test_utils

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class ImageRepoStub(object):
    def get(self, *args, **kwargs):
        return 'image_from_get'

    def save(self, *args, **kwargs):
        return 'image_from_save'

    def add(self, *args, **kwargs):
        return 'image_from_add'

    def list(self, *args, **kwargs):
        return ['image_from_list_0', 'image_from_list_1']


class ImageStub(object):
    def __init__(self, image_id, visibility='private'):
        self.image_id = image_id
        self.visibility = visibility
        self.status = 'active'

    def delete(self):
        self.status = 'deleted'


class ImageFactoryStub(object):
    def new_image(self, image_id=None, name=None, visibility='private',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, tags=None, **other_args):
        self.visibility = visibility
        return 'new_image'


class FakeContext(object):
    owner = 'someone'
    is_admin = False


class FakeImage(object):
    size = None
    image_id = 'someid'
    locations = [{'url': 'file:///not/a/path', 'metadata': {}}]

    def set_data(self, data, size=None):
        self.size = 0
        for d in data:
            self.size = self. size + len(d)


class TestImageQuota(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageQuota, self).setUp()
        self.mox = mox.Mox()

    def tearDown(self):
        super(TestImageQuota, self).tearDown()
        self.mox.UnsetStubs()

    def _get_image(self, location_count=1, image_size=10):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = 'xyz'
        base_image.size = image_size
        image = glance.quota.ImageProxy(base_image, context, db_api)
        locations = []
        for i in range(location_count):
            locations.append({'url': 'file:///g/there/it/is%d' % i,
                              'metadata': {}})
        image_values = {'id': 'xyz', 'owner': context.owner,
                        'status': 'active', 'size': image_size,
                        'locations': locations}
        db_api.image_create(context, image_values)
        return image

    def test_quota_allowed(self):
        quota = 10
        self.config(user_storage_quota=quota)
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = 'id'
        image = glance.quota.ImageProxy(base_image, context, db_api)
        data = '*' * quota
        base_image.set_data(data, size=None)
        image.set_data(data)
        self.assertEqual(quota, base_image.size)

    def _quota_exceeded_size(self, quota, data,
                             deleted=True, size=None):
        self.config(user_storage_quota=quota)
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = 'id'
        image = glance.quota.ImageProxy(base_image, context, db_api)

        if deleted:
            self.mox.StubOutWithMock(glance.store, 'safe_delete_from_backend')
            glance.store.safe_delete_from_backend(
                base_image.locations[0]['url'],
                context,
                image.image_id)

        self.mox.ReplayAll()
        self.assertRaises(exception.StorageQuotaFull,
                          image.set_data,
                          data,
                          size=size)
        self.mox.VerifyAll()

    def test_quota_exceeded_no_size(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size(quota, data)

    def test_quota_exceeded_with_right_size(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size(quota, data, size=len(data), deleted=False)

    def test_quota_exceeded_with_lie_size(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size(quota, data, deleted=False, size=quota - 1)

    def test_append_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {}}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.append(new_location)
        pre_add_locations.append(new_location)
        self.assertEqual(image.locations, pre_add_locations)

    def test_insert_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {}}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.insert(0, new_location)
        pre_add_locations.insert(0, new_location)
        self.assertEqual(image.locations, pre_add_locations)

    def test_extend_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {}}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.extend([new_location])
        pre_add_locations.extend([new_location])
        self.assertEqual(image.locations, pre_add_locations)

    def test_iadd_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {}}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations += [new_location]
        pre_add_locations += [new_location]
        self.assertEqual(image.locations, pre_add_locations)

    def test_set_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {}}
        image = self._get_image()
        image.locations = [new_location]
        self.assertEqual(image.locations, [new_location])

    def test_exceed_append_location(self):
        image_size = 10
        max_images = 2
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.append,
                          {'url': 'file:///a/path', 'metadata': {}})

    def test_exceed_append_location(self):
        image_size = 10
        max_images = 2
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.insert,
                          0,
                          {'url': 'file:///a/path', 'metadata': {}})

    def test_exceed_extend_location(self):
        image_size = 10
        max_images = 2
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.extend,
                          [{'url': 'file:///a/path', 'metadata': {}}])

    def test_set_location_under(self):
        image_size = 10
        max_images = 1
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        image.locations = [{'url': 'file:///a/path', 'metadata': {}}]

    def test_set_location_exceed(self):
        image_size = 10
        max_images = 1
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        try:
            image.locations = [{'url': 'file:///a/path', 'metadata': {}},
                               {'url': 'file:///a/path2', 'metadata': {}}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass

    def test_iadd_location_exceed(self):
        image_size = 10
        max_images = 1
        quota = image_size * max_images
        self.config(user_storage_quota=quota)
        image = self._get_image(image_size=image_size,
                                location_count=max_images)
        try:
            image.locations += [{'url': 'file:///a/path', 'metadata': {}}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass
