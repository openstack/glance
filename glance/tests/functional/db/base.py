# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack, LLC
# Copyright 2012 Justin Santa Barbara
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
import uuid

from glance.common import exception
from glance import context
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
import glance.tests.functional.db as db_tests
from glance.tests.unit import base


# The default sort order of results is whatever sort key is specified,
# plus created_at and id for ties.  When we're not specifying a sort_key,
# we get the default (created_at). Some tests below expect the fixtures to be
# returned in array-order, so if if the created_at timestamps are the same,
# these tests rely on the UUID* values being in order
UUID1, UUID2, UUID3 = sorted([uuidutils.generate_uuid() for x in range(3)])


def build_image_fixture(**kwargs):
    default_datetime = timeutils.utcnow()
    image = {
        'id': uuidutils.generate_uuid(),
        'name': 'fake image #2',
        'status': 'active',
        'disk_format': 'vhd',
        'container_format': 'ovf',
        'is_public': True,
        'created_at': default_datetime,
        'updated_at': default_datetime,
        'deleted_at': None,
        'deleted': False,
        'checksum': None,
        'min_disk': 5,
        'min_ram': 256,
        'size': 19,
        'locations': ["file:///tmp/glance-tests/2"],
        'properties': {},
    }
    image.update(kwargs)
    return image


class TestDriver(base.IsolatedUnitTest):

    def setUp(self):
        super(TestDriver, self).setUp()
        self.adm_context = context.RequestContext(is_admin=True)
        self.context = context.RequestContext(is_admin=False)
        self.db_api = db_tests.get_db(self.config)
        db_tests.reset_db(self.db_api)
        self.fixtures = self.build_image_fixtures()
        self.create_images(self.fixtures)
        self.addCleanup(timeutils.clear_time_override)

    def build_image_fixtures(self):
        dt1 = timeutils.utcnow()
        dt2 = dt1 + datetime.timedelta(microseconds=5)
        fixtures = [
            {
                'id': UUID1,
                'created_at': dt1,
                'updated_at': dt1,
                'properties': {'foo': 'bar'},
                'size': 13,
            },
            {
                'id': UUID2,
                'created_at': dt1,
                'updated_at': dt2,
                'size': 17,
            },
            {
                'id': UUID3,
                'created_at': dt2,
                'updated_at': dt2,
            },
        ]
        return [build_image_fixture(**fixture) for fixture in fixtures]

    def create_images(self, images):
        for fixture in images:
            self.db_api.image_create(self.adm_context, fixture)


