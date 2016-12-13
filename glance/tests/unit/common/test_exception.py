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

from oslo_utils import encodeutils
import six
from six.moves import http_client as http

from glance.common import exception
from glance.tests import utils as test_utils


class GlanceExceptionTestCase(test_utils.BaseTestCase):

    def test_default_error_msg(self):
        class FakeGlanceException(exception.GlanceException):
            message = "default message"

        exc = FakeGlanceException()
        self.assertEqual('default message',
                         encodeutils.exception_to_unicode(exc))

    def test_specified_error_msg(self):
        msg = exception.GlanceException('test')
        self.assertIn('test', encodeutils.exception_to_unicode(msg))

    def test_default_error_msg_with_kwargs(self):
        class FakeGlanceException(exception.GlanceException):
            message = "default message: %(code)s"

        exc = FakeGlanceException(code=int(http.INTERNAL_SERVER_ERROR))
        self.assertEqual("default message: 500",
                         encodeutils.exception_to_unicode(exc))

    def test_specified_error_msg_with_kwargs(self):
        msg = exception.GlanceException('test: %(code)s',
                                        code=int(http.INTERNAL_SERVER_ERROR))
        self.assertIn('test: 500', encodeutils.exception_to_unicode(msg))

    def test_non_unicode_error_msg(self):
        exc = exception.GlanceException(str('test'))
        self.assertIsInstance(encodeutils.exception_to_unicode(exc),
                              six.text_type)
