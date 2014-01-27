# Copyright 2013 Taobao Inc.
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
Functional tests for the Sheepdog store interface
"""

import os
import os.path

import fixtures
import oslo.config.cfg
import testtools

from glance.store import BackendException
import glance.store.sheepdog as sheepdog
import glance.tests.functional.store as store_tests
import glance.tests.utils


class TestSheepdogStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.sheepdog.Store'
    store_cls = glance.store.sheepdog.Store
    store_name = 'sheepdog'

    def setUp(self):
        image = sheepdog.SheepdogImage(sheepdog.DEFAULT_ADDR,
                                       sheepdog.DEFAULT_PORT,
                                       "test",
                                       sheepdog.DEFAULT_CHUNKSIZE)
        try:
            image.create(512)
        except BackendException:
            msg = "Sheepdog cluster isn't set up"
            self.skipTest(msg)
        image.delete()

        self.tmp_dir = self.useFixture(fixtures.TempDir()).path

        config_file = os.path.join(self.tmp_dir, 'glance.conf')
        with open(config_file, 'w') as f:
            f.write("[DEFAULT]\n")
            f.write("default_store = sheepdog")

        oslo.config.cfg.CONF(default_config_files=[config_file], args=[])
        super(TestSheepdogStore, self).setUp()

    def get_store(self, **kwargs):
        store = sheepdog.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        image_size = len(image_data)
        image = sheepdog.SheepdogImage(sheepdog.DEFAULT_ADDR,
                                       sheepdog.DEFAULT_PORT,
                                       image_id,
                                       sheepdog.DEFAULT_CHUNKSIZE)
        image.create(image_size)
        total = left = image_size
        while left > 0:
            length = min(sheepdog.DEFAULT_CHUNKSIZE, left)
            image.write(image_data, total - left, length)
            left -= length

        return 'sheepdog://%s' % image_id