class DriverTests(object):

    def test_image_create_requires_status(self):
        fixture = {'name': 'mark', 'size': 12}
        self.assertRaises(exception.Invalid,
                          self.db_api.image_create, self.context, fixture)
        fixture = {'name': 'mark', 'size': 12, 'status': 'queued'}
        self.db_api.image_create(self.context, fixture)

    def test_image_create_defaults(self):
        timeutils.set_time_override()
        image = self.db_api.image_create(self.context, {'status': 'queued'})
        create_time = timeutils.utcnow()

        self.assertEqual(None, image['name'])
        self.assertEqual(None, image['container_format'])
        self.assertEqual(0, image['min_ram'])
        self.assertEqual(0, image['min_disk'])
        self.assertEqual(None, image['owner'])
        self.assertEqual(False, image['is_public'])
        self.assertEqual(None, image['size'])
        self.assertEqual(None, image['checksum'])
        self.assertEqual(None, image['disk_format'])
        self.assertEqual([], image['locations'])
        self.assertEqual(False, image['protected'])
        self.assertEqual(False, image['deleted'])
        self.assertEqual(None, image['deleted_at'])
        self.assertEqual([], image['properties'])
        self.assertEqual(image['created_at'], create_time)
        self.assertEqual(image['updated_at'], create_time)

        # Image IDs aren't predictable, but they should be populated
        self.assertTrue(uuid.UUID(image['id']))

        #NOTE(bcwaldon): the tags attribute should not be returned as a part
        # of a core image entity
        self.assertFalse('tags' in image)

    def test_image_create_duplicate_id(self):
        self.assertRaises(exception.Duplicate,
                          self.db_api.image_create,
                          self.context, {'id': UUID1, 'status': 'queued'})

    def test_image_create_with_locations(self):
        fixture = {'status': 'queued', 'locations': ['a', 'b']}
        image = self.db_api.image_create(self.context, fixture)
        self.assertEqual(['a', 'b'], image['locations'])

    def test_image_create_properties(self):
        fixture = {'status': 'queued', 'properties': {'ping': 'pong'}}
        image = self.db_api.image_create(self.context, fixture)
        expected = [{'name': 'ping', 'value': 'pong'}]
        actual = [{'name': p['name'], 'value': p['value']}
                  for p in image['properties']]
        self.assertEqual(expected, actual)

    def test_image_create_unknown_attribtues(self):
        fixture = {'ping': 'pong'}
        self.assertRaises(exception.Invalid,
                          self.db_api.image_create, self.context, fixture)

    def test_image_update_core_attribute(self):
        fixture = {'status': 'queued'}
        image = self.db_api.image_update(self.adm_context, UUID3, fixture)
        self.assertEqual('queued', image['status'])
        self.assertNotEqual(image['created_at'], image['updated_at'])

    def test_image_update_with_locations(self):
        fixture = {'locations': ['a', 'b']}
        image = self.db_api.image_update(self.adm_context, UUID3, fixture)
        self.assertEqual(['a', 'b'], image['locations'])

    def test_image_update(self):
        fixture = {'status': 'queued', 'properties': {'ping': 'pong'}}
        image = self.db_api.image_update(self.adm_context, UUID3, fixture)
        expected = [{'name': 'ping', 'value': 'pong'}]
        actual = [{'name': p['name'], 'value': p['value']}
                  for p in image['properties']]
        self.assertEqual(expected, actual)
        self.assertEqual('queued', image['status'])
        self.assertNotEqual(image['created_at'], image['updated_at'])

    def test_image_update_properties(self):
        fixture = {'properties': {'ping': 'pong'}}
        image = self.db_api.image_update(self.adm_context, UUID1, fixture)
        expected = {'ping': 'pong', 'foo': 'bar'}
        actual = dict((p['name'], p['value']) for p in image['properties'])
        self.assertEqual(expected, actual)
        self.assertNotEqual(image['created_at'], image['updated_at'])

    def test_image_update_purge_properties(self):
        fixture = {'properties': {'ping': 'pong'}}
        image = self.db_api.image_update(self.adm_context, UUID1,
                                         fixture, purge_props=True)
        properties = dict((p['name'], p) for p in image['properties'])

        # New properties are set
        self.assertTrue('ping' in properties)
        self.assertEqual(properties['ping']['value'], 'pong')
        self.assertEqual(properties['ping']['deleted'], False)

        # Original properties still show up, but with deleted=True
        # TODO(markwash): db api should not return deleted properties
        self.assertTrue('foo' in properties)
        self.assertEqual(properties['foo']['value'], 'bar')
        self.assertEqual(properties['foo']['deleted'], True)

    def test_image_property_delete(self):
        fixture = {'name': 'ping', 'value': 'pong', 'image_id': UUID1}
        prop = self.db_api.image_property_create(self.context, fixture)
        timeutils.set_time_override()
        prop = self.db_api.image_property_delete(self.context, prop)
        self.assertEqual(prop['deleted_at'], timeutils.utcnow())
        self.assertTrue(prop['deleted'])

    def test_image_get(self):
        image = self.db_api.image_get(self.context, UUID1)
        self.assertEquals(image['id'], self.fixtures[0]['id'])

    def test_image_get_disallow_deleted(self):
        self.db_api.image_destroy(self.adm_context, UUID1)
        self.assertRaises(exception.NotFound, self.db_api.image_get,
                          self.context, UUID1)

    def test_image_get_allow_deleted(self):
        timeutils.set_time_override()
        self.db_api.image_destroy(self.adm_context, UUID1)
        image = self.db_api.image_get(self.adm_context, UUID1)
        self.assertEquals(image['id'], self.fixtures[0]['id'])
        self.assertEquals(image['deleted_at'], timeutils.utcnow())

    def test_image_get_force_allow_deleted(self):
        self.db_api.image_destroy(self.adm_context, UUID1)
        image = self.db_api.image_get(self.context, UUID1,
                                      force_show_deleted=True)
        self.assertEquals(image['id'], self.fixtures[0]['id'])

    def test_image_get_not_owned(self):
        TENANT1 = uuidutils.generate_uuid()
        TENANT2 = uuidutils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1)
        ctxt2 = context.RequestContext(is_admin=False, tenant=TENANT2)
        image = self.db_api.image_create(
                ctxt1, {'status': 'queued', 'owner': TENANT1})
        self.assertRaises(exception.Forbidden,
                          self.db_api.image_get, ctxt2, image['id'])

    def test_image_get_not_found(self):
        UUID = uuidutils.generate_uuid()
        self.assertRaises(exception.NotFound,
                          self.db_api.image_get, self.context, UUID)

    def test_image_get_all(self):
        images = self.db_api.image_get_all(self.context)
        self.assertEquals(3, len(images))

    def test_image_get_all_with_filter(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={
                                               'id': self.fixtures[0]['id'],
                                           })
        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], self.fixtures[0]['id'])

    def test_image_get_all_with_filter_user_defined_property(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={'foo': 'bar'})
        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], self.fixtures[0]['id'])

    def test_image_get_all_with_filter_user_deleted_property(self):
        fixture = {'name': 'poo', 'value': 'bear', 'image_id': UUID1}
        prop = self.db_api.image_property_create(self.context,
                                                 fixture)
        images = self.db_api.image_get_all(self.context,
                                           filters={
                                               'properties': {'poo': 'bear'},
                                           })
        self.assertEquals(len(images), 1)
        self.db_api.image_property_delete(self.context, prop)
        images = self.db_api.image_get_all(self.context,
                                           filters={
                                               'properties': {'poo': 'bear'},
                                           })
        self.assertEquals(len(images), 0)

    def test_image_get_all_with_filter_undefined_property(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={'poo': 'bear'})
        self.assertEquals(len(images), 0)

    def test_image_get_all_size_min_max(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={
                                               'size_min': 10,
                                               'size_max': 15,
                                           })
        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], self.fixtures[0]['id'])

    def test_image_get_all_size_min(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={'size_min': 15})
        self.assertEquals(len(images), 2)
        self.assertEquals(images[0]['id'], self.fixtures[2]['id'])
        self.assertEquals(images[1]['id'], self.fixtures[1]['id'])

    def test_image_get_all_size_range(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={'size_max': 15,
                                                    'size_min': 20})
        self.assertEquals(len(images), 0)

    def test_image_get_all_size_max(self):
        images = self.db_api.image_get_all(self.context,
                                           filters={'size_max': 15})
        self.assertEquals(len(images), 1)
        self.assertEquals(images[0]['id'], self.fixtures[0]['id'])

    def test_image_get_all_with_filter_min_range_bad_value(self):
        self.assertRaises(exception.InvalidFilterRangeValue,
                          self.db_api.image_get_all,
                          self.context, filters={'size_min': 'blah'})

    def test_image_get_all_with_filter_max_range_bad_value(self):
        self.assertRaises(exception.InvalidFilterRangeValue,
                          self.db_api.image_get_all,
                          self.context, filters={'size_max': 'blah'})

    def test_image_get_all_marker(self):
        images = self.db_api.image_get_all(self.context, marker=UUID3)
        self.assertEquals(2, len(images))

    def test_image_get_all_marker_deleted(self):
        """Cannot specify a deleted image as a marker."""
        self.db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': False}
        self.assertRaises(exception.NotFound, self.db_api.image_get_all,
                          self.context, marker=UUID1, filters=filters)

    def test_image_get_all_marker_deleted_showing_deleted_as_admin(self):
        """Specify a deleted image as a marker if showing deleted images."""
        self.db_api.image_destroy(self.adm_context, UUID3)
        images = self.db_api.image_get_all(self.adm_context, marker=UUID3)
        #NOTE(bcwaldon): an admin should see all images (deleted or not)
        self.assertEquals(2, len(images))

    def test_image_get_all_marker_deleted_showing_deleted(self):
        """Specify a deleted image as a marker if showing deleted images.

        A non-admin user has to explicitly ask for deleted
        images, and should only see deleted images in the results
        """
        self.db_api.image_destroy(self.adm_context, UUID3)
        self.db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': True}
        images = self.db_api.image_get_all(self.context, marker=UUID3,
                                           filters=filters)
        self.assertEquals(1, len(images))

    def test_image_get_all_limit(self):
        images = self.db_api.image_get_all(self.context, limit=2)
        self.assertEquals(2, len(images))

        # A limit of None should not equate to zero
        images = self.db_api.image_get_all(self.context, limit=None)
        self.assertEquals(3, len(images))

        # A limit of zero should actually mean zero
        images = self.db_api.image_get_all(self.context, limit=0)
        self.assertEquals(0, len(images))

    def test_image_get_all_owned(self):
        TENANT1 = uuidutils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1)
        UUIDX = uuidutils.generate_uuid()
        self.db_api.image_create(ctxt1, {'id': UUIDX,
                                         'status': 'queued',
                                         'owner': TENANT1})

        TENANT2 = uuidutils.generate_uuid()
        ctxt2 = context.RequestContext(is_admin=False, tenant=TENANT2)
        UUIDY = uuidutils.generate_uuid()
        self.db_api.image_create(ctxt2, {'id': UUIDY,
                                         'status': 'queued',
                                         'owner': TENANT2})

        images = self.db_api.image_get_all(ctxt1)
        image_ids = [image['id'] for image in images]
        expected = [UUIDX, UUID3, UUID2, UUID1]
        self.assertEqual(sorted(expected), sorted(image_ids))

    def test_image_paginate(self):
        """Paginate through a list of images using limit and marker"""
        extra_uuids = [uuidutils.generate_uuid() for i in range(2)]
        extra_images = [build_image_fixture(id=_id) for _id in extra_uuids]
        self.create_images(extra_images)

        # Reverse uuids to match default sort of created_at
        extra_uuids.reverse()

        page = self.db_api.image_get_all(self.context, limit=2)
        self.assertEquals(extra_uuids, [i['id'] for i in page])
        last = page[-1]['id']

        page = self.db_api.image_get_all(self.context, limit=2, marker=last)
        self.assertEquals([UUID3, UUID2], [i['id'] for i in page])

        page = self.db_api.image_get_all(self.context, limit=2, marker=UUID2)
        self.assertEquals([UUID1], [i['id'] for i in page])

    def test_image_get_all_invalid_sort_key(self):
        self.assertRaises(exception.InvalidSortKey, self.db_api.image_get_all,
                          self.context, sort_key='blah')

    def test_image_get_all_limit_marker(self):
        images = self.db_api.image_get_all(self.context, limit=2)
        self.assertEquals(2, len(images))

    def test_image_destroy(self):
        image = self.db_api.image_destroy(self.adm_context, UUID3)
        self.assertTrue(image['deleted'])
        self.assertTrue(image['deleted_at'])
        self.assertRaises(exception.NotFound, self.db_api.image_get,
                          self.context, UUID3)

    def test_image_get_multiple_members(self):
        TENANT1 = uuidutils.generate_uuid()
        TENANT2 = uuidutils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, user=TENANT2,
                                       owner_is_tenant=False)
        UUIDX = uuidutils.generate_uuid()
        #we need private image and context.owner should not match image owner
        self.db_api.image_create(ctxt1, {'id': UUIDX,
                                         'status': 'queued',
                                         'is_public': False,
                                         'owner': TENANT1})
        values = {'image_id': UUIDX, 'member': TENANT2, 'can_share': False}
        self.db_api.image_member_create(ctxt1, values)

        image = self.db_api.image_get(ctxt2, UUIDX)
        self.assertEquals(UUIDX, image['id'])

        # by default get_all displays only images with status 'accepted'
        images = self.db_api.image_get_all(ctxt2)
        self.assertEquals(3, len(images))

        # filter by rejected
        images = self.db_api.image_get_all(ctxt2, member_status='rejected')
        self.assertEquals(3, len(images))

        # filter by visibility
        images = self.db_api.image_get_all(ctxt2,
                                           filters={'visibility': 'shared'})
        self.assertEquals(0, len(images))

        # filter by visibility
        images = self.db_api.image_get_all(ctxt2, member_status='pending',
                                           filters={'visibility': 'shared'})
        self.assertEquals(1, len(images))

        # filter by visibility
        images = self.db_api.image_get_all(ctxt2, member_status='all',
                                           filters={'visibility': 'shared'})
        self.assertEquals(1, len(images))

        # filter by status pending
        images = self.db_api.image_get_all(ctxt2, member_status='pending')
        self.assertEquals(4, len(images))

        # filter by status all
        images = self.db_api.image_get_all(ctxt2, member_status='all')
        self.assertEquals(4, len(images))

    def test_is_image_visible(self):
        TENANT1 = uuidutils.generate_uuid()
        TENANT2 = uuidutils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, user=TENANT2,
                                       owner_is_tenant=False)
        UUIDX = uuidutils.generate_uuid()
        #we need private image and context.owner should not match image owner
        image = self.db_api.image_create(ctxt1, {'id': UUIDX,
                                                 'status': 'queued',
                                                 'is_public': False,
                                                 'owner': TENANT1})

        values = {'image_id': UUIDX, 'member': TENANT2, 'can_share': False}
        self.db_api.image_member_create(ctxt1, values)

        result = self.db_api.is_image_visible(ctxt2, image)
        self.assertTrue(result)

        # image should not be visible for a deleted memeber
        members = self.db_api.image_member_find(ctxt1, image_id=UUIDX)
        self.db_api.image_member_delete(ctxt1, members[0]['id'])

        result = self.db_api.is_image_visible(ctxt2, image)
        self.assertFalse(result)

    def test_image_tag_create(self):
        tag = self.db_api.image_tag_create(self.context, UUID1, 'snap')
        self.assertEqual('snap', tag)

    def test_image_tag_set_all(self):
        tags = self.db_api.image_tag_get_all(self.context, UUID1)
        self.assertEqual([], tags)

        self.db_api.image_tag_set_all(self.context, UUID1, ['ping', 'pong'])

        tags = self.db_api.image_tag_get_all(self.context, UUID1)
        #NOTE(bcwaldon): tag ordering should match exactly what was provided
        self.assertEqual(['ping', 'pong'], tags)

    def test_image_tag_get_all(self):
        self.db_api.image_tag_create(self.context, UUID1, 'snap')
        self.db_api.image_tag_create(self.context, UUID1, 'snarf')
        self.db_api.image_tag_create(self.context, UUID2, 'snarf')

        # Check the tags for the first image
        tags = self.db_api.image_tag_get_all(self.context, UUID1)
        expected = ['snap', 'snarf']
        self.assertEqual(expected, tags)

        # Check the tags for the second image
        tags = self.db_api.image_tag_get_all(self.context, UUID2)
        expected = ['snarf']
        self.assertEqual(expected, tags)

    def test_image_tag_get_all_no_tags(self):
        actual = self.db_api.image_tag_get_all(self.context, UUID1)
        self.assertEqual([], actual)

    def test_image_tag_delete(self):
        self.db_api.image_tag_create(self.context, UUID1, 'snap')
        self.db_api.image_tag_delete(self.context, UUID1, 'snap')
        self.assertRaises(exception.NotFound, self.db_api.image_tag_delete,
                          self.context, UUID1, 'snap')

    def test_image_member_create(self):
        timeutils.set_time_override()
        memberships = self.db_api.image_member_find(self.context)
        self.assertEqual([], memberships)

        create_time = timeutils.utcnow()
        TENANT1 = uuidutils.generate_uuid()
        self.db_api.image_member_create(self.context,
                                        {'member': TENANT1, 'image_id': UUID1})

        memberships = self.db_api.image_member_find(self.context)
        self.assertEqual(1, len(memberships))
        actual = memberships[0]
        self.assertEqual(actual['created_at'], create_time)
        self.assertEqual(actual['updated_at'], create_time)
        actual.pop('id')
        actual.pop('created_at')
        actual.pop('updated_at')
        expected = {
            'member': TENANT1,
            'image_id': UUID1,
            'can_share': False,
            'status': 'pending',
        }
        self.assertEqual(expected, actual)

    def test_image_member_update(self):
        TENANT1 = uuidutils.generate_uuid()
        member = self.db_api.image_member_create(self.context,
                                                 {'member': TENANT1,
                                                  'image_id': UUID1})
        member_id = member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')

        expected = {'member': TENANT1,
                    'image_id': UUID1,
                    'status': 'pending',
                    'can_share': False}
        self.assertEqual(expected, member)

        member = self.db_api.image_member_update(self.context,
                                                 member_id,
                                                 {'can_share': True})

        self.assertNotEqual(member['created_at'], member['updated_at'])
        member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')
        expected = {'member': TENANT1,
                    'image_id': UUID1,
                    'status': 'pending',
                    'can_share': True}
        self.assertEqual(expected, member)

        members = self.db_api.image_member_find(self.context,
                                                member=TENANT1,
                                                image_id=UUID1)
        member = members[0]
        member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')
        self.assertEqual(expected, member)

    def test_image_member_update_status(self):
        TENANT1 = uuidutils.generate_uuid()
        member = self.db_api.image_member_create(self.context,
                                                 {'member': TENANT1,
                                                  'image_id': UUID1})
        member_id = member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')

        expected = {'member': TENANT1,
                    'image_id': UUID1,
                    'status': 'pending',
                    'can_share': False}
        self.assertEqual(expected, member)

        member = self.db_api.image_member_update(self.context,
                                                 member_id,
                                                 {'status': 'accepted'})

        self.assertNotEqual(member['created_at'], member['updated_at'])
        member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')
        expected = {'member': TENANT1,
                    'image_id': UUID1,
                    'status': 'accepted',
                    'can_share': False}
        self.assertEqual(expected, member)

        members = self.db_api.image_member_find(self.context,
                                                member=TENANT1,
                                                image_id=UUID1)
        member = members[0]
        member.pop('id')
        member.pop('created_at')
        member.pop('updated_at')
        self.assertEqual(expected, member)

    def test_image_member_find(self):
        TENANT1 = uuidutils.generate_uuid()
        TENANT2 = uuidutils.generate_uuid()
        fixtures = [
            {'member': TENANT1, 'image_id': UUID1},
            {'member': TENANT1, 'image_id': UUID2, 'status': 'rejected'},
            {'member': TENANT2, 'image_id': UUID1, 'status': 'accepted'},
        ]
        for f in fixtures:
            self.db_api.image_member_create(self.context, copy.deepcopy(f))

        def _simplify(output):
            return

        def _assertMemberListMatch(list1, list2):
            _simple = lambda x: set([(o['member'], o['image_id']) for o in x])
            self.assertEqual(_simple(list1), _simple(list2))

        output = self.db_api.image_member_find(self.context, member=TENANT1)
        _assertMemberListMatch([fixtures[0], fixtures[1]], output)

        output = self.db_api.image_member_find(self.context, image_id=UUID1)
        _assertMemberListMatch([fixtures[0], fixtures[2]], output)

        output = self.db_api.image_member_find(self.context,
                                               member=TENANT2,
                                               image_id=UUID1)
        _assertMemberListMatch([fixtures[2]], output)

        output = self.db_api.image_member_find(self.context,
                                               status='accepted')
        _assertMemberListMatch([fixtures[2]], output)

        output = self.db_api.image_member_find(self.context,
                                               status='rejected')
        _assertMemberListMatch([fixtures[1]], output)

        output = self.db_api.image_member_find(self.context,
                                               status='pending')
        _assertMemberListMatch([fixtures[0]], output)

        output = self.db_api.image_member_find(self.context,
                                               status='pending',
                                               image_id=UUID2)
        _assertMemberListMatch([], output)

        image_id = uuidutils.generate_uuid()
        output = self.db_api.image_member_find(self.context,
                                               member=TENANT2,
                                               image_id=image_id)
        _assertMemberListMatch([], output)

    def test_image_member_delete(self):
        TENANT1 = uuidutils.generate_uuid()
        fixture = {'member': TENANT1, 'image_id': UUID1, 'can_share': True}
        member = self.db_api.image_member_create(self.context, fixture)
        self.assertEqual(1, len(self.db_api.image_member_find(self.context)))
        member = self.db_api.image_member_delete(self.context, member['id'])
        self.assertEqual(0, len(self.db_api.image_member_find(self.context)))


