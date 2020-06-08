# Copyright 2013, Red Hat, Inc.
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
import copy
from unittest import mock
from unittest.mock import patch
import uuid

from oslo_utils import encodeutils
from oslo_utils import units

# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.common import exception
from glance.common import store_utils
import glance.quota
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils as test_utils

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class FakeContext(object):
    owner = 'someone'
    is_admin = False


class FakeImage(object):
    size = None
    image_id = 'someid'
    locations = [{'url': 'file:///not/a/path', 'metadata': {}}]
    tags = set([])

    def set_data(self, data, size=None, backend=None, set_active=True):
        self.size = 0
        for d in data:
            self.size += len(d)

    def __init__(self, **kwargs):
        self.extra_properties = kwargs.get('extra_properties', {})


class TestImageQuota(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageQuota, self).setUp()

    def _get_image(self, location_count=1, image_size=10):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = 'xyz'
        base_image.size = image_size
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        locations = []
        for i in range(location_count):
            locations.append({'url': 'file:///g/there/it/is%d' % i,
                              'metadata': {}, 'status': 'active'})
        image_values = {'id': 'xyz', 'owner': context.owner,
                        'status': 'active', 'size': image_size,
                        'locations': locations}
        db_api.image_create(context, image_values)
        return image

    def test_quota_allowed(self):
        quota = 10
        self.config(user_storage_quota=str(quota))
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = 'id'
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        data = '*' * quota
        base_image.set_data(data, size=None)
        image.set_data(data)
        self.assertEqual(quota, base_image.size)

    def _test_quota_allowed_unit(self, data_length, config_quota):
        self.config(user_storage_quota=config_quota)
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = 'id'
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        data = '*' * data_length
        base_image.set_data(data, size=None)
        image.set_data(data)
        self.assertEqual(data_length, base_image.size)

    def test_quota_allowed_unit_b(self):
        self._test_quota_allowed_unit(10, '10B')

    def test_quota_allowed_unit_kb(self):
        self._test_quota_allowed_unit(10, '1KB')

    def test_quota_allowed_unit_mb(self):
        self._test_quota_allowed_unit(10, '1MB')

    def test_quota_allowed_unit_gb(self):
        self._test_quota_allowed_unit(10, '1GB')

    def test_quota_allowed_unit_tb(self):
        self._test_quota_allowed_unit(10, '1TB')

    def _quota_exceeded_size(self, quota, data,
                             deleted=True, size=None):
        self.config(user_storage_quota=quota)
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = 'id'
        image = glance.quota.ImageProxy(base_image, context, db_api, store)

        if deleted:
            with patch.object(store_utils, 'safe_delete_from_backend'):
                store_utils.safe_delete_from_backend(
                    context,
                    image.image_id,
                    base_image.locations[0])

        self.assertRaises(exception.StorageQuotaFull,
                          image.set_data,
                          data,
                          size=size)

    def test_quota_exceeded_no_size(self):
        quota = 10
        data = '*' * (quota + 1)
        # NOTE(jbresnah) When the image size is None it means that it is
        # not known.  In this case the only time we will raise an
        # exception is when there is no room left at all, thus we know
        # it will not fit.
        # That's why 'get_remaining_quota' is mocked with return_value = 0.
        with patch.object(glance.api.common, 'get_remaining_quota',
                          return_value=0):
            self._quota_exceeded_size(str(quota), data)

    def test_quota_exceeded_with_right_size(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size(str(quota), data, size=len(data),
                                  deleted=False)

    def test_quota_exceeded_with_right_size_b(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size('10B', data, size=len(data),
                                  deleted=False)

    def test_quota_exceeded_with_right_size_kb(self):
        quota = units.Ki
        data = '*' * (quota + 1)
        self._quota_exceeded_size('1KB', data, size=len(data),
                                  deleted=False)

    def test_quota_exceeded_with_lie_size(self):
        quota = 10
        data = '*' * (quota + 1)
        self._quota_exceeded_size(str(quota), data, deleted=False,
                                  size=quota - 1)

    def test_append_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {},
                        'status': 'active'}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.append(new_location)
        pre_add_locations.append(new_location)
        self.assertEqual(image.locations, pre_add_locations)

    def test_insert_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {},
                        'status': 'active'}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.insert(0, new_location)
        pre_add_locations.insert(0, new_location)
        self.assertEqual(image.locations, pre_add_locations)

    def test_extend_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {},
                        'status': 'active'}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations.extend([new_location])
        pre_add_locations.extend([new_location])
        self.assertEqual(image.locations, pre_add_locations)

    def test_iadd_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {},
                        'status': 'active'}
        image = self._get_image()
        pre_add_locations = image.locations[:]
        image.locations += [new_location]
        pre_add_locations += [new_location]
        self.assertEqual(image.locations, pre_add_locations)

    def test_set_location(self):
        new_location = {'url': 'file:///a/path', 'metadata': {},
                        'status': 'active'}
        image = self._get_image()
        image.locations = [new_location]
        self.assertEqual(image.locations, [new_location])

    def _make_image_with_quota(self, image_size=10, location_count=2):
        quota = image_size * location_count
        self.config(user_storage_quota=str(quota))
        return self._get_image(image_size=image_size,
                               location_count=location_count)

    def test_exceed_append_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.append,
                          {'url': 'file:///a/path', 'metadata': {},
                           'status': 'active'})

    def test_exceed_insert_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.insert,
                          0,
                          {'url': 'file:///a/path', 'metadata': {},
                           'status': 'active'})

    def test_exceed_extend_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.extend,
                          [{'url': 'file:///a/path', 'metadata': {},
                            'status': 'active'}])

    def test_set_location_under(self):
        image = self._make_image_with_quota(location_count=1)
        image.locations = [{'url': 'file:///a/path', 'metadata': {},
                            'status': 'active'}]

    def test_set_location_exceed(self):
        image = self._make_image_with_quota(location_count=1)
        try:
            image.locations = [{'url': 'file:///a/path', 'metadata': {},
                                'status': 'active'},
                               {'url': 'file:///a/path2', 'metadata': {},
                                'status': 'active'}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass

    def test_iadd_location_exceed(self):
        image = self._make_image_with_quota(location_count=1)
        try:
            image.locations += [{'url': 'file:///a/path', 'metadata': {},
                                 'status': 'active'}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass

    def test_append_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        self.assertIsNone(image.size)

        self.mock_object(store_api, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)
        image.locations.append({'url': 'file:///fake.img.tar.gz',
                                'metadata': {}})
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)

    def test_insert_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        self.assertIsNone(image.size)

        self.mock_object(store_api, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)
        image.locations.insert(0,
                               {'url': 'file:///fake.img.tar.gz',
                                'metadata': {}})
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)

    def test_set_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        self.assertIsNone(image.size)

        self.mock_object(store_api, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)
        image.locations = [{'url': 'file:///fake.img.tar.gz', 'metadata': {}}]
        self.assertEqual([{'url': 'file:///fake.img.tar.gz', 'metadata': {}}],
                         image.locations)

    def test_iadd_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api, store)
        self.assertIsNone(image.size)

        self.mock_object(store_api, 'get_size_from_backend',
                         unit_test_utils.fake_get_size_from_backend)
        image.locations += [{'url': 'file:///fake.img.tar.gz', 'metadata': {}}]
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)


