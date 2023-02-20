# Copyright 2021 Red Hat, Inc
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

import webob.exc

from glance.api.v2 import policy
from glance.common import exception
from glance.tests import utils


class APIPolicyBase(utils.BaseTestCase):
    def setUp(self):
        super(APIPolicyBase, self).setUp()
        self.enforcer = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.APIPolicyBase(self.context,
                                           enforcer=self.enforcer)

    def test_enforce(self):
        # Enforce passes
        self.policy._enforce('fake_rule')
        self.enforcer.enforce.assert_called_once_with(
            self.context,
            'fake_rule',
            mock.ANY)

        # Make sure that Forbidden gets caught and translated
        self.enforcer.enforce.side_effect = exception.Forbidden
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.policy._enforce, 'fake_rule')

        # Any other exception comes straight through
        self.enforcer.enforce.side_effect = exception.ImageNotFound
        self.assertRaises(exception.ImageNotFound,
                          self.policy._enforce, 'fake_rule')

    def test_check(self):
        # Check passes
        self.assertTrue(self.policy.check('_enforce', 'fake_rule'))

        # Check fails
        self.enforcer.enforce.side_effect = exception.Forbidden
        self.assertFalse(self.policy.check('_enforce', 'fake_rule'))

    def test_check_is_image_mutable(self):
        context = mock.MagicMock()
        image = mock.MagicMock()

        # Admin always wins
        context.is_admin = True
        context.owner = 'someuser'
        self.assertIsNone(policy.check_is_image_mutable(context, image))

        # Image has no owner is never mutable by non-admins
        context.is_admin = False
        image.owner = None
        self.assertRaises(exception.Forbidden,
                          policy.check_is_image_mutable,
                          context, image)

        # Not owner is not mutable
        image.owner = 'someoneelse'
        self.assertRaises(exception.Forbidden,
                          policy.check_is_image_mutable,
                          context, image)

        # No project in context means not mutable
        image.owner = 'someoneelse'
        context.owner = None
        self.assertRaises(exception.Forbidden,
                          policy.check_is_image_mutable,
                          context, image)

        # Context matches image owner is mutable
        image.owner = 'someuser'
        context.owner = 'someuser'
        self.assertIsNone(policy.check_is_image_mutable(context, image))


