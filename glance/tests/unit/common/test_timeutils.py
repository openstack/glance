# Copyright 2011 OpenStack Foundation.
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

import calendar
import datetime
from unittest import mock

import iso8601

from glance.common import timeutils
from glance.tests import utils as test_utils


class TimeUtilsTest(test_utils.BaseTestCase):

    def setUp(self):
        super(TimeUtilsTest, self).setUp()
        self.skynet_self_aware_time_str = '1997-08-29T06:14:00Z'
        self.skynet_self_aware_time_ms_str = '1997-08-29T06:14:00.000123Z'
        self.skynet_self_aware_time = datetime.datetime(1997, 8, 29, 6, 14, 0)
        self.skynet_self_aware_ms_time = datetime.datetime(
            1997, 8, 29, 6, 14, 0, 123)
        self.one_minute_before = datetime.datetime(1997, 8, 29, 6, 13, 0)
        self.one_minute_after = datetime.datetime(1997, 8, 29, 6, 15, 0)
        self.skynet_self_aware_time_perfect_str = '1997-08-29T06:14:00.000000'
        self.skynet_self_aware_time_perfect = datetime.datetime(1997, 8, 29,
                                                                6, 14, 0)

    def test_isotime(self):
        with mock.patch('datetime.datetime') as datetime_mock:
            datetime_mock.utcnow.return_value = self.skynet_self_aware_time
            dt = timeutils.isotime()
            self.assertEqual(dt, self.skynet_self_aware_time_str)

    def test_isotimei_micro_second_precision(self):
        with mock.patch('datetime.datetime') as datetime_mock:
            datetime_mock.utcnow.return_value = self.skynet_self_aware_ms_time
            dt = timeutils.isotime(subsecond=True)
            self.assertEqual(dt, self.skynet_self_aware_time_ms_str)

    def test_parse_isotime(self):
        expect = timeutils.parse_isotime(self.skynet_self_aware_time_str)
        skynet_self_aware_time_utc = self.skynet_self_aware_time.replace(
            tzinfo=iso8601.iso8601.UTC)
        self.assertEqual(skynet_self_aware_time_utc, expect)

    def test_parse_isotime_micro_second_precision(self):
        expect = timeutils.parse_isotime(self.skynet_self_aware_time_ms_str)
        skynet_self_aware_time_ms_utc = self.skynet_self_aware_ms_time.replace(
            tzinfo=iso8601.iso8601.UTC)
        self.assertEqual(skynet_self_aware_time_ms_utc, expect)

    def test_utcnow(self):
        with mock.patch('datetime.datetime') as datetime_mock:
            datetime_mock.utcnow.return_value = self.skynet_self_aware_time
            self.assertEqual(timeutils.utcnow(), self.skynet_self_aware_time)

        self.assertFalse(timeutils.utcnow() == self.skynet_self_aware_time)
        self.assertTrue(timeutils.utcnow())

    def test_delta_seconds(self):
        before = timeutils.utcnow()
        after = before + datetime.timedelta(days=7, seconds=59,
                                            microseconds=123456)
        self.assertAlmostEqual(604859.123456,
                               timeutils.delta_seconds(before, after))

    def test_iso8601_from_timestamp(self):
        utcnow = timeutils.utcnow()
        iso = timeutils.isotime(utcnow)
        ts = calendar.timegm(utcnow.timetuple())
        self.assertEqual(iso, timeutils.iso8601_from_timestamp(ts))


