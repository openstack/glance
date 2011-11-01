# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

import unittest

from glance.common import utils


class TestUtils(unittest.TestCase):
    """Test routines in glance.utils"""

    def test_generate_uuid_format(self):
        """Check the format of a uuid"""
        uuid = utils.generate_uuid()
        self.assertTrue(isinstance(uuid, basestring))
        self.assertTrue(len(uuid), 36)
        # make sure there are 4 dashes
        self.assertTrue(len(uuid.replace('-', '')), 36)

    def test_generate_uuid_unique(self):
        """Ensure generate_uuid will return unique values"""
        uuids = [utils.generate_uuid() for i in range(5)]
        # casting to set will drop duplicate values
        unique = set(uuids)
        self.assertEqual(len(uuids), len(list(unique)))

    def test_is_uuid_like_success(self):
        fixture = 'b694bf02-6b01-4905-a50e-fcf7bce7e4d2'
        self.assertTrue(utils.is_uuid_like(fixture))

    def test_is_uuid_like_fails(self):
        fixture = 'pants'
        self.assertFalse(utils.is_uuid_like(fixture))
