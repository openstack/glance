# Copyright 2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

from oslo_config import cfg
from oslo_db import options
from oslo_utils.fixture import uuidsentinel as uuids

from glance.common import exception
from glance import context as glance_context
import glance.db.sqlalchemy.api
from glance.db.sqlalchemy import models as db_models
from glance.db.sqlalchemy import models_metadef as metadef_models
import glance.tests.functional.db as db_tests
from glance.tests.functional.db import base
from glance.tests.functional.db import base_metadef

CONF = cfg.CONF


def get_db(config):
    options.set_defaults(CONF, connection='sqlite://')
    config(debug=False)
    db_api = glance.db.sqlalchemy.api
    return db_api


def reset_db(db_api):
    db_models.unregister_models(db_api.get_engine())
    db_models.register_models(db_api.get_engine())


def reset_db_metadef(db_api):
    metadef_models.unregister_models(db_api.get_engine())
    metadef_models.register_models(db_api.get_engine())


class TestSqlAlchemyDriver(base.TestDriver,
                           base.DriverTests,
                           base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyDriver, self).setUp()
        self.addCleanup(db_tests.reset)

    def test_get_image_with_invalid_long_image_id(self):
        image_id = '343f9ba5-0197-41be-9543-16bbb32e12aa-xxxxxx'
        self.assertRaises(exception.NotFound, self.db_api.image_get,
                          self.context, image_id)

    def test_image_tag_delete_with_invalid_long_image_id(self):
        image_id = '343f9ba5-0197-41be-9543-16bbb32e12aa-xxxxxx'
        self.assertRaises(exception.NotFound, self.db_api.image_tag_delete,
                          self.context, image_id, 'fake')

    def test_image_tag_get_all_with_invalid_long_image_id(self):
        image_id = '343f9ba5-0197-41be-9543-16bbb32e12aa-xxxxxx'
        self.assertRaises(exception.NotFound, self.db_api.image_tag_get_all,
                          self.context, image_id)

    def test_user_get_storage_usage_with_invalid_long_image_id(self):
        image_id = '343f9ba5-0197-41be-9543-16bbb32e12aa-xxxxxx'
        self.assertRaises(exception.NotFound,
                          self.db_api.user_get_storage_usage,
                          self.context, 'fake_owner_id', image_id)


