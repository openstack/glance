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

import mock
from mock import patch
import uuid

import six

from glance.common import exception
import glance.quota
import glance.store
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

    def set_data(self, data, size=None):
        self.size = 0
        for d in data:
            self.size += len(d)


class TestImageQuota(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageQuota, self).setUp()

    def tearDown(self):
        super(TestImageQuota, self).tearDown()

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
            with patch.object(glance.store, 'safe_delete_from_backend'):
                glance.store.safe_delete_from_backend(
                    context,
                    base_image.locations[0]['url'],
                    image.image_id)

        self.assertRaises(exception.StorageQuotaFull,
                          image.set_data,
                          data,
                          size=size)

    def test_quota_exceeded_no_size(self):
        quota = 10
        data = '*' * (quota + 1)
        #NOTE(jbresnah) When the image size is None it means that it is
        # not known.  In this case the only time we will raise an
        # exception is when there is no room left at all, thus we know
        # it will not fit.
        # That's why 'get_remaining_quota' is mocked with return_value = 0.
        with patch.object(glance.api.common, 'get_remaining_quota',
                          return_value=0):
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

    def _make_image_with_quota(self, image_size=10, location_count=2):
        quota = image_size * location_count
        self.config(user_storage_quota=quota)
        return self._get_image(image_size=image_size,
                               location_count=location_count)

    def test_exceed_append_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.append,
                          {'url': 'file:///a/path', 'metadata': {}})

    def test_exceed_insert_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.insert,
                          0,
                          {'url': 'file:///a/path', 'metadata': {}})

    def test_exceed_extend_location(self):
        image = self._make_image_with_quota()
        self.assertRaises(exception.StorageQuotaFull,
                          image.locations.extend,
                          [{'url': 'file:///a/path', 'metadata': {}}])

    def test_set_location_under(self):
        image = self._make_image_with_quota(location_count=1)
        image.locations = [{'url': 'file:///a/path', 'metadata': {}}]

    def test_set_location_exceed(self):
        image = self._make_image_with_quota(location_count=1)
        try:
            image.locations = [{'url': 'file:///a/path', 'metadata': {}},
                               {'url': 'file:///a/path2', 'metadata': {}}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass

    def test_iadd_location_exceed(self):
        image = self._make_image_with_quota(location_count=1)
        try:
            image.locations += [{'url': 'file:///a/path', 'metadata': {}}]
            self.fail('Should have raised the quota exception')
        except exception.StorageQuotaFull:
            pass

    def test_append_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api)
        self.assertIsNone(image.size)

        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        image.locations.append({'url': 'file:///fake.img.tar.gz',
                                'metadata': {}})
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)

    def test_insert_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api)
        self.assertIsNone(image.size)

        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        image.locations.insert(0,
                               {'url': 'file:///fake.img.tar.gz',
                                'metadata': {}})
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)

    def test_set_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api)
        self.assertIsNone(image.size)

        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        image.locations = [{'url': 'file:///fake.img.tar.gz', 'metadata': {}}]
        self.assertEqual([{'url': 'file:///fake.img.tar.gz', 'metadata': {}}],
                         image.locations)

    def test_iadd_location_for_queued_image(self):
        context = FakeContext()
        db_api = unit_test_utils.FakeDB()
        base_image = FakeImage()
        base_image.image_id = str(uuid.uuid4())
        image = glance.quota.ImageProxy(base_image, context, db_api)
        self.assertIsNone(image.size)

        self.stubs.Set(glance.store, 'get_size_from_backend',
                       unit_test_utils.fake_get_size_from_backend)
        image.locations += [{'url': 'file:///fake.img.tar.gz', 'metadata': {}}]
        self.assertIn({'url': 'file:///fake.img.tar.gz', 'metadata': {}},
                      image.locations)


