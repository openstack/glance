# Copyright (c) 2011 OpenStack Foundation
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

"""Policy Engine For Glance"""

from collections import abc

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import opts
from oslo_policy import policy

from glance.common import exception
from glance.domain import proxy
from glance import policies


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
_ENFORCER = None


# TODO(gmann): Remove overriding the default value of config options
# 'policy_file', 'enforce_scope', and 'enforce_new_defaults' once
# oslo_policy change their default value to what is overridden here.
DEFAULT_POLICY_FILE = 'policy.yaml'
opts.set_defaults(
    cfg.CONF,
    DEFAULT_POLICY_FILE,
    enforce_scope=True,
    enforce_new_defaults=True)


class Enforcer(policy.Enforcer):
    """Responsible for loading and enforcing rules"""

    def __init__(self, suppress_deprecation_warnings=False):
        """Init an policy Enforcer.
           :param suppress_deprecation_warnings: Whether to suppress the
                                                 deprecation warnings.
        """
        super(Enforcer, self).__init__(CONF, use_conf=True, overwrite=False)
        # NOTE(gmann): Explicitly disable the warnings for policies
        # changing their default check_str. For new RBAC, all the policy
        # defaults have been changed and warning for each policy started
        # filling the logs limit for various tool.
        # Once we move to new defaults only world then we can enable these
        # warning again.
        self.suppress_default_change_warnings = True
        if suppress_deprecation_warnings:
            self.suppress_deprecation_warnings = True
        self.register_defaults(policies.list_rules())

    def add_rules(self, rules):
        """Add new rules to the Rules object"""
        self.set_rules(rules, overwrite=False, use_conf=self.use_conf)

    def enforce(self, context, action, target, registered=True):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        if registered and action not in self.registered_rules:
            raise policy.PolicyNotRegistered(action)
        try:
            return super(Enforcer, self).enforce(action, target,
                                                 context,
                                                 do_raise=True,
                                                 exc=exception.Forbidden,
                                                 action=action)
        except policy.InvalidScope:
            raise exception.Forbidden(action=action)

    def check(self, context, action, target, registered=True):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        if registered and action not in self.registered_rules:
            raise policy.PolicyNotRegistered(action)
        return super(Enforcer, self).enforce(action,
                                             target,
                                             context)

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        return self.check(context, 'context_is_admin', context.to_dict())


def get_enforcer():
    CONF([], project='glance')
    global _ENFORCER
    if _ENFORCER is None:
        _ENFORCER = Enforcer()
    return _ENFORCER


def _enforce_image_visibility(policy, context, visibility, target):
    if visibility == 'public':
        policy.enforce(context, 'publicize_image', target)
    elif visibility == 'community':
        policy.enforce(context, 'communitize_image', target)


class ImageTarget(abc.Mapping):
    SENTINEL = object()

    def __init__(self, target):
        """Initialize the object

        :param target: Object being targeted
        """
        self.target = target
        self._target_keys = [k for k in dir(proxy.Image)
                             if not k.startswith('__')
                             # NOTE(lbragstad): The locations attributes is an
                             # instance of ImageLocationsProxy, which isn't
                             # serialized into anything oslo.policy can use. If
                             # we need to use locations in policies, we need to
                             # modify how we represent those location objects
                             # before we call enforcement with target
                             # information. Omitting for not until that is a
                             # necessity.
                             if not k == 'locations'
                             if not callable(getattr(proxy.Image, k))]

    def __getitem__(self, key):
        """Return the value of 'key' from the target.

        If the target has the attribute 'key', return it.

        :param key: value to retrieve
        """
        key = self.key_transforms(key)

        value = getattr(self.target, key, self.SENTINEL)
        if value is self.SENTINEL:
            extra_properties = getattr(self.target, 'extra_properties', None)
            if extra_properties is not None:
                value = extra_properties[key]
            else:
                value = None
        return value

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __len__(self):
        length = len(self._target_keys)
        length += len(getattr(self.target, 'extra_properties', {}))
        return length

    def __iter__(self):
        for key in self._target_keys:
            yield key
        for key in getattr(self.target, 'extra_properties', {}).keys():
            yield key
        for alias in ['project_id']:
            yield alias

    def key_transforms(self, key):
        transforms = {
            'id': 'image_id',
            'project_id': 'owner',
            'member_id': 'member',
        }

        return transforms.get(key, key)