class TestSqlAlchemyVisibility(base.TestVisibility,
                               base.VisibilityTests,
                               base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyVisibility, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSqlAlchemyMembershipVisibility(base.TestMembershipVisibility,
                                         base.MembershipVisibilityTests,
                                         base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyMembershipVisibility, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSqlAlchemyDBDataIntegrity(base.TestDriver,
                                    base.FunctionalInitWrapper):
    """Test class for checking the data integrity in the database.

    Helpful in testing scenarios specific to the sqlalchemy api.
    """

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyDBDataIntegrity, self).setUp()
        self.addCleanup(db_tests.reset)

    def test_paginate_redundant_sort_keys(self):
        original_method = self.db_api._paginate_query

        def fake_paginate_query(query, model, limit,
                                sort_keys, marker, sort_dir, sort_dirs):
            self.assertEqual(['created_at', 'id'], sort_keys)
            return original_method(query, model, limit,
                                   sort_keys, marker, sort_dir, sort_dirs)

        self.mock_object(self.db_api, '_paginate_query',
                         fake_paginate_query)
        self.db_api.image_get_all(self.context, sort_key=['created_at'])

    def test_paginate_non_redundant_sort_keys(self):
        original_method = self.db_api._paginate_query

        def fake_paginate_query(query, model, limit,
                                sort_keys, marker, sort_dir, sort_dirs):
            self.assertEqual(['name', 'created_at', 'id'], sort_keys)
            return original_method(query, model, limit,
                                   sort_keys, marker, sort_dir, sort_dirs)

        self.mock_object(self.db_api, '_paginate_query',
                         fake_paginate_query)
        self.db_api.image_get_all(self.context, sort_key=['name'])


class TestSqlAlchemyTask(base.TaskTests,
                         base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyTask, self).setUp()
        self.addCleanup(db_tests.reset)


class TestSqlAlchemyQuota(base.DriverQuotaTests,
                          base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestSqlAlchemyQuota, self).setUp()
        self.addCleanup(db_tests.reset)


class TestDBPurge(base.DBPurgeTests,
                  base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestDBPurge, self).setUp()
        self.addCleanup(db_tests.reset)


class TestMetadefSqlAlchemyDriver(base_metadef.TestMetadefDriver,
                                  base_metadef.MetadefDriverTests,
                                  base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db_metadef)
        super(TestMetadefSqlAlchemyDriver, self).setUp()
        self.addCleanup(db_tests.reset)


class TestImageCacheOperations(base.TestDriver,
                               base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestImageCacheOperations, self).setUp()

        self.addCleanup(db_tests.reset)

        # Create two images
        self.images = []
        for num in range(0, 2):
            size = 100
            image = self.db_api.image_create(
                self.adm_context,
                {'status': 'active',
                 'owner': self.adm_context.owner,
                 'size': size,
                 'name': 'test-%s-%i' % ('active', num)})
            self.images.append(image)

        # Create two node_references
        self.node_references = [
            self.db_api.node_reference_create(
                self.adm_context, 'node_url_1'),
            self.db_api.node_reference_create(
                self.adm_context, 'node_url_2'),
        ]

        # Cache two images on node_url_1
        for node in self.node_references:
            if node['node_reference_url'] == 'node_url_2':
                continue

            for image in self.images:
                self.db_api.insert_cache_details(
                    self.adm_context, 'node_url_1',
                    image['id'], image['size'], hits=3)

    def test_node_reference_get_by_url(self):
        node_reference = self.db_api.node_reference_get_by_url(
            self.adm_context, 'node_url_1')
        self.assertEqual('node_url_1',
                         node_reference['node_reference_url'])

    def test_node_reference_get_by_url_not_found(self):
        self.assertRaises(exception.NotFound,
                          self.db_api.node_reference_get_by_url,
                          self.adm_context,
                          'garbage_url')

    def test_get_cached_images(self):
        # Two images are cached on node 'node_url_1'
        cached_images = self.db_api.get_cached_images(
            self.adm_context, 'node_url_1')
        self.assertEqual(2, len(cached_images))

        # Nothing is cached on node 'node_url_2'
        cached_images = self.db_api.get_cached_images(
            self.adm_context, 'node_url_2')
        self.assertEqual(0, len(cached_images))

    def test_get_hit_count(self):
        # Hit count will be 3 for image on node_url_1
        hit_count = self.db_api.get_hit_count(
            self.adm_context, self.images[0]['id'], 'node_url_1')
        self.assertEqual(3, hit_count)

        # Hit count will be 0 for image on node_url_2
        hit_count = self.db_api.get_hit_count(
            self.adm_context, self.images[0]['id'], 'node_url_2')
        self.assertEqual(0, hit_count)

    def test_delete_all_cached_images(self):
        # delete all images from node_url_1
        self.db_api.delete_all_cached_images(
            self.adm_context, 'node_url_1')
        # Verify all images are deleted
        cached_images = self.db_api.get_cached_images(
            self.adm_context, 'node_url_1')
        self.assertEqual(0, len(cached_images))

    def test_delete_cached_image(self):
        # Delete cached image from node_url_1
        self.db_api.delete_cached_image(
            self.adm_context, self.images[0]['id'], 'node_url_1')

        # verify that image is deleted
        self.assertFalse(self.db_api.is_image_cached_for_node(
            self.adm_context, 'node_url_1', self.images[0]['id']))

    def test_get_least_recently_accessed(self):
        recently_accessed = self.db_api.get_least_recently_accessed(
            self.adm_context, 'node_url_1')
        # Verify we get last cached image in response
        self.assertEqual(self.images[0]['id'], recently_accessed)

    def test_is_image_cached_for_node(self):
        # Verify image is cached for node_url_1
        self.assertTrue(self.db_api.is_image_cached_for_node(
            self.adm_context, 'node_url_1', self.images[0]['id']))

        # Verify image is not cached for node_url_2
        self.assertFalse(self.db_api.is_image_cached_for_node(
            self.adm_context, 'node_url_2', self.images[0]['id']))

    def test_update_hit_count(self):
        # Verify image on node_url_1 has 3 as hit count
        hit_count = self.db_api.get_hit_count(
            self.adm_context, self.images[0]['id'], 'node_url_1')
        self.assertEqual(3, hit_count)

        # Update the hit count of UUID1
        self.db_api.update_hit_count(
            self.adm_context, self.images[0]['id'], 'node_url_1')

        # Verify hit count is now 4
        hit_count = self.db_api.get_hit_count(
            self.adm_context, self.images[0]['id'], 'node_url_1')
        self.assertEqual(4, hit_count)


class TestImageAtomicOps(base.TestDriver,
                         base.FunctionalInitWrapper):

    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestImageAtomicOps, self).setUp()

        self.addCleanup(db_tests.reset)
        self.image = self.db_api.image_create(
            self.adm_context,
            {'status': 'active',
             'owner': self.adm_context.owner,
             'properties': {'speed': '88mph'}})

    @staticmethod
    def _propdict(list_of_props):
        """
        Convert a list of ImageProperty objects to dict, ignoring
        deleted values.
        """
        return {x.name: x.value
                for x in list_of_props
                if x.deleted == 0}

    def assertOnlyImageHasProp(self, image_id, name, value):
        images_with_prop = self.db_api.image_get_all(
            self.adm_context,
            {'properties': {name: value}})
        self.assertEqual(1, len(images_with_prop))
        self.assertEqual(image_id, images_with_prop[0]['id'])

    def test_update(self):
        """Try to double-create a property atomically.

        This should ensure that a second attempt to create the property
        atomically fails with Duplicate.
        """

        # Atomically create the property
        self.db_api.image_set_property_atomic(self.image['id'],
                                              'test_property', 'foo')

        # Make sure only the matched image got it
        self.assertOnlyImageHasProp(self.image['id'], 'test_property', 'foo')

        # Trying again should fail
        self.assertRaises(exception.Duplicate,
                          self.db_api.image_set_property_atomic,
                          self.image['id'], 'test_property', 'bar')

        # Ensure that only the first one stuck
        image = self.db_api.image_get(self.adm_context, self.image['id'])
        self.assertEqual({'speed': '88mph', 'test_property': 'foo'},
                         self._propdict(image['properties']))
        self.assertOnlyImageHasProp(self.image['id'], 'test_property', 'foo')

    def test_update_drop_update(self):
        """Try to create, delete, re-create property atomically.

        If we fail to undelete and claim the property, this will
        fail as duplicate.
        """

        # Atomically create the property
        self.db_api.image_set_property_atomic(self.image['id'],
                                              'test_property', 'foo')

        # Ensure that it stuck
        image = self.db_api.image_get(self.adm_context, self.image['id'])
        self.assertEqual({'speed': '88mph', 'test_property': 'foo'},
                         self._propdict(image['properties']))
        self.assertOnlyImageHasProp(self.image['id'], 'test_property', 'foo')

        # Update the image with the property removed, like image_repo.save()
        new_props = self._propdict(image['properties'])
        del new_props['test_property']
        self.db_api.image_update(self.adm_context, self.image['id'],
                                 values={'properties': new_props},
                                 purge_props=True)

        # Make sure that a fetch shows the property deleted
        image = self.db_api.image_get(self.adm_context, self.image['id'])
        self.assertEqual({'speed': '88mph'},
                         self._propdict(image['properties']))

        # Atomically update the property, which still exists, but is
        # deleted
        self.db_api.image_set_property_atomic(self.image['id'],
                                              'test_property', 'bar')

        # Makes sure we updated the property and undeleted it
        image = self.db_api.image_get(self.adm_context, self.image['id'])
        self.assertEqual({'speed': '88mph', 'test_property': 'bar'},
                         self._propdict(image['properties']))
        self.assertOnlyImageHasProp(self.image['id'], 'test_property', 'bar')

    def test_update_prop_multiple_images(self):
        """Create and delete properties on two images, then set on one.

        This tests that the resurrect-from-deleted mode of the method only
        matches deleted properties from our image.
        """

        images = self.db_api.image_get_all(self.adm_context)

        image_id1 = images[0]['id']
        image_id2 = images[-1]['id']

        # Atomically create the property on each image
        self.db_api.image_set_property_atomic(image_id1,
                                              'test_property', 'foo')
        self.db_api.image_set_property_atomic(image_id2,
                                              'test_property', 'bar')

        # Make sure they got the right property value each
        self.assertOnlyImageHasProp(image_id1, 'test_property', 'foo')
        self.assertOnlyImageHasProp(image_id2, 'test_property', 'bar')

        # Delete the property on both images
        self.db_api.image_update(self.adm_context, image_id1,
                                 {'properties': {}},
                                 purge_props=True)
        self.db_api.image_update(self.adm_context, image_id2,
                                 {'properties': {}},
                                 purge_props=True)

        # Set the property value on one of the images. Both will have a
        # deleted previous value for the property, but only one should
        # be updated
        self.db_api.image_set_property_atomic(image_id2,
                                              'test_property', 'baz')

        # Make sure the update affected only the intended image
        self.assertOnlyImageHasProp(image_id2, 'test_property', 'baz')

    def test_delete(self):
        """Try to double-delete a property atomically.

        This should ensure that a second attempt fails.
        """

        self.db_api.image_delete_property_atomic(self.image['id'],
                                                 'speed', '88mph')

        self.assertRaises(exception.NotFound,
                          self.db_api.image_delete_property_atomic,
                          self.image['id'], 'speed', '88mph')

    def test_delete_create_delete(self):
        """Try to delete, re-create, and then re-delete property."""
        self.db_api.image_delete_property_atomic(self.image['id'],
                                                 'speed', '88mph')
        self.db_api.image_update(self.adm_context, self.image['id'],
                                 {'properties': {'speed': '89mph'}},
                                 purge_props=True)

        # We should no longer be able to delete the property by the *old*
        # value
        self.assertRaises(exception.NotFound,
                          self.db_api.image_delete_property_atomic,
                          self.image['id'], 'speed', '88mph')

        # Only the new value should result in proper deletion
        self.db_api.image_delete_property_atomic(self.image['id'],
                                                 'speed', '89mph')

    def test_image_update_ignores_atomics(self):
        image = self.db_api.image_get_all(self.adm_context)[0]

        # Set two atomic properties atomically
        self.db_api.image_set_property_atomic(image['id'],
                                              'test1', 'foo')
        self.db_api.image_set_property_atomic(image['id'],
                                              'test2', 'bar')

        # Try to change test1, delete test2, add test3 and test4 via
        # normal image_update() where the first three are passed as
        # atomic
        self.db_api.image_update(
            self.adm_context, image['id'],
            {'properties': {'test1': 'baz', 'test3': 'bat', 'test4': 'yep'}},
            purge_props=True, atomic_props=['test1', 'test2', 'test3'])

        # Expect that none of the updates to the atomics are applied, but
        # the regular property is added.
        image = self.db_api.image_get(self.adm_context, image['id'])
        self.assertEqual({'test1': 'foo', 'test2': 'bar', 'test4': 'yep'},
                         self._propdict(image['properties']))


