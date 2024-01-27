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

from hacking import core

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
    r"(\w|\.|\'|\"|\[|\])+\)\)")
asse_equal_type_re = re.compile(
    r"(.)*assertEqual\(type\((\w|\.|\'|\"|\[|\])+\), "
    r"(\w|\.|\'|\"|\[|\])+\)")
asse_equal_end_with_none_re = re.compile(
    r"(.)*assertEqual\((\w|\.|\'|\"|\[|\])+, None\)")
asse_equal_start_with_none_re = re.compile(
    r"(.)*assertEqual\(None, (\w|\.|\'|\"|\[|\])+\)")
unicode_func_re = re.compile(r"(\s|\W|^)unicode\(")
dict_constructor_with_list_copy_re = re.compile(r".*\bdict\((\[)?(\(|\[)")


@core.flake8ext
def assert_true_instance(logical_line):
    """Check for assertTrue(isinstance(a, b)) sentences

    G316
    """
    if asse_trueinst_re.match(logical_line):
        yield (0, "G316: assertTrue(isinstance(a, b)) sentences not allowed")


@core.flake8ext
def assert_equal_type(logical_line):
    """Check for assertEqual(type(A), B) sentences

    G317
    """
    if asse_equal_type_re.match(logical_line):
        yield (0, "G317: assertEqual(type(A), B) sentences not allowed")


@core.flake8ext
def assert_equal_none(logical_line):
    """Check for assertEqual(A, None) or assertEqual(None, A) sentences

    G318
    """
    res = (asse_equal_start_with_none_re.match(logical_line) or
           asse_equal_end_with_none_re.match(logical_line))
    if res:
        yield (0, "G318: assertEqual(A, None) or assertEqual(None, A) "
               "sentences not allowed")


@core.flake8ext
def no_translate_debug_logs(logical_line, filename):
    dirs = [
        "glance/api",
        "glance/cmd",
        "glance/common",
        "glance/db",
        "glance/domain",
        "glance/image_cache",
        "glance/quota",
        "glance/store",
        "glance/tests",
    ]

    if max([name in filename for name in dirs]):
        if logical_line.startswith("LOG.debug(_("):
            yield (0, "G319: Don't translate debug level logs")


@core.flake8ext
def check_no_contextlib_nested(logical_line):
    msg = ("G327: contextlib.nested is deprecated since Python 2.7. See "
           "https://docs.python.org/2/library/contextlib.html#contextlib."
           "nested for more information.")
    if ("with contextlib.nested(" in logical_line or
            "with nested(" in logical_line):
        yield (0, msg)


@core.flake8ext
def dict_constructor_with_list_copy(logical_line):
    msg = ("G328: Must use a dict comprehension instead of a dict constructor "
           "with a sequence of key-value pairs.")
    if dict_constructor_with_list_copy_re.match(logical_line):
        yield (0, msg)


@core.flake8ext
def no_log_warn(logical_line):
    """Disallow 'LOG.warn('

    Use LOG.warning() instead of Deprecated LOG.warn().
    https://docs.python.org/3/library/logging.html#logging.warning
    """

    msg = ("G330: LOG.warn is deprecated, please use LOG.warning!")
    if "LOG.warn(" in logical_line:
        yield (0, msg)
