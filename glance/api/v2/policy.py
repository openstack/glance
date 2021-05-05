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

from oslo_log import log as logging
import webob.exc

from glance.api import policy
from glance.common import exception

LOG = logging.getLogger(__name__)


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
