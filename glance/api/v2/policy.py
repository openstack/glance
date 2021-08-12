# Copyright 2021 Red Hat, Inc.
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

from oslo_config import cfg
from oslo_log import log as logging
import webob.exc

from glance.api import policy
from glance.common import exception
from glance.i18n import _

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


# TODO(danms): Remove this once secure RBAC is fully implemented and
# used instead of legacy policy checks.
def check_is_image_mutable(context, image):
    """Replicate the DB-layer admin-or-owner check for the API.

    Much of the API code depends on hard-coded admin-or-owner
    enforcement in the DB or authorization layer, as the policy layer
    is largely a no-op by default. During blueprint policy-refactor,
    we are trying to remove as much of that as possible, but in
    certain places we need to do that (if secure_rbac is not
    enabled). This transitional helper provides a way to do that
    enforcement where necessary.

    :param context: A RequestContext
    :param image: An ImageProxy
    :raises: exception.Forbidden if the context is not the owner or an admin
    """
    # Is admin == image mutable
    if context.is_admin:
        return

    # No owner == image not mutable
    # Image only mutable by its owner
    if (image.owner is None or context.owner is None or
            image.owner != context.owner):
        raise exception.Forbidden(_('You do not own this image'))


class APIPolicyBase(object):
    def __init__(self, context, target=None, enforcer=None):
        self._context = context
        self._target = target or {}
        self.enforcer = enforcer or policy.Enforcer()

    def _enforce(self, rule_name):
        try:
            self.enforcer.enforce(self._context, rule_name, self._target)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=str(e))

    def check(self, name, *args):
        """Perform a soft check of a named policy.

        This is used when you need to check if a policy is allowed for the
        given resource, without needing to catch an exception. If the policy
        check requires args, those are accepted here as well.

        :param name: Policy name to check
        :returns: bool indicating if the policy is allowed.
        """
        try:
            getattr(self, name)(*args)
            return True
        except webob.exc.HTTPForbidden:
            return False


class ImageAPIPolicy(APIPolicyBase):
    def __init__(self, context, image, enforcer=None):
        super(ImageAPIPolicy, self).__init__(context,
                                             policy.ImageTarget(image),
                                             enforcer)
        self._image = image

    def _enforce(self, rule_name):
        """Translate Forbidden->NotFound for images."""
        try:
            super(ImageAPIPolicy, self)._enforce(rule_name)
        except webob.exc.HTTPForbidden:
            # If we are checking get_image, then Forbidden means the
            # user cannot see this image, so raise NotFound. If we are
            # checking anything else and get Forbidden, then raise
            # NotFound in that case as well to avoid exposing images
            # the user can not see, while preserving the Forbidden
            # behavior for the ones they can see.
            if rule_name == 'get_image' or not self.check('get_image'):
                raise webob.exc.HTTPNotFound()
            raise

    def check(self, name, *args):
        try:
            return super(ImageAPIPolicy, self).check(name, *args)
        except webob.exc.HTTPNotFound:
            # NOTE(danms): Since our _enforce can raise NotFound, that
            # too means a False check response.
            return False

    def _enforce_visibility(self, visibility):
        # NOTE(danms): Use the existing enforcement routine for now,
        # which shows that we're enforcing the same behavior. In the
        # future, that should probably be moved here.
        try:
            policy._enforce_image_visibility(self.enforcer, self._context,
                                             visibility, self._target)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=str(e))

    def update_property(self, name, value=None):
        if name == 'visibility':
            # NOTE(danms): Visibility changes have their own policy,
            # so check that first, followed by the general
            # modify_image policy below.
            self._enforce_visibility(value)
        self._enforce('modify_image')

    def update_locations(self):
        self._enforce('set_image_location')

    def delete_locations(self):
        self._enforce('delete_image_location')

    def get_image(self):
        self._enforce('get_image')

    def get_images(self):
        self._enforce('get_images')

    def delete_image(self):
        self._enforce('delete_image')
        # TODO(danms): Remove this legacy fallback when secure RBAC
        # replaces the legacy policy.
        if not CONF.enforce_secure_rbac:
            check_is_image_mutable(self._context, self._image)


