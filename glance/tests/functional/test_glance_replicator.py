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

"""Functional test cases for glance-replicator"""

import sys

from glance.tests import functional
from glance.tests.utils import execute


class TestGlanceReplicator(functional.FunctionalTest):
    """Functional tests for glance-replicator"""

    def test_compare(self):
        # Test for issue: https://bugs.launchpad.net/glance/+bug/1598928
        cmd = ('%s -m glance.cmd.replicator '
               'compare az1:9292 az2:9292 --debug' %
               (sys.executable,))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertIn(
            b'Request: GET http://az1:9292/v1/images/detail?is_public=None',
            err
        )