class TestImagePropertyQuotas(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImagePropertyQuotas, self).setUp()
        self.base_image = mock.Mock()
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()

        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock())

    def test_save_image_with_image_property(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.save(self.image)

        self.image_repo_mock.save.assert_called_once_with(self.base_image)

    def test_save_image_too_many_image_properties(self):
        self.config(image_property_quota=1)

        self.image.extra_properties = {'foo': 'bar', 'foo2': 'bar2'}
        exc = self.assertRaises(exception.ImagePropertyLimitExceeded,
                                self.image_repo_proxy.save, self.image)
        self.assertTrue("Attempted: 2, Maximum: 1" in six.text_type(exc))

    def test_save_image_unlimited_image_properties(self):
        self.config(image_property_quota=-1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.save(self.image)

        self.image_repo_mock.save.assert_called_once_with(self.base_image)

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
        self.assertTrue("Attempted: 2, Maximum: 1" in six.text_type(exc))

    def test_add_image_unlimited_image_properties(self):
        self.config(image_property_quota=-1)

        self.image.extra_properties = {'foo': 'bar'}
        self.image_repo_proxy.add(self.image)

        self.image_repo_mock.add.assert_called_once_with(self.base_image)


class TestImageTagQuotas(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageTagQuotas, self).setUp()
        self.base_image = mock.Mock()
        self.base_image.tags = set([])
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()
        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock())

    def test_replace_image_tag(self):
        self.config(image_tag_quota=1)
        self.image.tags = ['foo']
        self.assertEqual(len(self.image.tags), 1)

    def test_replace_too_many_image_tags(self):
        self.config(image_tag_quota=0)

        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                setattr, self.image, 'tags', ['foo', 'bar'])
        self.assertTrue('Attempted: 2, Maximum: 0' in six.text_type(exc))
        self.assertEqual(len(self.image.tags), 0)

    def test_replace_unlimited_image_tags(self):
        self.config(image_tag_quota=-1)
        self.image.tags = ['foo']
        self.assertEqual(len(self.image.tags), 1)

    def test_add_image_tag(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        self.assertEqual(len(self.image.tags), 1)

    def test_add_too_many_image_tags(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                self.image.tags.add, 'bar')
        self.assertTrue('Attempted: 2, Maximum: 1' in six.text_type(exc))

    def test_add_unlimited_image_tags(self):
        self.config(image_tag_quota=-1)
        self.image.tags.add('foo')
        self.assertEqual(len(self.image.tags), 1)

    def test_remove_image_tag_while_over_quota(self):
        self.config(image_tag_quota=1)
        self.image.tags.add('foo')
        self.assertEqual(len(self.image.tags), 1)
        self.config(image_tag_quota=0)
        self.image.tags.remove('foo')
        self.assertEqual(len(self.image.tags), 0)


class TestQuotaImageTagsProxy(test_utils.BaseTestCase):
    def setUp(self):
        super(TestQuotaImageTagsProxy, self).setUp()

    def test_add(self):
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        proxy.add('foo')
        self.assertTrue('foo' in proxy)

    def test_add_too_many_tags(self):
        self.config(image_tag_quota=0)
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        exc = self.assertRaises(exception.ImageTagLimitExceeded,
                                proxy.add, 'bar')
        self.assertTrue('Attempted: 1, Maximum: 0' in six.text_type(exc))

    def test_equals(self):
        proxy = glance.quota.QuotaImageTagsProxy(set([]))
        self.assertEqual(set([]), proxy)

    def test_contains(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['foo']))
        self.assertTrue('foo' in proxy)

    def test_len(self):
        proxy = glance.quota.QuotaImageTagsProxy(set(['foo',
                                                      'bar',
                                                      'baz',
                                                      'niz']))
        self.assertEqual(len(proxy), 4)

    def test_iter(self):
        items = set(['foo', 'bar', 'baz', 'niz'])
        proxy = glance.quota.QuotaImageTagsProxy(items.copy())
        self.assertEqual(len(items), 4)
        for item in proxy:
            items.remove(item)
        self.assertEqual(len(items), 0)


class TestImageMemberQuotas(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageMemberQuotas, self).setUp()
        db_api = unit_test_utils.FakeDB()
        context = FakeContext()
        self.image = mock.Mock()
        self.base_image_member_factory = mock.Mock()
        self.image_member_factory = glance.quota.ImageMemberFactoryProxy(
            self.base_image_member_factory, context,
            db_api)

    def test_new_image_member(self):
        self.config(image_member_quota=1)

        self.image_member_factory.new_image_member(self.image,
                                                   'fake_id')
        self.base_image_member_factory.new_image_member\
            .assert_called_once_with(self.image.base, 'fake_id')

    def test_new_image_member_unlimited_members(self):
        self.config(image_member_quota=-1)

        self.image_member_factory.new_image_member(self.image,
                                                   'fake_id')
        self.base_image_member_factory.new_image_member\
            .assert_called_once_with(self.image.base, 'fake_id')

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
        self.image = glance.quota.ImageProxy(self.base_image,
                                             mock.Mock(),
                                             mock.Mock())

        self.image_repo_mock = mock.Mock()
        self.image_repo_proxy = glance.quota.ImageRepoProxy(
            self.image_repo_mock,
            mock.Mock(),
            mock.Mock())

    def test_replace_image_location(self):
        self.config(image_location_quota=1)
        self.image.locations = [{"url": "file:///fake.img.tar.gz",
                                 "metadata": {}
                                 }]
        self.assertEqual(len(self.image.locations), 1)

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
        self.assertTrue('Attempted: 3, Maximum: 1' in six.text_type(exc))
        self.assertEqual(len(self.image.locations), 1)

    def test_replace_unlimited_image_locations(self):
        self.config(image_location_quota=-1)
        self.image.locations = [{"url": "file:///fake.img.tar.gz",
                                 "metadata": {}}
                                ]
        self.assertEqual(len(self.image.locations), 1)

    def test_add_image_location(self):
        self.config(image_location_quota=1)
        location = {"url": "file:///fake.img.tar.gz", "metadata": {}}
        self.image.locations.append(location)
        self.assertEqual(len(self.image.locations), 1)

    def test_add_too_many_image_locations(self):
        self.config(image_location_quota=1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        location2 = {"url": "file:///fake2.img.tar.gz", "metadata": {}}
        exc = self.assertRaises(exception.ImageLocationLimitExceeded,
                                self.image.locations.append, location2)
        self.assertTrue('Attempted: 2, Maximum: 1' in six.text_type(exc))

    def test_add_unlimited_image_locations(self):
        self.config(image_location_quota=-1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        self.assertEqual(len(self.image.locations), 1)

    def test_remove_image_location_while_over_quota(self):
        self.config(image_location_quota=1)
        location1 = {"url": "file:///fake1.img.tar.gz", "metadata": {}}
        self.image.locations.append(location1)
        self.assertEqual(len(self.image.locations), 1)
        self.config(image_location_quota=0)
        self.image.locations.remove(location1)
        self.assertEqual(len(self.image.locations), 0)
