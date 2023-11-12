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

# Generic check string for checking if a user is authorized on a particular
# project, specifically with the member role.
PROJECT_MEMBER = 'role:member and project_id:%(project_id)s'
# Generic check string for checking if a user is authorized on a particular
# project but with read-only access. For example, this persona would be able to
# list private images owned by a project but cannot make any writeable changes
# to those images.
PROJECT_READER = 'role:reader and project_id:%(project_id)s'

# Make sure the member_id of the supplied target matches the project_id from
# the context object, which is derived from keystone tokens.
IMAGE_MEMBER_CHECK = 'project_id:%(member_id)s'
# Check if the visibility of the image supplied in the target matches
# "community"
COMMUNITY_VISIBILITY_CHECK = "'community':%(visibility)s"
# Check if the visibility of the resource supplied in the target matches
# "public"
PUBLIC_VISIBILITY_CHECK = "'public':%(visibility)s"
# Check if the visibility of the image supplied in the target matches "shared"
SHARED_VISIBILITY_CHECK = "'shared':%(visibility)s"

PROJECT_MEMBER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED = (
    f'role:member and (project_id:%(project_id)s or {IMAGE_MEMBER_CHECK} '
    f'or {COMMUNITY_VISIBILITY_CHECK} or {PUBLIC_VISIBILITY_CHECK} '
    f'or {SHARED_VISIBILITY_CHECK})'
)
PROJECT_READER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED = (
    f'role:reader and (project_id:%(project_id)s or {IMAGE_MEMBER_CHECK} '
    f'or {COMMUNITY_VISIBILITY_CHECK} or {PUBLIC_VISIBILITY_CHECK} '
    f'or {SHARED_VISIBILITY_CHECK})'
)
PROJECT_READER_OR_PUBLIC_NAMESPACE = (
    f'role:reader and (project_id:%(project_id)s or {PUBLIC_VISIBILITY_CHECK})'
)


# FIXME(lbragstad): These are composite check strings that represents glance's
# authorization code, some of which is implemented in the authorization wrapper
# and some is in the database driver.
#
# These check strings do not support tenancy with the `admin` role. This means
# anyone with the `admin` role on any project can execute a policy, which is
# typical in OpenStack services. But following check strings offer formal
# support for project membership and a read-only variant consistent with
# other OpenStack services.
ADMIN = 'rule:context_is_admin'
DEFAULT = 'rule:default'
ADMIN_OR_PROJECT_MEMBER = f'{ADMIN} or ({PROJECT_MEMBER})'
ADMIN_OR_PROJECT_READER = f'{ADMIN} or ({PROJECT_READER})'
ADMIN_OR_PROJECT_READER_GET_IMAGE = (
    f'{ADMIN} or '
    f'({PROJECT_READER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED})'
)
ADMIN_OR_PROJECT_MEMBER_DOWNLOAD_IMAGE = (
    f'{ADMIN} or '
    f'({PROJECT_MEMBER_OR_IMAGE_MEMBER_OR_COMMUNITY_OR_PUBLIC_OR_SHARED})'
)
ADMIN_OR_PROJECT_MEMBER_CREATE_IMAGE = (
    f'{ADMIN} or ({PROJECT_MEMBER} and project_id:%(owner)s)'
)
ADMIN_OR_PROJECT_READER_GET_NAMESPACE = (
    f'{ADMIN} or ({PROJECT_READER_OR_PUBLIC_NAMESPACE})'
)


ADMIN_OR_SHARED_MEMBER = (
    f'{ADMIN} or (role:member and {IMAGE_MEMBER_CHECK})'
)
ADMIN_OR_PROJECT_READER_OR_SHARED_MEMBER = (
    f'{ADMIN} or '
    f'role:reader and (project_id:%(project_id)s or {IMAGE_MEMBER_CHECK})'
)

rules = [
    policy.RuleDefault(name='default', check_str='',
                       description='Defines the default rule used for '
                                   'policies that historically had an empty '
                                   'policy in the supplied policy.json file.',
                       deprecated_rule=policy.DeprecatedRule(
                           name='default',
                           check_str=ADMIN,
                           deprecated_reason='In order to allow operators to '
                           'accept the default policies from code by not '
                           'defining them in the policy file, while still '
                           'working with old policy files that rely on the '
                           '``default`` rule for policies that are '
                           'not specified in the policy file, the ``default`` '
                           'rule must now be explicitly set to '
                           '``"role:admin"`` when that is the desired default '
                           'for unspecified rules.',
                           deprecated_since='Ussuri')),
    policy.RuleDefault(name='context_is_admin', check_str='role:admin',
                       description='Defines the rule for the is_admin:True '
                                   'check.'),
]


def list_rules():
    return rules