class TestVisibility(base.IsolatedUnitTest):
    def setUp(self):
        super(TestVisibility, self).setUp()
        self.db_api = db_tests.get_db(self.config)
        db_tests.reset_db(self.db_api)
        self.setup_tenants()
        self.setup_contexts()
        self.fixtures = self.build_image_fixtures()
        self.create_images(self.fixtures)

    def setup_tenants(self):
        self.admin_tenant = uuidutils.generate_uuid()
        self.tenant1 = uuidutils.generate_uuid()
        self.tenant2 = uuidutils.generate_uuid()

    def setup_contexts(self):
        self.admin_context = context.RequestContext(
                is_admin=True, tenant=self.admin_tenant)
        self.admin_none_context = context.RequestContext(
                is_admin=True, tenant=None)
        self.tenant1_context = context.RequestContext(tenant=self.tenant1)
        self.tenant2_context = context.RequestContext(tenant=self.tenant2)
        self.none_context = context.RequestContext(tenant=None)

    def build_image_fixtures(self):
        fixtures = []
        owners = {
            'Unowned': None,
            'Admin Tenant': self.admin_tenant,
            'Tenant 1': self.tenant1,
            'Tenant 2': self.tenant2,
        }
        visibilities = {'public': True, 'private': False}
        for owner_label, owner in owners.items():
            for visibility, is_public in visibilities.items():
                fixture = {
                    'name': '%s, %s' % (owner_label, visibility),
                    'owner': owner,
                    'is_public': is_public,
                }
                fixtures.append(fixture)
        return [build_image_fixture(**fixture) for fixture in fixtures]

    def create_images(self, images):
        for fixture in images:
            self.db_api.image_create(self.admin_context, fixture)


