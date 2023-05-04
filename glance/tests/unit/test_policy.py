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
from oslo_policy import policy as common_policy

import glance.api.policy
from glance.common import exception
import glance.context
from glance.policies import base as base_policy
from glance.tests.unit import base

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class IterableMock(mock.Mock, abc.Iterable):

    def __iter__(self):
        while False:
            yield None


class ImageRepoStub(object):

    def __init__(self):
        self.db_api = mock.Mock()
        self.db_api.image_member_find.return_value = [
            {'member': 'foo'}
        ]

    def get(self, *args, **kwargs):
        context = mock.Mock()
        policy = mock.Mock()
        return glance.api.policy.ImageProxy(
            ImageStub(image_id=UUID1), context, policy
        )

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
        self.member = self.owner

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

    def add_tags(self, tags, can_append=False):
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
        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)
        context = glance.context.RequestContext(roles=[])

        self.assertRaises(glance.api.policy.policy.PolicyNotRegistered,
                          enforcer.enforce,
                          context, 'wibble', {})

    def test_policy_check_unregistered(self):
        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)
        context = glance.context.RequestContext(roles=[])

        self.assertRaises(glance.api.policy.policy.PolicyNotRegistered,
                          enforcer.check,
                          context, 'wibble', {})

    def test_policy_file_default_rules_default_location(self):
        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=['reader'])
        enforcer.enforce(context, 'get_image',
                         {'project_id': context.project_id})

    def test_policy_file_custom_rules_default_location(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def test_policy_file_custom_location(self):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'),
                    group='oslo_policy')

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def test_policy_file_check(self):
        self.config(policy_file=os.path.join(self.test_dir, 'gobble.gobble'),
                    group='oslo_policy')

        rules = {"get_image": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertEqual(False, enforcer.check(context, 'get_image', {}))

    def test_policy_file_get_image_default_everybody(self):
        rules = {"default": '',
                 "get_image": ''}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertEqual(True, enforcer.check(context, 'get_image', {}))

    def test_policy_file_get_image_default_nobody(self):
        rules = {"default": '!'}
        self.set_policy_rules(rules)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'get_image', {})

    def _test_enforce_scope(self):
        policy_name = 'foo'
        rule = common_policy.RuleDefault(
            name=policy_name, check_str='role:bar', scope_types=['system'])

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)
        enforcer.register_default(rule)

        context = glance.context.RequestContext(
            user_id='user', project_id='project', roles=['bar'])
        target = {}
        return enforcer.enforce(context, policy_name, target)

    def test_policy_enforcer_raises_forbidden_when_enforcing_scope(self):
        # Make sure we raise an exception if the context scope doesn't match
        # the scope of the rule when oslo.policy is configured to raise an
        # exception.
        self.config(enforce_scope=True, group='oslo_policy')
        self.assertRaises(exception.Forbidden, self._test_enforce_scope)

    def test_policy_enforcer_does_not_raise_forbidden(self):
        # Make sure we don't raise an exception for mismatched scopes unless
        # oslo.policy is configured to do so.
        self.config(enforce_scope=False, group='oslo_policy')
        self.assertTrue(self._test_enforce_scope())

    def test_ensure_context_object_is_passed_to_policy_enforcement(self):
        # The oslo.policy Enforcer does some useful translation for us if we
        # pass it an oslo.context.RequestContext object. This prevents us from
        # having to handle the translation to a valid credential dictionary in
        # glance.
        context = glance.context.RequestContext()
        mock_enforcer = self.mock_object(common_policy.Enforcer, 'enforce')

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)
        enforcer.register_default(
            common_policy.RuleDefault(name='foo', check_str='role:bar')
        )

        enforcer.enforce(context, 'foo', {})
        mock_enforcer.assert_called_once_with('foo', {}, context,
                                              do_raise=True,
                                              exc=exception.Forbidden,
                                              action='foo')

        # Reset the mock and make sure glance.api.policy.Enforcer.check()
        # behaves the same way.
        mock_enforcer.reset_mock()
        enforcer.check(context, 'foo', {})
        mock_enforcer.assert_called_once_with('foo', {}, context)


