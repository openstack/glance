#    Copyright 2014 IBM Corp.
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

from glance.hacking import checks
from glance.tests import utils


class HackingTestCase(utils.BaseTestCase):
    def test_assert_true_instance(self):
        self.assertEqual(1, len(list(checks.assert_true_instance(
            "self.assertTrue(isinstance(e, "
            "exception.BuildAbortException))"))))

        self.assertEqual(
            0, len(list(checks.assert_true_instance("self.assertTrue()"))))

    def test_assert_equal_type(self):
        self.assertEqual(1, len(list(checks.assert_equal_type(
            "self.assertEqual(type(als['QuicAssist']), list)"))))

        self.assertEqual(
            0, len(list(checks.assert_equal_type("self.assertTrue()"))))

    def test_assert_equal_none(self):
        self.assertEqual(1, len(list(checks.assert_equal_none(
            "self.assertEqual(A, None)"))))

        self.assertEqual(1, len(list(checks.assert_equal_none(
            "self.assertEqual(None, A)"))))

        self.assertEqual(
            0, len(list(checks.assert_equal_none("self.assertIsNone()"))))