class APIImagePolicy(APIPolicyBase):
    def setUp(self):
        super(APIImagePolicy, self).setUp()
        self.image = mock.MagicMock()
        self.policy = policy.ImageAPIPolicy(self.context, self.image,
                                            enforcer=self.enforcer)

    def test_enforce(self):
        self.assertRaises(webob.exc.HTTPNotFound,
                          super(APIImagePolicy, self).test_enforce)

    @mock.patch('glance.api.policy._enforce_image_visibility')
    def test_enforce_visibility(self, mock_enf):
        # Visibility passes
        self.policy._enforce_visibility('something')
        mock_enf.assert_called_once_with(self.enforcer,
                                         self.context,
                                         'something',
                                         mock.ANY)

        # Make sure that Forbidden gets caught and translated
        mock_enf.side_effect = exception.Forbidden
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.policy._enforce_visibility, 'something')

        # Any other exception comes straight through
        mock_enf.side_effect = exception.ImageNotFound
        self.assertRaises(exception.ImageNotFound,
                          self.policy._enforce_visibility, 'something')

    def test_update_property(self):
        with mock.patch.object(self.policy, '_enforce') as mock_enf:
            self.policy.update_property('foo', None)
            mock_enf.assert_called_once_with('modify_image')

        with mock.patch.object(self.policy, '_enforce_visibility') as mock_enf:
            self.policy.update_property('visibility', 'foo')
            mock_enf.assert_called_once_with('foo')

    def test_update_locations(self):
        self.policy.update_locations()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'set_image_location',
                                                      mock.ANY)

    def test_delete_locations(self):
        self.policy.delete_locations()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'delete_image_location',
                                                      mock.ANY)

    def test_delete_locations_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.delete_locations()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.delete_locations()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.delete_locations)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.delete_locations()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=True and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.delete_locations()
            self.assertFalse(m.called)

    def test_get_image_location(self):
        self.policy.get_image_location()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_image_location',
                                                      mock.ANY)

    def test_enforce_exception_behavior(self):
        with mock.patch.object(self.policy.enforcer, 'enforce') as mock_enf:
            # First make sure we can update if allowed
            self.policy.update_property('foo', None)
            self.assertTrue(mock_enf.called)

            # Make sure that if modify_image and get_image both return
            # Forbidden then we should get NotFound. This is because
            # we are not allowed to delete the image, nor see that it
            # even exists.
            mock_enf.reset_mock()
            mock_enf.side_effect = exception.Forbidden
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.policy.update_property, 'foo', None)
            # Make sure we checked modify_image, and then get_image.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'modify_image', mock.ANY),
                mock.call(mock.ANY, 'get_image', mock.ANY)])

            # Make sure that if modify_image is disallowed, but
            # get_image is allowed, that we get Forbidden. This is
            # because we are allowed to see the image, but not modify
            # it, so 403 indicates that without confusing the user and
            # returning "not found" for an image they are able to GET.
            mock_enf.reset_mock()
            mock_enf.side_effect = [exception.Forbidden, lambda *a: None]
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.policy.update_property, 'foo', None)
            # Make sure we checked modify_image, and then get_image.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'modify_image', mock.ANY),
                mock.call(mock.ANY, 'get_image', mock.ANY)])

    def test_get_image(self):
        self.policy.get_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_image',
                                                      mock.ANY)

    def test_get_images(self):
        self.policy.get_images()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_images',
                                                      mock.ANY)

    def test_add_image(self):
        generic_target = {'project_id': self.context.project_id,
                          'owner': self.context.project_id,
                          'visibility': 'private'}
        self.policy = policy.ImageAPIPolicy(self.context, {},
                                            enforcer=self.enforcer)
        self.policy.add_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_image',
                                                      generic_target)

    def test_add_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        self.context.is_admin = False
        self.policy = policy.ImageAPIPolicy(self.context, {'owner': 'else'},
                                            enforcer=self.enforcer)
        self.assertRaises(exception.Forbidden, self.policy.add_image)

        # Make sure we're calling the legacy handler if secure_rbac is False
        with mock.patch('glance.api.v2.policy.check_admin_or_same_owner') as m:
            self.policy.add_image()
            m.assert_called_once_with(self.context, {'project_id': 'else',
                                                     'owner': 'else',
                                                     'visibility': 'private'})

        # Make sure we are not calling the legacy handler if
        # secure_rbac is being used. We won't fail the check because
        # our enforcer is a mock, just make sure we don't call that handler.
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_admin_or_same_owner') as m:
            self.policy.add_image()
            m.assert_not_called()

    def test_add_image_translates_owner_failure(self):
        self.policy = policy.ImageAPIPolicy(self.context, {'owner': 'else'},
                                            enforcer=self.enforcer)
        # Make sure add_image works with no exception
        self.policy.add_image()

        # Make sure we don't get in the way of any other exceptions
        self.enforcer.enforce.side_effect = exception.Duplicate
        self.assertRaises(exception.Duplicate, self.policy.add_image)

        # If the exception is HTTPForbidden and the owner differs,
        # make sure we get the proper message translation
        self.enforcer.enforce.side_effect = webob.exc.HTTPForbidden('original')
        exc = self.assertRaises(webob.exc.HTTPForbidden, self.policy.add_image)
        self.assertIn('You are not permitted to create images owned by',
                      str(exc))

        # If the owner does not differ, make sure we get the original reason
        self.policy = policy.ImageAPIPolicy(self.context, {},
                                            enforcer=self.enforcer)
        exc = self.assertRaises(webob.exc.HTTPForbidden, self.policy.add_image)
        self.assertIn('original', str(exc))

    def test_delete_image(self):
        self.policy.delete_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'delete_image',
                                                      mock.ANY)

    def test_delete_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')
        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.delete_image()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.delete_image()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.delete_image)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.delete_image()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=True and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.delete_image()
            self.assertFalse(m.called)

    def test_upload_image(self):
        self.policy.upload_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'upload_image',
                                                      mock.ANY)

    def test_upload_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.upload_image()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.upload_image()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.upload_image)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.upload_image()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=True and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.upload_image()
            self.assertFalse(m.called)

    def test_download_image(self):
        self.policy.download_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'download_image',
                                                      mock.ANY)

    def test_modify_image(self):
        self.policy.modify_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'modify_image',
                                                      mock.ANY)

    def test_modify_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.modify_image()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.modify_image()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.modify_image)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.modify_image()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=True and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.modify_image()
            self.assertFalse(m.called)

    def test_deactivate_image(self):
        self.policy.deactivate_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'deactivate',
                                                      mock.ANY)

    def test_deactivate_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.deactivate_image()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.delete_image()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.deactivate_image)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.deactivate_image()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=Truei and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.deactivate_image()
            self.assertFalse(m.called)

    def test_reactivate_image(self):
        self.policy.reactivate_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'reactivate',
                                                      mock.ANY)

    def test_reactivate_image_falls_back_to_legacy(self):
        self.config(enforce_new_defaults=False, group='oslo_policy')
        self.config(enforce_scope=False, group='oslo_policy')

        # As admin, image is mutable even if owner does not match
        self.context.is_admin = True
        self.context.owner = 'someuser'
        self.image.owner = 'someotheruser'
        self.policy.reactivate_image()

        # As non-admin, owner matches, so we're good
        self.context.is_admin = False
        self.context.owner = 'someuser'
        self.image.owner = 'someuser'
        self.policy.delete_image()

        # If owner does not match, we fail
        self.image.owner = 'someotheruser'
        self.assertRaises(exception.Forbidden,
                          self.policy.reactivate_image)

        # Make sure we are checking the legacy handler
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.reactivate_image()
            m.assert_called_once_with(self.context, self.image)

        # Make sure we are not checking it if enforce_new_defaults=True and
        # enforce_scope=True
        self.config(enforce_new_defaults=True, group='oslo_policy')
        self.config(enforce_scope=True, group='oslo_policy')
        with mock.patch('glance.api.v2.policy.check_is_image_mutable') as m:
            self.policy.reactivate_image()
            self.assertFalse(m.called)

    def test_copy_image(self):
        self.policy.copy_image()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'copy_image',
                                                      mock.ANY)


