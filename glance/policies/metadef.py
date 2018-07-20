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


metadef_policies = [
    policy.RuleDefault(name="get_metadef_namespace", check_str="rule:default"),
    policy.RuleDefault(name="get_metadef_namespaces",
                       check_str="rule:default"),
    policy.RuleDefault(name="modify_metadef_namespace",
                       check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_namespace", check_str="rule:default"),
    policy.RuleDefault(name="delete_metadef_namespace",
                       check_str="rule:default"),

    policy.RuleDefault(name="get_metadef_object", check_str="rule:default"),
    policy.RuleDefault(name="get_metadef_objects", check_str="rule:default"),
    policy.RuleDefault(name="modify_metadef_object", check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_object", check_str="rule:default"),
    policy.RuleDefault(name="delete_metadef_object", check_str="rule:default"),

    policy.RuleDefault(name="list_metadef_resource_types",
                       check_str="rule:default"),
    policy.RuleDefault(name="get_metadef_resource_type",
                       check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_resource_type_association",
                       check_str="rule:default"),
    policy.RuleDefault(name="remove_metadef_resource_type_association",
                       check_str="rule:default"),

    policy.RuleDefault(name="get_metadef_property", check_str="rule:default"),
    policy.RuleDefault(name="get_metadef_properties",
                       check_str="rule:default"),
    policy.RuleDefault(name="modify_metadef_property",
                       check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_property", check_str="rule:default"),
    policy.RuleDefault(name="remove_metadef_property",
                       check_str="rule:default"),

    policy.RuleDefault(name="get_metadef_tag", check_str="rule:default"),
    policy.RuleDefault(name="get_metadef_tags", check_str="rule:default"),
    policy.RuleDefault(name="modify_metadef_tag", check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_tag", check_str="rule:default"),
    policy.RuleDefault(name="add_metadef_tags", check_str="rule:default"),
    policy.RuleDefault(name="delete_metadef_tag", check_str="rule:default"),
    policy.RuleDefault(name="delete_metadef_tags", check_str="rule:default"),
]


def list_rules():
    return metadef_policies
