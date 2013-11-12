# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011-2013 OpenStack Foundation
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

from glance.store import base as store_base
from glance.tests.unit import base as test_base


class TestStoreBase(test_base.StoreClearingUnitTest):

    def setUp(self):
        self.config(default_store='file')
        super(TestStoreBase, self).setUp()

    def test_exception_to_unicode(self):
        class FakeException(Exception):
            def __str__(self):
                raise UnicodeError()

        exc = Exception('error message')
        ret = store_base._exception_to_unicode(exc)
        self.assertEqual(unicode, type(ret))
        self.assertEqual(ret, 'error message')

        exc = Exception('\xa5 error message')
        ret = store_base._exception_to_unicode(exc)
        self.assertEqual(unicode, type(ret))
        self.assertEqual(ret, ' error message')

        exc = FakeException('\xa5 error message')
        ret = store_base._exception_to_unicode(exc)
        self.assertEqual(unicode, type(ret))
        self.assertEqual(ret, _("Caught '%(exception)s' exception.") %
                         {'exception': 'FakeException'})
