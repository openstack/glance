# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import datetime
import unittest

import stubout

from glance.common import context
from glance.common import exception
from glance.common import utils
from glance.registry import context as rcontext
from glance.registry.db import api as db_api
from glance.registry.db import models as db_models
from glance.tests import stubs
from glance.tests import utils as test_utils


_gen_uuid = utils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


CONF = {'sql_connection': 'sqlite://',
        'verbose': False,
        'debug': False,
        'registry_host': '0.0.0.0',
        'registry_port': '9191',
        'default_store': 'file',
        'filesystem_store_datadir': stubs.FAKE_FILESYSTEM_ROOTDIR}

FIXTURES = [
    {'id': UUID1,
     'name': 'fake image #1',
     'status': 'active',
     'disk_format': 'ami',
     'container_format': 'ami',
     'is_public': False,
     'created_at': datetime.datetime.utcnow(),
     'updated_at': datetime.datetime.utcnow(),
     'deleted_at': None,
     'deleted': False,
     'checksum': None,
     'min_disk': 0,
     'min_ram': 0,
     'size': 13,
     'location': "swift://user:passwd@acct/container/obj.tar.0",
     'properties': {'type': 'kernel'}},
    {'id': UUID2,
     'name': 'fake image #2',
     'status': 'active',
     'disk_format': 'vhd',
     'container_format': 'ovf',
     'is_public': True,
     'created_at': datetime.datetime.utcnow(),
     'updated_at': datetime.datetime.utcnow(),
     'deleted_at': None,
     'deleted': False,
     'checksum': None,
     'min_disk': 5,
     'min_ram': 256,
     'size': 19,
     'location': "file:///tmp/glance-tests/2",
     'properties': {}}]


class TestRegistryDb(unittest.TestCase):

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_filesystem_backend()
        conf = test_utils.TestConfigOpts(CONF)
        self.adm_context = rcontext.RequestContext(is_admin=True)
        self.context = rcontext.RequestContext(is_admin=False)
        db_api.configure_db(conf)
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def create_fixtures(self):
        for fixture in FIXTURES:
            db_api.image_create(self.adm_context, fixture)

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_image_get(self):
        image = db_api.image_get(self.context, UUID1)
        self.assertEquals(image['id'], FIXTURES[0]['id'])

    def test_image_get_disallow_deleted(self):
        db_api.image_destroy(self.adm_context, UUID1)
        self.assertRaises(exception.NotFound, db_api.image_get,
                          self.context, UUID1)

    def test_image_get_allow_deleted(self):
        db_api.image_destroy(self.adm_context, UUID1)
        image = db_api.image_get(self.adm_context, UUID1)
        self.assertEquals(image['id'], FIXTURES[0]['id'])

    def test_image_get_force_allow_deleted(self):
        db_api.image_destroy(self.adm_context, UUID1)
        image = db_api.image_get(self.context, UUID1, force_show_deleted=True)
        self.assertEquals(image['id'], FIXTURES[0]['id'])

    def test_image_get_all(self):
        images = db_api.image_get_all(self.context)
        self.assertEquals(len(images), 2)

    def test_image_get_all_marker(self):
        images = db_api.image_get_all(self.context, marker=UUID2)
        self.assertEquals(len(images), 1)

    def test_image_get_all_marker_deleted(self):
        """Cannot specify a deleted image as a marker."""
        db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': False}
        self.assertRaises(exception.NotFound, db_api.image_get_all,
                          self.context, marker=UUID1, filters=filters)

    def test_image_get_all_marker_deleted_showing_deleted_as_admin(self):
        """Specify a deleted image as a marker if showing deleted images."""
        db_api.image_destroy(self.adm_context, UUID1)
        images = db_api.image_get_all(self.adm_context, marker=UUID1)
        self.assertEquals(len(images), 0)

    def test_image_get_all_marker_deleted_showing_deleted(self):
        """Specify a deleted image as a marker if showing deleted images."""
        db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': True}
        images = db_api.image_get_all(self.context, marker=UUID1,
                                      filters=filters)
        self.assertEquals(len(images), 0)
