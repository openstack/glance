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
from glance.common import utils
from glance import context


# The default sort order of results is whatever sort key is specified,
# plus created_at and id for ties.  When we're not specifying a sort_key,
# we get the default (created_at). Some tests below expect the fixtures to be
# returned in array-order, so if if the created_at timestamps are the same,
# these tests rely on the UUID* values being in order
UUID1, UUID2, UUID3 = sorted([utils.generate_uuid() for x in range(3)])


def build_image_fixture(**kwargs):
    default_datetime = datetime.datetime.now()
    image = {
        'id': utils.generate_uuid(),
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
        'location': "file:///tmp/glance-tests/2",
        'properties': {},
    }
    image.update(kwargs)
    return image


class BaseTestCase(object):
    def setUp(self):
        self.adm_context = context.RequestContext(is_admin=True)
        self.context = context.RequestContext(is_admin=False)
        self.configure()
        self.reset()
        self.fixtures = self.build_image_fixtures()
        self.create_images(self.fixtures)

    def build_image_fixtures(self):
        dt1 = datetime.datetime.now()
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

    def reset(self):
        pass

    def test_image_create_requires_status(self):
        fixture = {'name': 'mark', 'size': 12}
        self.assertRaises(exception.Invalid,
                          self.db_api.image_create, self.context, fixture)
        fixture = {'name': 'mark', 'size': 12, 'status': 'queued'}
        self.db_api.image_create(self.context, fixture)

    def test_image_create_defaults(self):
        image = self.db_api.image_create(self.context, {'status': 'queued'})

        self.assertEqual(None, image['name'])
        self.assertEqual(None, image['container_format'])
        self.assertEqual(0, image['min_ram'])
        self.assertEqual(0, image['min_disk'])
        self.assertEqual(None, image['owner'])
        self.assertEqual(False, image['is_public'])
        self.assertEqual(None, image['size'])
        self.assertEqual(None, image['checksum'])
        self.assertEqual(None, image['disk_format'])
        self.assertEqual(None, image['location'])
        self.assertEqual(False, image['protected'])
        self.assertEqual(False, image['deleted'])
        self.assertEqual(None, image['deleted_at'])
        self.assertEqual([], image['properties'])

        # These values aren't predictable, but they should be populated
        self.assertTrue(uuid.UUID(image['id']))
        self.assertTrue(isinstance(image['created_at'], datetime.datetime))
        self.assertTrue(isinstance(image['updated_at'], datetime.datetime))

        #NOTE(bcwaldon): the tags attribute should not be returned as a part
        # of a core image entity
        self.assertFalse('tags' in image)

    def test_image_create_duplicate_id(self):
        self.assertRaises(exception.Duplicate,
                          self.db_api.image_create,
                          self.context, {'id': UUID1, 'status': 'queued'})

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
        prop = self.db_api.image_property_delete(self.context, prop)
        self.assertNotEqual(None, prop['deleted_at'])
        self.assertTrue(isinstance(prop['deleted_at'], datetime.datetime))
        self.assertTrue(prop['deleted'])

    def test_image_get(self):
        image = self.db_api.image_get(self.context, UUID1)
        self.assertEquals(image['id'], self.fixtures[0]['id'])

    def test_image_get_disallow_deleted(self):
        self.db_api.image_destroy(self.adm_context, UUID1)
        self.assertRaises(exception.NotFound, self.db_api.image_get,
                          self.context, UUID1)

    def test_image_get_allow_deleted(self):
        self.db_api.image_destroy(self.adm_context, UUID1)
        image = self.db_api.image_get(self.adm_context, UUID1)
        self.assertEquals(image['id'], self.fixtures[0]['id'])

    def test_image_get_force_allow_deleted(self):
        self.db_api.image_destroy(self.adm_context, UUID1)
        image = self.db_api.image_get(self.context, UUID1,
                                      force_show_deleted=True)
        self.assertEquals(image['id'], self.fixtures[0]['id'])

    def test_image_get_not_owned(self):
        TENANT1 = utils.generate_uuid()
        TENANT2 = utils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1)
        ctxt2 = context.RequestContext(is_admin=False, tenant=TENANT2)
        image = self.db_api.image_create(
                ctxt1, {'status': 'queued', 'owner': TENANT1})
        self.assertRaises(exception.Forbidden,
                          self.db_api.image_get, ctxt2, image['id'])

    def test_image_get_not_found(self):
        UUID = utils.generate_uuid()
        self.assertRaises(exception.NotFound,
                          self.db_api.image_get, self.context, UUID)

    def test_image_get_all(self):
        images = self.db_api.image_get_all(self.context)
        self.assertEquals(3, len(images))

    def test_image_get_all_with_filter(self):
        images = self.db_api.image_get_all(self.context,
                                      filters={'id': self.fixtures[0]['id']})
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
                             filters={'properties': {'poo': 'bear'}})
        self.assertEquals(len(images), 1)
        self.db_api.image_property_delete(self.context, prop)
        images = self.db_api.image_get_all(self.context,
                             filters={'properties': {'poo': 'bear'}})
        self.assertEquals(len(images), 0)

    def test_image_get_all_with_filter_undefined_property(self):
        images = self.db_api.image_get_all(self.context,
                                      filters={'poo': 'bear'})
        self.assertEquals(len(images), 0)

    def test_image_get_all_size_min_max(self):
        images = self.db_api.image_get_all(self.context,
                                      filters={'size_min': 10,
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
        TENANT1 = utils.generate_uuid()
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1)
        UUIDX = utils.generate_uuid()
        self.db_api.image_create(ctxt1,
                {'id': UUIDX, 'status': 'queued', 'owner': TENANT1})

        TENANT2 = utils.generate_uuid()
        ctxt2 = context.RequestContext(is_admin=False, tenant=TENANT2)
        UUIDY = utils.generate_uuid()
        self.db_api.image_create(ctxt2,
                {'id': UUIDY, 'status': 'queued', 'owner': TENANT2})

        # NOTE(bcwaldon): the is_public=True flag indicates that you want
        # to get all images that are public AND those that are owned by the
        # calling context
        images = self.db_api.image_get_all(ctxt1, filters={'is_public': True})
        image_ids = [image['id'] for image in images]
        expected = [UUIDX, UUID3, UUID2, UUID1]
        self.assertEqual(sorted(expected), sorted(image_ids))

    def test_image_paginate(self):
        """Paginate through a list of images using limit and marker"""
        extra_uuids = [utils.generate_uuid() for i in range(2)]
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

    def test_image_tag_create(self):
        tag = self.db_api.image_tag_create(self.context, UUID1, 'snap')
        self.assertEqual('snap', tag)

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

    def test_image_member_find(self):
        TENANT1 = utils.generate_uuid()
        TENANT2 = utils.generate_uuid()
        fixtures = [
            {'member': TENANT1, 'image_id': UUID1},
            {'member': TENANT1, 'image_id': UUID2},
            {'member': TENANT2, 'image_id': UUID1},
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
                                               member=TENANT2,
                                               image_id=utils.generate_uuid())
        _assertMemberListMatch([], output)

    def test_image_member_delete(self):
        TENANT1 = utils.generate_uuid()
        fixture = {'member': TENANT1, 'image_id': UUID1}
        member = self.db_api.image_member_create(self.context, fixture)
        member = self.db_api.image_member_delete(self.context, member)
        self.assertNotEqual(None, member['deleted_at'])
        self.assertTrue(isinstance(member['deleted_at'], datetime.datetime))
        self.assertTrue(member['deleted'])
