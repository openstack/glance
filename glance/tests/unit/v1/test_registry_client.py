# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack Foundation
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

import copy
import datetime
import os
import stubout

import mox

import testtools

from glance.common import config
from glance.common import exception
from glance.common import client as test_client
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
import glance.registry.client.v1.api as rapi
from glance.registry.api.v1.images import Controller as rcontroller
from glance.registry.client.v1.api import client as rclient
from glance.tests.unit import base


_gen_uuid = uuidutils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()

#NOTE(bcwaldon): needed to init config_dir cli opt
config.parse_args(args=[])


class TestRegistryV1Client(base.IsolatedUnitTest):

    """
    Test proper actions made for both valid and invalid requests
    against a Registry service
    """

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryV1Client, self).setUp()
        db_api.setup_db_env()
        db_api.get_engine()
        self.context = context.RequestContext(is_admin=True)
        self.FIXTURES = [
            {'id': UUID1,
             'name': 'fake image #1',
             'status': 'active',
             'disk_format': 'ami',
             'container_format': 'ami',
             'is_public': False,
             'created_at': timeutils.utcnow(),
             'updated_at': timeutils.utcnow(),
             'deleted_at': None,
             'deleted': False,
             'checksum': None,
             'size': 13,
             'location': "swift://user:passwd@acct/container/obj.tar.0",
             'properties': {'type': 'kernel'}},
            {'id': UUID2,
             'name': 'fake image #2',
             'status': 'active',
             'disk_format': 'vhd',
             'container_format': 'ovf',
             'is_public': True,
             'created_at': timeutils.utcnow(),
             'updated_at': timeutils.utcnow(),
             'deleted_at': None,
             'deleted': False,
             'checksum': None,
             'size': 19,
             'location': "file:///tmp/glance-tests/2",
             'properties': {}}]
        self.destroy_fixtures()
        self.create_fixtures()
        self.client = rclient.RegistryClient("0.0.0.0")

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryV1Client, self).tearDown()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_get_image_index(self):
        """Test correct set of public image returned"""
        fixture = {
            'id': UUID2,
            'name': 'fake image #2'
        }
        images = self.client.get_images()
        self.assertEquals(len(images), 1)

        for k, v in fixture.items():
            self.assertEquals(v, images[0][k])

    def test_create_image_with_null_min_disk_min_ram(self):
        UUID3 = _gen_uuid()
        extra_fixture = {
            'id': UUID3,
            'status': 'active',
            'is_public': True,
            'disk_format': 'vhd',
            'container_format': 'ovf',
            'name': 'asdf',
            'size': 19,
            'checksum': None,
            'min_disk': None,
            'min_ram': None,
        }
        db_api.image_create(self.context, extra_fixture)
        image = self.client.get_image(UUID3)
        self.assertEqual(0, image["min_ram"])
        self.assertEqual(0, image["min_disk"])

    def test_get_index_sort_name_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by name in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='name', sort_dir='asc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID4)

    def test_get_index_sort_status_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by status in
        descending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'queued',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='status', sort_dir='desc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)

    def test_get_index_sort_disk_format_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by disk_format in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vdi',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='disk_format',
                                        sort_dir='asc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)

    def test_get_index_sort_container_format_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by container_format in
        descending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'iso',
                         'container_format': 'bare',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='container_format',
                                        sort_dir='desc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID2)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID3)

    def test_get_index_sort_size_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by size in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 100,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'iso',
                         'container_format': 'bare',
                         'name': 'xyz',
                         'size': 2,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='size', sort_dir='asc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID4)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID3)

    def test_get_index_sort_created_at_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by created_at in ascending order.
        """
        now = timeutils.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time2}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='created_at', sort_dir='asc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID2)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID3)

    def test_get_index_sort_updated_at_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by updated_at in descending order.
        """
        now = timeutils.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': time1}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': time2}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(sort_key='updated_at', sort_dir='desc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)

    def test_get_image_index_marker(self):
        """Test correct set of images returned with marker param."""
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(marker=UUID4)

        self.assertEquals(len(images), 2)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID2)

    def test_get_image_index_invalid_marker(self):
        """Test exception is raised when marker is invalid"""
        self.assertRaises(exception.Invalid,
                          self.client.get_images,
                          marker=_gen_uuid())

    def test_get_image_index_forbidden_marker(self):
        """Test exception is raised when marker is forbidden"""
        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'saving',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'owner': '0123',
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        def non_admin_get_images(self, context, *args, **kwargs):
            """Convert to non-admin context"""
            context.is_admin = False
            rcontroller.__get_images(self, context, *args, **kwargs)

        rcontroller.__get_images = rcontroller._get_images
        self.stubs.Set(rcontroller, '_get_images', non_admin_get_images)
        self.assertRaises(exception.Invalid,
                          self.client.get_images,
                          marker=UUID5)

    def test_get_image_index_private_marker(self):
        """Test exception is not raised if private non-owned marker is used"""
        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'saving',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None,
                         'owner': '1234'}

        db_api.image_create(self.context, extra_fixture)

        try:
            self.client.get_images(marker=UUID4)
        except Exception as e:
            self.fail("Unexpected exception '%s'" % e)

    def test_get_image_index_limit(self):
        """Test correct number of images returned with limit param."""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(limit=2)
        self.assertEquals(len(images), 2)

    def test_get_image_index_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(marker=UUID3, limit=1)

        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], UUID2)

    def test_get_image_index_limit_None(self):
        """Test correct set of images returned with limit param == None."""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(limit=None)
        self.assertEquals(len(images), 3)

    def test_get_image_index_by_name(self):
        """
        Test correct set of public, name-filtered image returned. This
        is just a sanity check, we test the details call more in-depth.
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images(filters={'name': 'new name! #123'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_get_image_details(self):
        """Tests that the detailed info about public images returned"""
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'properties': {}}

        images = self.client.get_images_detailed()

        self.assertEquals(len(images), 1)
        for k, v in fixture.items():
            self.assertEquals(v, images[0][k])

    def test_get_image_details_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(marker=UUID3, limit=1)

        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], UUID2)

    def test_get_image_details_invalid_marker(self):
        """Test exception is raised when marker is invalid"""
        self.assertRaises(exception.Invalid,
                          self.client.get_images_detailed,
                          marker=_gen_uuid())

    def test_get_image_details_forbidden_marker(self):
        """Test exception is raised when marker is forbidden"""
        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'saving',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'owner': '0123',
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        def non_admin_get_images(self, context, *args, **kwargs):
            """Convert to non-admin context"""
            context.is_admin = False
            rcontroller.__get_images(self, context, *args, **kwargs)

        rcontroller.__get_images = rcontroller._get_images
        self.stubs.Set(rcontroller, '_get_images', non_admin_get_images)
        self.assertRaises(exception.Invalid,
                          self.client.get_images_detailed,
                          marker=UUID5)

    def test_get_image_details_private_marker(self):
        """Test exception is not raised if private non-owned marker is used"""
        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'saving',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None,
                         'owner': '1234'}

        db_api.image_create(self.context, extra_fixture)

        try:
            self.client.get_images_detailed(marker=UUID4)
        except Exception as e:
            self.fail("Unexpected exception '%s'" % e)

    def test_get_image_details_by_name(self):
        """Tests that a detailed call can be filtered by name"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        filters = {'name': 'new name! #123'}
        images = self.client.get_images_detailed(filters=filters)

        self.assertEquals(len(images), 1)
        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_get_image_details_by_status(self):
        """Tests that a detailed call can be filtered by status"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(filters={'status': 'saving'})

        self.assertEquals(len(images), 1)
        for image in images:
            self.assertEquals('saving', image['status'])

    def test_get_image_details_by_container_format(self):
        """Tests that a detailed call can be filtered by container_format"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        filters = {'container_format': 'ovf'}
        images = self.client.get_images_detailed(filters=filters)

        self.assertEquals(len(images), 2)
        for image in images:
            self.assertEquals('ovf', image['container_format'])

    def test_get_image_details_by_disk_format(self):
        """Tests that a detailed call can be filtered by disk_format"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        filters = {'disk_format': 'vhd'}
        images = self.client.get_images_detailed(filters=filters)

        self.assertEquals(len(images), 2)
        for image in images:
            self.assertEquals('vhd', image['disk_format'])

    def test_get_image_details_with_maximum_size(self):
        """Tests that a detailed call can be filtered by size_max"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 21,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(filters={'size_max': 20})

        self.assertEquals(len(images), 1)
        for image in images:
            self.assertTrue(image['size'] <= 20)

    def test_get_image_details_with_minimum_size(self):
        """Tests that a detailed call can be filtered by size_min"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(filters={'size_min': 20})

        self.assertEquals(len(images), 1)
        for image in images:
            self.assertTrue(image['size'] >= 20)

    def test_get_image_details_with_changes_since(self):
        """Tests that a detailed call can be filtered by changes-since"""
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)

        dt2 = timeutils.utcnow() + datetime.timedelta(1)
        iso2 = timeutils.isotime(dt2)

        dt3 = timeutils.utcnow() + datetime.timedelta(2)
        iso3 = timeutils.isotime(dt3)

        dt4 = timeutils.utcnow() + datetime.timedelta(3)
        iso4 = timeutils.isotime(dt4)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)
        db_api.image_destroy(self.context, UUID3)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None,
                         'created_at': dt3,
                         'updated_at': dt3}

        db_api.image_create(self.context, extra_fixture)

        # Check a standard list, 4 images in db (2 deleted)
        images = self.client.get_images_detailed(filters={})
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID2)

        # Expect 3 images (1 deleted)
        filters = {'changes-since': iso1}
        images = self.client.get_images(filters=filters)
        self.assertEquals(len(images), 3)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID3)  # deleted
        self.assertEqual(images[2]['id'], UUID2)

        # Expect 1 images (0 deleted)
        filters = {'changes-since': iso2}
        images = self.client.get_images_detailed(filters=filters)
        self.assertEquals(len(images), 1)
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 0 images (0 deleted)
        filters = {'changes-since': iso4}
        images = self.client.get_images(filters=filters)
        self.assertEquals(len(images), 0)

    def test_get_image_details_with_size_min(self):
        """Tests that a detailed call can be filtered by size_min"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(filters={'size_min': 20})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertTrue(image['size'] >= 20)

    def test_get_image_details_by_property(self):
        """Tests that a detailed call can be filtered by a property"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'properties': {'p a': 'v a'}}

        db_api.image_create(self.context, extra_fixture)

        filters = {'property-p a': 'v a'}
        images = self.client.get_images_detailed(filters=filters)
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('v a', image['properties']['p a'])

    def test_get_image_is_public_v1(self):
        """Tests that a detailed call can be filtered by a property"""
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'properties': {'is_public': 'avalue'}}

        context = copy.copy(self.context)
        db_api.image_create(context, extra_fixture)

        filters = {'property-is_public': 'avalue'}
        images = self.client.get_images_detailed(filters=filters)
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('avalue', image['properties']['is_public'])

    def test_get_image_details_sort_disk_format_asc(self):
        """
        Tests that a detailed call returns list of
        public images sorted alphabetically by disk_format in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vdi',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        images = self.client.get_images_detailed(sort_key='disk_format',
                                                 sort_dir='asc')

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)

    def test_get_image(self):
        """Tests that the detailed info about an image returned"""
        fixture = {'id': UUID1,
                   'name': 'fake image #1',
                   'is_public': False,
                   'disk_format': 'ami',
                   'container_format': 'ami',
                   'status': 'active',
                   'size': 13,
                   'properties': {'type': 'kernel'}}

        data = self.client.get_image(UUID1)

        for k, v in fixture.items():
            el = data[k]
            self.assertEquals(v, data[k],
                              "Failed v != data[k] where v = %(v)s and "
                              "k = %(k)s and data[k] = %(el)s" % locals())

    def test_get_image_non_existing(self):
        """Tests that NotFound is raised when getting a non-existing image"""
        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          _gen_uuid())

    def test_add_image_basic(self):
        """Tests that we can add image metadata and returns the new id"""
        fixture = {
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'size': 19,
        }

        new_image = self.client.add_image(fixture)

        # Test all other attributes set
        data = self.client.get_image(new_image['id'])

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('active', data['status'])

    def test_add_image_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}

        new_image = self.client.add_image(fixture)

        del fixture['location']
        for k, v in fixture.items():
            self.assertEquals(v, new_image[k])

        # Test status was updated properly
        self.assertTrue('status' in new_image.keys())
        self.assertEquals('active', new_image['status'])

    def test_add_image_with_location_data(self):
        """Tests that we can add image metadata with properties"""
        location = "file:///tmp/glance-tests/2"
        loc_meta = {'key': 'value'}
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'size': 19,
                   'location_data': [{'url': location,
                                      'metadata': loc_meta}],
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}

        new_image = self.client.add_image(fixture)

        self.assertEquals(new_image['location'], location)
        self.assertEquals(new_image['location_data'][0]['url'], location)
        self.assertEquals(new_image['location_data'][0]['metadata'], loc_meta)

    def test_add_image_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = {
            'id': UUID2,
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'size': 19,
            'location': "file:///tmp/glance-tests/2",
        }

        self.assertRaises(exception.Duplicate,
                          self.client.add_image,
                          fixture)

    def test_add_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'status': 'bad status',
            'size': 19,
            'location': "file:///tmp/glance-tests/2",
        }

        self.assertRaises(exception.Invalid,
                          self.client.add_image,
                          fixture)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk'}

        self.assertTrue(self.client.update_image(UUID2, fixture))

        # Test all other attributes set
        data = self.client.get_image(UUID2)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_update_image_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = {
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'status': 'bad status',
        }

        self.assertRaises(exception.NotFound,
                          self.client.update_image,
                          _gen_uuid(),
                          fixture)

    def test_delete_image(self):
        """Tests that image metadata is deleted properly"""
        # Grab the original number of images
        orig_num_images = len(self.client.get_images())

        # Delete image #2
        image = self.FIXTURES[1]
        deleted_image = self.client.delete_image(image['id'])
        self.assertTrue(deleted_image)
        self.assertEquals(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

        # Verify one less image
        new_num_images = len(self.client.get_images())

        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests cannot delete non-existing image"""
        self.assertRaises(exception.NotFound,
                          self.client.delete_image,
                          _gen_uuid())

    def test_get_image_members(self):
        """Tests getting image members"""
        memb_list = self.client.get_image_members(UUID2)
        num_members = len(memb_list)
        self.assertEquals(num_members, 0)

    def test_get_image_members_not_existing(self):
        """Tests getting non-existent image members"""
        self.assertRaises(exception.NotFound,
                          self.client.get_image_members,
                          _gen_uuid())

    def test_get_member_images(self):
        """Tests getting member images"""
        memb_list = self.client.get_member_images('pattieblack')
        num_members = len(memb_list)
        self.assertEquals(num_members, 0)

    def test_add_replace_members(self):
        """Tests replacing image members"""
        self.assertTrue(self.client.add_member(UUID2, 'pattieblack'))
        self.assertTrue(self.client.replace_members(UUID2,
                                                    dict(member_id='pattie'
                                                                   'black2')))

    def test_add_delete_member(self):
        """Tests deleting image members"""
        self.client.add_member(UUID2, 'pattieblack')
        self.assertTrue(self.client.delete_member(UUID2, 'pattieblack'))


class TestBaseClient(testtools.TestCase):

    """
    Test proper actions made for both valid and invalid requests
    against a Registry service
    """
    def test_connect_kwargs_default_values(self):
        actual = test_client.BaseClient('127.0.0.1').get_connect_kwargs()
        self.assertEqual({'timeout': None}, actual)

    def test_connect_kwargs(self):
        base_client = test_client.BaseClient(
            host='127.0.0.1', port=80, timeout=1, use_ssl=True)
        actual = base_client.get_connect_kwargs()
        expected = {'insecure': False,
                    'key_file': None,
                    'ca_file': '/etc/ssl/certs/ca-certificates.crt',
                    'cert_file': None,
                    'timeout': 1}
        self.assertEqual(expected['insecure'], actual['insecure'])
        self.assertEqual(expected['key_file'], actual['key_file'])
        self.assertEqual(expected['cert_file'], actual['cert_file'])
        self.assertEqual(expected['timeout'], actual['timeout'])


class TestRegistryV1ClientApi(base.IsolatedUnitTest):

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryV1ClientApi, self).setUp()
        self.mox = mox.Mox()
        self.context = context.RequestContext()
        reload(rapi)

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryV1ClientApi, self).tearDown()
        self.mox.UnsetStubs()

    def test_get_registry_client(self):
        actual_client = rapi.get_registry_client(self.context)
        self.assertEqual(actual_client.identity_headers, None)

    def test_get_registry_client_with_identity_headers(self):
        self.config(send_identity_headers=True)
        expected_identity_headers = {
            'X-User-Id': self.context.user,
            'X-Tenant-Id': self.context.tenant,
            'X-Roles': ','.join(self.context.roles),
            'X-Identity-Status': 'Confirmed',
            'X-Service-Catalog': 'null',
        }
        actual_client = rapi.get_registry_client(self.context)
        self.assertEqual(actual_client.identity_headers,
                         expected_identity_headers)

    def test_configure_registry_client_not_using_use_user_token(self):
        self.config(use_user_token=False)
        self.mox.StubOutWithMock(rapi, 'configure_registry_admin_creds')
        rapi.configure_registry_admin_creds()

        self.mox.ReplayAll()

        rapi.configure_registry_client()
        self.mox.VerifyAll()

    def test_configure_registry_admin_creds(self):
        expected = {
            'user': 'user',
            'password': 'password',
            'username': 'user',
            'tenant': 'tenant',
            'auth_url': None,
            'strategy': 'configured_strategy',
            'region': 'region',
        }
        self.config(admin_user=expected['user'])
        self.config(admin_password=expected['password'])
        self.config(admin_tenant_name=expected['tenant'])
        self.config(auth_strategy=expected['strategy'])
        self.config(auth_region=expected['region'])
        self.stubs.Set(os, 'getenv', lambda x: None)

        self.assertEquals(rapi._CLIENT_CREDS, None)
        rapi.configure_registry_admin_creds()
        self.assertEquals(rapi._CLIENT_CREDS, expected)

    def test_configure_registry_admin_creds_with_auth_url(self):
        expected = {
            'user': 'user',
            'password': 'password',
            'username': 'user',
            'tenant': 'tenant',
            'auth_url': 'auth_url',
            'strategy': 'keystone',
            'region': 'region',
        }
        self.config(admin_user=expected['user'])
        self.config(admin_password=expected['password'])
        self.config(admin_tenant_name=expected['tenant'])
        self.config(auth_url=expected['auth_url'])
        self.config(auth_strategy='test_strategy')
        self.config(auth_region=expected['region'])

        self.assertEquals(rapi._CLIENT_CREDS, None)
        rapi.configure_registry_admin_creds()
        self.assertEquals(rapi._CLIENT_CREDS, expected)


class FakeResponse():
    status = 202

    def getheader(*args, **kwargs):
        return None


class TestRegistryV1ClientRequests(base.IsolatedUnitTest):

    def setUp(self):
        super(TestRegistryV1ClientRequests, self).setUp()
        self.mox = mox.Mox()

    def tearDown(self):
        super(TestRegistryV1ClientRequests, self).tearDown()
        self.mox.UnsetStubs()

    def test_do_request_with_identity_headers(self):
        identity_headers = {'foo': 'bar'}
        self.client = rclient.RegistryClient("0.0.0.0",
                                             identity_headers=identity_headers)

        self.mox.StubOutWithMock(test_client.BaseClient, 'do_request')
        test_client.BaseClient.do_request("GET", "/images",
                                          headers=identity_headers).AndReturn(
                                              FakeResponse())
        self.mox.ReplayAll()

        self.client.do_request("GET", "/images")

        self.mox.VerifyAll()

    def test_do_request(self):
        self.client = rclient.RegistryClient("0.0.0.0")

        self.mox.StubOutWithMock(test_client.BaseClient, 'do_request')
        test_client.BaseClient.do_request("GET", "/images",
                                          headers={}).AndReturn(FakeResponse())
        self.mox.ReplayAll()

        self.client.do_request("GET", "/images")

        self.mox.VerifyAll()
