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

import os.path

import oslo.config.cfg

import glance.api.policy
from glance.common import exception
import glance.context
from glance.tests.unit import base
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


class MemberRepoStub(object):
    def add(self, *args, **kwargs):
        return 'member_repo_add'

    def get(self, *args, **kwargs):
        return 'member_repo_get'

    def save(self, *args, **kwargs):
        return 'member_repo_save'

    def list(self, *args, **kwargs):
        return 'member_repo_list'

    def remove(self, *args, **kwargs):
        return 'member_repo_remove'


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
        self.policy = unit_test_utils.FakePolicyEnforcer()
        super(TestImagePolicy, self).setUp()

    def test_publicize_image_not_allowed(self):
        rules = {"publicize_image": False}
        self.policy.set_rules(rules)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden,
                          setattr, image, 'visibility', 'public')
        self.assertEquals(image.visibility, 'private')

    def test_publicize_image_allowed(self):
        rules = {"publicize_image": True}
        self.policy.set_rules(rules)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.visibility = 'public'
        self.assertEquals(image.visibility, 'public')

    def test_delete_image_not_allowed(self):
        rules = {"delete_image": False}
        self.policy.set_rules(rules)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.delete)
        self.assertEquals(image.status, 'active')

    def test_delete_image_allowed(self):
        rules = {"delete_image": True}
        self.policy.set_rules(rules)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.delete()
        self.assertEquals(image.status, 'deleted')

    def test_get_image_not_allowed(self):
        rules = {"get_image": False}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.get, UUID1)

    def test_get_image_allowed(self):
        rules = {"get_image": True}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        output = image_repo.get(UUID1)
        self.assertTrue(isinstance(output, glance.api.policy.ImageProxy))
        self.assertEqual(output.image, 'image_from_get')

    def test_get_images_not_allowed(self):
        rules = {"get_images": False}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.list)

    def test_get_images_allowed(self):
        rules = {"get_image": True}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        images = image_repo.list()
        for i, image in enumerate(images):
            self.assertTrue(isinstance(image, glance.api.policy.ImageProxy))
            self.assertEqual(image.image, 'image_from_list_%d' % i)

    def test_modify_image_not_allowed(self):
        rules = {"modify_image": False}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.save, image)

    def test_modify_image_allowed(self):
        rules = {"modify_image": True}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.save(image)

    def test_add_image_not_allowed(self):
        rules = {"add_image": False}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.add, image)

    def test_add_image_allowed(self):
        rules = {"add_image": True}
        self.policy.set_rules(rules)
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.add(image)

    def test_new_image_visibility(self):
        rules = {'publicize_image': False}
        self.policy.set_rules(rules)

        image_factory = glance.api.policy.ImageFactoryProxy(
                self.image_factory_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_factory.new_image,
                          visibility='public')

    def test_new_image_visibility_public_allowed(self):
        rules = {'publicize_image': True}
        self.policy.set_rules(rules)
        image_factory = glance.api.policy.ImageFactoryProxy(
                self.image_factory_stub, {}, self.policy)
        image_factory.new_image(visibility='public')

    def test_image_get_data(self):
        rules = {'download_image': False}
        self.policy.set_rules(rules)

        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.get_data)


class TestMemberPolicy(test_utils.BaseTestCase):
    def setUp(self):
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.member_repo = glance.api.policy.ImageMemberRepoProxy(
            MemberRepoStub(), {}, self.policy)
        super(TestMemberPolicy, self).setUp()

    def test_add_member_not_allowed(self):
        rules = {'add_member': False}
        self.policy.set_rules(rules)
        self.assertRaises(exception.Forbidden, self.member_repo.add, '')

    def test_add_member_allowed(self):
        rules = {'add_member': True}
        self.policy.set_rules(rules)
        output = self.member_repo.add('')
        self.assertEqual(output, 'member_repo_add')

    def test_get_member_not_allowed(self):
        rules = {'get_member': False}
        self.policy.set_rules(rules)
        self.assertRaises(exception.Forbidden, self.member_repo.get, '')

    def test_get_member_allowed(self):
        rules = {'get_member': True}
        self.policy.set_rules(rules)
        output = self.member_repo.get('')
        self.assertEqual(output, 'member_repo_get')

    def test_modify_member_not_allowed(self):
        rules = {'modify_member': False}
        self.policy.set_rules(rules)
        self.assertRaises(exception.Forbidden, self.member_repo.save, '')

    def test_modify_member_allowed(self):
        rules = {'modify_member': True}
        self.policy.set_rules(rules)
        output = self.member_repo.save('')
        self.assertEqual(output, 'member_repo_save')

    def test_get_members_not_allowed(self):
        rules = {'get_members': False}
        self.policy.set_rules(rules)
        self.assertRaises(exception.Forbidden, self.member_repo.list, '')

    def test_get_members_allowed(self):
        rules = {'get_members': True}
        self.policy.set_rules(rules)
        output = self.member_repo.list('')
        self.assertEqual(output, 'member_repo_list')

    def test_delete_member_not_allowed(self):
        rules = {'delete_member': False}
        self.policy.set_rules(rules)
        self.assertRaises(exception.Forbidden, self.member_repo.remove, '')

    def test_delete_member_allowed(self):
        rules = {'delete_member': True}
        self.policy.set_rules(rules)
        output = self.member_repo.remove('')
        self.assertEqual(output, 'member_repo_remove')


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
        self.assertEquals(context.is_admin, admin_expected)

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