class TestMetadefAPIPolicy(APIPolicyBase):
    def setUp(self):
        super(TestMetadefAPIPolicy, self).setUp()
        self.enforcer = mock.MagicMock()
        self.md_resource = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.MetadefAPIPolicy(self.context, self.md_resource,
                                              enforcer=self.enforcer)

    def test_enforce(self):
        self.assertRaises(webob.exc.HTTPNotFound,
                          super(TestMetadefAPIPolicy, self).test_enforce)

    def test_get_metadef_namespace(self):
        self.policy.get_metadef_namespace()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_namespace',
                                                      mock.ANY)

    def test_get_metadef_namespaces(self):
        self.policy.get_metadef_namespaces()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_namespaces',
                                                      mock.ANY)

    def test_add_metadef_namespace(self):
        self.policy.add_metadef_namespace()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_metadef_namespace',
                                                      mock.ANY)

    def test_modify_metadef_namespace(self):
        self.policy.modify_metadef_namespace()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'modify_metadef_namespace', mock.ANY)

    def test_delete_metadef_namespace(self):
        self.policy.delete_metadef_namespace()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'delete_metadef_namespace', mock.ANY)

    def test_get_metadef_objects(self):
        self.policy.get_metadef_objects()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_objects',
                                                      mock.ANY)

    def test_get_metadef_object(self):
        self.policy.get_metadef_object()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_object',
                                                      mock.ANY)

    def test_add_metadef_object(self):
        self.policy.add_metadef_object()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_metadef_object',
                                                      mock.ANY)

    def test_modify_metadef_object(self):
        self.policy.modify_metadef_object()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'modify_metadef_object',
                                                      mock.ANY)

    def test_delete_metadef_object(self):
        self.policy.delete_metadef_object()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'delete_metadef_object',
                                                      mock.ANY)

    def test_add_metadef_tag(self):
        self.policy.add_metadef_tag()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_metadef_tag',
                                                      mock.ANY)

    def test_add_metadef_tags(self):
        self.policy.add_metadef_tags()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_metadef_tags',
                                                      mock.ANY)

    def test_get_metadef_tags(self):
        self.policy.get_metadef_tags()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_tags',
                                                      mock.ANY)

    def test_get_metadef_tag(self):
        self.policy.get_metadef_tag()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_tag',
                                                      mock.ANY)

    def modify_metadef_tag(self):
        self.policy.modify_metadef_tag()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'modify_metadef_tag',
                                                      mock.ANY)

    def test_delete_metadef_tags(self):
        self.policy.delete_metadef_tags()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'delete_metadef_tags',
                                                      mock.ANY)

    def test_delete_metadef_tag(self):
        self.policy.delete_metadef_tag()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'delete_metadef_tag',
                                                      mock.ANY)

    def test_add_metadef_property(self):
        self.policy.add_metadef_property()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'add_metadef_property',
                                                      mock.ANY)

    def test_get_metadef_properties(self):
        self.policy.get_metadef_properties()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_properties',
                                                      mock.ANY)

    def test_get_metadef_property(self):
        self.policy.get_metadef_property()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'get_metadef_property',
                                                      mock.ANY)

    def test_modify_metadef_property(self):
        self.policy.modify_metadef_property()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'modify_metadef_property', mock.ANY)

    def test_remove_metadef_property(self):
        self.policy.remove_metadef_property()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'remove_metadef_property', mock.ANY)

    def test_add_metadef_resource_type_association(self):
        self.policy.add_metadef_resource_type_association()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'add_metadef_resource_type_association', mock.ANY)

    def test_list_metadef_resource_types(self):
        self.policy.list_metadef_resource_types()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'list_metadef_resource_types', mock.ANY)

    def test_enforce_exception_behavior(self):
        with mock.patch.object(self.policy.enforcer, 'enforce') as mock_enf:
            # First make sure we can update if allowed
            self.policy.modify_metadef_namespace()
            self.assertTrue(mock_enf.called)

            # Make sure that if modify_metadef_namespace and
            # get_metadef_namespace both return Forbidden then we
            # should get NotFound. This is because we are not allowed
            # to modify the namespace, nor see that it even exists.
            mock_enf.reset_mock()
            mock_enf.side_effect = exception.Forbidden
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.policy.modify_metadef_namespace)
            # Make sure we checked modify_metadef_namespace, and then
            # get_metadef_namespace.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'modify_metadef_namespace', mock.ANY),
                mock.call(mock.ANY, 'get_metadef_namespace', mock.ANY)])

            # Make sure that if modify_metadef_namespace is disallowed, but
            # get_metadef_namespace is allowed, that we get Forbidden. This is
            # because we are allowed to see the namespace, but not modify
            # it, so 403 indicates that without confusing the user and
            # returning "not found" for a namespace they are able to GET.
            mock_enf.reset_mock()
            mock_enf.side_effect = [exception.Forbidden, lambda *a: None]
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.policy.modify_metadef_namespace)
            # Make sure we checked modify_metadef_namespace, and then
            # get_metadef_namespace.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'modify_metadef_namespace', mock.ANY),
                mock.call(mock.ANY, 'get_metadef_namespace', mock.ANY)])

    def test_get_metadef_resource_type(self):
        self.policy.get_metadef_resource_type()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'get_metadef_resource_type', mock.ANY)

    def test_remove_metadef_resource_type_association(self):
        self.policy.remove_metadef_resource_type_association()
        self.enforcer.enforce.assert_called_once_with(
            self.context, 'remove_metadef_resource_type_association', mock.ANY)


