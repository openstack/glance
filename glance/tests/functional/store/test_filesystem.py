# Copyright 2012 OpenStack Foundation
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
Functional tests for the File store interface
"""

import os
import os.path

import fixtures
import oslo.config.cfg
import testtools

import glance.store.filesystem
import glance.tests.functional.store as store_tests


class TestFilesystemStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.filesystem.Store'
    store_cls = glance.store.filesystem.Store
    store_name = 'filesystem'

    def setUp(self):
        super(TestFilesystemStore, self).setUp()
        self.tmp_dir = self.useFixture(fixtures.TempDir()).path

        self.store_dir = os.path.join(self.tmp_dir, 'images')
        os.mkdir(self.store_dir)

        config_file = os.path.join(self.tmp_dir, 'glance.conf')
        with open(config_file, 'w') as fap:
            fap.write("[DEFAULT]\n")
            fap.write("filesystem_store_datadir=%s" % self.store_dir)

        oslo.config.cfg.CONF(default_config_files=[config_file], args=[])

    def get_store(self, **kwargs):
        store = glance.store.filesystem.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        filepath = os.path.join(self.store_dir, image_id)
        with open(filepath, 'w') as fap:
            fap.write(image_data)
        return 'file://%s' % filepath
