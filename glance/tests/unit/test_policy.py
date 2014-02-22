# Copyright 2012 OpenStack Foundation
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

import os.path

import mock
import oslo.config.cfg

import glance.api.policy
from glance.common import exception
import glance.context
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
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


class MemberRepoStub(object):
    def add(self, image_member):
        image_member.output = 'member_repo_add'

    def get(self, *args, **kwargs):
        return 'member_repo_get'

    def save(self, image_member):
        image_member.output = 'member_repo_save'

    def list(self, *args, **kwargs):
        return 'member_repo_list'

    def remove(self, image_member):
        image_member.output = 'member_repo_remove'


class ImageMembershipStub(object):
    def __init__(self, output=None):
        self.output = output


class TaskRepoStub(object):
    def get_task_and_details(self, *args, **kwargs):
        return 'task_from_get', 'task_details_from_get'

    def add(self, *args, **kwargs):
        return 'task_from_add'

    def list_tasks(self, *args, **kwargs):
        return ['task_from_list_0', 'task_from_list_1']


class TaskStub(object):
    def __init__(self, task_id):
        self.task_id = task_id
        self.status = 'pending'

    def run(self, executor):
        self.status = 'processing'


class TaskFactoryStub(object):
    def new_task(self, *args):
        return 'new_task'


class TestPolicyEnforcer(base.IsolatedUnitTest):
    def test_policy_file_default_rules_default_location(self):
        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        enforcer.enforce(context, 'get_image', {})

    def test_policy_file_custom_rules_default_location(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def test_policy_file_custom_location(self):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'))

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def test_policy_file_check(self):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'))

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertEqual(enforcer.check(context, 'get_image', {}), False)


class TestPolicyEnforcerNoFile(base.IsolatedUnitTest):
    def test_policy_file_specified_but_not_found(self):
        """Missing defined policy file should result in a default ruleset"""
        self.config(policy_file='gobble.gobble')
        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        enforcer.enforce(context, 'get_image', {})
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'manage_image_cache', {})

        admin_context = glance.context.RequestContext(roles=['admin'])
        enforcer.enforce(admin_context, 'manage_image_cache', {})

    def test_policy_file_default_not_found(self):
        """Missing default policy file should result in a default ruleset"""
        def fake_find_file(self, name):
            return None

        self.stubs.Set(oslo.config.cfg.ConfigOpts, 'find_file',
                       fake_find_file)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        enforcer.enforce(context, 'get_image', {})
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'manage_image_cache', {})

        admin_context = glance.context.RequestContext(roles=['admin'])
        enforcer.enforce(admin_context, 'manage_image_cache', {})


class TestImagePolicy(test_utils.BaseTestCase):
    def setUp(self):
        self.image_stub = ImageStub(UUID1)
        self.image_repo_stub = ImageRepoStub()
        self.image_factory_stub = ImageFactoryStub()
        self.policy = mock.Mock()
        self.policy.enforce = mock.Mock()
        super(TestImagePolicy, self).setUp()

    def test_publicize_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden,
                          setattr, image, 'visibility', 'public')
        self.assertEqual(image.visibility, 'private')
        self.policy.enforce.assert_called_once_with({}, "publicize_image", {})

    def test_publicize_image_allowed(self):
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.visibility = 'public'
        self.assertEqual(image.visibility, 'public')
        self.policy.enforce.assert_called_once_with({}, "publicize_image", {})

    def test_delete_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.delete)
        self.assertEqual(image.status, 'active')
        self.policy.enforce.assert_called_once_with({}, "delete_image", {})

    def test_delete_image_allowed(self):
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.policy.enforce.assert_called_once_with({}, "delete_image", {})

    def test_get_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.get, UUID1)
        self.policy.enforce.assert_called_once_with({}, "get_image", {})

    def test_get_image_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        output = image_repo.get(UUID1)
        self.assertIsInstance(output, glance.api.policy.ImageProxy)
        self.assertEqual(output.image, 'image_from_get')
        self.policy.enforce.assert_called_once_with({}, "get_image", {})

    def test_get_images_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.list)
        self.policy.enforce.assert_called_once_with({}, "get_images", {})

    def test_get_images_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        images = image_repo.list()
        for i, image in enumerate(images):
            self.assertIsInstance(image, glance.api.policy.ImageProxy)
            self.assertEqual(image.image, 'image_from_list_%d' % i)
            self.policy.enforce.assert_called_once_with({}, "get_images", {})

    def test_modify_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.save, image)
        self.policy.enforce.assert_called_once_with({}, "modify_image", {})

    def test_modify_image_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.save(image)
        self.policy.enforce.assert_called_once_with({}, "modify_image", {})

    def test_add_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.add, image)
        self.policy.enforce.assert_called_once_with({}, "add_image", {})

    def test_add_image_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.add(image)
        self.policy.enforce.assert_called_once_with({}, "add_image", {})

    def test_new_image_visibility(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_factory = glance.api.policy.ImageFactoryProxy(
            self.image_factory_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_factory.new_image,
                          visibility='public')
        self.policy.enforce.assert_called_once_with({}, "publicize_image", {})

    def test_new_image_visibility_public_allowed(self):
        image_factory = glance.api.policy.ImageFactoryProxy(
            self.image_factory_stub, {}, self.policy)
        image_factory.new_image(visibility='public')
        self.policy.enforce.assert_called_once_with({}, "publicize_image", {})

    def test_image_get_data(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.get_data)
        self.policy.enforce.assert_called_once_with({}, "download_image", {})

    def test_image_set_data(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.set_data)
        self.policy.enforce.assert_called_once_with({}, "upload_image", {})


class TestMemberPolicy(test_utils.BaseTestCase):
    def setUp(self):
        self.policy = mock.Mock()
        self.policy.enforce = mock.Mock()
        self.member_repo = glance.api.policy.ImageMemberRepoProxy(
            MemberRepoStub(), {}, self.policy)
        super(TestMemberPolicy, self).setUp()

    def test_add_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.add, '')
        self.policy.enforce.assert_called_once_with({}, "add_member", {})

    def test_add_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.add(image_member)
        self.assertEqual(image_member.output, 'member_repo_add')
        self.policy.enforce.assert_called_once_with({}, "add_member", {})

    def test_get_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.get, '')
        self.policy.enforce.assert_called_once_with({}, "get_member", {})

    def test_get_member_allowed(self):
        output = self.member_repo.get('')
        self.assertEqual(output, 'member_repo_get')
        self.policy.enforce.assert_called_once_with({}, "get_member", {})

    def test_modify_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.save, '')
        self.policy.enforce.assert_called_once_with({}, "modify_member", {})

    def test_modify_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.save(image_member)
        self.assertEqual(image_member.output, 'member_repo_save')
        self.policy.enforce.assert_called_once_with({}, "modify_member", {})

    def test_get_members_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.list, '')
        self.policy.enforce.assert_called_once_with({}, "get_members", {})

    def test_get_members_allowed(self):
        output = self.member_repo.list('')
        self.assertEqual(output, 'member_repo_list')
        self.policy.enforce.assert_called_once_with({}, "get_members", {})

    def test_delete_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.remove, '')
        self.policy.enforce.assert_called_once_with({}, "delete_member", {})

    def test_delete_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.remove(image_member)
        self.assertEqual(image_member.output, 'member_repo_remove')
        self.policy.enforce.assert_called_once_with({}, "delete_member", {})


