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


task_policies = [
    policy.RuleDefault(name="get_task", check_str="rule:default"),
    policy.RuleDefault(name="get_tasks", check_str="rule:default"),
    policy.RuleDefault(name="add_task", check_str="rule:default"),
    policy.RuleDefault(name="modify_task", check_str="rule:default"),
    policy.RuleDefault(name="tasks_api_access", check_str="role:admin"),
]


def list_rules():
    return task_policies