class VisibilityTests(object):

    def test_unknown_admin_sees_all(self):
        images = self.db_api.image_get_all(self.admin_none_context)
        self.assertEquals(len(images), 8)

    def test_unknown_admin_is_public_true(self):
        images = self.db_api.image_get_all(self.admin_none_context,
                                           filters={'is_public': True})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_unknown_admin_is_public_false(self):
        images = self.db_api.image_get_all(self.admin_none_context,
                                           filters={'is_public': False})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertFalse(i['is_public'])

    def test_unknown_admin_is_public_none(self):
        images = self.db_api.image_get_all(self.admin_none_context,
                                           filters={'is_public': None})
        self.assertEquals(len(images), 8)

    def test_known_admin_sees_all(self):
        images = self.db_api.image_get_all(self.admin_context)
        self.assertEquals(len(images), 8)

    def test_known_admin_is_public_true(self):
        images = self.db_api.image_get_all(self.admin_context,
                                           filters={'is_public': True})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_known_admin_is_public_false(self):
        images = self.db_api.image_get_all(self.admin_context,
                                           filters={'is_public': False})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertFalse(i['is_public'])

    def test_known_admin_is_public_none(self):
        images = self.db_api.image_get_all(self.admin_context,
                                           filters={'is_public': None})
        self.assertEquals(len(images), 8)

    def test_what_unknown_user_sees(self):
        images = self.db_api.image_get_all(self.none_context)
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_unknown_user_is_public_true(self):
        images = self.db_api.image_get_all(self.none_context,
                                           filters={'is_public': True})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_unknown_user_is_public_false(self):
        images = self.db_api.image_get_all(self.none_context,
                                           filters={'is_public': False})
        self.assertEquals(len(images), 0)

    def test_unknown_user_is_public_none(self):
        images = self.db_api.image_get_all(self.none_context,
                                           filters={'is_public': None})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_what_tenant1_sees(self):
        images = self.db_api.image_get_all(self.tenant1_context)
        self.assertEquals(len(images), 5)
        for i in images:
            if not i['is_public']:
                self.assertEquals(i['owner'], self.tenant1)

    def test_tenant1_is_public_true(self):
        images = self.db_api.image_get_all(self.tenant1_context,
                                           filters={'is_public': True})
        self.assertEquals(len(images), 4)
        for i in images:
            self.assertTrue(i['is_public'])

    def test_tenant1_is_public_false(self):
        images = self.db_api.image_get_all(self.tenant1_context,
                                           filters={'is_public': False})
        self.assertEquals(len(images), 1)
        self.assertFalse(images[0]['is_public'])
        self.assertEquals(images[0]['owner'], self.tenant1)

    def test_tenant1_is_public_none(self):
        images = self.db_api.image_get_all(self.tenant1_context,
                                           filters={'is_public': None})
        self.assertEquals(len(images), 5)
        for i in images:
            if not i['is_public']:
                self.assertEquals(i['owner'], self.tenant1)


