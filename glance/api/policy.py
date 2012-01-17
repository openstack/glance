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

from glance.common import cfg
from glance.common import exception
from glance.common import policy


class Enforcer(object):
    """Responsible for loading and enforcing rules"""

    policy_opts = (
        cfg.StrOpt('policy_file', default=None),
        cfg.StrOpt('policy_default_rule', default='default'),
    )

    def __init__(self, conf):
        for opt in self.policy_opts:
            conf.register_opt(opt)

        self.default_rule = conf.policy_default_rule
        self.policy_path = self._find_policy_file(conf)
        self.policy_file_mtime = None
        self.policy_file_contents = None

    def set_rules(self, rules):
        """Create a new Brain based on the provided dict of rules"""
        brain = policy.Brain(rules, self.default_rule)
        policy.set_brain(brain)

    def load_rules(self):
        """Set the rules found in the json file on disk"""
        rules = self._read_policy_file()
        self.set_rules(rules)

    @staticmethod
    def _find_policy_file(conf):
        """Locate the policy json data file"""
        if conf.policy_file:
            return conf.policy_file

        matches = cfg.find_config_files('glance', 'policy', 'json')

        try:
            return matches[0]
        except IndexError:
            raise cfg.ConfigFilesNotFoundError(('policy.json',))

    def _read_policy_file(self):
        """Read contents of the policy file

        This re-caches policy data if the file has been changed.
        """
        mtime = os.path.getmtime(self.policy_path)
        if not self.policy_file_contents or mtime != self.policy_file_mtime:
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
           :raises: `glance.common.exception.NotAuthorized`
           :returns: None
        """
        self.load_rules()

        match_list = ('rule:%s' % action,)
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }

        try:
            policy.enforce(match_list, target, credentials)
        except policy.NotAuthorized:
            raise exception.NotAuthorized(action=action)
