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
Functional tests for the RBD store interface.

Set the GLANCE_TEST_RBD_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
RBD backend. This backend must be running Ceph Bobtail (0.56) or later.
"""

import ConfigParser
import os
import uuid

import oslo.config.cfg
import six
import testtools

from glance.common import exception

import glance.store.rbd
import glance.tests.functional.store as store_tests

try:
    import rados
    import rbd
except ImportError:
    rados = None


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        'rbd_store_chunk_size',
        'rbd_store_pool',
        'rbd_store_user',
        'rbd_store_ceph_conf',
    ]

    for option in options:
        out[option] = config.defaults()[option]

    return out


class TestRBDStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.rbd.Store'
    store_cls = glance.store.rbd.Store
    store_name = 'rbd'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_RBD_CONF')
        if not config_path:
            msg = "GLANCE_TEST_RBD_CONF environ not set."
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])

        raw_config = read_config(config_path)
        config = parse_config(raw_config)

        if rados is None:
            self.skipTest("rados python library not found")

        rados_client = rados.Rados(conffile=config['rbd_store_ceph_conf'],
                                   rados_id=config['rbd_store_user'])
        try:
            rados_client.connect()
        except rados.Error as e:
            self.skipTest("Failed to connect to RADOS: %s" % e)

        try:
            rados_client.create_pool(config['rbd_store_pool'])
        except rados.Error as e:
            rados_client.shutdown()
            self.skipTest("Failed to create pool: %s")

        self.rados_client = rados_client
        self.rbd_config = config

        super(TestRBDStore, self).setUp()

    def tearDown(self):
        self.rados_client.delete_pool(self.rbd_config['rbd_store_pool'])
        self.rados_client.shutdown()

        super(TestRBDStore, self).tearDown()

    def get_store(self, **kwargs):
        store = glance.store.rbd.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        fsid = self.rados_client.get_fsid()
        pool = self.rbd_config['rbd_store_pool']
        librbd = rbd.RBD()
        # image_id must not be unicode since librbd doesn't handle it
        image_id = str(image_id)
        snap_name = 'snap'
        with self.rados_client.open_ioctx(pool) as ioctx:
            librbd.create(ioctx, image_id, len(image_data), old_format=False,
                          features=rbd.RBD_FEATURE_LAYERING)
            with rbd.Image(ioctx, image_id) as image:
                image.write(image_data, 0)
                image.create_snap(snap_name)

        return 'rbd://%s/%s/%s/%s' % (fsid, pool, image_id, snap_name)

    def test_unicode(self):
        # librbd does not handle unicode, so make sure
        # all paths through the rbd store convert a unicode image id
        # and uri to ascii before passing it to librbd.
        store = self.get_store()

        image_id = unicode(str(uuid.uuid4()))
        image_size = 300
        image_data = six.StringIO('X' * image_size)
        image_checksum = '41757066eaff7c4c6c965556b4d3c6c5'

        uri, add_size, add_checksum = store.add(image_id,
                                                image_data,
                                                image_size)
        uri = unicode(uri)

        self.assertEqual(image_size, add_size)
        self.assertEqual(image_checksum, add_checksum)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        self.assertEqual(image_size, store.get_size(location))

        get_iter, get_size = store.get(location)

        self.assertEqual(image_size, get_size)
        self.assertEqual('X' * image_size, ''.join(get_iter))

        store.delete(location)

        self.assertRaises(exception.NotFound, store.get, location)
