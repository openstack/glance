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
from oslo_log import versionutils
from oslo_policy import policy

from glance.policies import base


DEPRECATED_REASON = """
The image API now supports roles.
"""


cache_policies = [
    policy.DocumentedRuleDefault(
        name="cache_image",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Queue image for caching',
        operations=[
            {'path': '/v2/cache/{image_id}',
             'method': 'PUT'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="cache_image", check_str="rule:manage_image_cache",
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="cache_list",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='List cache status',
        operations=[
            {'path': '/v2/cache',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="cache_list", check_str="rule:manage_image_cache",
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="cache_delete",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Delete image(s) from cache and/or queue',
        operations=[
            {'path': '/v2/cache',
             'method': 'DELETE'},
            {'path': '/v2/cache/{image_id}',
             'method': 'DELETE'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="cache_delete", check_str="rule:manage_image_cache",
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
]


def list_rules():
    return cache_policies
