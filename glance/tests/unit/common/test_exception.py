# Copyright 2012 OpenStack Foundation
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

import six

from glance.common import exception
from glance.tests import utils as test_utils


class GlanceExceptionTestCase(test_utils.BaseTestCase):

    def test_default_error_msg(self):
        class FakeGlanceException(exception.GlanceException):
            message = "default message"

        exc = FakeGlanceException()
        self.assertEqual(unicode(exc), 'default message')

    def test_specified_error_msg(self):
        self.assertTrue('test' in unicode(exception.GlanceException('test')))

    def test_default_error_msg_with_kwargs(self):
        class FakeGlanceException(exception.GlanceException):
            message = "default message: %(code)s"

        exc = FakeGlanceException(code=500)
        self.assertEqual(unicode(exc), "default message: 500")

    def test_specified_error_msg_with_kwargs(self):
        self.assertTrue('test: 500' in
                        unicode(exception.GlanceException('test: %(code)s',
                                                          code=500)))

    def test_non_unicode_error_msg(self):
        exc = exception.GlanceException(str('test'))
        self.assertIsInstance(six.text_type(exc), six.text_type)
