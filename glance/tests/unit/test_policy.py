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

from collections import abc
from unittest import mock

import hashlib
import os.path
import oslo_config.cfg

import glance.api.policy
from glance.common import exception
import glance.context
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
from glance.tests import utils as test_utils

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class IterableMock(mock.Mock, abc.Iterable):

    def __iter__(self):
        while False:
            yield None


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

    def __init__(self, image_id=None, visibility='private',
                 container_format='bear', disk_format='raw',
                 status='active', extra_properties=None,
                 os_hidden=False):

        if extra_properties is None:
            extra_properties = {}

        self.image_id = image_id
        self.visibility = visibility
        self.container_format = container_format
        self.disk_format = disk_format
        self.status = status
        self.extra_properties = extra_properties
        self.checksum = 'c2e5db72bd7fd153f53ede5da5a06de3'
        self.os_hash_algo = 'sha512'
        self.os_hash_value = hashlib.sha512(b'glance').hexdigest()
        self.created_at = '2013-09-28T15:27:36Z'
        self.updated_at = '2013-09-28T15:27:37Z'
        self.locations = []
        self.min_disk = 0
        self.min_ram = 0
        self.name = 'image_name'
        self.owner = 'tenant1'
        self.protected = False
        self.size = 0
        self.virtual_size = 0
        self.tags = []
        self.os_hidden = os_hidden

    def delete(self):
        self.status = 'deleted'


class ImageFactoryStub(object):

    def new_image(self, image_id=None, name=None, visibility='private',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, hidden=False, tags=None,
                  **other_args):
        self.visibility = visibility
        self.hidden = hidden
        return 'new_image'


class MemberRepoStub(object):
    image = None

    def add(self, image_member):
        image_member.output = 'member_repo_add'

    def get(self, *args, **kwargs):
        return 'member_repo_get'

    def save(self, image_member, from_state=None):
        image_member.output = 'member_repo_save'

    def list(self, *args, **kwargs):
        return 'member_repo_list'

    def remove(self, image_member):
        image_member.output = 'member_repo_remove'


class ImageMembershipStub(object):

    def __init__(self, output=None):
        self.output = output


class TaskRepoStub(object):

    def get(self, *args, **kwargs):
        return 'task_from_get'

    def add(self, *args, **kwargs):
        return 'task_from_add'

    def list(self, *args, **kwargs):
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


class MdNamespaceRepoStub(object):
    def add(self, namespace):
        return 'mdns_add'

    def get(self, namespace):
        return 'mdns_get'

    def list(self, *args, **kwargs):
        return ['mdns_list']

    def save(self, namespace):
        return 'mdns_save'

    def remove(self, namespace):
        return 'mdns_remove'

    def remove_tags(self, namespace):
        return 'mdtags_remove'


class MdObjectRepoStub(object):
    def add(self, obj):
        return 'mdobj_add'

    def get(self, ns, obj_name):
        return 'mdobj_get'

    def list(self, *args, **kwargs):
        return ['mdobj_list']

    def save(self, obj):
        return 'mdobj_save'

    def remove(self, obj):
        return 'mdobj_remove'


class MdResourceTypeRepoStub(object):
    def add(self, rt):
        return 'mdrt_add'

    def get(self, *args, **kwargs):
        return 'mdrt_get'

    def list(self, *args, **kwargs):
        return ['mdrt_list']

    def remove(self, *args, **kwargs):
        return 'mdrt_remove'


class MdPropertyRepoStub(object):
    def add(self, prop):
        return 'mdprop_add'

    def get(self, ns, prop_name):
        return 'mdprop_get'

    def list(self, *args, **kwargs):
        return ['mdprop_list']

    def save(self, prop):
        return 'mdprop_save'

    def remove(self, prop):
        return 'mdprop_remove'


class MdTagRepoStub(object):
    def add(self, tag):
        return 'mdtag_add'

    def add_tags(self, tags):
        return ['mdtag_add_tags']

    def get(self, ns, tag_name):
        return 'mdtag_get'

    def list(self, *args, **kwargs):
        return ['mdtag_list']

    def save(self, tag):
        return 'mdtag_save'

    def remove(self, tag):
        return 'mdtag_remove'


