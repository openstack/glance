# Copyright 2013 Red Hat, Inc
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
Functional tests for the gridfs store interface

Set the GLANCE_TEST_GRIDFS_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
GridFS backend
"""

import ConfigParser
import os

import oslo.config.cfg
import testtools

import glance.store.gridfs
import glance.tests.functional.store as store_tests


try:
    import gridfs
    import pymongo
except ImportError:
    gridfs = None


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        'mongodb_store_db',
        'mongodb_store_uri']

    for option in options:
        out[option] = config.defaults()[option]

    return out


class TestGridfsStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.gridfs.Store'
    store_cls = glance.store.gridfs.Store
    store_name = 'gridfs'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_GRIDFS_CONF')
        if not config_path or not gridfs:
            msg = "GLANCE_TEST_GRIDFS_CONF environ not set."
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])

        raw_config = read_config(config_path)
        self.gfs_config = parse_config(raw_config)
        super(TestGridfsStore, self).setUp()

    def get_store(self, **kwargs):
        store = self.store_cls(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        conn = pymongo.MongoClient(self.gfs_config.get("mongodb_store_uri"))
        fs = gridfs.GridFS(conn[self.gfs_config.get("mongodb_store_db")])
        fs.put(image_data, _id=image_id)
        return 'gridfs://%s' % image_id
