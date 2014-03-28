# Copyright 2013 OpenStack Foundation
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
import stubout

from glance.common import exception
from glance.common import utils
from glance.openstack.common import processutils
import glance.store.sheepdog
from glance.store.sheepdog import Store
from glance.tests.unit import base


SHEEPDOG_CONF = {'verbose': True,
                 'debug': True,
                 'default_store': 'sheepdog'}


class TestStore(base.StoreClearingUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        def _fake_execute(*cmd, **kwargs):
            pass

        self.config(**SHEEPDOG_CONF)
        super(TestStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        self.stubs.Set(processutils, 'execute', _fake_execute)
        self.store = Store()
        self.addCleanup(self.stubs.UnsetAll)

    def test_cleanup_when_add_image_exception(self):
        called_commands = []

        def _fake_run_command(self, command, data, *params):
            called_commands.append(command)

        self.stubs.Set(glance.store.sheepdog.SheepdogImage,
                       '_run_command', _fake_run_command)

        self.assertRaises(exception.ImageSizeLimitExceeded,
                          self.store.add,
                          'fake_image_id',
                          utils.LimitingReader(six.StringIO('xx'), 1),
                          2)
        self.assertEqual([['list', '-r'], ['create'], ['delete']],
                         called_commands)