class TestPolicyEnforcer(base.IsolatedUnitTest):

    def test_policy_enforce_unregistered(self):
        enforcer = glance.api.policy.Enforcer()
        context = glance.context.RequestContext(roles=[])

        self.assertRaises(glance.api.policy.policy.PolicyNotRegistered,
                          enforcer.enforce,
                          context, 'wibble', {})

    def test_policy_check_unregistered(self):
        enforcer = glance.api.policy.Enforcer()
        context = glance.context.RequestContext(roles=[])

        self.assertRaises(glance.api.policy.policy.PolicyNotRegistered,
                          enforcer.check,
                          context, 'wibble', {})

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
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'),
                    group='oslo_policy')

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def test_policy_file_check(self):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'),
                    group='oslo_policy')

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertEqual(False, enforcer.check(context, 'get_image', {}))

    def test_policy_file_get_image_default_everybody(self):
        rules = {"default": ''}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertEqual(True, enforcer.check(context, 'get_image', {}))

    def test_policy_file_get_image_default_nobody(self):
        rules = {"default": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})


class TestPolicyEnforcerNoFile(base.IsolatedUnitTest):

    def test_policy_file_specified_but_not_found(self):
        """Missing defined policy file should result in a default ruleset"""
        self.config(policy_file='gobble.gobble', group='oslo_policy')
        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'manage_image_cache', {})

        admin_context = glance.context.RequestContext(roles=['admin'])
        enforcer.enforce(admin_context, 'manage_image_cache', {})

    def test_policy_file_default_not_found(self):
        """Missing default policy file should result in a default ruleset"""

        def fake_find_file(self, name):
            return None

        self.mock_object(oslo_config.cfg.ConfigOpts, 'find_file',
                         fake_find_file)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[])
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
        self.assertEqual('private', image.visibility)
        self.policy.enforce.assert_called_once_with({}, "publicize_image",
                                                    image.target)

    def test_publicize_image_allowed(self):
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.visibility = 'public'
        self.assertEqual('public', image.visibility)
        self.policy.enforce.assert_called_once_with({}, "publicize_image",
                                                    image.target)

    def test_communitize_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden,
                          setattr, image, 'visibility', 'community')
        self.assertEqual('private', image.visibility)
        self.policy.enforce.assert_called_once_with({}, "communitize_image",
                                                    image.target)

    def test_communitize_image_allowed(self):
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image.visibility = 'community'
        self.assertEqual('community', image.visibility)
        self.policy.enforce.assert_called_once_with({}, "communitize_image",
                                                    image.target)

    def test_delete_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image.delete)
        self.assertEqual('active', image.status)
        self.policy.enforce.assert_called_once_with({}, "delete_image",
                                                    image.target)

    def test_delete_image_allowed(self):
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        args = dict(image.target)
        image.delete()
        self.assertEqual('deleted', image.status)
        self.policy.enforce.assert_called_once_with({}, "delete_image", args)

    def test_get_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_target = IterableMock()
        with mock.patch.object(glance.api.policy, 'ImageTarget') as target:
            target.return_value = image_target
            image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                          {}, self.policy)
            self.assertRaises(exception.Forbidden, image_repo.get, UUID1)
        self.policy.enforce.assert_called_once_with({}, "get_image",
                                                    dict(image_target))

    def test_get_image_allowed(self):
        image_target = IterableMock()
        with mock.patch.object(glance.api.policy, 'ImageTarget') as target:
            target.return_value = image_target
            image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                          {}, self.policy)
            output = image_repo.get(UUID1)
        self.assertIsInstance(output, glance.api.policy.ImageProxy)
        self.assertEqual('image_from_get', output.image)
        self.policy.enforce.assert_called_once_with({}, "get_image",
                                                    dict(image_target))

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
            self.assertEqual('image_from_list_%d' % i, image.image)
            self.policy.enforce.assert_called_once_with({}, "get_images", {})

    def test_modify_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.save, image)
        self.policy.enforce.assert_called_once_with({}, "modify_image",
                                                    image.target)

    def test_modify_image_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.save(image)
        self.policy.enforce.assert_called_once_with({}, "modify_image",
                                                    image.target)

    def test_add_image_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_repo.add, image)
        self.policy.enforce.assert_called_once_with({}, "add_image",
                                                    image.target)

    def test_add_image_allowed(self):
        image_repo = glance.api.policy.ImageRepoProxy(self.image_repo_stub,
                                                      {}, self.policy)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        image_repo.add(image)
        self.policy.enforce.assert_called_once_with({}, "add_image",
                                                    image.target)

    def test_new_image_visibility_public_not_allowed(self):
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

    def test_new_image_visibility_community_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        image_factory = glance.api.policy.ImageFactoryProxy(
            self.image_factory_stub, {}, self.policy)
        self.assertRaises(exception.Forbidden, image_factory.new_image,
                          visibility='community')
        self.policy.enforce.assert_called_once_with({},
                                                    "communitize_image",
                                                    {})

    def test_new_image_visibility_community_allowed(self):
        image_factory = glance.api.policy.ImageFactoryProxy(
            self.image_factory_stub, {}, self.policy)
        image_factory.new_image(visibility='community')
        self.policy.enforce.assert_called_once_with({},
                                                    "communitize_image",
                                                    {})

    def test_image_get_data_policy_enforced_with_target(self):
        extra_properties = {
            'test_key': 'test_4321'
        }
        image_stub = ImageStub(UUID1, extra_properties=extra_properties)
        with mock.patch('glance.api.policy.ImageTarget'):
            image = glance.api.policy.ImageProxy(image_stub, {}, self.policy)
        target = image.target
        self.policy.enforce.side_effect = exception.Forbidden

        self.assertRaises(exception.Forbidden, image.get_data)
        self.policy.enforce.assert_called_once_with({}, "download_image",
                                                    target)


