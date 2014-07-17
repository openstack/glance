# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from glance.common import exception
from glance.common import semver_db
from glance.tests import utils as test_utils


class SemVerTestCase(test_utils.BaseTestCase):
    def test_long_conversion(self):
        initial = '1.2.3-beta+07.17.2014'
        v = semver_db.parse(initial)
        l, prerelease, build = v.__composite_values__()
        v2 = semver_db.DBVersion(l, prerelease, build)
        self.assertEqual(initial, str(v2))

    def test_major_comparison_as_long(self):
        v1 = semver_db.parse("1.1.100")
        v2 = semver_db.parse("2.0.0")
        self.assertTrue(v2.__composite_values__()[0] >
                        v1.__composite_values__()[0])

    def test_minor_comparison_as_long(self):
        v1 = semver_db.parse("1.1.100")
        v2 = semver_db.parse("2.0.0")
        self.assertTrue(v2.__composite_values__()[0] >
                        v1.__composite_values__()[0])

    def test_patch_comparison_as_long(self):
        v1 = semver_db.parse("1.1.1")
        v2 = semver_db.parse("1.1.100")
        self.assertTrue(v2.__composite_values__()[0] >
                        v1.__composite_values__()[0])

    def test_label_comparison_as_long(self):
        v1 = semver_db.parse("1.1.1-alpha")
        v2 = semver_db.parse("1.1.1")
        self.assertTrue(v2.__composite_values__()[0] >
                        v1.__composite_values__()[0])

    def test_label_comparison_as_string(self):
        versions = [
            semver_db.parse("1.1.1-0.10.a.23.y.255").__composite_values__()[1],
            semver_db.parse("1.1.1-0.10.z.23.x.255").__composite_values__()[1],
            semver_db.parse("1.1.1-0.10.z.23.y.255").__composite_values__()[1],
            semver_db.parse("1.1.1-0.10.z.23.y.256").__composite_values__()[1],
            semver_db.parse("1.1.1-0.10.z.24.y.255").__composite_values__()[1],
            semver_db.parse("1.1.1-0.11.z.24.y.255").__composite_values__()[1],
            semver_db.parse("1.1.1-1.11.z.24.y.255").__composite_values__()[1],
            semver_db.parse("1.1.1-alp.1.2.3.4.5.6").__composite_values__()[1]]
        for i in xrange(len(versions) - 1):
            self.assertLess(versions[i], versions[i + 1])

    def test_too_large_version(self):
        version1 = '1.1.65536'
        version2 = '1.65536.1'
        version3 = '65536.1.1'
        self.assertRaises(exception.InvalidVersion, semver_db.parse, version1)
        self.assertRaises(exception.InvalidVersion, semver_db.parse, version2)
        self.assertRaises(exception.InvalidVersion, semver_db.parse, version3)

    def test_too_long_numeric_segments(self):
        version = semver_db.parse('1.0.0-alpha.1234567')
        self.assertRaises(exception.InvalidVersion,
                          version.__composite_values__)
