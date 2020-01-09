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

import itertools

from glance.policies import base
from glance.policies import image
from glance.policies import metadef
from glance.policies import tasks


def list_rules():
    return itertools.chain(
        base.list_rules(),
        image.list_rules(),
        tasks.list_rules(),
        metadef.list_rules(),
    )
