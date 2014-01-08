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

import mock
from six.moves import xrange

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


class TestProxyRepoPlain(test_utils.BaseTestCase):
    def setUp(self):
        super(TestProxyRepoPlain, self).setUp()
        self.fake_repo = FakeRepo()
        self.proxy_repo = proxy.Repo(self.fake_repo)

    def _test_method(self, name, base_result, *args, **kwargs):
        self.fake_repo.result = base_result
        method = getattr(self.proxy_repo, name)
        proxy_result = method(*args, **kwargs)
        self.assertEqual(proxy_result, base_result)
        self.assertEqual(self.fake_repo.args, args)
        self.assertEqual(self.fake_repo.kwargs, kwargs)

    def test_get(self):
        self._test_method('get', 'snarf', 'abcd')

    def test_list(self):
        self._test_method('list', ['sniff', 'snarf'], 2, filter='^sn')

    def test_add(self):
        self._test_method('add', 'snuff', 'enough')

    def test_save(self):
        self._test_method('save', 'snuff', 'enough')

    def test_remove(self):
        self._test_method('add', None, 'flying')


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
        self.assertEqual(proxy_result.base, base_result)
        self.assertEqual(len(proxy_result.args), 0)
        self.assertEqual(proxy_result.kwargs, {'a': 1})
        self.assertEqual(self.fake_repo.args, args)
        self.assertEqual(self.fake_repo.kwargs, kwargs)

    def test_get(self):
        self.fake_repo.result = 'snarf'
        result = self.proxy_repo.get('some-id')
        self.assertIsInstance(result, FakeProxy)
        self.assertEqual(self.fake_repo.args, ('some-id',))
        self.assertEqual(self.fake_repo.kwargs, {})
        self.assertEqual(result.base, 'snarf')
        self.assertEqual(result.args, tuple())
        self.assertEqual(result.kwargs, {'a': 1})

    def test_list(self):
        self.fake_repo.result = ['scratch', 'sniff']
        results = self.proxy_repo.list(2, prefix='s')
        self.assertEqual(self.fake_repo.args, (2,))
        self.assertEqual(self.fake_repo.kwargs, {'prefix': 's'})
        self.assertEqual(len(results), 2)
        for i in xrange(2):
            self.assertIsInstance(results[i], FakeProxy)
            self.assertEqual(results[i].base, self.fake_repo.result[i])
            self.assertEqual(results[i].args, tuple())
            self.assertEqual(results[i].kwargs, {'a': 1})

    def _test_method_with_proxied_argument(self, name, result):
        self.fake_repo.result = result
        item = FakeProxy('snoop')
        method = getattr(self.proxy_repo, name)
        proxy_result = method(item)

        self.assertEqual(self.fake_repo.args, ('snoop',))
        self.assertEqual(self.fake_repo.kwargs, {})

        if result is None:
            self.assertTrue(proxy_result is None)
        else:
            self.assertIsInstance(proxy_result, FakeProxy)
            self.assertEqual(proxy_result.base, result)
            self.assertEqual(proxy_result.args, tuple())
            self.assertEqual(proxy_result.kwargs, {'a': 1})

    def test_add(self):
        self._test_method_with_proxied_argument('add', 'dog')

    def test_add_with_no_result(self):
        self._test_method_with_proxied_argument('add', None)

    def test_save(self):
        self._test_method_with_proxied_argument('save', 'dog')

    def test_save_with_no_result(self):
        self._test_method_with_proxied_argument('save', None)

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
        self.assertEqual(image, 'eddard')
        self.assertEqual(self.factory.kwargs, {'a': 1, 'b': 'two'})

    def test_proxy_wrapping(self):
        proxy_factory = proxy.ImageFactory(self.factory,
                                           proxy_class=FakeProxy,
                                           proxy_kwargs={'dog': 'bark'})
        self.factory.result = 'stark'
        image = proxy_factory.new_image(a=1, b='two')
        self.assertIsInstance(image, FakeProxy)
        self.assertEqual(image.base, 'stark')
        self.assertEqual(self.factory.kwargs, {'a': 1, 'b': 'two'})


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
        self.assertEqual(membership, 'tyrion')
        self.assertEqual(self.factory.image, 'jaime')
        self.assertEqual(self.factory.member_id, 'cersei')

    def test_proxy_wrapped_membership(self):
        proxy_factory = proxy.ImageMembershipFactory(
            self.factory, member_proxy_class=FakeProxy,
            member_proxy_kwargs={'a': 1})
        self.factory.result = 'tyrion'
        membership = proxy_factory.new_image_member('jaime', 'cersei')
        self.assertIsInstance(membership, FakeProxy)
        self.assertEqual(membership.base, 'tyrion')
        self.assertEqual(membership.kwargs, {'a': 1})
        self.assertEqual(self.factory.image, 'jaime')
        self.assertEqual(self.factory.member_id, 'cersei')

    def test_proxy_wrapped_image(self):
        proxy_factory = proxy.ImageMembershipFactory(
            self.factory, image_proxy_class=FakeProxy)
        self.factory.result = 'tyrion'
        image = FakeProxy('jaime')
        membership = proxy_factory.new_image_member(image, 'cersei')
        self.assertEqual(membership, 'tyrion')
        self.assertEqual(self.factory.image, 'jaime')
        self.assertEqual(self.factory.member_id, 'cersei')

    def test_proxy_both_wrapped(self):
        class FakeProxy2(FakeProxy):
            pass

        proxy_factory = proxy.ImageMembershipFactory(
            self.factory,
            member_proxy_class=FakeProxy,
            member_proxy_kwargs={'b': 2},
            image_proxy_class=FakeProxy2)

        self.factory.result = 'tyrion'
        image = FakeProxy2('jaime')
        membership = proxy_factory.new_image_member(image, 'cersei')
        self.assertIsInstance(membership, FakeProxy)
        self.assertEqual(membership.base, 'tyrion')
        self.assertEqual(membership.kwargs, {'b': 2})
        self.assertEqual(self.factory.image, 'jaime')
        self.assertEqual(self.factory.member_id, 'cersei')


