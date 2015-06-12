#    Copyright 2013 Rackspace
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

from collections import OrderedDict
import re

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import policy
from six.moves import configparser

import glance.api.policy
from glance.common import exception
from glance import i18n

# NOTE(bourke): The default dict_type is collections.OrderedDict in py27, but
# we must set manually for compatibility with py26
CONFIG = configparser.SafeConfigParser(dict_type=OrderedDict)
LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE

property_opts = [
    cfg.StrOpt('property_protection_file',
               help=_('The location of the property protection file.'
                      'This file contains the rules for property protections '
                      'and the roles/policies associated with it. If this '
                      'config value is not specified, by default, property '
                      'protections won\'t be enforced. If a value is '
                      'specified and the file is not found, then the '
                      'glance-api service will not start.')),
    cfg.StrOpt('property_protection_rule_format',
               default='roles',
               choices=('roles', 'policies'),
               help=_('This config value indicates whether "roles" or '
                      '"policies" are used in the property protection file.')),
]

CONF = cfg.CONF
CONF.register_opts(property_opts)

# NOTE (spredzy): Due to the particularly lengthy name of the exception
# and the number of occurrence it is raise in this file, a variable is
# created
InvalidPropProtectConf = exception.InvalidPropertyProtectionConfiguration


def is_property_protection_enabled():
    if CONF.property_protection_file:
        return True
    return False


class PropertyRules(object):

    def __init__(self, policy_enforcer=None):
        self.rules = []
        self.prop_exp_mapping = {}
        self.policies = []
        self.policy_enforcer = policy_enforcer or glance.api.policy.Enforcer()
        self.prop_prot_rule_format = CONF.property_protection_rule_format
        self.prop_prot_rule_format = self.prop_prot_rule_format.lower()
        self._load_rules()

    def _load_rules(self):
        try:
            conf_file = CONF.find_file(CONF.property_protection_file)
            CONFIG.read(conf_file)
        except Exception as e:
            msg = (_LE("Couldn't find property protection file %(file)s: "
                       "%(error)s.") % {'file': CONF.property_protection_file,
                                        'error': e})
            LOG.error(msg)
            raise InvalidPropProtectConf()

        if self.prop_prot_rule_format not in ['policies', 'roles']:
            msg = _LE("Invalid value '%s' for "
                      "'property_protection_rule_format'. "
                      "The permitted values are "
                      "'roles' and 'policies'") % self.prop_prot_rule_format
            LOG.error(msg)
            raise InvalidPropProtectConf()

        operations = ['create', 'read', 'update', 'delete']
        properties = CONFIG.sections()
        for property_exp in properties:
            property_dict = {}
            compiled_rule = self._compile_rule(property_exp)

            for operation in operations:
                permissions = CONFIG.get(property_exp, operation)
                if permissions:
                    if self.prop_prot_rule_format == 'policies':
                        if ',' in permissions:
                            LOG.error(
                                _LE("Multiple policies '%s' not allowed "
                                    "for a given operation. Policies can be "
                                    "combined in the policy file"),
                                permissions)
                            raise InvalidPropProtectConf()
                        self.prop_exp_mapping[compiled_rule] = property_exp
                        self._add_policy_rules(property_exp, operation,
                                               permissions)
                        permissions = [permissions]
                    else:
                        permissions = [permission.strip() for permission in
                                       permissions.split(',')]
                        if '@' in permissions and '!' in permissions:
                            msg = (_LE(
                                "Malformed property protection rule in "
                                "[%(prop)s] %(op)s=%(perm)s: '@' and '!' "
                                "are mutually exclusive") %
                                dict(prop=property_exp,
                                     op=operation,
                                     perm=permissions))
                            LOG.error(msg)
                            raise InvalidPropProtectConf()
                    property_dict[operation] = permissions
                else:
                    property_dict[operation] = []
                    LOG.warn(
                        _('Property protection on operation %(operation)s'
                          ' for rule %(rule)s is not found. No role will be'
                          ' allowed to perform this operation.') %
                        {'operation': operation,
                         'rule': property_exp})

            self.rules.append((compiled_rule, property_dict))

    def _compile_rule(self, rule):
        try:
            return re.compile(rule)
        except Exception as e:
            msg = (_LE("Encountered a malformed property protection rule"
                       " %(rule)s: %(error)s.") % {'rule': rule,
                                                   'error': e})
            LOG.error(msg)
            raise InvalidPropProtectConf()

    def _add_policy_rules(self, property_exp, action, rule):
        """Add policy rules to the policy enforcer.

        For example, if the file listed as property_protection_file has:
        [prop_a]
        create = glance_creator
        then the corresponding policy rule would be:
        "prop_a:create": "rule:glance_creator"
        where glance_creator is defined in policy.json. For example:
        "glance_creator": "role:admin or role:glance_create_user"
        """
        rule = "rule:%s" % rule
        rule_name = "%s:%s" % (property_exp, action)
        rule_dict = policy.Rules.from_dict({
            rule_name: rule
        })
        self.policy_enforcer.add_rules(rule_dict)

    def _check_policy(self, property_exp, action, context):
        try:
            action = ":".join([property_exp, action])
            self.policy_enforcer.enforce(context, action, {})
        except exception.Forbidden:
            return False
        return True

    def check_property_rules(self, property_name, action, context):
        roles = context.roles
        if not self.rules:
            return True

        if action not in ['create', 'read', 'update', 'delete']:
            return False

        for rule_exp, rule in self.rules:
            if rule_exp.search(str(property_name)):
                break
        else:  # no matching rules
            return False

        rule_roles = rule.get(action)
        if rule_roles:
            if '!' in rule_roles:
                return False
            elif '@' in rule_roles:
                return True
            if self.prop_prot_rule_format == 'policies':
                prop_exp_key = self.prop_exp_mapping[rule_exp]
                return self._check_policy(prop_exp_key, action,
                                          context)
            if set(roles).intersection(set([role.lower() for role
                                            in rule_roles])):
                return True
        return False