class TestImagePropertyQuotas(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImagePropertyQuotas, self).setUp()
        self.base_image = FakeImage()
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()
        self.image_repo_mock.add.return_value = self.base_image
        self.image_repo_mock.save.return_value = self.base_image

        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock(),
            mock.Mock())

    def test_save_image_with_image_property(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.save(self.image)

        self.image_repo_mock.save.assert_called_once_with(self.base_image,
                                                          from_state=None)

    def test_save_image_too_many_image_properties(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar', 'foo2': 'bar2'}
        exc = self.assertRaises(exception.ImagePropertyLimitExceeded,
                                self.image_repo_proxy.save, self.image)
        self.assertIn("Attempted: 2, Maximum: 1",
                      encodeutils.exception_to_unicode(exc))

    def test_save_image_unlimited_image_properties(self):
        self.config(image_property_quota=-1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.save(self.image)

        self.image_repo_mock.save.assert_called_once_with(self.base_image,
                                                          from_state=None)

    def test_add_image_with_image_property(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.add(self.image)

        self.image_repo_mock.add.assert_called_once_with(self.base_image)

    def test_add_image_too_many_image_properties(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar', 'foo2': 'bar2'}
        exc = self.assertRaises(exception.ImagePropertyLimitExceeded,
                                self.image_repo_proxy.add, self.image)
        self.assertIn("Attempted: 2, Maximum: 1",
                      encodeutils.exception_to_unicode(exc))

    def test_add_image_unlimited_image_properties(self):
        self.config(image_property_quota=-1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.add(self.image)

        self.image_repo_mock.add.assert_called_once_with(self.base_image)

    def _quota_exceed_setup(self):
        self.config(image_property_quota=2)
        self.base_image.extra_properties = {'foo': 'bar', 'spam': 'ham'}
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock(),
                                             mock.Mock())

    def test_modify_image_properties_when_quota_exceeded(self):
        self._quota_exceed_setup()
        self.config(image_property_quota=1)
        self.image.extra_properties = {'foo': 'frob', 'spam': 'eggs'}
        self.image_repo_proxy.save(self.image)
        self.image_repo_mock.save.assert_called_once_with(self.base_image,
                                                          from_state=None)
        self.assertEqual('frob', self.base_image.extra_properties['foo'])
        self.assertEqual('eggs', self.base_image.extra_properties['spam'])

    def test_delete_image_properties_when_quota_exceeded(self):
        self._quota_exceed_setup()
        self.config(image_property_quota=1)
        del self.image.extra_properties['foo']
        self.image_repo_proxy.save(self.image)
        self.image_repo_mock.save.assert_called_once_with(self.base_image,
                                                          from_state=None)
        self.assertNotIn('foo', self.base_image.extra_properties)
        self.assertEqual('ham', self.base_image.extra_properties['spam'])

    def test_invalid_quota_config_parameter(self):
        self.config(user_storage_quota='foo')
        location = {"url": "file:///fake.img.tar.gz", "metadata": {}}
        self.assertRaises(exception.InvalidOptionValue,
                          self.image.locations.append, location)

    def test_exceed_quota_during_patch_operation(self):
        self._quota_exceed_setup()
        self.image.extra_properties['frob'] = 'baz'
        self.image.extra_properties['lorem'] = 'ipsum'
        self.assertEqual('bar', self.base_image.extra_properties['foo'])
        self.assertEqual('ham', self.base_image.extra_properties['spam'])
        self.assertEqual('baz', self.base_image.extra_properties['frob'])
        self.assertEqual('ipsum', self.base_image.extra_properties['lorem'])

        del self.image.extra_properties['frob']
        del self.image.extra_properties['lorem']
        self.image_repo_proxy.save(self.image)
        call_args = mock.call(self.base_image, from_state=None)
        self.assertEqual(call_args, self.image_repo_mock.save.call_args)
        self.assertEqual('bar', self.base_image.extra_properties['foo'])
        self.assertEqual('ham', self.base_image.extra_properties['spam'])
        self.assertNotIn('frob', self.base_image.extra_properties)
        self.assertNotIn('lorem', self.base_image.extra_properties)

    def test_quota_exceeded_after_delete_image_properties(self):
        self.config(image_property_quota=3)
        self.base_image.extra_properties = {'foo': 'bar',
                                            'spam': 'ham',
                                            'frob': 'baz'}
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock(),
                                             mock.Mock())
        self.config(image_property_quota=1)
        del self.image.extra_properties['foo']
        self.image_repo_proxy.save(self.image)
        self.image_repo_mock.save.assert_called_once_with(self.base_image,
                                                          from_state=None)
        self.assertNotIn('foo', self.base_image.extra_properties)
        self.assertEqual('ham', self.base_image.extra_properties['spam'])
        self.assertEqual('baz', self.base_image.extra_properties['frob'])


class TestImageTagQuotas(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageTagQuotas, self).setUp()
        self.base_image = mock.Mock()
        self.base_image.tags = set([])
        self.base_image.extra_properties = {}
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()
        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock(),
            mock.Mock())

    def test_replace_image_tag(self):
        self.config(image_tag_quota=1)
        self.image.tags = ['foo']
        self.assertEqual(1, len(self.image.tags))

    def test_replace_too_many_image_tags(self):
        self.config(image_tag_quota=0)

        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                setattr, self.image, 'tags', ['foo', 'bar'])
        self.assertIn('Attempted: 2, Maximum: 0',
                      encodeutils.exception_to_unicode(exc))
        self.assertEqual(0, len(self.image.tags))

    def test_replace_unlimited_image_tags(self):
        self.config(image_tag_quota=-1)
        self.image.tags = ['foo']
        self.assertEqual(1, len(self.image.tags))

    def test_add_image_tag(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        self.assertEqual(1, len(self.image.tags))

    def test_add_too_many_image_tags(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                self.image.tags.add, 'bar')
        self.assertIn('Attempted: 2, Maximum: 1',
                      encodeutils.exception_to_unicode(exc))

    def test_add_unlimited_image_tags(self):
        self.config(image_tag_quota=-1)
        self.image.tags.add('foo')
        self.assertEqual(1, len(self.image.tags))

    def test_remove_image_tag_while_over_quota(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        self.assertEqual(1, len(self.image.tags))
        self.config(image_tag_quota=0)
        self.image.tags.remove('foo')
        self.assertEqual(0, len(self.image.tags))


class TestQuotaImageTagsProxy(test_utils.BaseTestCase):

    def setUp(self):
        super(TestQuotaImageTagsProxy, self).setUp()

    def test_add(self):
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        proxy.add('foo')
        self.assertIn('foo', proxy)

    def test_add_too_many_tags(self):
        self.config(image_tag_quota=0)
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                proxy.add, 'bar')
        self.assertIn('Attempted: 1, Maximum: 0',
                      encodeutils.exception_to_unicode(exc))

    def test_equals(self):
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        self.assertEqual(set([]), proxy)

    def test_not_equals(self):
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        self.assertNotEqual('foo', proxy)

    def test_contains(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['foo']))
        self.assertIn('foo', proxy)

    def test_len(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['foo',
                                                      'bar',
                                                      'baz',
                                                      'niz']))
        self.assertEqual(4, len(proxy))

    def test_iter(self):
        items = set(['foo', 'bar', 'baz', 'niz'])
        proxy = glance.quota.QuotaImageTagsProxy(items.copy())
        self.assertEqual(4, len(items))
        for item in proxy:
            items.remove(item)
        self.assertEqual(0, len(items))

    def test_tags_attr_no_loop(self):
        proxy = glance.quota.QuotaImageTagsProxy(None)
        self.assertEqual(set([]), proxy.tags)

    def test_tags_deepcopy(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['a', 'b']))
        proxy_copy = copy.deepcopy(proxy)
        self.assertEqual(set(['a', 'b']), proxy_copy.tags)
        self.assertIn('a', proxy_copy)
        # remove is a found via __getattr__
        proxy_copy.remove('a')
        self.assertNotIn('a', proxy_copy)

    def test_tags_delete(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['a', 'b']))
        self.assertEqual(set(['a', 'b']), proxy.tags)
        del proxy.tags
        self.assertIsNone(proxy.tags)


