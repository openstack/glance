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


image_policies = [
    policy.DocumentedRuleDefault(
        name="add_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER_CREATE_IMAGE,
        scope_types=['project'],
        description='Create new image',
        operations=[
            {'path': '/v2/images',
             'method': 'POST'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="add_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY)
    ),
    policy.DocumentedRuleDefault(
        name="delete_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Deletes the image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'DELETE'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="delete_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="get_image",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_IMAGE,
        scope_types=['project'],
        description='Get specified image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="get_images",
        check_str=base.ADMIN_OR_PROJECT_READER,
        scope_types=['project'],
        description='Get all available images',
        operations=[
            {'path': '/v2/images',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_images", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="modify_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Updates given image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'PATCH'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="modify_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="publicize_image",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Publicize given image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'PATCH'}
        ]
    ),
    policy.DocumentedRuleDefault(
        name="communitize_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Communitize given image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'PATCH'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="communitize_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),

    policy.DocumentedRuleDefault(
        name="download_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER_DOWNLOAD_IMAGE,
        scope_types=['project'],
        description='Downloads given image',
        operations=[
            {'path': '/v2/images/{image_id}/file',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="download_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="upload_image",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Uploads data to specified image',
        operations=[
            {'path': '/v2/images/{image_id}/file',
             'method': 'PUT'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="upload_image", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),

    policy.DocumentedRuleDefault(
        name="delete_image_location",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Deletes the location of given image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'PATCH'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="delete_image_location", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="get_image_location",
        check_str=base.ADMIN_OR_PROJECT_READER,
        scope_types=['project'],
        description='Reads the location of the image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_image_location", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="set_image_location",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Sets location URI to given image',
        operations=[
            {'path': '/v2/images/{image_id}',
             'method': 'PATCH'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="set_image_location", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),

    policy.DocumentedRuleDefault(
        name="add_member",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Create image member',
        operations=[
            {'path': '/v2/images/{image_id}/members',
             'method': 'POST'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="add_member", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="delete_member",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Delete image member',
        operations=[
            {'path': '/v2/images/{image_id}/members/{member_id}',
             'method': 'DELETE'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="delete_member", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="get_member",
        check_str=base.ADMIN_OR_PROJECT_READER_OR_SHARED_MEMBER,
        scope_types=['project'],
        description='Show image member details',
        operations=[
            {'path': '/v2/images/{image_id}/members/{member_id}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_member", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="get_members",
        check_str=base.ADMIN_OR_PROJECT_READER_OR_SHARED_MEMBER,
        scope_types=['project'],
        description='List image members',
        operations=[
            {'path': '/v2/images/{image_id}/members',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_members", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="modify_member",
        check_str=base.ADMIN_OR_SHARED_MEMBER,
        scope_types=['project'],
        description='Update image member',
        operations=[
            {'path': '/v2/images/{image_id}/members/{member_id}',
             'method': 'PUT'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="modify_member", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),

    policy.RuleDefault(
        name="manage_image_cache",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Manage image cache'
    ),

    policy.DocumentedRuleDefault(
        name="deactivate",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Deactivate image',
        operations=[
            {'path': '/v2/images/{image_id}/actions/deactivate',
             'method': 'POST'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="deactivate", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),
    policy.DocumentedRuleDefault(
        name="reactivate",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=['project'],
        description='Reactivate image',
        operations=[
            {'path': '/v2/images/{image_id}/actions/reactivate',
             'method': 'POST'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="reactivate", check_str=base.DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.WALLABY),
    ),

    policy.DocumentedRuleDefault(
        name="copy_image",
        check_str=base.ADMIN,
        # For now this is restricted to project-admins.
        # That might change in the future if we decide to push
        # this functionality down to project-members.
        scope_types=['project'],
        description='Copy existing image to other stores',
        operations=[
            {'path': '/v2/images/{image_id}/import',
             'method': 'POST'}
        ]
    ),
]


def list_rules():
    return image_policies