class TestTaskPolicy(test_utils.BaseTestCase):
    def setUp(self):
        self.task_stub = TaskStub(UUID1)
        self.task_repo_stub = TaskRepoStub()
        self.task_factory_stub = TaskFactoryStub()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        super(TestTaskPolicy, self).setUp()

    def test_get_task_not_allowed(self):
        rules = {"get_task": False}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        self.assertRaises(exception.Forbidden,
                          task_repo.get_task_and_details,
                          UUID1)

    def test_get_task_allowed(self):
        rules = {"get_task": True}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        task, task_details = task_repo.get_task_and_details(UUID1)
        self.assertIsInstance(task, glance.api.policy.TaskProxy)
        self.assertEqual(task.task, 'task_from_get')

    def test_get_tasks_not_allowed(self):
        rules = {"get_tasks": False}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        self.assertRaises(exception.Forbidden, task_repo.list_tasks)

    def test_get_tasks_allowed(self):
        rules = {"get_task": True}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        tasks = task_repo.list_tasks()
        for i, task in enumerate(tasks):
            self.assertIsInstance(task, glance.api.policy.TaskProxy)
            self.assertEqual(task.task, 'task_from_list_%d' % i)

    def test_add_task_not_allowed(self):
        rules = {"add_task": False}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        task = glance.api.policy.TaskProxy(self.task_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, task_repo.add, task)

    def test_add_task_allowed(self):
        rules = {"add_task": True}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        task = glance.api.policy.TaskProxy(self.task_stub, {}, self.policy)
        task_repo.add(task)


class TestContextPolicyEnforcer(base.IsolatedUnitTest):
    def _do_test_policy_influence_context_admin(self,
                                                policy_admin_role,
                                                context_role,
                                                context_is_admin,
                                                admin_expected):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'))

        rules = {'context_is_admin': 'role:%s' % policy_admin_role}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[context_role],
                                                is_admin=context_is_admin,
                                                policy_enforcer=enforcer)
        self.assertEqual(context.is_admin, admin_expected)

    def test_context_admin_policy_admin(self):
        self._do_test_policy_influence_context_admin('test_admin',
                                                     'test_admin',
                                                     True,
                                                     True)

    def test_context_nonadmin_policy_admin(self):
        self._do_test_policy_influence_context_admin('test_admin',
                                                     'test_admin',
                                                     False,
                                                     True)

    def test_context_admin_policy_nonadmin(self):
        self._do_test_policy_influence_context_admin('test_admin',
                                                     'demo',
                                                     True,
                                                     True)

    def test_context_nonadmin_policy_nonadmin(self):
        self._do_test_policy_influence_context_admin('test_admin',
                                                     'demo',
                                                     False,
                                                     False)
