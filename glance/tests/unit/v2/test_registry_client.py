# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Red Hat, Inc.
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
Tests for Glance Registry's client.

This tests are temporary and will be removed once
the registry's driver tests will be added.
"""

import copy
import datetime

from glance.common import config
from glance.common import exception
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
from glance.registry.client.v2.api import client as rclient
from glance.registry.api import v2 as rserver
from glance.tests.unit import base


_gen_uuid = uuidutils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()

#NOTE(bcwaldon): needed to init config_dir cli opt
config.parse_args(args=[])


class TestRegistryV2Client(base.IsolatedUnitTest):
    """
    Test proper actions made for both valid and invalid requests
    against a Registry service
    """

    # Registry server to user
    # in the stub.
    registry = rserver

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryV2Client, self).setUp()
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
        super(TestRegistryV2Client, self).tearDown()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_image_get_index(self):
        """Test correct set of public image returned"""
        images = self.client.image_get_all()
        self.assertEquals(len(images), 2)

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
        image = self.client.image_get(image_id=UUID3)
        self.assertEqual(0, image["min_ram"])
        self.assertEqual(0, image["min_disk"])

    def test_get_index_sort_name_asc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='name', sort_dir='asc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID1)
        self.assertEquals(images[2]['id'], UUID2)
        self.assertEquals(images[3]['id'], UUID4)

    def test_get_index_sort_status_desc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='status', sort_dir='desc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)
        self.assertEquals(images[3]['id'], UUID1)

    def test_get_index_sort_disk_format_asc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='disk_format',
                                           sort_dir='asc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID1)
        self.assertEquals(images[1]['id'], UUID3)
        self.assertEquals(images[2]['id'], UUID4)
        self.assertEquals(images[3]['id'], UUID2)

    def test_get_index_sort_container_format_desc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='container_format',
                                           sort_dir='desc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID2)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID3)
        self.assertEquals(images[3]['id'], UUID1)

    def test_get_index_sort_size_asc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='size', sort_dir='asc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID4)
        self.assertEquals(images[1]['id'], UUID1)
        self.assertEquals(images[2]['id'], UUID2)
        self.assertEquals(images[3]['id'], UUID3)

    def test_get_index_sort_created_at_asc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='created_at',
                                           sort_dir='asc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID1)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID4)
        self.assertEquals(images[3]['id'], UUID3)

    def test_get_index_sort_updated_at_desc(self):
        """
        Tests that the registry API returns list of
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

        images = self.client.image_get_all(sort_key='updated_at',
                                           sort_dir='desc')

        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)
        self.assertEquals(images[3]['id'], UUID1)

    def test_image_get_index_marker(self):
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

        images = self.client.image_get_all(marker=UUID4)

        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID1)

    def test_image_get_index_limit(self):
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

        images = self.client.image_get_all(limit=2)
        self.assertEquals(len(images), 2)

    def test_image_get_index_marker_limit(self):
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

        images = self.client.image_get_all(marker=UUID3, limit=1)

        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], UUID2)

    def test_image_get_index_limit_None(self):
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

        images = self.client.image_get_all(limit=None)
        self.assertEquals(len(images), 4)

    def test_image_get_index_by_name(self):
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

        images = self.client.image_get_all(filters={'name': 'new name! #123'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_image_get_is_public_v2(self):
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

        filters = {'is_public': 'avalue'}
        images = self.client.image_get_all(filters=filters)
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('avalue', image['properties'][0]['value'])

    def test_image_get(self):
        """Tests that the detailed info about an image returned"""
        fixture = {'id': UUID1,
                   'name': 'fake image #1',
                   'is_public': False,
                   'disk_format': 'ami',
                   'container_format': 'ami',
                   'status': 'active',
                   'size': 13}

        data = self.client.image_get(image_id=UUID1)

        for k, v in fixture.items():
            el = data[k]
            self.assertEquals(v, data[k],
                              "Failed v != data[k] where v = %(v)s and "
                              "k = %(k)s and data[k] = %(el)s" %
                              dict(v=v, k=k, el=el))

    def test_image_get_non_existing(self):
        """Tests that NotFound is raised when getting a non-existing image"""
        self.assertRaises(exception.NotFound,
                          self.client.image_get,
                          image_id=_gen_uuid())

    def test_image_create_basic(self):
        """Tests that we can add image metadata and returns the new id"""
        fixture = {
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'size': 19,
            'status': 'active',
        }

        new_image = self.client.image_create(values=fixture)

        # Test all other attributes set
        data = self.client.image_get(image_id=new_image['id'])

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('active', data['status'])

    def test_image_create_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'size': 19,
                   'status': 'active',
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}

        new_image = self.client.image_create(values=fixture)

        self.assertIn('properties', new_image)
        self.assertEquals(new_image['properties'][0]['value'],
                          fixture['properties']['distro'])

        del fixture['location']
        del fixture['properties']

        for k, v in fixture.items():
            self.assertEquals(v, new_image[k])

        # Test status was updated properly
        self.assertTrue('status' in new_image.keys())
        self.assertEquals('active', new_image['status'])

    def test_image_create_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = {
            'id': UUID2,
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'size': 19,
            'status': 'active',
            'location': "file:///tmp/glance-tests/2",
        }

        self.assertRaises(exception.Duplicate,
                          self.client.image_create,
                          values=fixture)

    def test_image_create_with_bad_status(self):
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
                          self.client.image_create,
                          values=fixture)

    def test_image_update(self):
        """Tests that the registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk'}

        self.assertTrue(self.client.image_update(image_id=UUID2,
                                                 values=fixture))

        # Test all other attributes set
        data = self.client.image_get(image_id=UUID2)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_image_update_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = {
            'name': 'fake public image',
            'is_public': True,
            'disk_format': 'vmdk',
            'container_format': 'ovf',
            'status': 'bad status',
        }

        self.assertRaises(exception.NotFound,
                          self.client.image_update,
                          image_id=_gen_uuid(),
                          values=fixture)

    def test_image_destroy(self):
        """Tests that image metadata is deleted properly"""
        # Grab the original number of images
        orig_num_images = len(self.client.image_get_all())

        # Delete image #2
        image = self.FIXTURES[1]
        deleted_image = self.client.image_destroy(image_id=image['id'])
        self.assertTrue(deleted_image)
        self.assertEquals(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

        # Verify one less image
        filters = {'deleted': False}
        new_num_images = len(self.client.image_get_all(filters=filters))

        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_image_destroy_not_existing(self):
        """Tests cannot delete non-existing image"""
        self.assertRaises(exception.NotFound,
                          self.client.image_destroy,
                          image_id=_gen_uuid())

    def test_image_get_members(self):
        """Tests getting image members"""
        memb_list = self.client.image_member_find(image_id=UUID2)
        num_members = len(memb_list)
        self.assertEquals(num_members, 0)

    def test_image_get_members_not_existing(self):
        """Tests getting non-existent image members"""
        self.assertRaises(exception.NotFound,
                          self.client.image_get_members,
                          image_id=_gen_uuid())

    def test_image_member_find(self):
        """Tests getting member images"""
        memb_list = self.client.image_member_find(member='pattieblack')
        num_members = len(memb_list)
        self.assertEquals(num_members, 0)

    def test_add_update_members(self):
        """Tests updating image members"""
        values = dict(image_id=UUID2, member='pattieblack')
        member = self.client.image_member_create(values=values)
        self.assertTrue(member)

        values['member'] = 'pattieblack2'
        self.assertTrue(self.client.image_member_update(memb_id=member['id'],
                                                        values=values))

    def test_add_delete_member(self):
        """Tests deleting image members"""
        values = dict(image_id=UUID2, member='pattieblack')
        member = self.client.image_member_create(values=values)

        self.client.image_member_delete(memb_id=member['id'])
        memb_list = self.client.image_member_find(member='pattieblack')
        self.assertEquals(len(memb_list), 0)
