# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

import json
import os.path

from glance.common import exception
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
from glance.openstack.common import policy

LOG = logging.getLogger(__name__)

policy_opts = (
    cfg.StrOpt('policy_file', default='policy.json'),
    cfg.StrOpt('policy_default_rule', default='default'),
    )

CONF = cfg.CONF
CONF.register_opts(policy_opts)


DEFAULT_RULES = {
    'default': [[]],
    'manage_image_cache': [['role:admin']]
}


class Enforcer(object):
    """Responsible for loading and enforcing rules"""

    def __init__(self):
        self.default_rule = CONF.policy_default_rule
        self.policy_path = self._find_policy_file()
        self.policy_file_mtime = None
        self.policy_file_contents = None

    def set_rules(self, rules):
        """Create a new Brain based on the provided dict of rules"""
        brain = policy.Brain(rules, self.default_rule)
        policy.set_brain(brain)

    def load_rules(self):
        """Set the rules found in the json file on disk"""
        if self.policy_path:
            rules = self._read_policy_file()
            LOG.debug(_('Loaded policy rules: %s') % rules)
        else:
            rules = DEFAULT_RULES
            LOG.debug(_('Using default policy rules: %s') % rules)
        self.set_rules(rules)

    @staticmethod
    def _find_policy_file():
        """Locate the policy json data file"""
        policy_file = CONF.find_file(CONF.policy_file)
        if policy_file:
            return policy_file
        else:
            LOG.warn(_('Unable to find policy file'))
            return None

    def _read_policy_file(self):
        """Read contents of the policy file

        This re-caches policy data if the file has been changed.
        """
        mtime = os.path.getmtime(self.policy_path)
        if not self.policy_file_contents or mtime != self.policy_file_mtime:
            LOG.debug(_("Loading policy from %s") % self.policy_path)
            with open(self.policy_path) as fap:
                raw_contents = fap.read()
                self.policy_file_contents = json.loads(raw_contents)
            self.policy_file_mtime = mtime
        return self.policy_file_contents

    def enforce(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: None
        """
        self.load_rules()

        match_list = ('rule:%s' % action,)
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }

        policy.enforce(match_list, target, credentials,
                       exception.Forbidden, action=action)