class MetadefAPIPolicy(APIPolicyBase):
    def __init__(self, context, md_resource=None, target=None, enforcer=None):
        self._context = context
        self._md_resource = md_resource
        if not target:
            self._target = self._build_target()
        else:
            self._target = target
        self.enforcer = enforcer or policy.Enforcer()
        super(MetadefAPIPolicy, self).__init__(context, target=self._target,
                                               enforcer=self.enforcer)

    def _build_target(self):
        target = {
            "project_id": self._context.project_id
        }
        if self._md_resource:
            target['project_id'] = self._md_resource.owner
            target['visibility'] = self._md_resource.visibility

        return target

    def _enforce(self, rule_name):
        """Translate Forbidden->NotFound for images."""
        try:
            super(MetadefAPIPolicy, self)._enforce(rule_name)
        except webob.exc.HTTPForbidden:
            # If we are checking get_metadef_namespace, then Forbidden means
            # the user cannot see this namespace, so raise NotFound. If we are
            # checking anything else and get Forbidden, then raise
            # NotFound in that case as well to avoid exposing namespaces
            # the user can not see, while preserving the Forbidden
            # behavior for the ones they can see.
            if rule_name == 'get_metadef_namespace' or not self.check(
                    'get_metadef_namespace'):
                raise webob.exc.HTTPNotFound()
            raise

    def check(self, name, *args):
        try:
            return super(MetadefAPIPolicy, self).check(name, *args)
        except webob.exc.HTTPNotFound:
            # NOTE(danms): Since our _enforce can raise NotFound, that
            # too means a False check response.
            return False

    def get_metadef_namespace(self):
        self._enforce('get_metadef_namespace')

    def get_metadef_namespaces(self):
        self._enforce('get_metadef_namespaces')

    def add_metadef_namespace(self):
        self._enforce('add_metadef_namespace')

    def modify_metadef_namespace(self):
        self._enforce('modify_metadef_namespace')

    def delete_metadef_namespace(self):
        self._enforce('delete_metadef_namespace')

    def get_metadef_objects(self):
        self._enforce('get_metadef_objects')

    def add_metadef_object(self):
        self._enforce('add_metadef_object')

    def get_metadef_object(self):
        self._enforce('get_metadef_object')

    def modify_metadef_object(self):
        self._enforce('modify_metadef_object')

    def delete_metadef_object(self):
        self._enforce('delete_metadef_object')

    def add_metadef_tag(self):
        self._enforce('add_metadef_tag')

    def get_metadef_tags(self):
        self._enforce('get_metadef_tags')

    def delete_metadef_tags(self):
        self._enforce('delete_metadef_tags')

    def add_metadef_property(self):
        self._enforce('add_metadef_property')

    def get_metadef_properties(self):
        self._enforce('get_metadef_properties')

    def add_metadef_resource_type_association(self):
        self._enforce('add_metadef_resource_type_association')

    def list_metadef_resource_types(self):
        self._enforce('list_metadef_resource_types')


class MemberAPIPolicy(APIPolicyBase):
    def __init__(self, context, image, target=None, enforcer=None):
        self._context = context
        self._image = image
        if not target:
            self._target = self._build_target()

        self.enforcer = enforcer or policy.Enforcer()
        super(MemberAPIPolicy, self).__init__(context, target=self._target,
                                              enforcer=self.enforcer)

    def _build_target(self):
        target = {
            "project_id": self._context.project_id
        }
        if self._image:
            target = policy.ImageTarget(self._image)

        return target

    def _enforce(self, rule_name):
        ImageAPIPolicy(self._context, self._image,
                       enforcer=self.enforcer).get_image()
        super(MemberAPIPolicy, self)._enforce(rule_name)

    def get_members(self):
        self._enforce("get_members")

    def get_member(self):
        self._enforce("get_member")

    def delete_member(self):
        self._enforce("delete_member")

    def modify_member(self):
        self._enforce("modify_member")

    def add_member(self):
        self._enforce("add_member")
