# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack LLC.
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

from mock import Mock
from oslo.config import cfg
import testtools

from glance import db as db_api
from glance.openstack.common import importutils

CONF = cfg.CONF
CONF.import_opt('use_tpool', 'glance.db')
CONF.import_opt('data_api', 'glance.db')


class DbApiTest(testtools.TestCase):
    def test_get_dbapi_when_db_pool_is_enabled(self):
        CONF.set_override('use_tpool', True)
        dbapi = db_api.get_api()
        self.assertTrue(isinstance(dbapi, db_api.ThreadPoolWrapper))

    def test_get_dbapi_when_db_pool_is_disabled(self):
        CONF.set_override('use_tpool', False)
        dbapi = db_api.get_api()
        self.assertFalse(isinstance(dbapi, db_api.ThreadPoolWrapper))
        self.assertEqual(importutils.import_module(CONF.data_api), dbapi)


def method_for_test_1(*args, **kwargs):
    return args, kwargs


class ThreadPoolWrapper(testtools.TestCase):
    def test_thread_pool(self):
        module = importutils.import_module('glance.tests.functional.db.'
                                           'test_db_api')
        CONF.set_override('use_tpool', True)
        CONF.set_override('data_api', 'glance.tests.functional.db.'
                          'test_db_api')
        dbapi = db_api.get_api()

        from eventlet import tpool
        tpool.execute = Mock()

        dbapi.method_for_test_1(1, 2, kwarg='arg')
        tpool.execute.assert_called_with(method_for_test_1, 1, 2, kwarg='arg')

    def tearDown(self):
        super(ThreadPoolWrapper, self).tearDown()
        CONF.set_override('use_tpool', False)
