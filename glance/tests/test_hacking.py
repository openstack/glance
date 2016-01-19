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

    def test_no_translate_debug_logs(self):
        self.assertEqual(1, len(list(checks.no_translate_debug_logs(
            "LOG.debug(_('foo'))", "glance/store/foo.py"))))

        self.assertEqual(0, len(list(checks.no_translate_debug_logs(
            "LOG.debug('foo')", "glance/store/foo.py"))))

        self.assertEqual(0, len(list(checks.no_translate_debug_logs(
            "LOG.info(_('foo'))", "glance/store/foo.py"))))

    def test_no_direct_use_of_unicode_function(self):
        self.assertEqual(1, len(list(checks.no_direct_use_of_unicode_function(
            "unicode('the party dont start til the unicode walks in')"))))
        self.assertEqual(1, len(list(checks.no_direct_use_of_unicode_function(
            """unicode('something '
                       'something else"""))))
        self.assertEqual(0, len(list(checks.no_direct_use_of_unicode_function(
            "six.text_type('party over')"))))
        self.assertEqual(0, len(list(checks.no_direct_use_of_unicode_function(
            "not_actually_unicode('something completely different')"))))

    def test_no_contextlib_nested(self):
        self.assertEqual(1, len(list(checks.check_no_contextlib_nested(
            "with contextlib.nested("))))

        self.assertEqual(1, len(list(checks.check_no_contextlib_nested(
            "with nested("))))

        self.assertEqual(0, len(list(checks.check_no_contextlib_nested(
            "with foo as bar"))))

    def test_dict_constructor_with_list_copy(self):
        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "    dict([(i, connect_info[i])"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "    attrs = dict([(k, _from_json(v))"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "        type_names = dict((value, key) for key, value in"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "   dict((value, key) for key, value in"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "foo(param=dict((k, v) for k, v in bar.items()))"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            " dict([[i,i] for i in range(3)])"))))

        self.assertEqual(1, len(list(checks.dict_constructor_with_list_copy(
            "  dd = dict([i,i] for i in range(3))"))))

        self.assertEqual(0, len(list(checks.dict_constructor_with_list_copy(
            "        create_kwargs = dict(snapshot=snapshot,"))))

        self.assertEqual(0, len(list(checks.dict_constructor_with_list_copy(
            "      self._render_dict(xml, data_el, data.__dict__)"))))

    def test_check_python3_xrange(self):
        func = checks.check_python3_xrange
        self.assertEqual(1, len(list(func('for i in xrange(10)'))))
        self.assertEqual(1, len(list(func('for i in xrange    (10)'))))
        self.assertEqual(0, len(list(func('for i in range(10)'))))
        self.assertEqual(0, len(list(func('for i in six.moves.range(10)'))))
        self.assertEqual(0, len(list(func('testxrange(10)'))))

    def test_dict_iteritems(self):
        self.assertEqual(1, len(list(checks.check_python3_no_iteritems(
            "obj.iteritems()"))))

        self.assertEqual(0, len(list(checks.check_python3_no_iteritems(
            "six.iteritems(obj)"))))

        self.assertEqual(0, len(list(checks.check_python3_no_iteritems(
            "obj.items()"))))

    def test_dict_iterkeys(self):
        self.assertEqual(1, len(list(checks.check_python3_no_iterkeys(
            "obj.iterkeys()"))))

        self.assertEqual(0, len(list(checks.check_python3_no_iterkeys(
            "six.iterkeys(obj)"))))

        self.assertEqual(0, len(list(checks.check_python3_no_iterkeys(
            "obj.keys()"))))

    def test_dict_itervalues(self):
        self.assertEqual(1, len(list(checks.check_python3_no_itervalues(
            "obj.itervalues()"))))

        self.assertEqual(0, len(list(checks.check_python3_no_itervalues(
            "six.itervalues(ob)"))))

        self.assertEqual(0, len(list(checks.check_python3_no_itervalues(
            "obj.values()"))))
