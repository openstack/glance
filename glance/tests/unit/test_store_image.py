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


class ImageRepoStub(object):
    def get(self, *args, **kwargs):
        return 'image_from_get'

    def list(self, *args, **kwargs):
        return ['image_from_list_0', 'image_from_list_1']


class ImageStub(object):
    def __init__(self, image_id, status, location):
        self.image_id = image_id
        self.status = status
        self.location = location

    def delete(self):
        self.status = 'deleted'


class TestStoreImage(utils.BaseTestCase):
    def setUp(self):
        location = '%s/%s' % (BASE_URI, UUID1)
        self.image_stub = ImageStub(UUID1, 'active', location)
        self.image_repo_stub = ImageRepoStub()
        self.store_api = unit_test_utils.FakeStoreAPI()
        super(TestStoreImage, self).setUp()

    def test_image_delete(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEquals(image.status, 'active')
        self.store_api.get_from_backend({}, image.location)  # no exception
        image.delete()
        self.assertEquals(image.status, 'deleted')
        self.assertRaises(exception.NotFound,
                          self.store_api.get_from_backend, {}, image.location)

    def test_image_delayed_delete(self):
        self.config(delayed_delete=True)
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEquals(image.status, 'active')
        image.delete()
        self.assertEquals(image.status, 'pending_delete')
        self.store_api.get_from_backend({}, image.location)  # no exception

    def test_image_get_data(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEquals(image.get_data(), 'XXX')

    def test_image_set_data(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', location=None)
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', 4)
        self.assertEquals(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEquals(image.location, UUID2)
        self.assertEquals(image.checksum, 'Z')
        self.assertEquals(image.status, 'active')

    def test_image_set_data_unknown_size(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', location=None)
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', None)
        self.assertEquals(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEquals(image.location, UUID2)
        self.assertEquals(image.checksum, 'Z')
        self.assertEquals(image.status, 'active')

    def test_image_repo_get(self):
        image_repo = glance.store.ImageRepoProxy({}, self.store_api,
                                                 self.image_repo_stub)
        image = image_repo.get(UUID1)
        self.assertTrue(isinstance(image, glance.store.ImageProxy))
        self.assertEqual(image.image, 'image_from_get')

    def test_image_repo_list(self):
        image_repo = glance.store.ImageRepoProxy({}, self.store_api,
                                                 self.image_repo_stub)
        images = image_repo.list()
        for i, image in enumerate(images):
            self.assertTrue(isinstance(image, glance.store.ImageProxy))
            self.assertEqual(image.image, 'image_from_list_%d' % i)
