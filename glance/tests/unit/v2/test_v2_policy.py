# Copyright 2021 Red Hat, Inc
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

from unittest import mock

import webob.exc

from glance.api.v2 import policy
from glance.common import exception
from glance.tests import utils


class APIPolicyBase(utils.BaseTestCase):
    def setUp(self):
        super(APIPolicyBase, self).setUp()
        self.enforcer = mock.MagicMock()
        self.context = mock.MagicMock()
        self.policy = policy.APIPolicyBase(self.context,
                                           enforcer=self.enforcer)

    def test_enforce(self):
        # Enforce passes
        self.policy._enforce('fake_rule')
        self.enforcer.enforce.assert_called_once_with(
            self.context,
            'fake_rule',
            mock.ANY)

        # Make sure that Forbidden gets caught and translated
        self.enforcer.enforce.side_effect = exception.Forbidden
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.policy._enforce, 'fake_rule')

        # Any other exception comes straight through
        self.enforcer.enforce.side_effect = exception.ImageNotFound
        self.assertRaises(exception.ImageNotFound,
                          self.policy._enforce, 'fake_rule')

    def test_check(self):
        # Check passes
        self.assertTrue(self.policy.check('_enforce', 'fake_rule'))

        # Check fails
        self.enforcer.enforce.side_effect = exception.Forbidden
        self.assertFalse(self.policy.check('_enforce', 'fake_rule'))
