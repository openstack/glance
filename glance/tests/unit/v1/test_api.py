# vim: tabstop=4 shiftwidth=4 softtabstop=4
# -*- coding: utf-8 -*-

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
import hashlib
import httplib
import json
import StringIO

import routes
from sqlalchemy import exc
import stubout
import webob

import glance.api.middleware.context as context_middleware
import glance.api.common
from glance.api.v1 import images
from glance.api.v1 import router
import glance.common.config
from glance.common import utils
import glance.context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.openstack.common import cfg
from glance.openstack.common import timeutils
from glance.registry.api import v1 as rserver
import glance.store.filesystem
from glance.tests.unit import base
from glance.tests import utils as test_utils


CONF = cfg.CONF

_gen_uuid = utils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


class TestRegistryDb(test_utils.BaseTestCase):

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryDb, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        self.orig_engine = db_api._ENGINE

    def test_bad_sql_connection(self):
        """
        Test that a bad sql_connection option supplied to the registry
        API controller results in a) an Exception being thrown and b)
        a message being logged to the registry log file...
        """
        self.config(verbose=True, debug=True, sql_connection='baddriver:///')

        # We set this to None to trigger a reconfigure, otherwise
        # other modules may have already correctly configured the DB
        db_api._ENGINE = None
        self.assertRaises((ImportError, exc.ArgumentError),
                          db_api.configure_db)
        exc_raised = False
        self.log_written = False

        def fake_log_error(msg):
            if 'Error configuring registry database' in msg:
                self.log_written = True

        self.stubs.Set(db_api.LOG, 'error', fake_log_error)
        try:
            api_obj = rserver.API(routes.Mapper())
        except exc.ArgumentError:
            exc_raised = True
        except ImportError:
            exc_raised = True

        self.assertTrue(exc_raised)
        self.assertTrue(self.log_written)

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryDb, self).setUp()
        db_api._ENGINE = self.orig_engine
        self.stubs.UnsetAll()


