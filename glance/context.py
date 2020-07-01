# Copyright 2011-2014 OpenStack Foundation
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

import copy

from oslo_context import context

from glance.api import policy


class RequestContext(context.RequestContext):
    """Stores information about the security context.

    Stores how the user accesses the system, as well as additional request
    information.

    """

    def __init__(self, owner_is_tenant=True, service_catalog=None,
                 policy_enforcer=None, **kwargs):
        # TODO(mriedem): Remove usage of user and tenant from old tests.
        if 'tenant' in kwargs:
            # Prefer project_id if passed, otherwise alias tenant as project_id
            tenant = kwargs.pop('tenant')
            kwargs['project_id'] = kwargs.get('project_id', tenant)
        if 'user' in kwargs:
            # Prefer user_id if passed, otherwise alias user as user_id
            user = kwargs.pop('user')
            kwargs['user_id'] = kwargs.get('user_id', user)
        super(RequestContext, self).__init__(**kwargs)
        self.owner_is_tenant = owner_is_tenant
        self.service_catalog = service_catalog
        self.policy_enforcer = policy_enforcer or policy.Enforcer()
        if not self.is_admin:
            self.is_admin = self.policy_enforcer.check_is_admin(self)

    def to_dict(self):
        d = super(RequestContext, self).to_dict()
        d.update({
            'roles': self.roles,
            'service_catalog': self.service_catalog,
        })
        return d

    def to_policy_values(self):
        pdict = super(RequestContext, self).to_policy_values()
        pdict['user_id'] = self.user_id
        pdict['project_id'] = self.project_id
        return pdict

    @classmethod
    def from_dict(cls, values):
        return cls(**values)

    @property
    def owner(self):
        """Return the owner to correlate with an image."""
        return self.project_id if self.owner_is_tenant else self.user_id

    @property
    def can_see_deleted(self):
        """Admins can see deleted by default"""
        return self.show_deleted or self.is_admin

    def elevated(self):
        """Return a copy of this context with admin flag set."""

        context = copy.copy(self)
        context.roles = copy.deepcopy(self.roles)
        if 'admin' not in context.roles:
            context.roles.append('admin')

        context.is_admin = True

        return context


def get_admin_context(show_deleted=False):
    """Create an administrator context."""
    return RequestContext(auth_token=None,
                          project_id=None,
                          is_admin=True,
                          show_deleted=show_deleted,
                          overwrite=False)
