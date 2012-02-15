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

import iso8601

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


class TestIso8601Time(unittest.TestCase):

    def _instaneous(self, timestamp, yr, mon, day, hr, min, sec, micro):
        self.assertEquals(timestamp.year, yr)
        self.assertEquals(timestamp.month, mon)
        self.assertEquals(timestamp.day, day)
        self.assertEquals(timestamp.hour, hr)
        self.assertEquals(timestamp.minute, min)
        self.assertEquals(timestamp.second, sec)
        self.assertEquals(timestamp.microsecond, micro)

    def _do_test(self, str, yr, mon, day, hr, min, sec, micro, shift):
        DAY_SECONDS = 24 * 60 * 60
        timestamp = utils.parse_isotime(str)
        self._instaneous(timestamp, yr, mon, day, hr, min, sec, micro)
        offset = timestamp.tzinfo.utcoffset(None)
        self.assertEqual(offset.seconds + offset.days * DAY_SECONDS, shift)

    def test_zulu(self):
        str = '2012-02-14T20:53:07Z'
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 0, 0)

    def test_zulu_micros(self):
        str = '2012-02-14T20:53:07.123Z'
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 123000, 0)

    def test_offset_east(self):
        str = '2012-02-14T20:53:07+04:30'
        offset = 4.5 * 60 * 60
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 0, offset)

    def test_offset_east_micros(self):
        str = '2012-02-14T20:53:07.42+04:30'
        offset = 4.5 * 60 * 60
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 420000, offset)

    def test_offset_west(self):
        str = '2012-02-14T20:53:07-05:30'
        offset = -5.5 * 60 * 60
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 0, offset)

    def test_offset_west_micros(self):
        str = '2012-02-14T20:53:07.654321-05:30'
        offset = -5.5 * 60 * 60
        self._do_test(str, 2012, 02, 14, 20, 53, 7, 654321, offset)

    def test_compare(self):
        zulu = utils.parse_isotime('2012-02-14T20:53:07')
        east = utils.parse_isotime('2012-02-14T20:53:07-01:00')
        west = utils.parse_isotime('2012-02-14T20:53:07+01:00')
        self.assertTrue(east > west)
        self.assertTrue(east > zulu)
        self.assertTrue(zulu > west)

    def test_compare_micros(self):
        zulu = utils.parse_isotime('2012-02-14T20:53:07.6544')
        east = utils.parse_isotime('2012-02-14T19:53:07.654321-01:00')
        west = utils.parse_isotime('2012-02-14T21:53:07.655+01:00')
        self.assertTrue(east < west)
        self.assertTrue(east < zulu)
        self.assertTrue(zulu < west)

    def test_zulu_roundtrip(self):
        str = '2012-02-14T20:53:07Z'
        zulu = utils.parse_isotime(str)
        self.assertEquals(zulu.tzinfo, iso8601.iso8601.UTC)
        self.assertEquals(utils.isotime(zulu), str)

    def test_east_roundtrip(self):
        str = '2012-02-14T20:53:07-07:00'
        east = utils.parse_isotime(str)
        self.assertEquals(east.tzinfo.tzname(None), '-07:00')
        self.assertEquals(utils.isotime(east), str)

    def test_west_roundtrip(self):
        str = '2012-02-14T20:53:07+11:30'
        west = utils.parse_isotime(str)
        self.assertEquals(west.tzinfo.tzname(None), '+11:30')
        self.assertEquals(utils.isotime(west), str)

    def test_now_roundtrip(self):
        str = utils.isotime()
        now = utils.parse_isotime(str)
        self.assertEquals(now.tzinfo, iso8601.iso8601.UTC)
        self.assertEquals(utils.isotime(now), str)

    def test_zulu_normalize(self):
        str = '2012-02-14T20:53:07Z'
        zulu = utils.parse_isotime(str)
        normed = utils.normalize_time(zulu)
        self._instaneous(normed, 2012, 2, 14, 20, 53, 07, 0)

    def test_east_normalize(self):
        str = '2012-02-14T20:53:07-07:00'
        east = utils.parse_isotime(str)
        normed = utils.normalize_time(east)
        self._instaneous(normed, 2012, 2, 15, 03, 53, 07, 0)

    def test_west_normalize(self):
        str = '2012-02-14T20:53:07+21:00'
        west = utils.parse_isotime(str)
        normed = utils.normalize_time(west)
        self._instaneous(normed, 2012, 2, 13, 23, 53, 07, 0)