class TestImageMemberQuotas(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageMemberQuotas, self).setUp()
        db_api = unit_test_utils.FakeDB()
        store_api = unit_test_utils.FakeStoreAPI()
        store = unit_test_utils.FakeStoreUtils(store_api)
        context = FakeContext()
        self.image = mock.Mock()
        self.base_image_member_factory = mock.Mock()
        self.image_member_factory = glance.quota.ImageMemberFactoryProxy(
            self.base_image_member_factory, context,
            db_api, store)

    def test_new_image_member(self):
        self.config(image_member_quota=1)

        self.image_member_factory.new_image_member(self.image,
                                                   'fake_id')
        nim = self.base_image_member_factory.new_image_member
        nim.assert_called_once_with(self.image, 'fake_id')

    def test_new_image_member_unlimited_members(self):
        self.config(image_member_quota=-1)

        self.image_member_factory.new_image_member(self.image,
                                                   'fake_id')
        nim = self.base_image_member_factory.new_image_member
        nim.assert_called_once_with(self.image, 'fake_id')

    def test_new_image_member_too_many_members(self):
        self.config(image_member_quota=0)

        self.assertRaises(exception.ImageMemberLimitExceeded,
                          self.image_member_factory.new_image_member,
                          self.image, 'fake_id')


class TestImageLocationQuotas(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageLocationQuotas, self).setUp()
        self.base_image = mock.Mock()
        self.base_image.locations = []
        self.base_image.size = 1
        self.base_image.extra_properties = {}
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()
        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock(),
            mock.Mock())

    def test_replace_image_location(self):
        self.config(image_location_quota=1)
        self.image.locations = [{"url": "file:///fake.img.tar.gz",
                                 "metadata": {}
                                 }]
        self.assertEqual(1, len(self.image.locations))

    def test_replace_too_many_image_locations(self):
        self.config(image_location_quota=1)
        self.image.locations = [{"url": "file:///fake.img.tar.gz",
                                 "metadata": {}}
                                ]
        locations = [
            {"url": "file:///fake1.img.tar.gz", "metadata": {}},
            {"url": "file:///fake2.img.tar.gz", "metadata": {}},
            {"url": "file:///fake3.img.tar.gz", "metadata": {}}
        ]
        exc = self.assertRaises(exception.ImageLocationLimitExceeded,
                                setattr, self.image, 'locations', locations)
        self.assertIn('Attempted: 3, Maximum: 1',
                      encodeutils.exception_to_unicode(exc))
        self.assertEqual(1, len(self.image.locations))

    def test_replace_unlimited_image_locations(self):
        self.config(image_location_quota=-1)
        self.image.locations = [{"url": "file:///fake.img.tar.gz",
                                 "metadata": {}}
                                ]
        self.assertEqual(1, len(self.image.locations))

    def test_add_image_location(self):
        self.config(image_location_quota=1)
        location = {"url": "file:///fake.img.tar.gz", "metadata": {}}
        self.image.locations.append(location)
        self.assertEqual(1, len(self.image.locations))

    def test_add_too_many_image_locations(self):
        self.config(image_location_quota=1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        location2 = {"url": "file:///fake2.img.tar.gz", "metadata": {}}
        exc = self.assertRaises(exception.ImageLocationLimitExceeded,
                                self.image.locations.append, location2)
        self.assertIn('Attempted: 2, Maximum: 1',
                      encodeutils.exception_to_unicode(exc))

    def test_add_unlimited_image_locations(self):
        self.config(image_location_quota=-1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        self.assertEqual(1, len(self.image.locations))

    def test_remove_image_location_while_over_quota(self):
        self.config(image_location_quota=1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        self.assertEqual(1, len(self.image.locations))
        self.config(image_location_quota=0)
        self.image.locations.remove(location1)
        self.assertEqual(0, len(self.image.locations))
