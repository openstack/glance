# Copyright 2013 Red Hat, Inc.
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

from oslo_config import cfg
from oslo_db import options

import glance.db
import glance.tests.functional.db as db_tests
from glance.tests.functional.db import base
from glance.tests.functional.db import base_metadef

CONF = cfg.CONF


def get_db(config):
    options.set_defaults(CONF, connection='sqlite://')
    config(data_api='glance.db.registry.api')
    return glance.db.get_api()


def reset_db(db_api):
    pass


class FunctionalInitWrapper(base.FunctionalInitWrapper):

    def setUp(self):
        # NOTE(flaper87): We need to start the
        # registry service *before* TestDriver's
        # setup goes on, since it'll create some
        # images that will be later used in tests.
        #
        # Python's request is way too magical and
        # it will make the TestDriver's super call
        # FunctionalTest's without letting us start
        # the server.
        #
        # This setUp will be called by TestDriver
        # and will be used to call FunctionalTest
        # setUp method *and* start the registry
        # service right after it.
        super(FunctionalInitWrapper, self).setUp()
        self.registry_server.deployment_flavor = 'fakeauth'
        self.start_with_retry(self.registry_server,
                              'registry_port', 3,
                              api_version=2)

        self.config(registry_port=self.registry_server.bind_port,
                    use_user_token=True)


class TestRegistryDriver(base.TestDriver,
                         base.DriverTests,
                         FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestRegistryDriver, self).setUp()
        self.addCleanup(db_tests.reset)

    def tearDown(self):
        self.registry_server.stop()
        super(TestRegistryDriver, self).tearDown()


class TestRegistryQuota(base.DriverQuotaTests, FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestRegistryQuota, self).setUp()
        self.addCleanup(db_tests.reset)

    def tearDown(self):
        self.registry_server.stop()
        super(TestRegistryQuota, self).tearDown()


class TestRegistryMetadefDriver(base_metadef.TestMetadefDriver,
                                base_metadef.MetadefDriverTests,
                                FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestRegistryMetadefDriver, self).setUp()
        self.addCleanup(db_tests.reset)

    def tearDown(self):
        self.registry_server.stop()
        super(TestRegistryMetadefDriver, self).tearDown()


class TestTasksDriver(base.TaskTests, FunctionalInitWrapper):
    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestTasksDriver, self).setUp()
        self.addCleanup(db_tests.reset)

    def tearDown(self):
        self.registry_server.stop()
        super(TestTasksDriver, self).tearDown()
