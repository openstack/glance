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
The metadata API now supports project scope and default roles.
"""

METADEF_ADMIN = "rule:metadef_admin"
METADEF_DEFAULT = "rule:metadef_default"


metadef_policies = [
    policy.RuleDefault(name="metadef_default", check_str=""),
    policy.RuleDefault(name="metadef_admin",
                       check_str=base.ADMIN),
    policy.DocumentedRuleDefault(
        name="get_metadef_namespace",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get a specific namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_namespace", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="get_metadef_namespaces",
        check_str=base.ADMIN_OR_PROJECT_READER,
        scope_types=['project'],
        description="List namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_namespaces", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="modify_metadef_namespace",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Modify an existing namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}',
             'method': 'PUT'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_namespace",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Create a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="delete_metadef_namespace",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}',
             'method': 'DELETE'}
        ],
    ),

    policy.DocumentedRuleDefault(
        name="get_metadef_object",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get a specific object from a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/objects'
                     '/{object_name}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_object", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="get_metadef_objects",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get objects from a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/objects',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_objects", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="modify_metadef_object",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Update an object within a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/objects'
                     '/{object_name}',
             'method': 'PUT'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_object",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Create an object within a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/objects',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="delete_metadef_object",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete an object within a namespace.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/objects'
                     '/{object_name}',
             'method': 'DELETE'}
        ],
    ),

    policy.DocumentedRuleDefault(
        name="list_metadef_resource_types",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="List meta definition resource types.",
        operations=[
            {'path': '/v2/metadefs/resource_types',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="list_metadef_resource_types",
            check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="get_metadef_resource_type",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get meta definition resource types associations.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/resource_types',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_resource_type",
            check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_resource_type_association",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Create meta definition resource types association.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/resource_types',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="remove_metadef_resource_type_association",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete meta definition resource types association.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/resource_types'
                     '/{name}',
             'method': 'POST'}
        ],
    ),

    policy.DocumentedRuleDefault(
        name="get_metadef_property",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get a specific meta definition property.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/properties'
                     '/{property_name}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_property",
            check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="get_metadef_properties",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="List meta definition properties.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/properties',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_properties",
            check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="modify_metadef_property",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Update meta definition property.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/properties'
                     '/{property_name}',
             'method': 'GET'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_property",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Create meta definition property.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/properties',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="remove_metadef_property",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete meta definition property.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/properties'
                     '/{property_name}',
             'method': 'DELETE'}
        ],
    ),

    policy.DocumentedRuleDefault(
        name="get_metadef_tag",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="Get tag definition.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags'
                     '/{tag_name}',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_tag", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="get_metadef_tags",
        check_str=base.ADMIN_OR_PROJECT_READER_GET_NAMESPACE,
        scope_types=['project'],
        description="List tag definitions.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags',
             'method': 'GET'}
        ],
        deprecated_rule=policy.DeprecatedRule(
            name="get_metadef_tags", check_str=METADEF_DEFAULT,
            deprecated_reason=DEPRECATED_REASON,
            deprecated_since=versionutils.deprecated.XENA
        ),
    ),
    policy.DocumentedRuleDefault(
        name="modify_metadef_tag",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Update tag definition.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags'
                     '/{tag_name}',
             'method': 'PUT'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_tag",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Add tag definition.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags'
                     '/{tag_name}',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="add_metadef_tags",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Create tag definitions.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags',
             'method': 'POST'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="delete_metadef_tag",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete tag definition.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags'
                     '/{tag_name}',
             'method': 'DELETE'}
        ],
    ),
    policy.DocumentedRuleDefault(
        name="delete_metadef_tags",
        check_str=METADEF_ADMIN,
        scope_types=['project'],
        description="Delete tag definitions.",
        operations=[
            {'path': '/v2/metadefs/namespaces/{namespace_name}/tags',
             'method': 'DELETE'}
        ],
    )
]


def list_rules():
    return metadef_policies
