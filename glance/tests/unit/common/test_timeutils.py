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

import datetime
from unittest import mock

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
        with mock.patch('oslo_utils.timeutils.utcnow') as utcnow_mock:
            utcnow_mock.return_value = self.skynet_self_aware_time
            dt = timeutils.isotime()
            self.assertEqual(dt, self.skynet_self_aware_time_str)

    def test_isotimei_micro_second_precision(self):
        with mock.patch('oslo_utils.timeutils.utcnow') as utcnow_mock:
            utcnow_mock.return_value = self.skynet_self_aware_ms_time
            dt = timeutils.isotime(subsecond=True)
            self.assertEqual(dt, self.skynet_self_aware_time_ms_str)
