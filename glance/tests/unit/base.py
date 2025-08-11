# Copyright 2012 OpenStack Foundation.
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

import os
from unittest import mock

import glance_store as store
from glance_store._drivers import cinder
from glance_store._drivers import rbd as rbd_store
from glance_store._drivers import swift
from glance_store import location
from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_db import options
from oslo_serialization import jsonutils

from glance.tests import stubs
from glance.tests import utils as test_utils

CONF = cfg.CONF


class StoreClearingUnitTest(test_utils.BaseTestCase):

    def setUp(self):
        super(StoreClearingUnitTest, self).setUp()
        # Ensure stores + locations cleared
        location.SCHEME_TO_CLS_MAP = {}

        self._create_stores()
        self.addCleanup(setattr, location, 'SCHEME_TO_CLS_MAP', dict())

    def _create_stores(self, passing_config=True):
        """Create known stores.

        :param passing_config: making store driver passes basic configurations.
        :returns: the number of how many store drivers been loaded.
        """
        store.register_opts(CONF)

        self.config(default_store='filesystem',
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        store.create_stores(CONF)


class MultiStoreClearingUnitTest(test_utils.BaseTestCase):

    def setUp(self):
        super(MultiStoreClearingUnitTest, self).setUp()
        # Ensure stores + locations cleared
        location.SCHEME_TO_CLS_BACKEND_MAP = {}

        self._create_multi_stores()
        self.addCleanup(setattr, location, 'SCHEME_TO_CLS_MAP', dict())

    def _create_multi_stores(self, passing_config=True):
        """Create known stores.

        :param passing_config: making store driver passes basic configurations.
        :returns: the number of how many store drivers been loaded.
        """
        fake_fsid = "db437934-7e1c-445b-a4f5-7cc5bc44ba1b"
        rbd_store.rados = mock.MagicMock()
        rbd_store.rbd = mock.MagicMock()
        rbd_store.Store.get_connection = mock.MagicMock()
        conn_mock = rbd_store.Store.get_connection.return_value.__enter__()
        conn_mock.get_fsid.return_value = fake_fsid
        cinder.cinderclient = mock.MagicMock()
        cinder.Store.get_cinderclient = mock.MagicMock()
        swift.swiftclient = mock.MagicMock()
        swift.BaseStore.get_store_connection = mock.MagicMock()
        self.config(enabled_backends={'fast': 'file', 'cheap': 'file',
                                      'readonly_store': 'http',
                                      'fast-cinder': 'cinder',
                                      'fast-rbd': 'rbd', 'reliable': 'swift'})
        store.register_store_opts(
            CONF, reserved_stores={'os_glance_tasks_store': 'file'})

        self.config(default_backend='fast',
                    group='glance_store')

        self.config(filesystem_store_datadir=self.test_dir,
                    group='os_glance_tasks_store')
        self.config(filesystem_store_datadir=self.test_dir,
                    filesystem_thin_provisioning=False,
                    filesystem_store_chunk_size=65536,
                    group='fast')
        self.config(filesystem_store_datadir=self.test_dir2,
                    filesystem_thin_provisioning=False,
                    filesystem_store_chunk_size=65536,
                    group='cheap')
        self.config(rbd_store_chunk_size=8688388, rbd_store_pool='images',
                    rbd_thin_provisioning=False, group='fast-rbd')
        self.config(cinder_volume_type='lvmdriver-1',
                    cinder_use_multipath=False, group='fast-cinder')
        self.config(swift_store_container='glance',
                    swift_store_large_object_size=524288000,
                    swift_store_large_object_chunk_size=204800000,
                    group='reliable')

        store.create_multi_stores(CONF)


class IsolatedUnitTest(StoreClearingUnitTest):

    """
    Unit test case that establishes a mock environment within
    a testing directory (in isolation)
    """

    def setUp(self):
        super(IsolatedUnitTest, self).setUp()
        options.set_defaults(CONF, connection='sqlite://')
        lockutils.set_defaults(os.path.join(self.test_dir))

        self.config(debug=False)

        self.config(default_store='filesystem',
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        store.create_stores()

        def fake_get_conection_type(client):
            DEFAULT_API_PORT = 9292

            if client.port == DEFAULT_API_PORT:
                return stubs.FakeGlanceConnection

        self.patcher = mock.patch(
            'glance.common.client.BaseClient.get_connection_type',
            fake_get_conection_type)
        self.addCleanup(self.patcher.stop)
        self.patcher.start()

    def set_policy_rules(self, rules):
        fap = open(CONF.oslo_policy.policy_file, 'w')
        fap.write(jsonutils.dumps(rules))
        fap.close()


class MultiIsolatedUnitTest(MultiStoreClearingUnitTest):

    """
    Unit test case that establishes a mock environment within
    a testing directory (in isolation)
    """

    def setUp(self):
        super(MultiIsolatedUnitTest, self).setUp()
        options.set_defaults(CONF, connection='sqlite://')
        lockutils.set_defaults(os.path.join(self.test_dir))

        self.config(debug=False)

    def set_policy_rules(self, rules):
        fap = open(CONF.oslo_policy.policy_file, 'w')
        fap.write(jsonutils.dumps(rules))
        fap.close()

    def mock_object(self, obj, attr_name, *args, **kwargs):
        """Use python mock to mock an object attribute

        Mocks the specified objects attribute with the given value.
        Automatically performs 'addCleanup' for the mock.
        """
        patcher = mock.patch.object(obj, attr_name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result
