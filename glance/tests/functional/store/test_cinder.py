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

"""
Functional tests for the Cinder store interface
"""

import os

import oslo.config.cfg
import testtools

import glance.store.cinder as cinder
import glance.tests.functional.store as store_tests
import glance.tests.functional.store.test_swift as store_tests_swift
import glance.tests.utils


def parse_config(config):
    out = {}
    options = [
        'test_cinder_store_auth_address',
        'test_cinder_store_auth_version',
        'test_cinder_store_tenant',
        'test_cinder_store_user',
        'test_cinder_store_key',
    ]

    for option in options:
        out[option] = config.defaults()[option]

    return out


class TestCinderStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.cinder.Store'
    store_cls = glance.store.cinder.Store
    store_name = 'cinder'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_CINDER_CONF')
        if not config_path:
            msg = "GLANCE_TEST_CINDER_CONF environ not set."
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])
        raw_config = store_tests_swift.read_config(config_path)

        try:
            self.cinder_config = parse_config(raw_config)
            ret = store_tests_swift.keystone_authenticate(
                self.cinder_config['test_cinder_store_auth_address'],
                self.cinder_config['test_cinder_store_auth_version'],
                self.cinder_config['test_cinder_store_tenant'],
                self.cinder_config['test_cinder_store_user'],
                self.cinder_config['test_cinder_store_key'])
            (tenant_id, auth_token, service_catalog) = ret
            self.context = glance.context.RequestContext(
                tenant=tenant_id,
                service_catalog=service_catalog,
                auth_tok=auth_token)
            self.cinder_client = cinder.get_cinderclient(self.context)
        except Exception as e:
            msg = "Cinder backend isn't set up: %s" % e
            self.skipTest(msg)

        super(TestCinderStore, self).setUp()

    def get_store(self, **kwargs):
        store = cinder.Store(context=kwargs.get('context') or self.context)
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        #(zhiyan): Currently cinder store is a partial implementation,
        # after Cinder expose 'brick' library, 'host-volume-attaching' and
        # 'multiple-attaching' enhancement ready, the store will support
        # ADD/GET/DELETE interface.
        raise NotImplementedError('stash_image can not be implemented so far')
