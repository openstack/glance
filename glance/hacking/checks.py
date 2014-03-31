# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re

"""
Guidelines for writing new hacking checks

 - Use only for Glance-specific tests. OpenStack general tests
   should be submitted to the common 'hacking' module.
 - Pick numbers in the range G3xx. Find the current test with
   the highest allocated number and then pick the next value.
   If nova has an N3xx code for that test, use the same number.
 - Keep the test method code in the source file ordered based
   on the G3xx value.
 - List the new rule in the top level HACKING.rst file
 - Add test cases for each new rule to glance/tests/test_hacking.py

"""


asse_trueinst_re = re.compile(
    r"(.)*assertTrue\(isinstance\((\w|\.|\'|\"|\[|\])+, "
    "(\w|\.|\'|\"|\[|\])+\)\)")
asse_equal_type_re = re.compile(
    r"(.)*assertEqual\(type\((\w|\.|\'|\"|\[|\])+\), "
    "(\w|\.|\'|\"|\[|\])+\)")
asse_equal_end_with_none_re = re.compile(
    r"(.)*assertEqual\((\w|\.|\'|\"|\[|\])+, None\)")
asse_equal_start_with_none_re = re.compile(
    r"(.)*assertEqual\(None, (\w|\.|\'|\"|\[|\])+\)")


def assert_true_instance(logical_line):
    """Check for assertTrue(isinstance(a, b)) sentences

    G316
    """
    if asse_trueinst_re.match(logical_line):
        yield (0, "G316: assertTrue(isinstance(a, b)) sentences not allowed")


def assert_equal_type(logical_line):
    """Check for assertEqual(type(A), B) sentences

    G317
    """
    if asse_equal_type_re.match(logical_line):
        yield (0, "G317: assertEqual(type(A), B) sentences not allowed")


def assert_equal_none(logical_line):
    """Check for assertEqual(A, None) or assertEqual(None, A) sentences

    G318
    """
    res = (asse_equal_start_with_none_re.match(logical_line) or
           asse_equal_end_with_none_re.match(logical_line))
    if res:
        yield (0, "G318: assertEqual(A, None) or assertEqual(None, A) "
               "sentences not allowed")


def no_translate_debug_logs(logical_line, filename):
    dirs = [
        "glance/api",
        "glance/cmd",
        "glance/common",
        "glance/db",
        "glance/domain",
        "glance/image_cache",
        "glance/quota",
        "glance/registry",
        "glance/store",
        "glance/tests",
    ]

    if max([name in filename for name in dirs]):
        if logical_line.startswith("LOG.debug(_("):
            yield(0, "N319: Don't translate debug level logs")


def factory(register):
    register(assert_true_instance)
    register(assert_equal_type)
    register(assert_equal_none)
    register(no_translate_debug_logs)
