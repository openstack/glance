# Copyright 2021 Red Hat, Inc.
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
from oslo_policy import policy

from glance.policies import base


discovery_policies = [
    policy.DocumentedRuleDefault(
        name="stores_info_detail",
        check_str=base.ADMIN,
        scope_types=['project'],
        description='Expose store specific information',
        operations=[
            {'path': '/v2/info/stores/detail',
             'method': 'GET'}
        ]
    ),
]


def list_rules():
    return discovery_policies
