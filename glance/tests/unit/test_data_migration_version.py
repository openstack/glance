# Copyright 2019 Red Hat, Inc.
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

import six
import testtools

from glance.db.migration import CURRENT_RELEASE
from glance.version import version_info


class TestDataMigrationVersion(testtools.TestCase):

    def test_migration_version(self):
        """Make sure the data migration version info has been updated."""

        release_number = int(version_info.version_string().split('.', 1)[0])

        # by rule, release names must be composed of the 26 letters of the
        # ISO Latin alphabet (ord('A')==65, ord('Z')==90)
        release_letter = six.text_type(CURRENT_RELEASE[:1].upper()).encode(
            'ascii')

        # Convert release letter into an int in [1:26].  The first
        # glance release was 'Bexar'.
        converted_release_letter = (ord(release_letter) -
                                    ord(u'B'.encode('ascii')) + 1)

        # Project the release number into [1:26]
        converted_release_number = release_number % 26

        # Prepare for the worst with a super-informative message
        msg = ('\n\n'
               'EMERGENCY!\n'
               'glance.db.migration.CURRENT_RELEASE is out of sync '
               'with the glance version.\n'
               '  CURRENT_RELEASE: %s\n'
               '  glance version: %s\n'
               'glance.db.migration.CURRENT_RELEASE needs to be '
               'updated IMMEDIATELY.\n'
               'The gate will be wedged until the update is made.\n'
               'EMERGENCY!\n'
               '\n') % (CURRENT_RELEASE,
                        version_info.version_string())

        self.assertEqual(converted_release_letter,
                         converted_release_number,
                         msg)