class TestIso8601Time(test_utils.BaseTestCase):

    def _instaneous(self, timestamp, yr, mon, day, hr, minute, sec, micro):
        self.assertEqual(timestamp.year, yr)
        self.assertEqual(timestamp.month, mon)
        self.assertEqual(timestamp.day, day)
        self.assertEqual(timestamp.hour, hr)
        self.assertEqual(timestamp.minute, minute)
        self.assertEqual(timestamp.second, sec)
        self.assertEqual(timestamp.microsecond, micro)

    def _do_test(self, time_str, yr, mon, day, hr, minute, sec, micro, shift):
        DAY_SECONDS = 24 * 60 * 60
        timestamp = timeutils.parse_isotime(time_str)
        self._instaneous(timestamp, yr, mon, day, hr, minute, sec, micro)
        offset = timestamp.tzinfo.utcoffset(None)
        self.assertEqual(offset.seconds + offset.days * DAY_SECONDS, shift)

    def test_zulu(self):
        time_str = '2012-02-14T20:53:07Z'
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 0, 0)

    def test_zulu_micros(self):
        time_str = '2012-02-14T20:53:07.123Z'
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 123000, 0)

    def test_offset_east(self):
        time_str = '2012-02-14T20:53:07+04:30'
        offset = 4.5 * 60 * 60
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 0, offset)

    def test_offset_east_micros(self):
        time_str = '2012-02-14T20:53:07.42+04:30'
        offset = 4.5 * 60 * 60
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 420000, offset)

    def test_offset_west(self):
        time_str = '2012-02-14T20:53:07-05:30'
        offset = -5.5 * 60 * 60
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 0, offset)

    def test_offset_west_micros(self):
        time_str = '2012-02-14T20:53:07.654321-05:30'
        offset = -5.5 * 60 * 60
        self._do_test(time_str, 2012, 2, 14, 20, 53, 7, 654321, offset)

    def test_compare(self):
        zulu = timeutils.parse_isotime('2012-02-14T20:53:07')
        east = timeutils.parse_isotime('2012-02-14T20:53:07-01:00')
        west = timeutils.parse_isotime('2012-02-14T20:53:07+01:00')
        self.assertGreater(east, west)
        self.assertGreater(east, zulu)
        self.assertGreater(zulu, west)

    def test_compare_micros(self):
        zulu = timeutils.parse_isotime('2012-02-14T20:53:07.6544')
        east = timeutils.parse_isotime('2012-02-14T19:53:07.654321-01:00')
        west = timeutils.parse_isotime('2012-02-14T21:53:07.655+01:00')
        self.assertLess(east, west)
        self.assertLess(east, zulu)
        self.assertLess(zulu, west)

    def test_zulu_roundtrip(self):
        time_str = '2012-02-14T20:53:07Z'
        zulu = timeutils.parse_isotime(time_str)
        self.assertEqual(zulu.tzinfo, iso8601.iso8601.UTC)
        self.assertEqual(timeutils.isotime(zulu), time_str)

    def test_east_roundtrip(self):
        time_str = '2012-02-14T20:53:07-07:00'
        east = timeutils.parse_isotime(time_str)
        self.assertEqual(east.tzinfo.tzname(None), '-07:00')
        self.assertEqual(timeutils.isotime(east), time_str)

    def test_west_roundtrip(self):
        time_str = '2012-02-14T20:53:07+11:30'
        west = timeutils.parse_isotime(time_str)
        self.assertEqual(west.tzinfo.tzname(None), '+11:30')
        self.assertEqual(timeutils.isotime(west), time_str)

    def test_now_roundtrip(self):
        time_str = timeutils.isotime()
        now = timeutils.parse_isotime(time_str)
        self.assertEqual(now.tzinfo, iso8601.iso8601.UTC)
        self.assertEqual(timeutils.isotime(now), time_str)

    def test_zulu_normalize(self):
        time_str = '2012-02-14T20:53:07Z'
        zulu = timeutils.parse_isotime(time_str)
        normed = timeutils.normalize_time(zulu)
        self._instaneous(normed, 2012, 2, 14, 20, 53, 7, 0)

    def test_east_normalize(self):
        time_str = '2012-02-14T20:53:07-07:00'
        east = timeutils.parse_isotime(time_str)
        normed = timeutils.normalize_time(east)
        self._instaneous(normed, 2012, 2, 15, 3, 53, 7, 0)

    def test_west_normalize(self):
        time_str = '2012-02-14T20:53:07+21:00'
        west = timeutils.parse_isotime(time_str)
        normed = timeutils.normalize_time(west)
        self._instaneous(normed, 2012, 2, 13, 23, 53, 7, 0)

    def test_normalize_aware_to_naive(self):
        dt = datetime.datetime(2011, 2, 14, 20, 53, 7)
        time_str = '2011-02-14T20:53:07+21:00'
        aware = timeutils.parse_isotime(time_str)
        naive = timeutils.normalize_time(aware)
        self.assertLess(naive, dt)

    def test_normalize_zulu_aware_to_naive(self):
        dt = datetime.datetime(2011, 2, 14, 20, 53, 7)
        time_str = '2011-02-14T19:53:07Z'
        aware = timeutils.parse_isotime(time_str)
        naive = timeutils.normalize_time(aware)
        self.assertLess(naive, dt)

    def test_normalize_naive(self):
        dt = datetime.datetime(2011, 2, 14, 20, 53, 7)
        dtn = datetime.datetime(2011, 2, 14, 19, 53, 7)
        naive = timeutils.normalize_time(dtn)
        self.assertLess(naive, dt)
