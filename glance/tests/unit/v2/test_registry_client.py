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
import os
import uuid

from mock import patch
from oslo_utils import timeutils

from glance.common import config
from glance.common import exception
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance import i18n
from glance.registry.api import v2 as rserver
import glance.registry.client.v2.api as rapi
from glance.registry.client.v2.api import client as rclient
from glance.tests.unit import base
from glance.tests import utils as test_utils

_ = i18n._

_gen_uuid = lambda: str(uuid.uuid4())

UUID1 = str(uuid.uuid4())
UUID2 = str(uuid.uuid4())

# NOTE(bcwaldon): needed to init config_dir cli opt
config.parse_args(args=[])


class TestRegistryV2Client(base.IsolatedUnitTest,
                           test_utils.RegistryAPIMixIn):
    """Test proper actions made against a registry service.

    Test for both valid and invalid requests.
    """

    # Registry server to user
    # in the stub.
    registry = rserver

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryV2Client, self).setUp()
        db_api.get_engine()
        self.context = context.RequestContext(is_admin=True)
        uuid1_time = timeutils.utcnow()
        uuid2_time = uuid1_time + datetime.timedelta(seconds=5)
        self.FIXTURES = [
            self.get_extra_fixture(
                id=UUID1, name='fake image #1', is_public=False,
                disk_format='ami', container_format='ami', size=13,
                virtual_size=26, properties={'type': 'kernel'},
                location="swift://user:passwd@acct/container/obj.tar.0",
                created_at=uuid1_time),
            self.get_extra_fixture(id=UUID2, name='fake image #2',
                                   properties={}, size=19, virtual_size=38,
                                   location="file:///tmp/glance-tests/2",
                                   created_at=uuid2_time)]
        self.destroy_fixtures()
        self.create_fixtures()
        self.client = rclient.RegistryClient("0.0.0.0")

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryV2Client, self).tearDown()
        self.destroy_fixtures()

    def test_image_get_index(self):
        """Test correct set of public image returned"""
        images = self.client.image_get_all()
        self.assertEqual(2, len(images))

    def test_create_image_with_null_min_disk_min_ram(self):
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf', min_disk=None,
                                         min_ram=None)
        db_api.image_create(self.context, extra_fixture)
        image = self.client.image_get(image_id=UUID3)
        self.assertEqual(0, image["min_ram"])
        self.assertEqual(0, image["min_disk"])

    def test_get_index_sort_name_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by name in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf')

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['name'],
                                           sort_dir=['asc'])

        self.assertEqualImages(images, (UUID3, UUID1, UUID2, UUID4),
                               unjsonify=False)

    def test_get_index_sort_status_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by status in descending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         status='queued')

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz',
                                         created_at=uuid4_time)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['status'],
                                           sort_dir=['desc'])

        self.assertEqualImages(images, (UUID3, UUID4, UUID2, UUID1),
                               unjsonify=False)

    def test_get_index_sort_disk_format_asc(self):
        """Tests that the registry API returns list of public images.

        Must besorted alphabetically by disk_format in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz',
                                         disk_format='vdi')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['disk_format'],
                                           sort_dir=['asc'])

        self.assertEqualImages(images, (UUID1, UUID3, UUID4, UUID2),
                               unjsonify=False)

    def test_get_index_sort_container_format_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by container_format in descending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz',
                                         disk_format='iso',
                                         container_format='bare')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['container_format'],
                                           sort_dir=['desc'])

        self.assertEqualImages(images, (UUID2, UUID4, UUID3, UUID1),
                               unjsonify=False)

    def test_get_index_sort_size_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by size in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         disk_format='ami',
                                         container_format='ami',
                                         size=100, virtual_size=200)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='asdf',
                                         disk_format='iso',
                                         container_format='bare',
                                         size=2, virtual_size=4)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['size'], sort_dir=['asc'])

        self.assertEqualImages(images, (UUID4, UUID1, UUID2, UUID3),
                               unjsonify=False)

    def test_get_index_sort_created_at_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by created_at in ascending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, created_at=uuid3_time)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=uuid4_time)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['created_at'],
                                           sort_dir=['asc'])

        self.assertEqualImages(images, (UUID1, UUID2, UUID4, UUID3),
                               unjsonify=False)

    def test_get_index_sort_updated_at_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by updated_at in descending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, created_at=None,
                                         updated_at=uuid3_time)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=None,
                                         updated_at=uuid4_time)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['updated_at'],
                                           sort_dir=['desc'])

        self.assertEqualImages(images, (UUID3, UUID4, UUID2, UUID1),
                               unjsonify=False)

    def test_get_image_details_sort_multiple_keys(self):
        """
        Tests that a detailed call returns list of
        public images sorted by name-size and
        size-name in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name=u'xyz',
                                         size=20)

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID5, name=u'asdf',
                                         size=20)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['name', 'size'],
                                           sort_dir=['asc'])

        self.assertEqualImages(images, (UUID3, UUID5, UUID1, UUID2, UUID4),
                               unjsonify=False)

        images = self.client.image_get_all(sort_key=['size', 'name'],
                                           sort_dir=['asc'])

        self.assertEqualImages(images, (UUID1, UUID3, UUID2, UUID5, UUID4),
                               unjsonify=False)

    def test_get_image_details_sort_multiple_dirs(self):
        """
        Tests that a detailed call returns list of
        public images sorted by name-size and
        size-name in ascending and descending orders.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf',
                                         size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz',
                                         size=20)

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID5, name='asdf',
                                         size=20)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(sort_key=['name', 'size'],
                                           sort_dir=['asc', 'desc'])

        self.assertEqualImages(images, (UUID5, UUID3, UUID1, UUID2, UUID4),
                               unjsonify=False)

        images = self.client.image_get_all(sort_key=['name', 'size'],
                                           sort_dir=['desc', 'asc'])

        self.assertEqualImages(images, (UUID4, UUID2, UUID1, UUID3, UUID5),
                               unjsonify=False)

        images = self.client.image_get_all(sort_key=['size', 'name'],
                                           sort_dir=['asc', 'desc'])

        self.assertEqualImages(images, (UUID1, UUID2, UUID3, UUID4, UUID5),
                               unjsonify=False)

        images = self.client.image_get_all(sort_key=['size', 'name'],
                                           sort_dir=['desc', 'asc'])

        self.assertEqualImages(images, (UUID5, UUID4, UUID3, UUID2, UUID1),
                               unjsonify=False)

    def test_image_get_index_marker(self):
        """Test correct set of images returned with marker param."""
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='new name! #123',
                                         status='saving',
                                         created_at=uuid3_time)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='new name! #125',
                                         status='saving',
                                         created_at=uuid4_time)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(marker=UUID3)

        self.assertEqualImages(images, (UUID4, UUID2, UUID1), unjsonify=False)

    def test_image_get_index_limit(self):
        """Test correct number of images returned with limit param."""
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123',
                                         status='saving')

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #125',
                                         status='saving')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(limit=2)
        self.assertEqual(2, len(images))

    def test_image_get_index_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='new name! #123',
                                         status='saving',
                                         created_at=uuid3_time)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='new name! #125',
                                         status='saving',
                                         created_at=uuid4_time)

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(marker=UUID4, limit=1)

        self.assertEqualImages(images, (UUID2,), unjsonify=False)

    def test_image_get_index_limit_None(self):
        """Test correct set of images returned with limit param == None."""
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123',
                                         status='saving')

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #125',
                                         status='saving')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(limit=None)
        self.assertEqual(4, len(images))

    def test_image_get_index_by_name(self):
        """Test correct set of public, name-filtered image returned.

        This is just a sanity check, we test the details call more in-depth.
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123')

        db_api.image_create(self.context, extra_fixture)

        images = self.client.image_get_all(filters={'name': 'new name! #123'})
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_image_get_is_public_v2(self):
        """Tests that a detailed call can be filtered by a property"""
        extra_fixture = self.get_fixture(id=_gen_uuid(), status='saving',
                                         properties={'is_public': 'avalue'})

        context = copy.copy(self.context)
        db_api.image_create(context, extra_fixture)

        filters = {'is_public': 'avalue'}
        images = self.client.image_get_all(filters=filters)
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual('avalue', image['properties'][0]['value'])

    def test_image_get(self):
        """Tests that the detailed info about an image returned"""
        fixture = self.get_fixture(id=UUID1, name='fake image #1',
                                   is_public=False, size=13, virtual_size=26,
                                   disk_format='ami', container_format='ami')

        data = self.client.image_get(image_id=UUID1)

        for k, v in fixture.items():
            el = data[k]
            self.assertEqual(v, data[k],
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
        fixture = self.get_fixture()

        new_image = self.client.image_create(values=fixture)

        # Test all other attributes set
        data = self.client.image_get(image_id=new_image['id'])

        for k, v in fixture.items():
            self.assertEqual(v, data[k])

        # Test status was updated properly
        self.assertIn('status', data)
        self.assertEqual('active', data['status'])

    def test_image_create_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = self.get_fixture(location="file:///tmp/glance-tests/2",
                                   properties={'distro': 'Ubuntu 10.04 LTS'})

        new_image = self.client.image_create(values=fixture)

        self.assertIn('properties', new_image)
        self.assertEqual(new_image['properties'][0]['value'],
                         fixture['properties']['distro'])

        del fixture['location']
        del fixture['properties']

        for k, v in fixture.items():
            self.assertEqual(v, new_image[k])

        # Test status was updated properly
        self.assertIn('status', new_image.keys())
        self.assertEqual('active', new_image['status'])

    def test_image_create_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = self.get_fixture(id=UUID2,
                                   location="file:///tmp/glance-tests/2")

        self.assertRaises(exception.Duplicate,
                          self.client.image_create,
                          values=fixture)

    def test_image_create_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = self.get_fixture(status='bad status',
                                   location="file:///tmp/glance-tests/2")

        self.assertRaises(exception.Invalid,
                          self.client.image_create,
                          values=fixture)

    def test_image_update(self):
        """Tests that the registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk',
                   'status': 'saving'}

        self.assertTrue(self.client.image_update(image_id=UUID2,
                                                 values=fixture))

        # Test all other attributes set
        data = self.client.image_get(image_id=UUID2)

        for k, v in fixture.items():
            self.assertEqual(v, data[k])

    def test_image_update_conflict(self):
        """Tests that the registry API updates the image"""
        next_state = 'saving'
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk',
                   'status': next_state}

        image = self.client.image_get(image_id=UUID2)
        current = image['status']
        self.assertEqual('active', current)

        # image is in 'active' state so this should cause a failure.
        from_state = 'saving'

        self.assertRaises(exception.Conflict, self.client.image_update,
                          image_id=UUID2, values=fixture,
                          from_state=from_state)

        try:
            self.client.image_update(image_id=UUID2, values=fixture,
                                     from_state=from_state)
        except exception.Conflict as exc:
            msg = (_('cannot transition from %(current)s to '
                     '%(next)s in update (wanted '
                     'from_state=%(from)s)') %
                   {'current': current, 'next': next_state,
                    'from': from_state})
            self.assertEqual(str(exc), msg)

    def test_image_update_with_invalid_min_disk(self):
        """Tests that the registry API updates the image"""
        next_state = 'saving'
        fixture = {'name': 'fake image',
                   'disk_format': 'vmdk',
                   'min_disk': str(2 ** 31 + 1),
                   'status': next_state}

        image = self.client.image_get(image_id=UUID2)
        current = image['status']
        self.assertEqual('active', current)

        # image is in 'active' state so this should cause a failure.
        from_state = 'saving'

        self.assertRaises(exception.Invalid, self.client.image_update,
                          image_id=UUID2, values=fixture,
                          from_state=from_state)

    def test_image_update_with_invalid_min_ram(self):
        """Tests that the registry API updates the image"""
        next_state = 'saving'
        fixture = {'name': 'fake image',
                   'disk_format': 'vmdk',
                   'min_ram': str(2 ** 31 + 1),
                   'status': next_state}

        image = self.client.image_get(image_id=UUID2)
        current = image['status']
        self.assertEqual('active', current)

        # image is in 'active' state so this should cause a failure.
        from_state = 'saving'

        self.assertRaises(exception.Invalid, self.client.image_update,
                          image_id=UUID2, values=fixture,
                          from_state=from_state)

    def _test_image_update_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = self.get_fixture(status='bad status')

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
        self.assertEqual(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

        # Verify one less image
        filters = {'deleted': False}
        new_num_images = len(self.client.image_get_all(filters=filters))

        self.assertEqual(new_num_images, orig_num_images - 1)

    def test_image_destroy_not_existing(self):
        """Tests cannot delete non-existing image"""
        self.assertRaises(exception.NotFound,
                          self.client.image_destroy,
                          image_id=_gen_uuid())

    def test_image_get_members(self):
        """Tests getting image members"""
        memb_list = self.client.image_member_find(image_id=UUID2)
        num_members = len(memb_list)
        self.assertEqual(0, num_members)

    def test_image_get_members_not_existing(self):
        """Tests getting non-existent image members"""
        self.assertRaises(exception.NotFound,
                          self.client.image_get_members,
                          image_id=_gen_uuid())

    def test_image_member_find(self):
        """Tests getting member images"""
        memb_list = self.client.image_member_find(member='pattieblack')
        num_members = len(memb_list)
        self.assertEqual(0, num_members)

    def test_image_member_find_include_deleted(self):
        """Tests getting member images include the delted member"""
        values = dict(image_id=UUID2, member='pattieblack')
        # create a member
        member = self.client.image_member_create(values=values)
        memb_list = self.client.image_member_find(member='pattieblack')
        memb_list2 = self.client.image_member_find(member='pattieblack',
                                                   include_deleted=True)
        self.assertEqual(1, len(memb_list))
        self.assertEqual(1, len(memb_list2))
        # delete the member
        self.client.image_member_delete(memb_id=member['id'])
        memb_list = self.client.image_member_find(member='pattieblack')
        memb_list2 = self.client.image_member_find(member='pattieblack',
                                                   include_deleted=True)
        self.assertEqual(0, len(memb_list))
        self.assertEqual(1, len(memb_list2))
        # create it again
        member = self.client.image_member_create(values=values)
        memb_list = self.client.image_member_find(member='pattieblack')
        memb_list2 = self.client.image_member_find(member='pattieblack',
                                                   include_deleted=True)
        self.assertEqual(1, len(memb_list))
        self.assertEqual(2, len(memb_list2))

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
        self.assertEqual(0, len(memb_list))


class TestRegistryV2ClientApi(base.IsolatedUnitTest):
    """Test proper actions made against a registry service.

    Test for both valid and invalid requests.
    """

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryV2ClientApi, self).setUp()
        reload(rapi)

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryV2ClientApi, self).tearDown()

    def test_configure_registry_client_not_using_use_user_token(self):
        self.config(use_user_token=False)
        with patch.object(rapi,
                          'configure_registry_admin_creds') as mock_rapi:
            rapi.configure_registry_client()
            mock_rapi.assert_called_once_with()

    def _get_fake_config_creds(self, auth_url='auth_url', strategy='keystone'):
        return {
            'user': 'user',
            'password': 'password',
            'username': 'user',
            'tenant': 'tenant',
            'auth_url': auth_url,
            'strategy': strategy,
            'region': 'region'
        }

    def test_configure_registry_admin_creds(self):
        expected = self._get_fake_config_creds(auth_url=None,
                                               strategy='configured_strategy')
        self.config(admin_user=expected['user'])
        self.config(admin_password=expected['password'])
        self.config(admin_tenant_name=expected['tenant'])
        self.config(auth_strategy=expected['strategy'])
        self.config(auth_region=expected['region'])
        self.stubs.Set(os, 'getenv', lambda x: None)

        self.assertIsNone(rapi._CLIENT_CREDS)
        rapi.configure_registry_admin_creds()
        self.assertEqual(expected, rapi._CLIENT_CREDS)

    def test_configure_registry_admin_creds_with_auth_url(self):
        expected = self._get_fake_config_creds()
        self.config(admin_user=expected['user'])
        self.config(admin_password=expected['password'])
        self.config(admin_tenant_name=expected['tenant'])
        self.config(auth_url=expected['auth_url'])
        self.config(auth_strategy='test_strategy')
        self.config(auth_region=expected['region'])

        self.assertIsNone(rapi._CLIENT_CREDS)
        rapi.configure_registry_admin_creds()
        self.assertEqual(expected, rapi._CLIENT_CREDS)