class FakeImage(object):
    def __init__(self, result=None):
        self.result = result

    def get_member_repo(self):
        return self.result


class TestImage(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImage, self).setUp()
        self.image = FakeImage()

    def test_normal_member_repo(self):
        proxy_image = proxy.Image(self.image)
        self.image.result = 'mormont'
        self.assertEqual(proxy_image.get_member_repo(), 'mormont')

    def test_proxied_member_repo(self):
        proxy_image = proxy.Image(self.image,
                                  member_repo_proxy_class=FakeProxy,
                                  member_repo_proxy_kwargs={'a': 10})
        self.image.result = 'corn'
        member_repo = proxy_image.get_member_repo()
        self.assertIsInstance(member_repo, FakeProxy)
        self.assertEqual(member_repo.base, 'corn')


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

        proxy_factory.new_task_details("task_01", "input")

        self.factory.new_task_details.assert_called_once_with(
            "task_01",
            "input",
            None, None
        )

    def test_proxy_wrapping(self):
        proxy_factory = proxy.TaskFactory(
            self.factory,
            task_proxy_class=FakeProxy,
            task_proxy_kwargs={'dog': 'bark'},
            task_details_proxy_class=FakeProxy,
            task_details_proxy_kwargs={'dog': 'bark'})

        self.factory.new_task.return_value = 'fake_task'
        self.factory.new_task_details.return_value = 'fake_task_detail'

        task = proxy_factory.new_task(
            type=self.fake_type,
            owner=self.fake_owner
        )

        self.factory.new_task.assert_called_once_with(
            type=self.fake_type,
            owner=self.fake_owner
        )
        self.assertIsInstance(task, FakeProxy)
        self.assertEqual(task.base, 'fake_task')

        task_details = proxy_factory.new_task_details('task_01', "input")

        self.factory.new_task_details.assert_called_once_with(
            'task_01',
            "input",
            None, None
        )

        self.assertIsInstance(task_details, FakeProxy)
        self.assertEqual(task_details.base, 'fake_task_detail')