class TestMemberAPIPolicy(utils.BaseTestCase):
    def setUp(self):
        super(TestMemberAPIPolicy, self).setUp()
        self.enforcer = mock.MagicMock()
        self.image = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.MemberAPIPolicy(self.context, self.image,
                                             enforcer=self.enforcer)

    def test_enforce(self):
        # Enforce passes
        self.policy._enforce('fake_rule')
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'fake_rule', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_get_member(self):
        self.policy.get_member()
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'get_member', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_get_members(self):
        self.policy.get_members()
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'get_members', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_add_member(self):
        self.policy.add_member()
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'add_member', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_modify_member(self):
        self.policy.modify_member()
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'modify_member', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_delete_member(self):
        self.policy.delete_member()
        expected_calls = [
            mock.call(self.context, 'get_image', mock.ANY),
            mock.call(self.context, 'delete_member', mock.ANY)
        ]
        self.enforcer.enforce.assert_has_calls(expected_calls)

    def test_enforce_exception_behavior(self):
        with mock.patch.object(self.policy.enforcer, 'enforce') as mock_enf:
            # First make sure we can update if allowed
            self.policy.modify_member()
            self.assertTrue(mock_enf.called)

            # Make sure that if while checking modify_member if get_image
            # both returns forbidden then we should get NotFound. This is
            # because we are not allowed to fetch image details.
            mock_enf.reset_mock()
            mock_enf.side_effect = exception.Forbidden
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.policy.modify_member)
            # Make sure we checked modify_image, and then get_image.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'get_image', mock.ANY)])

            # Make sure that if modify_member is disallowed, but
            # get_image is allowed, that we get Forbidden. This is
            # because we are allowed to see the image, but not modify
            # it, so 403 indicates that without confusing the user and
            # returning "not found" for an image they are able to GET.
            mock_enf.reset_mock()
            mock_enf.side_effect = [lambda *a: None, exception.Forbidden]
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.policy.modify_member)
            # Make sure we checked get_image, and then modify_member.
            mock_enf.assert_has_calls([
                mock.call(mock.ANY, 'get_image', mock.ANY),
                mock.call(mock.ANY, 'modify_member', mock.ANY)])


