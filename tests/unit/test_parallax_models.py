# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

import unittest
import sqlalchemy.exceptions as sa_exc

from glance.common import exception
from glance.parallax import db
from glance.common import flags
from glance.parallax.db.sqlalchemy import models

FLAGS = flags.FLAGS


class TestModels(unittest.TestCase):
    """ Test Parllax SQLAlchemy models using an in-memory sqlite DB"""

    def setUp(self):
        FLAGS.sql_connection = "sqlite://" # in-memory db
        models.unregister_models()
        models.register_models()
        self.image = self._make_image(id=2, name='fake image #2')

    def test_metadata_key_constraint_ok(self):
        """Two different images are permitted to have metadata that share the
        same key

        """
        self._make_metadatum(self.image, key="spam", value="eggs")
        
        second_image = self._make_image(id=3, name='fake image #3')
        self._make_metadatum(second_image, key="spam", value="eggs")

    def test_metadata_key_constraint_bad(self):
        """The same image cannot have two distinct pieces of metadata with the
        same key.

        """
        self._make_metadatum(self.image, key="spam", value="eggs")

        self.assertRaises(sa_exc.IntegrityError,
            self._make_metadatum, self.image, key="spam", value="eggs")

    def _make_image(self, id, name):
        """Convenience method to create an image with a given name and id"""
        fixture = {'id': id,
                   'name': name,
                   'is_public': True,
                   'image_type': 'kernel',
                   'status': 'available'}
        
        context = None
        image = db.api.image_create(context, fixture)
        return image

    def _make_metadatum(self, image, key, value):
        """Convenience method to create metadata attached to an image"""
        metadata = {'image_id': image['id'], 'key': key, 'value': value}
        context = None
        metadatum = db.api.image_metadatum_create(context, metadata)
        return metadatum