class TestMemberPolicy(test_utils.BaseTestCase):

    def setUp(self):
        self.policy = mock.Mock()
        self.policy.enforce = mock.Mock()
        self.image_stub = ImageStub(UUID1)
        image = glance.api.policy.ImageProxy(self.image_stub, {}, self.policy)
        self.member_repo = glance.api.policy.ImageMemberRepoProxy(
            MemberRepoStub(), image, {}, self.policy)
        self.target = self.member_repo.target
        super(TestMemberPolicy, self).setUp()

    def test_add_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.add, '')
        self.policy.enforce.assert_called_once_with({}, "add_member",
                                                    self.target)

    def test_add_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.add(image_member)
        self.assertEqual('member_repo_add', image_member.output)
        self.policy.enforce.assert_called_once_with({}, "add_member",
                                                    self.target)

    def test_get_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.get, '')
        self.policy.enforce.assert_called_once_with({}, "get_member",
                                                    self.target)

    def test_get_member_allowed(self):
        output = self.member_repo.get('')
        self.assertEqual('member_repo_get', output)
        self.policy.enforce.assert_called_once_with({}, "get_member",
                                                    self.target)

    def test_modify_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.save, '')
        self.policy.enforce.assert_called_once_with({}, "modify_member",
                                                    self.target)

    def test_modify_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.save(image_member)
        self.assertEqual('member_repo_save', image_member.output)
        self.policy.enforce.assert_called_once_with({}, "modify_member",
                                                    self.target)

    def test_get_members_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.list, '')
        self.policy.enforce.assert_called_once_with({}, "get_members",
                                                    self.target)

    def test_get_members_allowed(self):
        output = self.member_repo.list('')
        self.assertEqual('member_repo_list', output)
        self.policy.enforce.assert_called_once_with({}, "get_members",
                                                    self.target)

    def test_delete_member_not_allowed(self):
        self.policy.enforce.side_effect = exception.Forbidden
        self.assertRaises(exception.Forbidden, self.member_repo.remove, '')
        self.policy.enforce.assert_called_once_with({}, "delete_member",
                                                    self.target)

    def test_delete_member_allowed(self):
        image_member = ImageMembershipStub()
        self.member_repo.remove(image_member)
        self.assertEqual('member_repo_remove', image_member.output)
        self.policy.enforce.assert_called_once_with({}, "delete_member",
                                                    self.target)


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
                          task_repo.get,
                          UUID1)

    def test_get_task_allowed(self):
        rules = {"get_task": True}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        task = task_repo.get(UUID1)
        self.assertIsInstance(task, glance.api.policy.TaskProxy)
        self.assertEqual('task_from_get', task.task)

    def test_get_tasks_not_allowed(self):
        rules = {"get_tasks": False}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskStubRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        self.assertRaises(exception.Forbidden, task_repo.list)

    def test_get_tasks_allowed(self):
        rules = {"get_task": True}
        self.policy.set_rules(rules)
        task_repo = glance.api.policy.TaskStubRepoProxy(
            self.task_repo_stub,
            {},
            self.policy
        )
        tasks = task_repo.list()
        for i, task in enumerate(tasks):
            self.assertIsInstance(task, glance.api.policy.TaskStubProxy)
            self.assertEqual('task_from_list_%d' % i, task.task_stub)

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


