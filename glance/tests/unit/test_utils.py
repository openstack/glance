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

from glance import utils
from glance.common import utils as common_utils


class TestUtils(unittest.TestCase):

    """Test routines in glance.utils"""

    def test_headers_are_unicode(self):
        """
        Verifies that the headers returned by conversion code are unicode.

        Headers are passed via http in non-testing mode, which automatically
        converts them to unicode. Verifying that the method does the
        conversion proves that we aren't passing data that works in tests
        but will fail in production.
        """
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'type': 'kernel',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}
        headers = utils.image_meta_to_http_headers(fixture)
        for k, v in headers.iteritems():
            self.assert_(isinstance(v, unicode), "%s is not unicode" % v)

    def test_data_passed_properly_through_headers(self):
        """
        Verifies that data is the same after being passed through headers
        """
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'deleted': False,
                   'type': 'kernel',
                   'name': None,
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}
        headers = utils.image_meta_to_http_headers(fixture)

        class FakeResponse():
            pass

        response = FakeResponse()
        response.headers = headers
        result = utils.get_image_meta_from_headers(response)
        for k, v in fixture.iteritems():
            self.assertEqual(v, result[k])

    def test_boolean_header_values(self):
        """
        Tests that boolean headers like is_public can be set
        to True if any of ('True', 'On', 1) is provided, case-insensitive
        """
        fixtures = [{'is_public': True},
                    {'is_public': 'True'},
                    {'is_public': 'true'}]

        expected = {'is_public': True}

        class FakeResponse():
            pass

        for fixture in fixtures:
            headers = utils.image_meta_to_http_headers(fixture)

            response = FakeResponse()
            response.headers = headers
            result = utils.get_image_meta_from_headers(response)
            for k, v in expected.items():
                self.assertEqual(v, result[k])

        # Ensure False for other values...
        fixtures = [{'is_public': False},
                    {'is_public': 'Off'},
                    {'is_public': 'on'},
                    {'is_public': '1'},
                    {'is_public': 'False'}]

        expected = {'is_public': False}

        for fixture in fixtures:
            headers = utils.image_meta_to_http_headers(fixture)

            response = FakeResponse()
            response.headers = headers
            result = utils.get_image_meta_from_headers(response)
            for k, v in expected.items():
                self.assertEqual(v, result[k])

    def test_generate_uuid_format(self):
        """Check the format of a uuid"""
        uuid = common_utils.generate_uuid()
        self.assertTrue(isinstance(uuid, basestring))
        self.assertTrue(len(uuid), 36)
        # make sure there are 4 dashes
        self.assertTrue(len(uuid.replace('-', '')), 36)

    def test_generate_uuid_unique(self):
        """Ensure generate_uuid will return unique values"""
        uuids = [common_utils.generate_uuid() for i in range(5)]
        # casting to set will drop duplicate values
        unique = set(uuids)
        self.assertEqual(len(uuids), len(list(unique)))

    def test_is_uuid_like_success(self):
        fixture = 'b694bf02-6b01-4905-a50e-fcf7bce7e4d2'
        self.assertTrue(common_utils.is_uuid_like(fixture))

    def test_is_uuid_like_fails(self):
        fixture = 'pants'
        self.assertFalse(common_utils.is_uuid_like(fixture))