class TestTasksAPIPolicy(APIPolicyBase):
    def setUp(self):
        super(TestTasksAPIPolicy, self).setUp()
        self.enforcer = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.TasksAPIPolicy(self.context,
                                            enforcer=self.enforcer)

    def test_tasks_api_access(self):
        self.policy.tasks_api_access()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'tasks_api_access',
                                                      mock.ANY)


class TestCacheImageAPIPolicy(utils.BaseTestCase):
    def setUp(self):
        super(TestCacheImageAPIPolicy, self).setUp()
        self.enforcer = mock.MagicMock()
        self.context = mock.MagicMock()

    def test_manage_image_cache(self):
        self.policy = policy.CacheImageAPIPolicy(
            self.context, enforcer=self.enforcer,
            policy_str='manage_image_cache')
        self.policy.manage_image_cache()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'manage_image_cache',
                                                      mock.ANY)

    def test_manage_image_cache_with_cache_delete(self):
        self.policy = policy.CacheImageAPIPolicy(
            self.context, enforcer=self.enforcer,
            policy_str='cache_delete')
        self.policy.manage_image_cache()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'cache_delete',
                                                      mock.ANY)

    def test_manage_image_cache_with_cache_list(self):
        self.policy = policy.CacheImageAPIPolicy(
            self.context, enforcer=self.enforcer,
            policy_str='cache_list')
        self.policy.manage_image_cache()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'cache_list',
                                                      mock.ANY)

    def test_manage_image_cache_with_cache_image(self):
        self.policy = policy.CacheImageAPIPolicy(
            self.context, enforcer=self.enforcer,
            policy_str='cache_image')
        self.policy.manage_image_cache()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'cache_image',
                                                      mock.ANY)


class TestDiscoveryAPIPolicy(APIPolicyBase):
    def setUp(self):
        super(TestDiscoveryAPIPolicy, self).setUp()
        self.enforcer = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.DiscoveryAPIPolicy(
            self.context, enforcer=self.enforcer)

    def test_stores_info_detail(self):
        self.policy.stores_info_detail()
        self.enforcer.enforce.assert_called_once_with(self.context,
                                                      'stores_info_detail',
                                                      mock.ANY)
