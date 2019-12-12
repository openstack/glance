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

from oslo_policy import policy


rules = [
    policy.RuleDefault(name='default', check_str='',
                       description='Defines the default rule used for '
                                   'policies that historically had an empty '
                                   'policy in the supplied policy.json file.',
                       deprecated_rule=policy.DeprecatedRule(
                           name='default',
                           check_str='role:admin'),
                       deprecated_reason='In order to allow operators to '
                       'accept the default policies from code by not defining '
                       'them in the policy file, while still working with old '
                       'policy files that rely on the ``default`` rule for '
                       'policies that are not specified in the policy file, '
                       'the ``default`` rule must now be explicitly set to '
                       '``"role:admin"`` when that is the desired default for '
                       'unspecified rules.',
                       deprecated_since='Ussuri'),
    policy.RuleDefault(name='context_is_admin', check_str='role:admin',
                       description='Defines the rule for the is_admin:True '
                                   'check.'),
]


def list_rules():
    return rules
