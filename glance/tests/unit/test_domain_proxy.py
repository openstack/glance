# Copyright 2013 OpenStack Foundation.
# Copyright 2013 IBM Corp.
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

from unittest import mock

from glance.domain import proxy
import glance.tests.utils as test_utils


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'


class FakeProxy(object):
    def __init__(self, base, *args, **kwargs):
        self.base = base
        self.args = args
        self.kwargs = kwargs


class FakeRepo(object):
    def __init__(self, result=None):
        self.args = None
        self.kwargs = None
        self.result = result

    def fake_method(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        return self.result

    get = fake_method
    list = fake_method
    add = fake_method
    save = fake_method
    remove = fake_method
    set_property_atomic = fake_method
    delete_property_atomic = fake_method


class TestProxyRepoPlain(test_utils.BaseTestCase):
    def setUp(self):
        super(TestProxyRepoPlain, self).setUp()
        self.fake_repo = FakeRepo()
        self.proxy_repo = proxy.Repo(self.fake_repo)

    def _test_method(self, name, base_result, *args, **kwargs):
        self.fake_repo.result = base_result
        method = getattr(self.proxy_repo, name)
        proxy_result = method(*args, **kwargs)
        self.assertEqual(base_result, proxy_result)
        self.assertEqual(args, self.fake_repo.args)
        self.assertEqual(kwargs, self.fake_repo.kwargs)

    def test_get(self):
        self._test_method('get', 'snarf', 'abcd')

    def test_list(self):
        self._test_method('list', ['sniff', 'snarf'], 2, filter='^sn')

    def test_add(self):
        self._test_method('add', 'snuff', 'enough')

    def test_save(self):
        self._test_method('save', 'snuff', 'enough', from_state=None)

    def test_remove(self):
        self._test_method('add', None, 'flying')

    def test_set_property_atomic(self):
        image = mock.MagicMock()
        image.image_id = 'foo'
        self._test_method('set_property_atomic', None, image, 'foo', 'bar')

    def test_set_property_nonimage(self):
        self.assertRaises(
            AssertionError,
            self._test_method,
            'set_property_atomic', None, 'notimage', 'foo', 'bar')

    def test_delete_property_atomic(self):
        image = mock.MagicMock()
        image.image_id = 'foo'
        self._test_method('delete_property_atomic', None, image, 'foo', 'bar')

    def test_delete_property_nonimage(self):
        self.assertRaises(
            AssertionError,
            self._test_method,
            'delete_property_atomic', None, 'notimage', 'foo', 'bar')


class TestProxyRepoWrapping(test_utils.BaseTestCase):
    def setUp(self):
        super(TestProxyRepoWrapping, self).setUp()
        self.fake_repo = FakeRepo()
        self.proxy_repo = proxy.Repo(self.fake_repo,
                                     item_proxy_class=FakeProxy,
                                     item_proxy_kwargs={'a': 1})

    def _test_method(self, name, base_result, *args, **kwargs):
        self.fake_repo.result = base_result
        method = getattr(self.proxy_repo, name)
        proxy_result = method(*args, **kwargs)
        self.assertIsInstance(proxy_result, FakeProxy)
        self.assertEqual(base_result, proxy_result.base)
        self.assertEqual(0, len(proxy_result.args))
        self.assertEqual({'a': 1}, proxy_result.kwargs)
        self.assertEqual(args, self.fake_repo.args)
        self.assertEqual(kwargs, self.fake_repo.kwargs)

    def test_get(self):
        self.fake_repo.result = 'snarf'
        result = self.proxy_repo.get('some-id')
        self.assertIsInstance(result, FakeProxy)
        self.assertEqual(('some-id',), self.fake_repo.args)
        self.assertEqual({}, self.fake_repo.kwargs)
        self.assertEqual('snarf', result.base)
        self.assertEqual(tuple(), result.args)
        self.assertEqual({'a': 1}, result.kwargs)

    def test_list(self):
        self.fake_repo.result = ['scratch', 'sniff']
        results = self.proxy_repo.list(2, prefix='s')
        self.assertEqual((2,), self.fake_repo.args)
        self.assertEqual({'prefix': 's'}, self.fake_repo.kwargs)
        self.assertEqual(2, len(results))
        for i in range(2):
            self.assertIsInstance(results[i], FakeProxy)
            self.assertEqual(self.fake_repo.result[i], results[i].base)
            self.assertEqual(tuple(), results[i].args)
            self.assertEqual({'a': 1}, results[i].kwargs)

    def _test_method_with_proxied_argument(self, name, result, **kwargs):
        self.fake_repo.result = result
        item = FakeProxy('snoop')
        method = getattr(self.proxy_repo, name)
        proxy_result = method(item)

        self.assertEqual(('snoop',), self.fake_repo.args)
        self.assertEqual(kwargs, self.fake_repo.kwargs)

        if result is None:
            self.assertIsNone(proxy_result)
        else:
            self.assertIsInstance(proxy_result, FakeProxy)
            self.assertEqual(result, proxy_result.base)
            self.assertEqual(tuple(), proxy_result.args)
            self.assertEqual({'a': 1}, proxy_result.kwargs)

    def test_add(self):
        self._test_method_with_proxied_argument('add', 'dog')

    def test_add_with_no_result(self):
        self._test_method_with_proxied_argument('add', None)

    def test_save(self):
        self._test_method_with_proxied_argument('save', 'dog',
                                                from_state=None)

    def test_save_with_no_result(self):
        self._test_method_with_proxied_argument('save', None,
                                                from_state=None)

    def test_remove(self):
        self._test_method_with_proxied_argument('remove', 'dog')

    def test_remove_with_no_result(self):
        self._test_method_with_proxied_argument('remove', None)


class FakeImageFactory(object):
    def __init__(self, result=None):
        self.result = None
        self.kwargs = None

    def new_image(self, **kwargs):
        self.kwargs = kwargs
        return self.result


class TestImageFactory(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageFactory, self).setUp()
        self.factory = FakeImageFactory()

    def test_proxy_plain(self):
        proxy_factory = proxy.ImageFactory(self.factory)
        self.factory.result = 'eddard'
        image = proxy_factory.new_image(a=1, b='two')
        self.assertEqual('eddard', image)
        self.assertEqual({'a': 1, 'b': 'two'}, self.factory.kwargs)

    def test_proxy_wrapping(self):
        proxy_factory = proxy.ImageFactory(self.factory,
                                           proxy_class=FakeProxy,
                                           proxy_kwargs={'dog': 'bark'})
        self.factory.result = 'stark'
        image = proxy_factory.new_image(a=1, b='two')
        self.assertIsInstance(image, FakeProxy)
        self.assertEqual('stark', image.base)
        self.assertEqual({'a': 1, 'b': 'two'}, self.factory.kwargs)


class FakeImageMembershipFactory(object):
    def __init__(self, result=None):
        self.result = None
        self.image = None
        self.member_id = None

    def new_image_member(self, image, member_id):
        self.image = image
        self.member_id = member_id
        return self.result


class TestImageMembershipFactory(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageMembershipFactory, self).setUp()
        self.factory = FakeImageMembershipFactory()

    def test_proxy_plain(self):
        proxy_factory = proxy.ImageMembershipFactory(self.factory)
        self.factory.result = 'tyrion'
        membership = proxy_factory.new_image_member('jaime', 'cersei')
        self.assertEqual('tyrion', membership)
        self.assertEqual('jaime', self.factory.image)
        self.assertEqual('cersei', self.factory.member_id)

    def test_proxy_wrapped_membership(self):
        proxy_factory = proxy.ImageMembershipFactory(
            self.factory, proxy_class=FakeProxy, proxy_kwargs={'a': 1})
        self.factory.result = 'tyrion'
        membership = proxy_factory.new_image_member('jaime', 'cersei')
        self.assertIsInstance(membership, FakeProxy)
        self.assertEqual('tyrion', membership.base)
        self.assertEqual({'a': 1}, membership.kwargs)
        self.assertEqual('jaime', self.factory.image)
        self.assertEqual('cersei', self.factory.member_id)

    def test_proxy_wrapped_image(self):
        proxy_factory = proxy.ImageMembershipFactory(
            self.factory, proxy_class=FakeProxy)
        self.factory.result = 'tyrion'
        image = FakeProxy('jaime')
        membership = proxy_factory.new_image_member(image, 'cersei')
        self.assertIsInstance(membership, FakeProxy)
        self.assertIsInstance(self.factory.image, FakeProxy)
        self.assertEqual('cersei', self.factory.member_id)

    def test_proxy_both_wrapped(self):
        class FakeProxy2(FakeProxy):
            pass

        proxy_factory = proxy.ImageMembershipFactory(
            self.factory,
            proxy_class=FakeProxy,
            proxy_kwargs={'b': 2})

        self.factory.result = 'tyrion'
        image = FakeProxy2('jaime')
        membership = proxy_factory.new_image_member(image, 'cersei')
        self.assertIsInstance(membership, FakeProxy)
        self.assertEqual('tyrion', membership.base)
        self.assertEqual({'b': 2}, membership.kwargs)
        self.assertIsInstance(self.factory.image, FakeProxy2)
        self.assertEqual('cersei', self.factory.member_id)


class FakeImage(object):
    def __init__(self, result=None):
        self.result = result


class TestTaskFactory(test_utils.BaseTestCase):
    def setUp(self):
        super(TestTaskFactory, self).setUp()
        self.factory = mock.Mock()
        self.fake_type = 'import'
        self.fake_owner = "owner"

    def test_proxy_plain(self):
        proxy_factory = proxy.TaskFactory(self.factory)

        proxy_factory.new_task(
            type=self.fake_type,
            owner=self.fake_owner
        )

        self.factory.new_task.assert_called_once_with(
            type=self.fake_type,
            owner=self.fake_owner
        )

    def test_proxy_wrapping(self):
        proxy_factory = proxy.TaskFactory(
            self.factory,
            task_proxy_class=FakeProxy,
            task_proxy_kwargs={'dog': 'bark'})

        self.factory.new_task.return_value = 'fake_task'

        task = proxy_factory.new_task(
            type=self.fake_type,
            owner=self.fake_owner
        )

        self.factory.new_task.assert_called_once_with(
            type=self.fake_type,
            owner=self.fake_owner
        )
        self.assertIsInstance(task, FakeProxy)
        self.assertEqual('fake_task', task.base)
