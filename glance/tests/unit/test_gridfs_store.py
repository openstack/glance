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
from glance.store.gridfs import Store
from glance.tests.unit import base
try:
    import gridfs
    import pymongo
except ImportError:
    pymongo = None


GRIDFS_CONF = {'verbose': True,
               'debug': True,
               'default_store': 'gridfs',
               'mongodb_store_uri': 'mongodb://fake_store_uri',
               'mongodb_store_db': 'fake_store_db'}


def stub_out_gridfs(stubs):
    class FakeMongoClient(object):
        def __init__(self, *args, **kwargs):
            pass

        def __getitem__(self, key):
            return None

    class FakeGridFS(object):
        image_data = {}
        called_commands = []

        def __init__(self, *args, **kwargs):
            pass

        def exists(self, image_id):
            self.called_commands.append('exists')
            return False

        def put(self, image_file, _id):
            self.called_commands.append('put')
            data = None
            while True:
                data = image_file.read(64)
                if data:
                    self.image_data[_id] = \
                        self.image_data.setdefault(_id, '') + data
                else:
                    break

        def delete(self, _id):
            self.called_commands.append('delete')

    if pymongo is not None:
        stubs.Set(pymongo, 'MongoClient', FakeMongoClient)
        stubs.Set(gridfs, 'GridFS', FakeGridFS)


class TestStore(base.StoreClearingUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        self.config(**GRIDFS_CONF)
        super(TestStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        stub_out_gridfs(self.stubs)
        self.store = Store()
        self.addCleanup(self.stubs.UnsetAll)

    def test_cleanup_when_add_image_exception(self):
        if pymongo is None:
            msg = 'GridFS store can not add images, skip test.'
            self.skipTest(msg)

        self.assertRaises(exception.ImageSizeLimitExceeded,
                          self.store.add,
                          'fake_image_id',
                          utils.LimitingReader(six.StringIO('xx'), 1),
                          2)
        self.assertEqual(self.store.fs.called_commands,
                         ['exists', 'put', 'delete'])
