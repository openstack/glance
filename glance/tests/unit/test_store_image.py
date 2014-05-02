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
import mox

from glance.common import exception
import glance.store
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils


BASE_URI = 'http://storeurl.com/container'
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
        self.size = 1

    def delete(self):
        self.status = 'deleted'

    def get_member_repo(self):
        return FakeMemberRepo(self, [TENANT1, TENANT2])


class ImageFactoryStub(object):
    def new_image(self, image_id=None, name=None, visibility='private',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, tags=None, **other_args):
        return ImageStub(image_id, visibility=visibility, **other_args)


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
        locations = [{'url': '%s/%s' % (BASE_URI, UUID1),
                      'metadata': {}}]
        self.image_stub = ImageStub(UUID1, 'active', locations)
        self.store_api = unit_test_utils.FakeStoreAPI()
        super(TestStoreImage, self).setUp()

    def test_image_delete(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        location = image.locations[0]
        self.assertEqual(image.status, 'active')
        self.store_api.get_from_backend({}, location['url'])
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.assertRaises(exception.NotFound,
                          self.store_api.get_from_backend, {}, location['url'])

    def test_image_get_data(self):
        image = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEqual(image.get_data(), 'XXX')

    def test_image_get_data_from_second_location(self):
        def fake_get_from_backend(self, context, location):
            if UUID1 in location:
                raise Exception('not allow download from %s' % location)
            else:
                return self.data[location]

        image1 = glance.store.ImageProxy(self.image_stub, {}, self.store_api)
        self.assertEqual(image1.get_data(), 'XXX')
        # Multiple location support
        context = glance.context.RequestContext(user=USER1)
        (image2, image_stub2) = self._add_image(context, UUID2, 'ZZZ', 3)
        location_data = image2.locations[0]
        image1.locations.append(location_data)
        self.assertEqual(len(image1.locations), 2)
        self.assertEqual(location_data['url'], UUID2)

        self.stubs.Set(unit_test_utils.FakeStoreAPI, 'get_from_backend',
                       fake_get_from_backend)
        # This time, image1.get_data() returns the data wrapped in a
        # LimitingReader|CooperativeReader pipeline, so peeking under
        # the hood of those objects to get at the underlying string.
        self.assertEqual(image1.get_data().data.fd, 'ZZZ')
        image1.locations.pop(0)
        self.assertEqual(len(image1.locations), 1)
        image2.delete()

    def test_image_set_data(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', 4)
        self.assertEqual(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(image.locations[0]['url'], UUID2)
        self.assertEqual(image.checksum, 'Z')
        self.assertEqual(image.status, 'active')

    def test_image_set_data_location_metadata(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        loc_meta = {'key': 'value5032'}
        store_api = unit_test_utils.FakeStoreAPI(store_metadata=loc_meta)
        image = glance.store.ImageProxy(image_stub, context, store_api)
        image.set_data('YYYY', 4)
        self.assertEqual(image.size, 4)
        location_data = image.locations[0]
        self.assertEqual(location_data['url'], UUID2)
        self.assertEqual(location_data['metadata'], loc_meta)
        self.assertEqual(image.checksum, 'Z')
        self.assertEqual(image.status, 'active')
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.assertRaises(exception.NotFound,
                          self.store_api.get_from_backend, {},
                          image.locations[0]['url'])

    def test_image_set_data_unknown_size(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image = glance.store.ImageProxy(image_stub, context, self.store_api)
        image.set_data('YYYY', None)
        self.assertEqual(image.size, 4)
        #NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(image.locations[0]['url'], UUID2)
        self.assertEqual(image.checksum, 'Z')
        self.assertEqual(image.status, 'active')
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.assertRaises(exception.NotFound,
                          self.store_api.get_from_backend, {},
                          image.locations[0]['url'])

    def _add_image(self, context, image_id, data, len):
        image_stub = ImageStub(image_id, status='queued', locations=[])
        image = glance.store.ImageProxy(image_stub,
                                        context, self.store_api)
        image.set_data(data, len)
        self.assertEqual(image.size, len)
        #NOTE(markwash): FakeStore returns image_id for location
        location = {'url': image_id, 'metadata': {}}
        self.assertEqual(image.locations, [location])
        self.assertEqual(image_stub.locations, [location])
        self.assertEqual(image.status, 'active')
        return (image, image_stub)

    def test_image_change_append_invalid_location_uri(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.append, location_bad)

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

    def test_image_change_append_invalid_location_metatdata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        # Using only one test rule here is enough to make sure
        # 'store.check_location_metadata()' can be triggered
        # in Location proxy layer. Complete test rule for
        # 'store.check_location_metadata()' testing please
        # check below cases within 'TestStoreMetaDataChecker'.
        location_bad = {'url': UUID3, 'metadata': "a invalid metadata"}

        self.assertRaises(glance.store.BackendException,
                          image1.locations.append, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

    def test_image_change_append_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.append(location3)

        self.assertEqual(image_stub1.locations, [location2, location3])
        self.assertEqual(image1.locations, [location2, location3])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image2.delete()

    def test_image_change_pop_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.append(location3)

        self.assertEqual(image_stub1.locations, [location2, location3])
        self.assertEqual(image1.locations, [location2, location3])

        image1.locations.pop()

        self.assertEqual(image_stub1.locations, [location2])
        self.assertEqual(image1.locations, [location2])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image2.delete()

    def test_image_change_extend_invalid_locations_uri(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}

        self.assertRaises(exception.BadStoreUri,
                          image1.locations.extend, [location_bad])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

    def test_image_change_extend_invalid_locations_metadata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location_bad = {'url': UUID3, 'metadata': "a invalid metadata"}

        self.assertRaises(glance.store.BackendException,
                          image1.locations.extend, [location_bad])

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

    def test_image_change_extend_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.extend([location3])

        self.assertEqual(image_stub1.locations, [location2, location3])
        self.assertEqual(image1.locations, [location2, location3])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image2.delete()

    def test_image_change_remove_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}
        location_bad = {'url': 'unknown://location', 'metadata': {}}

        image1.locations.extend([location3])
        image1.locations.remove(location2)

        self.assertEqual(image_stub1.locations, [location3])
        self.assertEqual(image1.locations, [location3])
        self.assertRaises(ValueError,
                          image1.locations.remove, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

    def test_image_change_delete_location(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        del image1.locations[0]

        self.assertEqual(image_stub1.locations, [])
        self.assertEqual(len(image1.locations), 0)

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

        image1.delete()

    def test_image_change_insert_invalid_location_uri(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.insert, 0, location_bad)

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

    def test_image_change_insert_invalid_location_metadata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location_bad = {'url': UUID3, 'metadata': "a invalid metadata"}

        self.assertRaises(glance.store.BackendException,
                          image1.locations.insert, 0, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

    def test_image_change_insert_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.insert(0, location3)

        self.assertEqual(image_stub1.locations, [location3, location2])
        self.assertEqual(image1.locations, [location3, location2])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image2.delete()

    def test_image_change_delete_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.insert(0, location3)
        del image1.locations[0:100]

        self.assertEqual(image_stub1.locations, [])
        self.assertEqual(len(image1.locations), 0)
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.insert, 0, location2)
        self.assertRaises(exception.BadStoreUri,
                          image2.locations.insert, 0, location3)

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

    def test_image_change_adding_invalid_location_uri(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        image_stub1 = ImageStub('fake_image_id', status='queued', locations=[])
        image1 = glance.store.ImageProxy(image_stub1, context, self.store_api)

        location_bad = {'url': 'unknown://location', 'metadata': {}}

        self.assertRaises(exception.BadStoreUri,
                          image1.locations.__iadd__, [location_bad])
        self.assertEqual(image_stub1.locations, [])
        self.assertEqual(image1.locations, [])

        image1.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

    def test_image_change_adding_invalid_location_metadata(self):
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        image_stub2 = ImageStub('fake_image_id', status='queued', locations=[])
        image2 = glance.store.ImageProxy(image_stub2, context, self.store_api)

        location_bad = {'url': UUID2, 'metadata': "a invalid metadata"}

        self.assertRaises(glance.store.BackendException,
                          image2.locations.__iadd__, [location_bad])
        self.assertEqual(image_stub2.locations, [])
        self.assertEqual(image2.locations, [])

        image1.delete()
        image2.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())

    def test_image_change_adding_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.store.ImageProxy(image_stub3, context, self.store_api)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image3.locations += [location2, location3]

        self.assertEqual(image_stub3.locations, [location2, location3])
        self.assertEqual(image3.locations, [location2, location3])

        image3.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_get_location_index(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)
        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.store.ImageProxy(image_stub3, context, self.store_api)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image3.locations += [location2, location3]

        self.assertEqual(image_stub3.locations.index(location3), 1)

        image3.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_get_location_by_index(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)
        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.store.ImageProxy(image_stub3, context, self.store_api)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image3.locations += [location2, location3]

        self.assertEqual(image_stub3.locations.index(location3), 1)
        self.assertEqual(image_stub3.locations[0], location2)

        image3.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_checking_location_exists(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.store.ImageProxy(image_stub3, context, self.store_api)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}
        location_bad = {'url': 'unknown://location', 'metadata': {}}

        image3.locations += [location2, location3]

        self.assertTrue(location3 in image_stub3.locations)
        self.assertFalse(location_bad in image_stub3.locations)

        image3.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_reverse_locations_order(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(len(self.store_api.data.keys()), 2)

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.store.ImageProxy(image_stub3, context, self.store_api)
        image3.locations += [location2, location3]

        image_stub3.locations.reverse()

        self.assertEqual(image_stub3.locations, [location3, location2])
        self.assertEqual(image3.locations, [location3, location2])

        image3.delete()

        self.assertEqual(len(self.store_api.data.keys()), 2)
        self.assertFalse(UUID2 in self.store_api.data.keys())
        self.assertFalse(UUID3 in self.store_api.data.keys())

        image1.delete()
        image2.delete()


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
        self.image_stub.locations = [{'url': 'foo', 'metadata': {}},
                                     {'url': 'bar', 'metadata': {}}]
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
        self.image_stub.locations = [{'url': 'foo', 'metadata': {}}]
        self.image_repo.save(self.image)
        self.assertIn('foo', self.store_api.acls)

    def test_add_fetches_members_if_private(self):
        self.image_stub.locations = [{'url': 'glue', 'metadata': {}}]
        self.image_stub.visibility = 'private'
        self.image_repo.add(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEqual(acls['write'], [])
        self.assertEqual(acls['read'], [TENANT1, TENANT2])

    def test_save_fetches_members_if_private(self):
        self.image_stub.locations = [{'url': 'glue', 'metadata': {}}]
        self.image_stub.visibility = 'private'
        self.image_repo.save(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEqual(acls['write'], [])
        self.assertEqual(acls['read'], [TENANT1, TENANT2])

    def test_member_addition_updates_acls(self):
        self.image_stub.locations = [{'url': 'glug', 'metadata': {}}]
        self.image_stub.visibility = 'private'
        member_repo = self.image.get_member_repo()
        membership = glance.domain.ImageMembership(
            UUID1, TENANT3, None, None, status='accepted')
        member_repo.add(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEqual(acls['write'], [])
        self.assertEqual(acls['read'], [TENANT1, TENANT2, TENANT3])

    def test_member_removal_updates_acls(self):
        self.image_stub.locations = [{'url': 'glug', 'metadata': {}}]
        self.image_stub.visibility = 'private'
        member_repo = self.image.get_member_repo()
        membership = glance.domain.ImageMembership(
            UUID1, TENANT1, None, None, status='accepted')
        member_repo.remove(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEqual(acls['write'], [])
        self.assertEqual(acls['read'], [TENANT2])


class TestImageFactory(utils.BaseTestCase):

    def setUp(self):
        super(TestImageFactory, self).setUp()
        self.image_factory = glance.store.ImageFactoryProxy(
            ImageFactoryStub(),
            glance.context.RequestContext(user=USER1),
            unit_test_utils.FakeStoreAPI())

    def test_new_image(self):
        image = self.image_factory.new_image()
        self.assertTrue(image.image_id is None)
        self.assertTrue(image.status is None)
        self.assertEqual(image.visibility, 'private')
        self.assertEqual(image.locations, [])

    def test_new_image_with_location(self):
        locations = [{'url': '%s/%s' % (BASE_URI, UUID1),
                      'metadata': {}}]
        image = self.image_factory.new_image(locations=locations)
        self.assertEqual(image.locations, locations)
        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          self.image_factory.new_image,
                          locations=[location_bad])


class TestStoreMetaDataChecker(utils.BaseTestCase):

    def test_empty(self):
        glance.store.check_location_metadata({})

    def test_unicode(self):
        m = {'key': u'somevalue'}
        glance.store.check_location_metadata(m)

    def test_unicode_list(self):
        m = {'key': [u'somevalue', u'2']}
        glance.store.check_location_metadata(m)

    def test_unicode_dict(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        m = {'topkey': inner}
        glance.store.check_location_metadata(m)

    def test_unicode_dict_list(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        m = {'topkey': inner, 'list': [u'somevalue', u'2'], 'u': u'2'}
        glance.store.check_location_metadata(m)

    def test_nested_dict(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        inner = {'newkey': inner}
        inner = {'anotherkey': inner}
        m = {'topkey': inner}
        glance.store.check_location_metadata(m)

    def test_simple_bad(self):
        m = {'key1': object()}
        self.assertRaises(glance.store.BackendException,
                          glance.store.check_location_metadata,
                          m)

    def test_list_bad(self):
        m = {'key1': [u'somevalue', object()]}
        self.assertRaises(glance.store.BackendException,
                          glance.store.check_location_metadata,
                          m)

    def test_nested_dict_bad(self):
        inner = {'key1': u'somevalue', 'key2': object()}
        inner = {'newkey': inner}
        inner = {'anotherkey': inner}
        m = {'topkey': inner}

        self.assertRaises(glance.store.BackendException,
                          glance.store.check_location_metadata,
                          m)


class TestStoreAddToBackend(utils.BaseTestCase):

    def setUp(self):
        super(TestStoreAddToBackend, self).setUp()
        self.image_id = "animage"
        self.data = "dataandstuff"
        self.size = len(self.data)
        self.location = "file:///ab/cde/fgh"
        self.checksum = "md5"
        self.mox = mox.Mox()

    def tearDown(self):
        super(TestStoreAddToBackend, self).tearDown()
        self.mox.UnsetStubs()

    def _bad_metadata(self, in_metadata):
        store = self.mox.CreateMockAnything()
        store.add(self.image_id, mox.IgnoreArg(), self.size).AndReturn(
            (self.location, self.size, self.checksum, in_metadata))
        store.__str__ = lambda: "hello"
        store.__unicode__ = lambda: "hello"

        self.mox.ReplayAll()

        self.assertRaises(glance.store.BackendException,
                          glance.store.store_add_to_backend,
                          self.image_id,
                          self.data,
                          self.size,
                          store)
        self.mox.VerifyAll()

    def _good_metadata(self, in_metadata):

        store = self.mox.CreateMockAnything()
        store.add(self.image_id, mox.IgnoreArg(), self.size).AndReturn(
            (self.location, self.size, self.checksum, in_metadata))

        self.mox.ReplayAll()
        (location,
         size,
         checksum,
         metadata) = glance.store.store_add_to_backend(self.image_id,
                                                       self.data,
                                                       self.size,
                                                       store)
        self.mox.VerifyAll()
        self.assertEqual(self.location, location)
        self.assertEqual(self.size, size)
        self.assertEqual(self.checksum, checksum)
        self.assertEqual(in_metadata, metadata)

    def test_empty(self):
        metadata = {}
        self._good_metadata(metadata)

    def test_string(self):
        metadata = {'key': u'somevalue'}
        self._good_metadata(metadata)

    def test_list(self):
        m = {'key': [u'somevalue', u'2']}
        self._good_metadata(m)

    def test_unicode_dict(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        m = {'topkey': inner}
        self._good_metadata(m)

    def test_unicode_dict_list(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        m = {'topkey': inner, 'list': [u'somevalue', u'2'], 'u': u'2'}
        self._good_metadata(m)

    def test_nested_dict(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue'}
        inner = {'newkey': inner}
        inner = {'anotherkey': inner}
        m = {'topkey': inner}
        self._good_metadata(m)

    def test_bad_top_level_nonunicode(self):
        metadata = {'key': 'a string'}
        self._bad_metadata(metadata)

    def test_bad_nonunicode_dict_list(self):
        inner = {'key1': u'somevalue', 'key2': u'somevalue',
                 'k3': [1, object()]}
        m = {'topkey': inner, 'list': [u'somevalue', u'2'], 'u': u'2'}
        self._bad_metadata(m)

    def test_bad_metadata_not_dict(self):
        store = self.mox.CreateMockAnything()
        store.add(self.image_id, mox.IgnoreArg(), self.size).AndReturn(
            (self.location, self.size, self.checksum, []))
        store.__str__ = lambda: "hello"
        store.__unicode__ = lambda: "hello"

        self.mox.ReplayAll()

        self.assertRaises(glance.store.BackendException,
                          glance.store.store_add_to_backend,
                          self.image_id,
                          self.data,
                          self.size,
                          store)
        self.mox.VerifyAll()
