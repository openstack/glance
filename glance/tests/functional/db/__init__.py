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
import random

from glance.common import context
from glance.common import exception
from glance.common import utils
from glance.openstack.common import timeutils


# The default sort order of results is whatever sort key is specified,
# plus created_at and id for ties.  When we're not specifying a sort_key,
# we get the default (created_at). Some tests below expect the fixtures to be
# returned in array-order, so if if the created_at timestamps are the same,
# these tests rely on the UUID* values being in order
UUID1, UUID2, UUID3 = sorted([utils.generate_uuid() for x in range(3)])


def build_fixtures():
    dt = datetime.datetime.now()
    return [
        {
            'id': UUID1,
            'name': 'fake image #1',
            'status': 'active',
            'disk_format': 'ami',
            'container_format': 'ami',
            'is_public': False,
            'created_at': dt,
            'updated_at': dt,
            'deleted_at': None,
            'deleted': False,
            'checksum': None,
            'min_disk': 0,
            'min_ram': 0,
            'size': 13,
            'location': "swift://user:passwd@acct/container/obj.tar.0",
            'properties': {'type': 'kernel', 'foo': 'bar'},
        },
        {
            'id': UUID2,
            'name': 'fake image #2',
            'status': 'active',
            'disk_format': 'vhd',
            'container_format': 'ovf',
            'is_public': True,
            'created_at': dt,
            'updated_at': dt + datetime.timedelta(microseconds=5),
            'deleted_at': None,
            'deleted': False,
            'checksum': None,
            'min_disk': 5,
            'min_ram': 256,
            'size': 19,
            'location': "file:///tmp/glance-tests/2",
            'properties': {}
        },
        {
            'id': UUID3,
            'name': 'fake image #2',
            'status': 'active',
            'disk_format': 'vhd',
            'container_format': 'ovf',
            'is_public': True,
            'created_at': dt + datetime.timedelta(microseconds=5),
            'updated_at': dt + datetime.timedelta(microseconds=5),
            'deleted_at': None,
            'deleted': False,
            'checksum': None,
            'min_disk': 5,
            'min_ram': 256,
            'size': 19,
            'location': "file:///tmp/glance-tests/2",
            'properties': {},
        },
    ]


class BaseTestCase(object):
    def setUp(self):
        self.adm_context = context.RequestContext(is_admin=True)
        self.context = context.RequestContext(is_admin=False)
        self.configure()
        self.reset()
        self.fixtures = build_fixtures()
        self.create_fixtures(self.fixtures)

    def create_fixtures(self, fixtures):
        for fixture in fixtures:
            self.db_api.image_create(self.adm_context, fixture)

    def reset(self):
        pass

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
        self.assertEquals(2, len(images))

    def test_image_get_all_marker_deleted_showing_deleted(self):
        """Specify a deleted image as a marker if showing deleted images."""
        self.db_api.image_destroy(self.adm_context, UUID3)
        self.db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': True}
        images = self.db_api.image_get_all(self.context, marker=UUID3,
                                      filters=filters)
        self.assertEquals(1, len(images))

    def test_image_get_all_invalid_sort_key(self):
        self.assertRaises(exception.InvalidSortKey, self.db_api.image_get_all,
                          self.context, sort_key='blah')

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


class BaseTestCasePaging(object):
    """ Checks the paging order, by paging through random images.

    It generates images with random min_disk, created_at and image id.
    Image id is a UUID and unique, min_disk and created_at are drawn from
    a small range so are expected to have duplicates.  Then we try paging
    through, and check that we get back the images in the order we expect.
    """

    ITEM_COUNT = 20
    PAGE_SIZE = 5
    TIME_VALUES = 10
    MINDISK_VALUES = 10

    def setUp(self):
        self.adm_context = context.RequestContext(is_admin=True)
        self.context = context.RequestContext(is_admin=False)
        self.configure()
        self.reset()
        self.fixtures = self.build_fixtures()
        self.create_fixtures(self.fixtures)

    def configure(self):
        pass

    def create_fixtures(self, fixtures):
        for fixture in fixtures:
            self.db_api.image_create(self.adm_context, fixture)

    def reset(self):
        pass

    def _build_random_image(self, t, min_disk):
        image_id = utils.generate_uuid()

        return {'id': image_id,
         'name': 'fake image #' + image_id,
         'status': 'active',
         'disk_format': 'ami',
         'container_format': 'ami',
         'is_public': True,
         'created_at': t,
         'updated_at': t,
         'deleted_at': None,
         'deleted': False,
         'checksum': None,
         'min_disk': min_disk,
         'min_ram': 0,
         'size': 0,
         'location': "file:///tmp/glance-tests/" + image_id,
         'properties': {}}

    def build_fixtures(self):
        self.images = []
        t0 = timeutils.utcnow()
        for _ in xrange(0, self.ITEM_COUNT):
            tdelta = random.uniform(0, self.TIME_VALUES)
            min_disk = random.uniform(0, self.MINDISK_VALUES)
            t = t0 + datetime.timedelta(microseconds=tdelta)
            image = self._build_random_image(t, min_disk)
            self.images.append(image)
        return self.images

    def _sort_results(self, sort_dir, sort_key):
        results = self.images
        results = sorted(results, key=lambda i: (i[sort_key],
                                                 i['created_at'],
                                                 i['id']))
        if sort_dir == 'desc':
            results.reverse()
        return results

    def _do_test(self, sort_dir, sort_key, **kwargs):
        try:
            limit = kwargs['limit']
        except KeyError:
            limit = self.PAGE_SIZE

        marker = None

        output = []
        expected = []

        for image in self._sort_results(sort_dir, sort_key):
            expected.append(image)

        while True:
            results = self.db_api.image_get_all(self.context,
                                                marker=marker,
                                                limit=limit,
                                                sort_key=sort_key,
                                                sort_dir=sort_dir)
            if not results:
                break
            else:
                output.extend(results)

            # Prevent this running infinitely in error cases
            self.assertTrue(len(output) < (500 + len(expected)))

            marker = results[-1]['id']

        self.assertEquals(len(output), len(expected))
        self.assertEquals([image['id'] for image in expected],
                          [image['id'] for image in output])

    def test_sort_by_disk_asc(self):
        self._do_test('asc', 'min_disk')

    def test_sort_by_disk_desc(self):
        self._do_test('desc', 'min_disk')

    def test_sort_by_created_at_asc(self):
        self._do_test('asc', 'created_at')

    def test_sort_by_created_at_desc(self):
        self._do_test('desc', 'created_at')

    def test_sort_by_id_asc(self):
        self._do_test('asc', 'id')

    def test_sort_by_id_desc(self):
        self._do_test('desc', 'id')

    #NOTE(bcwaldon): make sure this works!
    def test_limit_None(self):
        self._do_test('desc', 'id', limit=None)