class TestMembershipVisibility(base.IsolatedUnitTest):
    def setUp(self):
        super(TestMembershipVisibility, self).setUp()
        self.db_api = db_tests.get_db(self.config)
        db_tests.reset_db(self.db_api)
        self._create_contexts()
        self._create_images()

    def _create_contexts(self):
        self.owner1, self.owner1_ctx = self._user_fixture()
        self.owner2, self.owner2_ctx = self._user_fixture()
        self.tenant1, self.user1_ctx = self._user_fixture()
        self.tenant2, self.user2_ctx = self._user_fixture()
        self.tenant3, self.user3_ctx = self._user_fixture()
        self.admin_tenant, self.admin_ctx = self._user_fixture(admin=True)

    def _user_fixture(self, admin=False):
        tenant_id = uuidutils.generate_uuid()
        ctx = context.RequestContext(tenant=tenant_id, is_admin=admin)
        return tenant_id, ctx

    def _create_images(self):
        self.image_ids = {}
        for owner in [self.owner1, self.owner2]:
            self._create_image('not_shared', owner)
            self._create_image('shared-with-1', owner, members=[self.tenant1])
            self._create_image('shared-with-2', owner, members=[self.tenant2])
            self._create_image('shared-with-both', owner,
                               members=[self.tenant1, self.tenant2])

    def _create_image(self, name, owner, members=None):
        image = build_image_fixture(name=name, owner=owner, is_public=False)
        self.image_ids[(owner, name)] = image['id']
        self.db_api.image_create(self.admin_ctx, image)
        for member in members or []:
            member = {'image_id': image['id'], 'member': member}
            self.db_api.image_member_create(self.admin_ctx, member)