class TestRegistryAPI(base.IsolatedUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryAPI, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)
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
             'min_disk': 0,
             'min_ram': 0,
             'size': 13,
             'location': "file:///%s/%s" % (self.test_dir, UUID1),
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
             'min_disk': 5,
             'min_ram': 256,
             'size': 19,
             'location': "file:///%s/%s" % (self.test_dir, UUID2),
             'properties': {}}]
        self.context = glance.context.RequestContext(is_admin=True)
        db_api.configure_db()
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryAPI, self).tearDown()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)
            # We write a fake image file to the filesystem
            with open("%s/%s" % (self.test_dir, fixture['id']), 'wb') as image:
                image.write("chunk00000remainder")
                image.flush()

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_show(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns the expected image
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'min_ram': 256,
                   'min_disk': 5,
                   'checksum': None}
        req = webob.Request.blank('/images/%s' % UUID2)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        image = res_dict['image']
        for k, v in fixture.iteritems():
            self.assertEquals(v, image[k])

    def test_show_unknown(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for an unknown image id
        """
        req = webob.Request.blank('/images/%s' % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

    def test_show_invalid(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for an invalid (therefore unknown) image id
        """
        req = webob.Request.blank('/images/%s' % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

    def test_show_deleted_image_as_admin(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 200 for deleted image to admin user.
        """
        # Delete image #2
        req = webob.Request.blank('/images/%s' % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s' % UUID2)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

    def test_show_deleted_image_as_nonadmin(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for deleted image to non-admin user.
        """
        # Delete image #2
        req = webob.Request.blank('/images/%s' % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                            is_admin=False)
        req = webob.Request.blank('/images/%s' % UUID2)
        res = req.get_response(api)
        self.assertEquals(res.status_int, 404)

    def test_get_root(self):
        """
        Tests that the root registry API returns "index",
        which is a list of public images
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}
        req = webob.Request.blank('/')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_index(self):
        """
        Tests that the /images registry API returns list of
        public images
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_index_marker(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a marker query param
        """
        time1 = timeutils.utcnow() + datetime.timedelta(seconds=5)
        time2 = timeutils.utcnow() + datetime.timedelta(seconds=4)
        time3 = timeutils.utcnow()

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

        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time3}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?marker=%s' % UUID4)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        # should be sorted by created_at desc, id desc
        # page should start after marker 4
        self.assertEquals(len(images), 2)
        self.assertEquals(images[0]['id'], UUID5)
        self.assertEquals(images[1]['id'], UUID2)

    def test_get_index_unknown_marker(self):
        """
        Tests that the /images registry API returns a 400
        when an unknown marker is provided
        """
        req = webob.Request.blank('/images?marker=%s' % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_malformed_marker(self):
        """
        Tests that the /images registry API returns a 400
        when a malformed marker is provided
        """
        req = webob.Request.blank('/images?marker=4')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)
        self.assertTrue('marker' in res.body)

    def test_get_index_limit(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertTrue(images[0]['id'], UUID4)

    def test_get_index_limit_negative(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        req = webob.Request.blank('/images?limit=-1')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_limit_non_int(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        req = webob.Request.blank('/images?limit=a')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_limit_marker(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to limit and marker query params
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?marker=%s&limit=1' % UUID3)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(images[0]['id'], UUID2)

    def test_get_index_filter_name(self):
        """
        Tests that the /images registry API returns list of
        public images that have a specific name. This is really a sanity
        check, filtering is tested more in-depth using /images/detail
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?name=new name! #123')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_index_sort_default_created_at_desc(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a default sort key/dir
        """
        time1 = timeutils.utcnow() + datetime.timedelta(seconds=5)
        time2 = timeutils.utcnow() + datetime.timedelta(seconds=4)
        time3 = timeutils.utcnow()

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

        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time3}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 4)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID5)
        self.assertEquals(images[3]['id'], UUID2)

    def test_get_index_bad_sort_key(self):
        """Ensure a 400 is returned when a bad sort_key is provided."""
        req = webob.Request.blank('/images?sort_key=asdf')
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_get_index_bad_sort_dir(self):
        """Ensure a 400 is returned when a bad sort_dir is provided."""
        req = webob.Request.blank('/images?sort_dir=asdf')
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

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

        req = webob.Request.blank('/images?sort_key=name&sort_dir=asc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        req = webob.Request.blank('/images?sort_key=status&sort_dir=desc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        req = webob.Request.blank('/images?sort_key=disk_format&sort_dir=asc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        url = '/images?sort_key=container_format&sort_dir=desc'
        req = webob.Request.blank(url)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        url = '/images?sort_key=size&sort_dir=asc'
        req = webob.Request.blank(url)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        req = webob.Request.blank('/images?sort_key=created_at&sort_dir=asc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
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

        req = webob.Request.blank('/images?sort_key=updated_at&sort_dir=desc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID4)
        self.assertEquals(images[2]['id'], UUID2)

    def test_get_details(self):
        """
        Tests that the /images/detail registry API returns
        a mapping containing a list of detailed image information
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'size': 19,
                   'min_disk': 5,
                   'min_ram': 256,
                   'checksum': None,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active'}

        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_details_limit_marker(self):
        """
        Tests that the /images/details registry API returns list of
        public images that conforms to limit and marker query params.
        This functionality is tested more thoroughly on /images, this is
        just a sanity check
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?marker=%s&limit=1' % UUID3)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(images[0]['id'], UUID2)

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images/detail?marker=%s'
                                  % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_details_filter_name(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific name
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

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?name=new name! #123')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_details_filter_status(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific status
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?status=saving')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual('saving', image['status'])

    def test_get_details_filter_container_format(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific container_format
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vdi',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?container_format=ovf')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('ovf', image['container_format'])

    def test_get_details_filter_min_disk(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific min_disk
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'min_disk': 7,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?min_disk=7')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual(7, image['min_disk'])

    def test_get_details_filter_min_ram(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific min_ram
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'min_ram': 514,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?min_ram=514')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual(514, image['min_ram'])

    def test_get_details_filter_disk_format(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific disk_format
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?disk_format=vhd')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('vhd', image['disk_format'])

    def test_get_details_filter_size_min(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size greater than or equal to size_min
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?size_min=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] >= 19)

    def test_get_details_filter_size_max(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?size_max=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] <= 19)

    def test_get_details_filter_size_min_max(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        and greater than or equal to size_min
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #5',
                         'size': 6,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?size_min=18&size_max=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] <= 19 and image['size'] >= 18)

    def test_get_details_filter_changes_since(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        """
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)

        dt2 = timeutils.utcnow() + datetime.timedelta(1)
        iso2 = timeutils.isotime(dt2)

        image_ts = timeutils.utcnow() + datetime.timedelta(2)
        hour_before = image_ts.strftime('%Y-%m-%dT%H:%M:%S%%2B01:00')
        hour_after = image_ts.strftime('%Y-%m-%dT%H:%M:%S-01:00')

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
                         'created_at': image_ts,
                         'updated_at': image_ts}

        db_api.image_create(self.context, extra_fixture)

        # Check a standard list, 4 images in db (2 deleted)
        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 2)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID2)

        # Expect 3 images (1 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso1)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID3)  # deleted
        self.assertEqual(images[2]['id'], UUID2)

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso2)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 1)
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_before)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 1)
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_after)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 0)

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso4)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 0)

        # Bad request (empty changes-since param)
        req = webob.Request.blank('/images/detail?changes-since=')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

        # Bad request (invalid changes-since param)
        req = webob.Request.blank('/images/detail?changes-since=2011-09-05')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_details_filter_property(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific custom property
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None,
                         'properties': {'prop_123': 'v a'}}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None,
                         'properties': {'prop_123': 'v b'}}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?property-prop_123=v%20a')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual('v a', image['properties']['prop_123'])

    def test_get_details_filter_public_none(self):
        """
        Tests that the /images/detail registry API returns list of
        all images if is_public none is passed
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?is_public=None')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 3)

    def test_get_details_filter_public_false(self):
        """
        Tests that the /images/detail registry API returns list of
        private images if is_public false is passed
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?is_public=False')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual(False, image['is_public'])

    def test_get_details_filter_public_true(self):
        """
        Tests that the /images/detail registry API returns list of
        public images if is_public true is passed (same as default)
        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': False,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?is_public=True')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual(True, image['is_public'])

    def test_get_details_sort_name_asc(self):
        """
        Tests that the /images/details registry API returns list of
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

        req = webob.Request.blank('/images/detail?sort_key=name&sort_dir=asc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID4)

    def test_create_image(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k, v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

        # Test status was updated properly
        self.assertEquals('active', res_dict['image']['status'])

    def test_create_image_with_min_disk(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'min_disk': 5,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        self.assertEquals(5, res_dict['image']['min_disk'])

    def test_create_image_with_min_ram(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'min_ram': 256,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        self.assertEquals(256, res_dict['image']['min_ram'])

    def test_create_image_with_min_ram_default(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        self.assertEquals(0, res_dict['image']['min_ram'])

    def test_create_image_with_min_disk_default(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        self.assertEquals(0, res_dict['image']['min_disk'])

    def test_create_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': _gen_uuid(),
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'bad status'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid image status' in res.body)

    def test_create_image_with_bad_id(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = {'id': 'asdf',
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'min_disk': 5,
                   'min_ram': 256,
                   'disk_format': 'raw'}

        req = webob.Request.blank('/images/%s' % UUID2)

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        self.assertNotEquals(res_dict['image']['created_at'],
                             res_dict['image']['updated_at'])

        for k, v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

    def test_update_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to update
        non-existing image
        """
        fixture = {'status': 'killed'}

        req = webob.Request.blank('/images/%s' % _gen_uuid())

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_update_image_with_bad_status(self):
        """Tests that exception raised trying to set a bad status"""
        fixture = {'status': 'invalid'}

        req = webob.Request.blank('/images/%s' % UUID2)

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid image status' in res.body)

    def test_delete_image(self):
        """Tests that the /images DELETE registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        orig_num_images = len(res_dict['images'])

        # Delete image #2
        req = webob.Request.blank('/images/%s' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        # Verify one less image
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        new_num_images = len(res_dict['images'])
        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_response(self):
        """Tests that the registry API delete returns the image metadata"""

        image = self.FIXTURES[0]
        req = webob.Request.blank('/images/%s' % image['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)
        deleted_image = json.loads(res.body)['image']

        self.assertEquals(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

    def test_delete_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to delete
        non-existing image
        """
        req = webob.Request.blank('/images/%s' % _gen_uuid())
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        memb_list = json.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEquals(num_members, 0)

    def test_get_image_members_not_existing(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image
        """
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_get_member_images(self):
        """
        Tests image listing for members
        """
        req = webob.Request.blank('/shared-images/pattieblack')
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        memb_list = json.loads(res.body)
        num_members = len(memb_list['shared_images'])
        self.assertEquals(num_members, 0)

    def test_replace_members(self):
        """
        Tests replacing image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_delete_member_invalid(self):
        """
        Tests deleting a invalid/non existing member raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
        self.assertTrue('Membership could not be found' in res.body)


class TestGlanceAPI(base.IsolatedUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestGlanceAPI, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper))
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
             'location': "file:///%s/%s" % (self.test_dir, UUID1),
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
             'location': "file:///%s/%s" % (self.test_dir, UUID2),
             'properties': {}}]
        self.context = glance.context.RequestContext(is_admin=True)
        db_api.configure_db()
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        super(TestGlanceAPI, self).tearDown()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)
            # We write a fake image file to the filesystem
            with open("%s/%s" % (self.test_dir, fixture['id']), 'wb') as image:
                image.write("chunk00000remainder")
                image.flush()

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def _do_test_defaulted_format(self, format_key, format_value):
        fixture_headers = {'x-image-meta-name': 'defaulted',
                           'x-image-meta-location': 'http://localhost:0/image',
                           format_key: format_value}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)
        res_body = json.loads(res.body)['image']
        self.assertEquals(format_value, res_body['disk_format'])
        self.assertEquals(format_value, res_body['container_format'])

    def test_defaulted_amazon_format(self):
        for key in ('x-image-meta-disk-format',
                    'x-image-meta-container-format'):
            for value in ('aki', 'ari', 'ami'):
                self._do_test_defaulted_format(key, value)

    def test_bad_disk_format(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'invalid',
            'x-image-meta-container-format': 'ami',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body, res.body)

    def test_create_with_location_no_container_format(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'vhd',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_bad_container_format(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'vhd',
            'x-image-meta-container-format': 'invalid',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_bad_image_size(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://example.com/image.tar.gz',
            'x-image-meta-disk-format': 'vhd',
            'x-image-meta-size': 'invalid',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Incoming image size' in res.body)

    def test_bad_image_name(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'X' * 256,
            'x-image-meta-location': 'http://example.com/image.tar.gz',
            'x-image-meta-disk-format': 'vhd',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_add_image_no_location_no_image_as_body(self):
        """Tests creates a queued image for no body and no loc header"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])
        image_id = res_body['id']

        # Test that we are able to edit the Location field
        # per LP Bug #911599

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-location'] = 'http://localhost:0/images/123'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)

        res_body = json.loads(res.body)['image']
        # Once the location is set, the image should be activated
        # see LP Bug #939484
        self.assertEquals('active', res_body['status'])
        self.assertFalse('location' in res_body)  # location never shown

    def test_add_image_no_location_no_content_type(self):
        """Tests creates a queued image for no body and no loc header"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = "chunk00000remainder"
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_image_size_header_too_big(self):
        """Tests raises BadRequest for supplied image size that is too big"""
        fixture_headers = {'x-image-meta-size': CONF.image_size_cap + 1,
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_image_size_chunked_data_too_big(self):
        self.config(image_size_cap=512)
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'ami',
            'x-image-meta-disk_format': 'ami',
            'transfer-encoding': 'chunked',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'

        req.body_file = StringIO.StringIO('X' * (CONF.image_size_cap + 1))
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_image_size_data_too_big(self):
        self.config(image_size_cap=512)
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'ami',
            'x-image-meta-disk_format': 'ami',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'

        req.body = 'X' * (CONF.image_size_cap + 1)
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_image_zero_size(self):
        """Tests creating an active image with explicitly zero size"""
        fixture_headers = {'x-image-meta-disk-format': 'ami',
                           'x-image-meta-container-format': 'ami',
                           'x-image-meta-size': '0',
                           'x-image-meta-name': 'empty image'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('active', res_body['status'])
        image_id = res_body['id']

        # GET empty image
        req = webob.Request.blank("/images/%s" % image_id)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(len(res.body), 0)

    def test_add_image_checksum_mismatch(self):
        fixture_headers = {
            'x-image-meta-checksum': 'asdf',
            'x-image-meta-size': '4',
            'x-image-meta-name': 'fake image #3',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "XXXX"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_image_bad_store(self):
        """Tests raises BadRequest for invalid store header"""
        fixture_headers = {'x-image-meta-store': 'bad',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_add_image_basic_file_store(self):
        """Tests to add a basic image in the file store"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        # Test that the Location: header is set to the URI to
        # edit the newly-created image, as required by APP.
        # See LP Bug #719825
        self.assertTrue('location' in res.headers,
                        "'location' not in response headers.\n"
                        "res.headerlist = %r" % res.headerlist)
        res_body = json.loads(res.body)['image']
        self.assertTrue('/images/%s' % res_body['id']
                        in res.headers['location'])
        self.assertEquals('active', res_body['status'])
        image_id = res_body['id']

        # Test that we are NOT able to edit the Location field
        # per LP Bug #911599

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-location'] = 'http://example.com/images/123'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.BAD_REQUEST)

    def test_add_image_unauthorized(self):
        rules = {"add_image": '!'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_add_public_image_unauthorized(self):
        rules = {"add_image": '@', "publicize_image": '!'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-is-public': 'true',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def _do_test_post_image_content_missing_format(self, missing):
        """Tests creation of an image with missing format"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        header = 'x-image-meta-' + missing.replace('_', '-')

        del fixture_headers[header]

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.BAD_REQUEST)

    def test_post_image_content_missing_disk_format(self):
        """Tests creation of an image with missing disk format"""
        self._do_test_post_image_content_missing_format('disk_format')

    def test_post_image_content_missing_container_type(self):
        """Tests creation of an image with missing container format"""
        self._do_test_post_image_content_missing_format('container_format')

    def _do_test_put_image_content_missing_format(self, missing):
        """Tests delayed activation of an image with missing format"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        header = 'x-image-meta-' + missing.replace('_', '-')

        del fixture_headers[header]

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])
        image_id = res_body['id']

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.BAD_REQUEST)

    def test_put_image_content_missing_disk_format(self):
        """Tests delayed activation of image with missing disk format"""
        self._do_test_put_image_content_missing_format('disk_format')

    def test_put_image_content_missing_container_type(self):
        """Tests delayed activation of image with missing container format"""
        self._do_test_put_image_content_missing_format('container_format')

    def test_update_deleted_image(self):
        """Tests that exception raised trying to update a deleted image"""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        fixture = {'name': 'test_del_img'}
        req = webob.Request.blank('/images/%s' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)
        self.assertTrue('Forbidden to update deleted image' in res.body)

    def test_delete_deleted_image(self):
        """Tests that exception raised trying to delete a deleted image"""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)
        self.assertTrue('Forbidden to delete a deleted image' in res.body)

    def test_register_and_upload(self):
        """
        Test that the process of registering an image with
        some metadata, then uploading an image file with some
        more metadata doesn't mark the original metadata deleted
        :see LP Bug#901534
        """
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-property-key1': 'value1'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)
        res_body = json.loads(res.body)['image']

        self.assertTrue('id' in res_body)

        image_id = res_body['id']
        self.assertTrue('/images/%s' % image_id in res.headers['location'])

        # Verify the status is queued
        self.assertTrue('status' in res_body)
        self.assertEqual('queued', res_body['status'])

        # Check properties are not deleted
        self.assertTrue('properties' in res_body)
        self.assertTrue('key1' in res_body['properties'])
        self.assertEqual('value1', res_body['properties']['key1'])

        # Now upload the image file along with some more
        # metadata and verify original metadata properties
        # are not marked deleted
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['x-image-meta-property-key2'] = 'value2'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)

        # Verify the status is queued
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)
        self.assertTrue('x-image-meta-property-key1' in res.headers,
                        "Did not find required property in headers. "
                        "Got headers: %r" % res.headers)
        self.assertEqual("active", res.headers['x-image-meta-status'])

    def test_disable_purge_props(self):
        """
        Test the special x-glance-registry-purge-props header controls
        the purge property behaviour of the registry.
        :see LP Bug#901534
        """
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-property-key1': 'value1'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)
        res_body = json.loads(res.body)['image']

        self.assertTrue('id' in res_body)

        image_id = res_body['id']
        self.assertTrue('/images/%s' % image_id in res.headers['location'])

        # Verify the status is queued
        self.assertTrue('status' in res_body)
        self.assertEqual('active', res_body['status'])

        # Check properties are not deleted
        self.assertTrue('properties' in res_body)
        self.assertTrue('key1' in res_body['properties'])
        self.assertEqual('value1', res_body['properties']['key1'])

        # Now update the image, setting new properties without
        # passing the x-glance-registry-purge-props header and
        # verify that original properties are marked deleted.
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-property-key2'] = 'value2'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)

        # Verify the original property no longer in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)
        self.assertTrue('x-image-meta-property-key2' in res.headers,
                        "Did not find required property in headers. "
                        "Got headers: %r" % res.headers)
        self.assertFalse('x-image-meta-property-key1' in res.headers,
                         "Found property in headers that was not expected. "
                         "Got headers: %r" % res.headers)

        # Now update the image, setting new properties and
        # passing the x-glance-registry-purge-props header with
        # a value of "false" and verify that second property
        # still appears in headers.
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-property-key3'] = 'value3'
        req.headers['x-glance-registry-purge-props'] = 'false'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)

        # Verify the second and third property in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.OK)
        self.assertTrue('x-image-meta-property-key2' in res.headers,
                        "Did not find required property in headers. "
                        "Got headers: %r" % res.headers)
        self.assertTrue('x-image-meta-property-key3' in res.headers,
                        "Did not find required property in headers. "
                        "Got headers: %r" % res.headers)

    def test_publicize_image_unauthorized(self):
        """Create a non-public image then fail to make public"""
        rules = {"add_image": '@', "publicize_image": '!'}
        self.set_policy_rules(rules)

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-is-public': 'false',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'PUT'
        req.headers['x-image-meta-is-public'] = 'true'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_update_image_size_header_too_big(self):
        """Tests raises BadRequest for supplied image size that is too big"""
        fixture_headers = {'x-image-meta-size': CONF.image_size_cap + 1}

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'PUT'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_update_image_size_data_too_big(self):
        self.config(image_size_cap=512)

        fixture_headers = {'content-type': 'application/octet-stream'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'PUT'

        req.body = 'X' * (CONF.image_size_cap + 1)
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_update_image_size_chunked_data_too_big(self):
        self.config(image_size_cap=512)

        # Create new image that has no data
        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.headers['x-image-meta-name'] = 'something'
        req.headers['x-image-meta-container_format'] = 'ami'
        req.headers['x-image-meta-disk_format'] = 'ami'
        res = req.get_response(self.api)
        image_id = json.loads(res.body)['image']['id']

        fixture_headers = {
            'content-type': 'application/octet-stream',
            'transfer-encoding': 'chunked',
        }
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'

        req.body_file = StringIO.StringIO('X' * (CONF.image_size_cap + 1))
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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

        req = webob.Request.blank('/images?sort_key=name&sort_dir=asc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEquals(images[0]['id'], UUID3)
        self.assertEquals(images[1]['id'], UUID2)
        self.assertEquals(images[2]['id'], UUID4)

    def test_get_details_filter_changes_since(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        """
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)

        dt2 = timeutils.utcnow() + datetime.timedelta(1)
        iso2 = timeutils.isotime(dt2)

        image_ts = timeutils.utcnow() + datetime.timedelta(2)
        hour_before = image_ts.strftime('%Y-%m-%dT%H:%M:%S%%2B01:00')
        hour_after = image_ts.strftime('%Y-%m-%dT%H:%M:%S-01:00')

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
                         'created_at': image_ts,
                         'updated_at': image_ts}

        db_api.image_create(self.context, extra_fixture)

        # Check a standard list, 4 images in db (2 deleted)
        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 2)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID2)

        # Expect 3 images (1 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso1)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID3)  # deleted
        self.assertEqual(images[2]['id'], UUID2)

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso2)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 1)
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_before)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 1)
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_after)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 0)

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso4)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)
        images = res_dict['images']
        self.assertEquals(len(images), 0)

        # Bad request (empty changes-since param)
        req = webob.Request.blank('/images/detail?changes-since=')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

        # Bad request (invalid changes-since param)
        req = webob.Request.blank('/images/detail?changes-since=2011-09-05')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_images_detailed_unauthorized(self):
        rules = {"get_images": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_get_images_unauthorized(self):
        rules = {"get_images": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_store_location_not_revealed(self):
        """
        Test that the internal store location is NOT revealed
        through the API server
        """
        # Check index and details...
        for url in ('/images', '/images/detail'):
            req = webob.Request.blank(url)
            res = req.get_response(self.api)
            self.assertEquals(res.status_int, 200)
            res_dict = json.loads(res.body)

            images = res_dict['images']
            num_locations = sum([1 for record in images
                                if 'location' in record.keys()])
            self.assertEquals(0, num_locations, images)

        # Check GET
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertFalse('X-Image-Meta-Location' in res.headers)

        # Check HEAD
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertFalse('X-Image-Meta-Location' in res.headers)

        # Check PUT
        req = webob.Request.blank("/images/%s" % UUID2)
        req.body = res.body
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_body = json.loads(res.body)
        self.assertFalse('location' in res_body['image'])

        # Check POST
        req = webob.Request.blank("/images")
        headers = {'x-image-meta-location': 'http://localhost',
                   'x-image-meta-disk-format': 'vhd',
                   'x-image-meta-container-format': 'ovf',
                   'x-image-meta-name': 'fake image #3'}
        for k, v in headers.iteritems():
            req.headers[k] = v
        req.method = 'POST'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 201)
        res_body = json.loads(res.body)
        self.assertFalse('location' in res_body['image'])

    def test_image_is_checksummed(self):
        """Test that the image contents are checksummed properly"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}
        image_contents = "chunk00000remainder"
        image_checksum = hashlib.md5(image_contents).hexdigest()

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals(image_checksum, res_body['checksum'],
                          "Mismatched checksum. Expected %s, got %s" %
                          (image_checksum, res_body['checksum']))

    def test_etag_equals_checksum_header(self):
        """Test that the ETag header matches the x-image-meta-checksum"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}
        image_contents = "chunk00000remainder"
        image_checksum = hashlib.md5(image_contents).hexdigest()

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        image = json.loads(res.body)['image']

        # HEAD the image and check the ETag equals the checksum header...
        expected_headers = {'x-image-meta-checksum': image_checksum,
                            'etag': image_checksum}
        req = webob.Request.blank("/images/%s" % image['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key in expected_headers.keys():
            self.assertTrue(key in res.headers,
                            "required header '%s' missing from "
                            "returned headers" % key)
        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_bad_checksum_prevents_image_creation(self):
        """Test that the image contents are checksummed properly"""
        image_contents = "chunk00000remainder"
        bad_checksum = hashlib.md5("invalid").hexdigest()
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-checksum': bad_checksum,
                           'x-image-meta-is-public': 'true'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

        # Test that only one image was returned (that already exists)
        req = webob.Request.blank("/images")
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        images = json.loads(res.body)['images']
        self.assertEqual(len(images), 1)

    def test_image_meta(self):
        """Test for HEAD /images/<ID>"""
        expected_headers = {'x-image-meta-id': UUID2,
                            'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_image_meta_unauthorized(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_show_image_basic(self):
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(res.content_type, 'application/octet-stream')
        self.assertEqual('chunk00000remainder', res.body)

    def test_show_non_exists_image(self):
        req = webob.Request.blank("/images/%s" % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_show_image_unauthorized(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 403)

    def test_show_image_unauthorized_download(self):
        rules = {"download_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 403)

    def test_delete_image(self):
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code,
                          res.body)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEquals(res.headers['x-image-meta-deleted'], 'True')
        self.assertEquals(res.headers['x-image-meta-status'], 'deleted')

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/%s" % _gen_uuid())
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_queued_image(self):
        """Delete an image in a queued state

        Bug #747799 demonstrated that trying to DELETE an image
        that had had its save process killed manually results in failure
        because the location attribute is None.

        Bug #1048851 demonstrated that the status was not properly
        being updated to 'deleted' from 'queued'.
        """
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s' % res_body['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEquals(res.headers['x-image-meta-deleted'], 'True')
        self.assertEquals(res.headers['x-image-meta-status'], 'deleted')

    def test_delete_queued_image_delayed_delete(self):
        """Delete an image in a queued state when delayed_delete is on

        Bug #1048851 demonstrated that the status was not properly
        being updated to 'deleted' from 'queued'.
        """
        self.config(delayed_delete=True)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s' % res_body['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEquals(res.headers['x-image-meta-deleted'], 'True')
        self.assertEquals(res.headers['x-image-meta-status'], 'deleted')

    def test_delete_protected_image(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-protected': 'True'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.FORBIDDEN)

    def test_delete_image_unauthorized(self):
        rules = {"delete_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images/detail?marker=%s' % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        memb_list = json.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEquals(num_members, 0)

    def test_get_image_members_not_existing(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image
        """
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_get_member_images(self):
        """
        Tests image listing for members
        """
        req = webob.Request.blank('/shared-images/pattieblack')
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        memb_list = json.loads(res.body)
        num_members = len(memb_list['shared_images'])
        self.assertEquals(num_members, 0)

    def test_replace_members(self):
        """
        Tests replacing image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=False)
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)


class TestImageSerializer(base.IsolatedUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestImageSerializer, self).setUp()
        self.receiving_user = 'fake_user'
        self.receiving_tenant = 2
        self.context = glance.context.RequestContext(
                is_admin=True,
                user=self.receiving_user,
                tenant=self.receiving_tenant)
        self.serializer = images.ImageSerializer()

        def image_iter():
            for x in ['chunk', '678911234', '56789']:
                yield x

        self.FIXTURE = {
            'image_iterator': image_iter(),
            'image_meta': {
                'id': UUID2,
                'name': 'fake image #2',
                'status': 'active',
                'disk_format': 'vhd',
                'container_format': 'ovf',
                'is_public': True,
                'created_at': timeutils.utcnow(),
                'updated_at': timeutils.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'checksum': '06ff575a2856444fbe93100157ed74ab92eb7eff',
                'size': 19,
                'owner': _gen_uuid(),
                'location': "file:///tmp/glance-tests/2",
                'properties': {},
            }
        }

    def test_meta(self):
        exp_headers = {'x-image-meta-id': UUID2,
                       'x-image-meta-location': 'file:///tmp/glance-tests/2',
                       'ETag': self.FIXTURE['image_meta']['checksum'],
                       'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        req.remote_addr = "1.2.3.4"
        req.context = self.context
        response = webob.Response(request=req)
        self.serializer.meta(response, self.FIXTURE)
        for key, value in exp_headers.iteritems():
            self.assertEquals(value, response.headers[key])

    def test_meta_utf8(self):
        # We get unicode strings from JSON, and therefore all strings in the
        # metadata will actually be unicode when handled internally. But we
        # want to output utf-8.
        FIXTURE = {
            'image_meta': {
                'id': unicode(UUID2),
                'name': u'fake image #2 with utf-8 éàè',
                'status': u'active',
                'disk_format': u'vhd',
                'container_format': u'ovf',
                'is_public': True,
                'created_at': timeutils.utcnow(),
                'updated_at': timeutils.utcnow(),
                'deleted_at': None,
                'deleted': False,
                'checksum': u'06ff575a2856444fbe93100157ed74ab92eb7eff',
                'size': 19,
                'owner': unicode(_gen_uuid()),
                'location': u"file:///tmp/glance-tests/2",
                'properties': {
                    u'prop_éé': u'ça marche',
                    u'prop_çé': u'çé',
                }
            }
        }
        exp_headers = {'x-image-meta-id': UUID2.encode('utf-8'),
                       'x-image-meta-location': 'file:///tmp/glance-tests/2',
                       'ETag': '06ff575a2856444fbe93100157ed74ab92eb7eff',
                       'x-image-meta-size': '19',  # str, not int
                       'x-image-meta-name': 'fake image #2 with utf-8 éàè',
                       'x-image-meta-property-prop_éé': 'ça marche',
                       'x-image-meta-property-prop_çé': u'çé'.encode('utf-8')}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        req.remote_addr = "1.2.3.4"
        req.context = self.context
        response = webob.Response(request=req)
        self.serializer.meta(response, FIXTURE)
        self.assertNotEqual(type(FIXTURE['image_meta']['name']),
                            type(response.headers['x-image-meta-name']))
        self.assertEqual(response.headers['x-image-meta-name'].decode('utf-8'),
                         FIXTURE['image_meta']['name'])
        for key, value in exp_headers.iteritems():
            self.assertEquals(value, response.headers[key])

        FIXTURE['image_meta']['properties'][u'prop_bad'] = 'çé'
        self.assertRaises(UnicodeDecodeError,
                          self.serializer.meta, response, FIXTURE)

    def test_show(self):
        exp_headers = {'x-image-meta-id': UUID2,
                       'x-image-meta-location': 'file:///tmp/glance-tests/2',
                       'ETag': self.FIXTURE['image_meta']['checksum'],
                       'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.context = self.context
        response = webob.Response(request=req)
        self.serializer.show(response, self.FIXTURE)
        for key, value in exp_headers.iteritems():
            self.assertEquals(value, response.headers[key])

        self.assertEqual(response.body, 'chunk67891123456789')

    def test_show_notify(self):
        """Make sure an eventlet posthook for notify_image_sent is added."""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.context = self.context
        response = webob.Response(request=req)
        response.request.environ['eventlet.posthooks'] = []

        self.serializer.show(response, self.FIXTURE)

        #just make sure the app_iter is called
        for chunk in response.app_iter:
            pass

        self.assertNotEqual(response.request.environ['eventlet.posthooks'], [])

    def test_image_send_notification(self):
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.remote_addr = '1.2.3.4'
        req.context = self.context

        image_meta = self.FIXTURE['image_meta']
        called = {"notified": False}
        expected_payload = {
            'bytes_sent': 19,
            'image_id': UUID2,
            'owner_id': image_meta['owner'],
            'receiver_tenant_id': self.receiving_tenant,
            'receiver_user_id': self.receiving_user,
            'destination_ip': '1.2.3.4',
        }

        def fake_info(_event_type, _payload):
            self.assertEqual(_payload, expected_payload)
            called['notified'] = True

        self.stubs.Set(self.serializer.notifier, 'info', fake_info)

        glance.api.common.image_send_notification(19, 19, image_meta, req,
                                                  self.serializer.notifier)

        self.assertTrue(called['notified'])

    def test_image_send_notification_error(self):
        """Ensure image.send notification is sent on error."""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.remote_addr = '1.2.3.4'
        req.context = self.context

        image_meta = self.FIXTURE['image_meta']
        called = {"notified": False}
        expected_payload = {
            'bytes_sent': 17,
            'image_id': UUID2,
            'owner_id': image_meta['owner'],
            'receiver_tenant_id': self.receiving_tenant,
            'receiver_user_id': self.receiving_user,
            'destination_ip': '1.2.3.4',
        }

        def fake_error(_event_type, _payload):
            self.assertEqual(_payload, expected_payload)
            called['notified'] = True

        self.stubs.Set(self.serializer.notifier, 'error', fake_error)

        #expected and actually sent bytes differ
        glance.api.common.image_send_notification(17, 19, image_meta, req,
                                                  self.serializer.notifier)

        self.assertTrue(called['notified'])
