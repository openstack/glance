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