class MembershipVisibilityTests(object):
    def _check_by_member(self, ctx, member_id, expected):
        members = self.db_api.image_member_find(ctx, member=member_id)
        images = [self.db_api.image_get(self.admin_ctx, member['image_id'])
                  for member in members]
        facets = [(image['owner'], image['name']) for image in images]
        self.assertEqual(set(expected), set(facets))

    def test_owner1_finding_user1_memberships(self):
        """ Owner1 should see images it owns that are shared with User1 """
        expected = [
            (self.owner1, 'shared-with-1'),
            (self.owner1, 'shared-with-both'),
        ]
        self._check_by_member(self.owner1_ctx, self.tenant1, expected)

    def test_user1_finding_user1_memberships(self):
        """ User1 should see all images shared with User1 """
        expected = [
            (self.owner1, 'shared-with-1'),
            (self.owner1, 'shared-with-both'),
            (self.owner2, 'shared-with-1'),
            (self.owner2, 'shared-with-both'),
        ]
        self._check_by_member(self.user1_ctx, self.tenant1, expected)

    def test_user2_finding_user1_memberships(self):
        """ User2 should see no images shared with User1 """
        expected = []
        self._check_by_member(self.user2_ctx, self.tenant1, expected)

    def test_admin_finding_user1_memberships(self):
        """ Admin should see all images shared with User1 """
        expected = [
            (self.owner1, 'shared-with-1'),
            (self.owner1, 'shared-with-both'),
            (self.owner2, 'shared-with-1'),
            (self.owner2, 'shared-with-both'),
        ]
        self._check_by_member(self.admin_ctx, self.tenant1, expected)

    def _check_by_image(self, context, image_id, expected):
        members = self.db_api.image_member_find(context, image_id=image_id)
        member_ids = [member['member'] for member in members]
        self.assertEqual(set(expected), set(member_ids))

    def test_owner1_finding_owner1s_image_members(self):
        """ Owner1 should see all memberships of its image """
        expected = [self.tenant1, self.tenant2]
        image_id = self.image_ids[(self.owner1, 'shared-with-both')]
        self._check_by_image(self.owner1_ctx, image_id, expected)

    def test_admin_finding_owner1s_image_members(self):
        """ Admin should see all memberships of owner1's image """
        expected = [self.tenant1, self.tenant2]
        image_id = self.image_ids[(self.owner1, 'shared-with-both')]
        self._check_by_image(self.admin_ctx, image_id, expected)

    def test_user1_finding_owner1s_image_members(self):
        """ User1 should see its own membership of owner1's image """
        expected = [self.tenant1]
        image_id = self.image_ids[(self.owner1, 'shared-with-both')]
        self._check_by_image(self.user1_ctx, image_id, expected)

    def test_user2_finding_owner1s_image_members(self):
        """ User2 should see its own membership of owner1's image """
        expected = [self.tenant2]
        image_id = self.image_ids[(self.owner1, 'shared-with-both')]
        self._check_by_image(self.user2_ctx, image_id, expected)

    def test_user3_finding_owner1s_image_members(self):
        """ User3 should see no memberships of owner1's image """
        expected = []
        image_id = self.image_ids[(self.owner1, 'shared-with-both')]
        self._check_by_image(self.user3_ctx, image_id, expected)
