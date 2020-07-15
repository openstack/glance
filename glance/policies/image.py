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


image_policies = [
    policy.RuleDefault(name="add_image", check_str="rule:default"),
    policy.RuleDefault(name="delete_image", check_str="rule:default"),
    policy.RuleDefault(name="get_image", check_str="rule:default"),
    policy.RuleDefault(name="get_images", check_str="rule:default"),
    policy.RuleDefault(name="modify_image", check_str="rule:default"),
    policy.RuleDefault(name="publicize_image", check_str="role:admin"),
    policy.RuleDefault(name="communitize_image", check_str="rule:default"),

    policy.RuleDefault(name="download_image", check_str="rule:default"),
    policy.RuleDefault(name="upload_image", check_str="rule:default"),

    policy.RuleDefault(name="delete_image_location", check_str="rule:default"),
    policy.RuleDefault(name="get_image_location", check_str="rule:default"),
    policy.RuleDefault(name="set_image_location", check_str="rule:default"),

    policy.RuleDefault(name="add_member", check_str="rule:default"),
    policy.RuleDefault(name="delete_member", check_str="rule:default"),
    policy.RuleDefault(name="get_member", check_str="rule:default"),
    policy.RuleDefault(name="get_members", check_str="rule:default"),
    policy.RuleDefault(name="modify_member", check_str="rule:default"),

    policy.RuleDefault(name="manage_image_cache", check_str="role:admin"),

    policy.RuleDefault(name="deactivate", check_str="rule:default"),
    policy.RuleDefault(name="reactivate", check_str="rule:default"),

    policy.RuleDefault(name="copy_image", check_str="role:admin"),
]


def list_rules():
    return image_policies