class TestPolicyEnforcerNoFile(base.IsolatedUnitTest):

    def test_policy_file_specified_but_not_found(self):
        """Missing defined policy file should result in a default ruleset"""
        self.config(policy_file='gobble.gobble', group='oslo_policy')
        self.config(enforce_new_defaults=True, group='oslo_policy')
        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'manage_image_cache', {})

        admin_context = glance.context.RequestContext(roles=['admin'])
        enforcer.enforce(admin_context, 'manage_image_cache', {})

    def test_policy_file_default_not_found(self):
        """Missing default policy file should result in a default ruleset"""

        self.config(enforce_new_defaults=True, group='oslo_policy')

        def fake_find_file(self, name):
            return None

        self.mock_object(oslo_config.cfg.ConfigOpts, 'find_file',
                         fake_find_file)

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

        context = glance.context.RequestContext(roles=[])
        self.assertRaises(exception.Forbidden,
                          enforcer.enforce, context, 'manage_image_cache', {})

        admin_context = glance.context.RequestContext(roles=['admin'])
        enforcer.enforce(admin_context, 'manage_image_cache', {})


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

        enforcer = glance.api.policy.Enforcer(
            suppress_deprecation_warnings=True)

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


class TestDefaultPolicyCheckStrings(base.IsolatedUnitTest):

    def test_project_member_check_string(self):
        expected = 'role:member and project_id:%(project_id)s'
        self.assertEqual(expected, base_policy.PROJECT_MEMBER)

    def test_admin_or_project_member_check_string(self):
        expected = ('rule:context_is_admin or '
                    '(role:member and project_id:%(project_id)s)')
        self.assertEqual(expected, base_policy.ADMIN_OR_PROJECT_MEMBER)

    def test_project_member_download_image_check_string(self):
        expected = (
            "role:member and (project_id:%(project_id)s or "
            "project_id:%(member_id)s or 'community':%(visibility)s or "
            "'public':%(visibility)s or 'shared':%(visibility)s)"
        )
        self.assertEqual(
            expected,
            base_policy.
            PROJECT_MEMBER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED
        )

    def test_project_reader_check_string(self):
        expected = 'role:reader and project_id:%(project_id)s'
        self.assertEqual(expected, base_policy.PROJECT_READER)

    def test_admin_or_project_reader_check_string(self):
        expected = ('rule:context_is_admin or '
                    '(role:reader and project_id:%(project_id)s)')
        self.assertEqual(expected, base_policy.ADMIN_OR_PROJECT_READER)

    def test_project_reader_get_image_check_string(self):
        expected = (
            "role:reader and (project_id:%(project_id)s or "
            "project_id:%(member_id)s or \'community\':%(visibility)s or "
            "'public':%(visibility)s or 'shared':%(visibility)s)"
        )
        self.assertEqual(
            expected,
            base_policy.
            PROJECT_READER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED
        )


class TestImageTarget(base.IsolatedUnitTest):
    def test_image_target_ignores_locations(self):
        image = ImageStub()
        target = glance.api.policy.ImageTarget(image)
        self.assertNotIn('locations', list(target))

    def test_image_target_project_id_alias(self):
        image = ImageStub()
        target = glance.api.policy.ImageTarget(image)
        self.assertIn('project_id', target)
        self.assertEqual(image.owner, target['project_id'])
        self.assertEqual(image.owner, target['owner'])

    def test_image_target_transforms(self):
        fake_image = mock.MagicMock()
        fake_image.image_id = mock.sentinel.image_id
        fake_image.owner = mock.sentinel.owner
        fake_image.member = mock.sentinel.member

        target = glance.api.policy.ImageTarget(fake_image)

        # Make sure the key transforms work
        self.assertEqual(mock.sentinel.image_id, target['id'])
        self.assertEqual(mock.sentinel.owner, target['project_id'])
        self.assertEqual(mock.sentinel.member, target['member_id'])

        # Also make sure the base properties still work
        self.assertEqual(mock.sentinel.image_id, target['image_id'])
        self.assertEqual(mock.sentinel.owner, target['owner'])
        self.assertEqual(mock.sentinel.member, target['member'])
