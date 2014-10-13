# Copyright 2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

from glance.api import CONF
import glance.db.simple.api
import glance.tests.functional.db as db_tests
from glance.tests.functional.db import base


def get_db(config):
    CONF.set_override('data_api', 'glance.db.simple.api')
    db_api = glance.db.get_api()
    return db_api


def reset_db(db_api):
    db_api.reset()


class TestSimpleDriver(base.TestDriver,
                       base.DriverTests,
                       base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSimpleDriver, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSimpleQuota(base.DriverQuotaTests,
                      base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSimpleQuota, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSimpleVisibility(base.TestVisibility,
                           base.VisibilityTests,
                           base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSimpleVisibility, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSimpleMembershipVisibility(base.TestMembershipVisibility,
                                     base.MembershipVisibilityTests,
                                     base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSimpleMembershipVisibility, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSimpleTask(base.TaskTests,
                     base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSimpleTask, self).setUp()
        self.addCleanup(db_tests.reset)
