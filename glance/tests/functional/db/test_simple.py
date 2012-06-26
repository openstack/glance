# Copyright 2012 OpenStack, LLC
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


import glance.db.simple.api
import glance.tests.functional.db as tests
from glance.tests.unit import base


class TestSimpleDriver(base.IsolatedUnitTest, tests.BaseTestCase):

    def setUp(self):
        base.IsolatedUnitTest.setUp(self)
        tests.BaseTestCase.setUp(self)

    def configure(self):
        self.db_api = glance.db.simple.api

    def reset(self):
        self.db_api.reset()