class TestMetadefPolicy(test_utils.BaseTestCase):
    def setUp(self):
        self.fakens = mock.Mock()
        self.fakeobj = mock.Mock()
        self.fakert = mock.Mock()
        self.fakeprop = mock.Mock()
        self.faketag = mock.Mock()
        self.policy = unit_test_utils.FakePolicyEnforcer()
        super(TestMetadefPolicy, self).setUp()

    def test_md_namespace_not_allowed(self):
        rules = {'get_metadef_namespace': False,
                 'get_metadef_namespaces': False,
                 'modify_metadef_namespace': False,
                 'add_metadef_namespace': False,
                 'delete_metadef_namespace': False}
        self.policy.set_rules(rules)
        mdns_repo = glance.api.policy.MetadefNamespaceRepoProxy(
            MdNamespaceRepoStub(), {}, self.policy)
        self.assertRaises(exception.Forbidden, mdns_repo.add, self.fakens)
        self.assertRaises(exception.Forbidden, mdns_repo.get, self.fakens)
        self.assertRaises(exception.Forbidden, mdns_repo.list)
        self.assertRaises(exception.Forbidden, mdns_repo.remove, self.fakens)
        self.assertRaises(exception.Forbidden, mdns_repo.save, self.fakens)

    def test_md_namespace_allowed(self):
        rules = {'get_metadef_namespace': True,
                 'get_metadef_namespaces': True,
                 'modify_metadef_namespace': True,
                 'add_metadef_namespace': True,
                 'delete_metadef_namespace': True}
        self.policy.set_rules(rules)
        mdns_repo = glance.api.policy.MetadefNamespaceRepoProxy(
            MdNamespaceRepoStub(), {}, self.policy)
        self.assertEqual(None, mdns_repo.add(self.fakens))
        self.assertEqual('mdns_get',
                         mdns_repo.get(self.fakens).namespace_input)
        self.assertEqual(['mdns_list'],
                         [ns.namespace_input for ns in mdns_repo.list()])
        self.assertEqual('mdns_save',
                         mdns_repo.save(self.fakens).namespace_input)
        self.assertEqual('mdns_remove',
                         mdns_repo.remove(self.fakens).namespace_input)

    def test_md_object_not_allowed(self):
        rules = {'get_metadef_object': False,
                 'get_metadef_objects': False,
                 'modify_metadef_object': False,
                 'add_metadef_object': False,
                 'delete_metadef_object': False}
        self.policy.set_rules(rules)
        mdobj_repo = glance.api.policy.MetadefObjectRepoProxy(
            MdObjectRepoStub(), {}, self.policy)
        self.assertRaises(exception.Forbidden, mdobj_repo.add, self.fakeobj)
        self.assertRaises(exception.Forbidden, mdobj_repo.get, self.fakens,
                          self.fakeobj)
        self.assertRaises(exception.Forbidden, mdobj_repo.list)
        self.assertRaises(exception.Forbidden, mdobj_repo.remove, self.fakeobj)
        self.assertRaises(exception.Forbidden, mdobj_repo.save, self.fakeobj)

    def test_md_object_allowed(self):
        rules = {'get_metadef_object': True,
                 'get_metadef_objects': True,
                 'modify_metadef_object': True,
                 'add_metadef_object': True,
                 'delete_metadef_object': True}
        self.policy.set_rules(rules)
        mdobj_repo = glance.api.policy.MetadefObjectRepoProxy(
            MdObjectRepoStub(), {}, self.policy)
        self.assertEqual(None, mdobj_repo.add(self.fakeobj))
        self.assertEqual('mdobj_get',
                         mdobj_repo.get(self.fakens, 'fakeobj').meta_object)
        self.assertEqual(['mdobj_list'],
                         [obj.meta_object for obj in mdobj_repo.list()])
        self.assertEqual('mdobj_save',
                         mdobj_repo.save(self.fakeobj).meta_object)
        self.assertEqual('mdobj_remove',
                         mdobj_repo.remove(self.fakeobj).meta_object)

    def test_md_resource_type_not_allowed(self):
        rules = {'get_metadef_resource_type': False,
                 'list_metadef_resource_types': False,
                 'add_metadef_resource_type_association': False,
                 'remove_metadef_resource_type_association': False}
        self.policy.set_rules(rules)
        mdrt_repo = glance.api.policy.MetadefResourceTypeRepoProxy(
            MdResourceTypeRepoStub(), {}, self.policy)
        self.assertRaises(exception.Forbidden, mdrt_repo.add, self.fakert)
        self.assertRaises(exception.Forbidden, mdrt_repo.get, self.fakert)
        self.assertRaises(exception.Forbidden, mdrt_repo.list)
        self.assertRaises(exception.Forbidden, mdrt_repo.remove, self.fakert)

    def test_md_resource_type_allowed(self):
        rules = {'get_metadef_resource_type': True,
                 'list_metadef_resource_types': True,
                 'add_metadef_resource_type_association': True,
                 'remove_metadef_resource_type_association': True}
        self.policy.set_rules(rules)
        mdrt_repo = glance.api.policy.MetadefResourceTypeRepoProxy(
            MdResourceTypeRepoStub(), {}, self.policy)
        self.assertEqual(None, mdrt_repo.add(self.fakert))
        self.assertEqual(
            'mdrt_get', mdrt_repo.get(self.fakens,
                                      'fakert').meta_resource_type)
        self.assertEqual(['mdrt_list'],
                         [rt.meta_resource_type for rt in mdrt_repo.list()])
        self.assertEqual('mdrt_remove',
                         mdrt_repo.remove(self.fakert).meta_resource_type)

    def test_md_property_not_allowed(self):
        rules = {'get_metadef_property': False,
                 'get_metadef_properties': False,
                 'modify_metadef_property': False,
                 'add_metadef_property': False,
                 'remove_metadef_property': False}
        self.policy.set_rules(rules)
        mdprop_repo = glance.api.policy.MetadefPropertyRepoProxy(
            MdPropertyRepoStub(), {}, self.policy)
        self.assertRaises(exception.Forbidden, mdprop_repo.add, self.fakeprop)
        self.assertRaises(exception.Forbidden, mdprop_repo.get, self.fakens,
                          self.fakeprop)
        self.assertRaises(exception.Forbidden, mdprop_repo.list)
        self.assertRaises(exception.Forbidden, mdprop_repo.remove,
                          self.fakeprop)
        self.assertRaises(exception.Forbidden, mdprop_repo.save, self.fakeprop)

    def test_md_property_allowed(self):
        rules = {'get_metadef_property': True,
                 'get_metadef_properties': True,
                 'modify_metadef_property': True,
                 'add_metadef_property': True,
                 'remove_metadef_property': True}
        self.policy.set_rules(rules)
        mdprop_repo = glance.api.policy.MetadefPropertyRepoProxy(
            MdPropertyRepoStub(), {}, self.policy)
        self.assertEqual(None, mdprop_repo.add(self.fakeprop))
        self.assertEqual(
            'mdprop_get', mdprop_repo.get(self.fakens,
                                          'fakeprop').namespace_property)
        self.assertEqual(['mdprop_list'],
                         [prop.namespace_property for prop
                          in mdprop_repo.list()])
        self.assertEqual('mdprop_save',
                         mdprop_repo.save(self.fakeprop).namespace_property)
        self.assertEqual('mdprop_remove',
                         mdprop_repo.remove(self.fakeprop).namespace_property)

    def test_md_tag_not_allowed(self):
        rules = {'get_metadef_tag': False,
                 'get_metadef_tags': False,
                 'modify_metadef_tag': False,
                 'add_metadef_tag': False,
                 'add_metadef_tags': False,
                 'delete_metadef_tag': False,
                 'delete_metadef_tags': False}
        self.policy.set_rules(rules)
        mdtag_repo = glance.api.policy.MetadefTagRepoProxy(
            MdTagRepoStub(), {}, self.policy)
        mdns_repo = glance.api.policy.MetadefNamespaceRepoProxy(
            MdNamespaceRepoStub(), {}, self.policy)
        self.assertRaises(exception.Forbidden, mdtag_repo.add, self.faketag)
        self.assertRaises(exception.Forbidden, mdtag_repo.add_tags,
                          [self.faketag])
        self.assertRaises(exception.Forbidden, mdtag_repo.get, self.fakens,
                          self.faketag)
        self.assertRaises(exception.Forbidden, mdtag_repo.list)
        self.assertRaises(exception.Forbidden, mdtag_repo.remove, self.faketag)
        self.assertRaises(exception.Forbidden, mdns_repo.remove_tags,
                          self.fakens)
        self.assertRaises(exception.Forbidden, mdtag_repo.save, self.faketag)

    def test_md_tag_allowed(self):
        rules = {'get_metadef_tag': True,
                 'get_metadef_tags': True,
                 'modify_metadef_tag': True,
                 'add_metadef_tag': True,
                 'add_metadef_tags': True,
                 'delete_metadef_tag': True,
                 'delete_metadef_tags': True}
        self.policy.set_rules(rules)
        mdtag_repo = glance.api.policy.MetadefTagRepoProxy(
            MdTagRepoStub(), {}, self.policy)
        mdns_repo = glance.api.policy.MetadefNamespaceRepoProxy(
            MdNamespaceRepoStub(), {}, self.policy)
        self.assertEqual(None, mdtag_repo.add(self.faketag))
        self.assertEqual(None, mdtag_repo.add_tags([self.faketag]))
        self.assertEqual('mdtag_get',
                         mdtag_repo.get(self.fakens, 'faketag').base)
        self.assertEqual(['mdtag_list'],
                         [tag.base for tag in mdtag_repo.list()])
        self.assertEqual('mdtag_save',
                         mdtag_repo.save(self.faketag).base)
        self.assertEqual('mdtag_remove',
                         mdtag_repo.remove(self.faketag).base)
        self.assertEqual('mdtags_remove',
                         mdns_repo.remove_tags(self.fakens).base)


class TestContextPolicyEnforcer(base.IsolatedUnitTest):

    def _do_test_policy_influence_context_admin(self,
                                                policy_admin_role,
                                                context_role,
                                                context_is_admin,
                                                admin_expected):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'),
                    group='oslo_policy')

        rules = {'context_is_admin': 'role:%s' % policy_admin_role}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer()

        context = glance.context.RequestContext(roles=[context_role],
                                                is_admin=context_is_admin,
                                                policy_enforcer=enforcer)
        self.assertEqual(admin_expected, context.is_admin)

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