class TestImageStorageUsage(base.TestDriver,
                            base.FunctionalInitWrapper):
    def setUp(self):
        db_tests.load(get_db, reset_db)
        super(TestImageStorageUsage, self).setUp()
        self.addCleanup(db_tests.reset)

        self.contexts = {}

        for owner in (uuids.owner1, uuids.owner2):
            ctxt = glance_context.RequestContext(project_id=owner)
            self.contexts[owner] = ctxt
            statuses = ['queued', 'active', 'uploading', 'importing',
                        'deleted']
            for status in statuses:
                for num in range(0, 2):
                    # Make the size of each image differ by status
                    # so we can make sure we count the right one.
                    size = statuses.index(status) * 100
                    image = self.db_api.image_create(
                        ctxt,
                        {'status': status,
                         'owner': owner,
                         'size': size,
                         'name': 'test-%s-%i' % (status, num)})
                    if status == 'active':
                        # Active images get one location, active if they
                        # are the first. The first image is also copying
                        # to another store.
                        loc_status = num == 0 and 'active' or 'deleted'
                        self.db_api.image_location_add(
                            ctxt, image['id'],
                            {'url': 'foo://bar',
                             'metadata': {},
                             'status': loc_status})
                        self.db_api.image_set_property_atomic(
                            image['id'],
                            'os_glance_importing_to_stores',
                            num == 0 and 'fakestore' or '')

    def test_get_staging_usage(self):
        for owner, ctxt in self.contexts.items():
            usage = self.db_api.user_get_staging_usage(ctxt, ctxt.owner)
            # Each user has two staged images of size 200 each, plus one
            # active image of size 100 that is copying, and two importing
            # of size 300.
            self.assertEqual(1100, usage)

    def test_get_storage_usage(self):
        for owner, ctxt in self.contexts.items():
            usage = self.db_api.user_get_storage_usage(ctxt, ctxt.owner)
            # Each user has two active images of size 100 each, but only one
            # has an active location.
            self.assertEqual(100, usage)

    def test_get_image_count(self):
        for owner, ctxt in self.contexts.items():
            count = self.db_api.user_get_image_count(ctxt, ctxt.owner)
            # Each user has two active images, two staged images, two
            # importing, and two queued images
            self.assertEqual(8, count)

    def test_get_uploading_count(self):
        for owner, ctxt in self.contexts.items():
            count = self.db_api.user_get_uploading_count(ctxt, ctxt.owner)
            # Each user has two staged images, one image being copied,
            # and two importing.
            self.assertEqual(5, count)
