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
import hashlib
import httplib
import os
import json
import unittest

import stubout
import webob

from glance.api import v1 as server
from glance.common import context
from glance.registry import context as rcontext
from glance.registry import server as rserver
from glance.registry.db import api as db_api
from glance.registry.db import models as db_models
from glance.tests import stubs

OPTIONS = {'sql_connection': 'sqlite://',
           'verbose': False,
           'debug': False,
           'registry_host': '0.0.0.0',
           'registry_port': '9191',
           'default_store': 'file',
           'filesystem_store_datadir': stubs.FAKE_FILESYSTEM_ROOTDIR,
           'context_class': 'glance.registry.context.RequestContext'}


class TestRegistryAPI(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_filesystem_backend()
        self.api = context.ContextMiddleware(rserver.API(OPTIONS), OPTIONS)
        self.FIXTURES = [
            {'id': 1,
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
             'size': 13,
             'location': "swift://user:passwd@acct/container/obj.tar.0",
             'properties': {'type': 'kernel'}},
            {'id': 2,
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
             'size': 19,
             'location': "file:///tmp/glance-tests/2",
             'properties': {}}]
        self.context = rcontext.RequestContext(is_admin=True)
        db_api.configure_db(OPTIONS)
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_show(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns the expected image
        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}
        req = webob.Request.blank('/images/2')
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
        req = webob.Request.blank('/images/3')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

    def test_show_invalid(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for an invalid (therefore unknown) image id
        """
        req = webob.Request.blank('/images/2a')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

    def test_get_root(self):
        """
        Tests that the root registry API returns "index",
        which is a list of public images
        """
        fixture = {'id': 2,
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
        fixture = {'id': 2,
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
        time1 = datetime.datetime.utcnow() + datetime.timedelta(seconds=5)
        time2 = datetime.datetime.utcnow()

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time2}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?marker=4')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        # should be sorted by created_at desc, id desc
        # page should start after marker 4
        self.assertEquals(len(images), 3)
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 5)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_index_invalid_marker(self):
        """
        Tests that the /images registry API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images?marker=10')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_limit(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertTrue(int(images[0]['id']), 4)

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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?marker=3&limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(int(images[0]['id']), 2)

    def test_get_index_filter_name(self):
        """
        Tests that the /images registry API returns list of
        public images that have a specific name. This is really a sanity
        check, filtering is tested more in-depth using /images/detail
        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        time1 = datetime.datetime.utcnow() + datetime.timedelta(seconds=5)
        time2 = datetime.datetime.utcnow()

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time2}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 4)
        self.assertEquals(int(images[0]['id']), 4)
        self.assertEquals(int(images[1]['id']), 3)
        self.assertEquals(int(images[2]['id']), 5)
        self.assertEquals(int(images[3]['id']), 2)

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

    def test_get_index_sort_id_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by id in descending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images?sort_key=id&sort_dir=desc')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        res_dict = json.loads(res.body)

        images = res_dict['images']
        self.assertEquals(len(images), 3)
        self.assertEquals(int(images[0]['id']), 4)
        self.assertEquals(int(images[1]['id']), 3)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_index_sort_name_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by name in
        ascending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 2)
        self.assertEquals(int(images[2]['id']), 4)

    def test_get_index_sort_status_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by status in
        descending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'queued',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 4)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_index_sort_disk_format_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by disk_format in
        ascending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 4)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_index_sort_container_format_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by container_format in
        descending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 2)
        self.assertEquals(int(images[1]['id']), 4)
        self.assertEquals(int(images[2]['id']), 3)

    def test_get_index_sort_size_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by size in ascending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 100,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 4)
        self.assertEquals(int(images[1]['id']), 2)
        self.assertEquals(int(images[2]['id']), 3)

    def test_get_index_sort_created_at_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by created_at in ascending order.
        """
        now = datetime.datetime.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': time1}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 2)
        self.assertEquals(int(images[1]['id']), 4)
        self.assertEquals(int(images[2]['id']), 3)

    def test_get_index_sort_updated_at_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by updated_at in descending order.
        """
        now = datetime.datetime.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        extra_fixture = {'id': 3,
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

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 4)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_details(self):
        """
        Tests that the /images/detail registry API returns
        a mapping containing a list of detailed image information
        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'size': 19,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/images/detail?marker=3&limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(int(images[0]['id']), 2)

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images/detail?marker=10')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_details_filter_name(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific name
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vdi',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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

    def test_get_details_filter_disk_format(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific disk_format
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 5,
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

    def test_get_details_filter_property(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific custom property
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None,
                         'properties': {'prop_123': 'v a'}}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        extra_fixture = {'id': 3,
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
        extra_fixture = {'id': 3,
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
        extra_fixture = {'id': 3,
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
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 2)
        self.assertEquals(int(images[2]['id']), 4)

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

        # Test ID auto-assigned properly
        self.assertEquals(3, res_dict['image']['id'])

        # Test status was updated properly
        self.assertEquals('active', res_dict['image']['status'])

    def test_create_image_with_bad_container_format(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'invalid'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_create_image_with_bad_disk_format(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'invalid',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body)

    def test_create_image_with_mismatched_formats(self):
        """
        Tests that exception raised for bad matching disk and
        container formats
        """
        fixture = {'name': 'fake public image #3',
                   'container_format': 'aki',
                   'disk_format': 'ari'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid mix of disk and container formats'
                        in res.body)

    def test_create_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': 3,
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

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'raw'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k, v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

    def test_update_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to update
        non-existing image
        """
        fixture = {'status': 'killed'}

        req = webob.Request.blank('/images/3')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_update_image_with_bad_status(self):
        """Tests that exception raised trying to set a bad status"""
        fixture = {'status': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid image status' in res.body)

    def test_update_image_with_bad_disk_format(self):
        """Tests that exception raised trying to set a bad disk_format"""
        fixture = {'disk_format': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body)

    def test_update_image_with_bad_container_format(self):
        """Tests that exception raised trying to set a bad container_format"""
        fixture = {'container_format': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_update_image_with_mismatched_formats(self):
        """
        Tests that exception raised for bad matching disk and
        container formats
        """
        fixture = {'container_format': 'ari'}

        req = webob.Request.blank('/images/2')  # Image 2 has disk format 'vhd'

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid mix of disk and container formats'
                        in res.body)

    def test_delete_image(self):
        """Tests that the /images DELETE registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        orig_num_images = len(res_dict['images'])

        # Delete image #2
        req = webob.Request.blank('/images/2')

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

    def test_delete_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to delete
        non-existing image
        """
        req = webob.Request.blank('/images/3')

        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/images/2/members')

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
        req = webob.Request.blank('/images/3/members')

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
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/2/members')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        req = webob.Request.blank('/images/2/members/pattieblack')

        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        req = webob.Request.blank('/images/2/members/pattieblack')

        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)


class TestGlanceAPI(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""

        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_filesystem_backend()
        sql_connection = os.environ.get('GLANCE_SQL_CONNECTION', "sqlite://")
        self.api = context.ContextMiddleware(server.API(OPTIONS), OPTIONS)
        self.FIXTURES = [
            {'id': 1,
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
             'size': 13,
             'location': "swift://user:passwd@acct/container/obj.tar.0",
             'properties': {'type': 'kernel'}},
            {'id': 2,
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
             'size': 19,
             'location': "file:///tmp/glance-tests/2",
             'properties': {}}]
        self.context = rcontext.RequestContext(is_admin=True)
        db_api.configure_db(OPTIONS)
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()
        self.destroy_fixtures()

    def create_fixtures(self):
        for fixture in self.FIXTURES:
            db_api.image_create(self.context, fixture)

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def test_bad_disk_format(self):
        fixture_headers = {'x-image-meta-store': 'bad',
                   'x-image-meta-name': 'bogus',
                   'x-image-meta-location': 'http://example.com/image.tar.gz',
                   'x-image-meta-disk-format': 'invalid',
                   'x-image-meta-container-format': 'ami'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body, res.body)

    def test_bad_container_format(self):
        fixture_headers = {'x-image-meta-store': 'bad',
                   'x-image-meta-name': 'bogus',
                   'x-image-meta-location': 'http://example.com/image.tar.gz',
                   'x-image-meta-disk-format': 'vhd',
                   'x-image-meta-container-format': 'invalid'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

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

        res_body = json.loads(res.body)['image']
        self.assertEquals(res_body['location'],
                          'file:///tmp/glance-tests/3')

        # Test that the Location: header is set to the URI to
        # edit the newly-created image, as required by APP.
        # See LP Bug #719825
        self.assertTrue('location' in res.headers,
                        "'location' not in response headers.\n"
                        "res.headerlist = %r" % res.headerlist)
        self.assertTrue('/images/3' in res.headers['location'])

    def test_get_index_sort_name_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by name in
        ascending order.
        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': 4,
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
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 2)
        self.assertEquals(int(images[2]['id']), 4)

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
        self.assertEquals(res_body['location'],
                          'file:///tmp/glance-tests/3')
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

        # HEAD the image and check the ETag equals the checksum header...
        expected_headers = {'x-image-meta-checksum': image_checksum,
                            'etag': image_checksum}
        req = webob.Request.blank("/images/3")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key in expected_headers.keys():
            self.assertTrue(key in res.headers,
                            "required header '%s' missing from "
                            "returned headers" % key)
        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_bad_checksum_kills_image(self):
        """Test that the image contents are checksummed properly"""
        image_contents = "chunk00000remainder"
        bad_checksum = hashlib.md5("invalid").hexdigest()
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-checksum': bad_checksum}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

        # Test the image was killed...
        expected_headers = {'x-image-meta-id': '3',
                            'x-image-meta-status': 'killed'}
        req = webob.Request.blank("/images/3")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_image_meta(self):
        """Test for HEAD /images/<ID>"""
        expected_headers = {'x-image-meta-id': '2',
                            'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/2")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_show_image_basic(self):
        req = webob.Request.blank("/images/2")
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(res.content_type, 'application/octet-stream')
        self.assertEqual('chunk00000remainder', res.body)

    def test_show_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_image(self):
        req = webob.Request.blank("/images/2")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/2")
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code,
                          res.body)

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_queued_image(self):
        """
        Here, we try to delete an image that is in the queued state.
        Bug #747799 demonstrated that trying to DELETE an image
        that had had its save process killed manually results in failure
        because the location attribute is None.
        """
        # Add an image the way that glance-upload adds an image...
        # by reserving a place in the database for an image without
        # really any attributes or information on the image and then
        # later doing an update with the image body and other attributes.
        # We will stop the process after the reservation stage, then
        # try to delete the image.
        fixture_headers = {'x-image-meta-store': 'file',
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
        req = webob.Request.blank("/images/3")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images/detail?marker=10')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/images/2/members')

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
        req = webob.Request.blank('/images/3/members')

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
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/2/members')

        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        req = webob.Request.blank('/images/2/members/pattieblack')

        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        req = webob.Request.blank('/images/2/members/pattieblack')

        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPUnauthorized.code)
