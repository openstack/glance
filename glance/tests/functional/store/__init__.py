# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import StringIO

import testtools

from oslo.config import cfg

from glance.common import exception
from glance.openstack.common import uuidutils
import glance.store.location
#NOTE(bcwaldon): importing this to get the default_store option
import glance.api.v1.images

CONF = cfg.CONF


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()

    def tearDown(self):
        CONF.reset()
        super(BaseTestCase, self).tearDown()

    def config(self, **kw):
        for k, v in kw.iteritems():
            CONF.set_override(k, v, group=None)

    def get_store(self, **kwargs):
        raise NotImplementedError('get_store() must be implemented')

    def stash_image(self, image_id, image_data):
        """Store image data in the backend manually

        :param image_id: image identifier
        :param image_data: string representing image data fixture
        :return URI referencing newly-created backend object
        """
        raise NotImplementedError('stash_image must be implemented')

    def test_create_store(self):
        self.config(known_stores=[self.store_cls_path])
        count = glance.store.create_stores()
        self.assertEqual(count, 1)

    def test_lifecycle(self):
        """Add, get and delete an image"""
        store = self.get_store()

        image_id = uuidutils.generate_uuid()
        image_data = StringIO.StringIO('XXX')
        image_checksum = 'bc9189406be84ec297464a514221406d'
        try:
            uri, add_size, add_checksum = store.add(image_id, image_data, 3)
        except NotImplementedError:
            msg = 'Configured store can not add images'
            self.skipTest(msg)

        self.assertEqual(3, add_size)
        self.assertEqual(image_checksum, add_checksum)

        store = self.get_store()
        location = glance.store.location.Location(
                self.store_name,
                store.get_store_location_class(),
                uri=uri,
                image_id=image_id)

        (get_iter, get_size) = store.get(location)
        self.assertEqual(3, get_size)
        self.assertEqual('XXX', ''.join(get_iter))

        image_size = store.get_size(location)
        self.assertEqual(3, image_size)

        store.delete(location)

        self.assertRaises(exception.NotFound, store.get, location)

    def test_get_remote_image(self):
        """Get an image that was created externally to Glance"""
        image_id = uuidutils.generate_uuid()
        image_uri = self.stash_image(image_id, 'XXX')
        store = self.get_store()
        location = glance.store.location.Location(
                self.store_name,
                store.get_store_location_class(),
                uri=image_uri)

        (get_iter, get_size) = store.get(location)
        self.assertEqual(3, get_size)
        self.assertEqual('XXX', ''.join(get_iter))

        image_size = store.get_size(location)
        self.assertEqual(3, image_size)
