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

import datetime
import random

from glance.common import context
from glance.common import exception
from glance.common import utils
from glance.openstack.common import timeutils


_gen_uuid = utils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


# The default sort order of results is whatever sort key is specified,
# plus created_at and id for ties.  When we're not specifying a sort_key,
# we get the default (created_at); some tests below expect the fixtures to be
# returned in array-order; so if if the created_at timestamps are the same,
# these tests rely on UUID1 < UUID2. Swap so that's the case.
if UUID1 > UUID2:
    UUID1, UUID2 = UUID2, UUID1


def build_fixtures(t1, t2):
    return [
    {'id': UUID1,
     'name': 'fake image #1',
     'status': 'active',
     'disk_format': 'ami',
     'container_format': 'ami',
     'is_public': False,
     'created_at': t1,
     'updated_at': t1,
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
     'created_at': t2,
     'updated_at': t2,
     'deleted_at': None,
     'deleted': False,
     'checksum': None,
     'min_disk': 5,
     'min_ram': 256,
     'size': 19,
     'location': "file:///tmp/glance-tests/2",
     'properties': {}}]


class BaseTestCase(object):
    def setUp(self):
        self.adm_context = context.RequestContext(is_admin=True)
        self.context = context.RequestContext(is_admin=False)
        self.configure()
        self.reset()
        self.fixtures = self.build_fixtures()
        self.create_fixtures(self.fixtures)

    def build_fixtures(self):
        t1 = timeutils.utcnow()
        t2 = t1 + datetime.timedelta(microseconds=1)
        return build_fixtures(t1, t2)

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
        self.assertEquals(len(images), 2)

    def test_image_get_all_marker(self):
        images = self.db_api.image_get_all(self.context, marker=UUID2)
        self.assertEquals(len(images), 1)

    def test_image_get_all_marker_deleted(self):
        """Cannot specify a deleted image as a marker."""
        self.db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': False}
        self.assertRaises(exception.NotFound, self.db_api.image_get_all,
                          self.context, marker=UUID1, filters=filters)

    def test_image_get_all_marker_deleted_showing_deleted_as_admin(self):
        """Specify a deleted image as a marker if showing deleted images."""
        self.db_api.image_destroy(self.adm_context, UUID1)
        images = self.db_api.image_get_all(self.adm_context, marker=UUID1)
        self.assertEquals(len(images), 0)

    def test_image_get_all_marker_deleted_showing_deleted(self):
        """Specify a deleted image as a marker if showing deleted images."""
        self.db_api.image_destroy(self.adm_context, UUID1)
        filters = {'deleted': True}
        images = self.db_api.image_get_all(self.context, marker=UUID1,
                                      filters=filters)
        self.assertEquals(len(images), 0)

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


class BaseTestCaseSameTime(BaseTestCase):
    def build_fixtures(self):
        t1 = timeutils.utcnow()
        t2 = t1  # Same timestamp!
        return build_fixtures(t1, t2)


class BaseTestCasePaging(object):
    """ Checks the paging order, by paging through random images.

    It generates images with random min_disk, created_at and image id.
    Image id is a UUID and unique, min_disk and created_at are drawn from
    a small range so are expected to have duplicates.  Then we try paging
    through, and check that we get back the images in the order we expect.
    """

    ITEM_COUNT = 100
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
        image_id = _gen_uuid()

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

    def _do_test(self, sort_dir, sort_key):
        limit = self.PAGE_SIZE
        marker = None

        got_ids = []
        expected_ids = []

        for i in self._sort_results(sort_dir, sort_key):
            expected_ids.append(i['id'])

        while True:
            results = self.db_api.image_get_all(self.context,
                                                marker=marker,
                                                limit=limit,
                                                sort_key=sort_key,
                                                sort_dir=sort_dir)
            if not results:
                break

            for result in results:
                got_ids.append(result['id'])

            # Prevent this running infinitely in error cases
            self.assertTrue(len(got_ids) < (500 + len(expected_ids)))

            marker = results[-1].id

        self.assertEquals(len(got_ids), len(expected_ids))
        self.assertEquals(got_ids, expected_ids)

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
