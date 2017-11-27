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

"""Fixtures for Glance unit tests."""
# NOTE(mriedem): This is needed for importing from fixtures.
from __future__ import absolute_import

import warnings

import fixtures as pyfixtures


class WarningsFixture(pyfixtures.Fixture):
    """Filters out warnings during test runs."""

    def setUp(self):
        super(WarningsFixture, self).setUp()
        # NOTE(sdague): Make deprecation warnings only happen once. Otherwise
        # this gets kind of crazy given the way that upstream python libs use
        # this.
        warnings.simplefilter('once', DeprecationWarning)

        # NOTE(sdague): this remains an unresolved item around the way
        # forward on is_admin, the deprecation is definitely really premature.
        warnings.filterwarnings(
            'ignore',
            message='Policy enforcement is depending on the value of is_admin.'
                    ' This key is deprecated. Please update your policy '
                    'file to use the standard policy values.')

        self.addCleanup(warnings.resetwarnings)
