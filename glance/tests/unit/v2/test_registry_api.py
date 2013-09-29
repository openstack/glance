# vim: tabstop=4 shiftwidth=4 softtabstop=4
# -*- coding: utf-8 -*-

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

import datetime
import json

from oslo.config import cfg
import routes
import webob

import glance.api.common
import glance.common.config
import glance.context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
from glance.registry.api import v2 as rserver
import glance.store.filesystem
from glance.tests.unit import base
from glance.tests import utils as test_utils

CONF = cfg.CONF

_gen_uuid = uuidutils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


class TestRegistryRPC(base.IsolatedUnitTest):

    def setUp(self):
        super(TestRegistryRPC, self).setUp()
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
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID1),
                            'metadata': {}}],
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
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID2),
                            'metadata': {}}],
             'properties': {}}]

        self.context = glance.context.RequestContext(is_admin=True)
        db_api.setup_db_env()
        db_api.get_engine()
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryRPC, self).tearDown()
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
        Tests that registry API endpoint
        returns the expected image
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'min_ram': 256,
                   'min_disk': 5,
                   'checksum': None}
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get',
            'kwargs': {'image_id': UUID2},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]
        image = res_dict
        for k, v in fixture.iteritems():
            self.assertEqual(v, image[k])

    def test_show_unknown(self):
        """
        Tests that the registry API endpoint
        returns a 404 for an unknown image id
        """
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get',
            'kwargs': {'image_id': _gen_uuid()},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res_dict["_error"]["cls"],
                         'glance.common.exception.NotFound')

    def test_get_index(self):
        """
        Tests that the image_get_all command returns list of
        images
        """
        fixture = {'id': UUID2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': fixture},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEqual(v, images[0][k])

    def test_get_index_marker(self):
        """
        Tests that the registry API returns list of
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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID4, "is_public": True},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        images = json.loads(res.body)[0]
        # should be sorted by created_at desc, id desc
        # page should start after marker 4
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]['id'], UUID5)
        self.assertEqual(images[1]['id'], UUID2)

    def test_get_index_marker_and_name_asc(self):
        """Test marker and null name ascending

        Tests that the registry API returns 200
        when a marker and a null name are combined
        ascending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': None,
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'name',
                       'sort_dir': 'asc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 2)

    def test_get_index_marker_and_name_desc(self):
        """Test marker and null name descending

        Tests that the registry API returns 200
        when a marker and a null name are combined
        descending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': None,
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'name',
                       'sort_dir': 'desc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 0)

    def test_get_index_marker_and_disk_format_asc(self):
        """Test marker and null disk format ascending

        Tests that the registry API returns 200
        when a marker and a null disk_format are combined
        ascending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': None,
                         'container_format': 'ovf',
                         'name': 'Fake image',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'disk_format',
                       'sort_dir': 'asc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 2)

    def test_get_index_marker_and_disk_format_desc(self):
        """Test marker and null disk format descending

        Tests that the registry API returns 200
        when a marker and a null disk_format are combined
        descending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': None,
                         'container_format': 'ovf',
                         'name': 'Fake image',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'disk_format',
                       'sort_dir': 'desc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 0)

    def test_get_index_marker_and_container_format_asc(self):
        """Test marker and null container format ascending

        Tests that the registry API returns 200
        when a marker and a null container_format are combined
        ascending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': None,
                         'name': 'Fake image',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'container_format',
                       'sort_dir': 'asc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 2)

    def test_get_index_marker_and_container_format_desc(self):
        """Test marker and null container format descending

        Tests that the registry API returns 200
        when a marker and a null container_format are combined
        descending order
        """
        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': None,
                         'name': 'Fake image',
                         'size': 19,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'sort_key': 'container_format',
                       'sort_dir': 'desc'},
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        images = json.loads(res.body)[0]
        self.assertEqual(len(images), 0)

    def test_get_index_unknown_marker(self):
        """
        Tests that the registry API returns a NotFound
        when an unknown marker is provided
        """
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': _gen_uuid()},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        result = json.loads(res.body)[0]

        self.assertIn("_error", result)
        self.assertIn("NotFound", result["_error"]["cls"])

    def test_get_index_limit(self):
        """
        Tests that the registry API returns list of
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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'limit': 1},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        images = res_dict
        self.assertEqual(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(images[0]['id'], UUID4)

    def test_get_index_limit_marker(self):
        """
        Tests that the registry API returns list of
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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'limit': 1},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        images = res_dict
        self.assertEqual(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(images[0]['id'], UUID2)

    def test_get_index_filter_name(self):
        """
        Tests that the registry API returns list of
        public images that have a specific name. This is really a sanity
        check, filtering is tested more in-depth using /images/detail
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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'name': 'new name! #123'}},
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        images = res_dict
        self.assertEqual(len(images), 2)

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_index_sort_default_created_at_desc(self):
        """
        Tests that the registry API returns list of
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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        images = res_dict
        # (flaper87)registry's v1 forced is_public to True
        # when no value was specified. This is not
        # the default behaviour anymore.
        self.assertEqual(len(images), 5)
        self.assertEqual(images[0]['id'], UUID3)
        self.assertEqual(images[1]['id'], UUID4)
        self.assertEqual(images[2]['id'], UUID5)
        self.assertEqual(images[3]['id'], UUID2)
        self.assertEqual(images[4]['id'], UUID1)

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
        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': None,
                         'size': 20,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'name', 'sort_dir': 'asc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 5)
        self.assertEqual(images[0]['id'], UUID5)
        self.assertEqual(images[1]['id'], UUID3)
        self.assertEqual(images[2]['id'], UUID1)
        self.assertEqual(images[3]['id'], UUID2)
        self.assertEqual(images[4]['id'], UUID4)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'status', 'sort_dir': 'asc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID1)
        self.assertEqual(images[1]['id'], UUID2)
        self.assertEqual(images[2]['id'], UUID4)
        self.assertEqual(images[3]['id'], UUID3)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'disk_format', 'sort_dir': 'asc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID1)
        self.assertEqual(images[1]['id'], UUID3)
        self.assertEqual(images[2]['id'], UUID4)
        self.assertEqual(images[3]['id'], UUID2)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'container_format',
                       'sort_dir': 'desc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID2)
        self.assertEqual(images[1]['id'], UUID4)
        self.assertEqual(images[2]['id'], UUID3)
        self.assertEqual(images[3]['id'], UUID1)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'size',
                       'sort_dir': 'asc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID4)
        self.assertEqual(images[1]['id'], UUID1)
        self.assertEqual(images[2]['id'], UUID2)
        self.assertEqual(images[3]['id'], UUID3)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'created_at',
                       'sort_dir': 'asc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID1)
        self.assertEqual(images[1]['id'], UUID2)
        self.assertEqual(images[2]['id'], UUID4)
        self.assertEqual(images[3]['id'], UUID3)

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

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': 'updated_at',
                       'sort_dir': 'desc'}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)[0]

        images = res_dict
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0]['id'], UUID3)
        self.assertEqual(images[1]['id'], UUID4)
        self.assertEqual(images[2]['id'], UUID2)
        self.assertEqual(images[3]['id'], UUID1)

    def test_create_image(self):
        """Tests that the registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'status': 'active',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_create',
            'kwargs': {'values': fixture}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)

        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        for k, v in fixture.iteritems():
            self.assertEqual(v, res_dict[k])

        # Test status was updated properly
        self.assertEqual('active', res_dict['status'])

    def test_create_image_with_min_disk(self):
        """Tests that the registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'status': 'active',
                   'min_disk': 5,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_create',
            'kwargs': {'values': fixture}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        self.assertEqual(5, res_dict['min_disk'])

    def test_create_image_with_min_ram(self):
        """Tests that the registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'status': 'active',
                   'min_ram': 256,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_create',
            'kwargs': {'values': fixture}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        self.assertEqual(256, res_dict['min_ram'])

    def test_create_image_with_min_ram_default(self):
        """Tests that the registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'status': 'active',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_create',
            'kwargs': {'values': fixture}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        self.assertEqual(0, res_dict['min_ram'])

    def test_create_image_with_min_disk_default(self):
        """Tests that the registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'status': 'active',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_create',
            'kwargs': {'values': fixture}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        self.assertEqual(0, res_dict['min_disk'])

    def test_update_image(self):
        """Tests that the registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'min_disk': 5,
                   'min_ram': 256,
                   'disk_format': 'raw'}

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_update',
            'kwargs': {'values': fixture,
                       'image_id': UUID2}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        res_dict = json.loads(res.body)[0]

        self.assertNotEqual(res_dict['created_at'],
                            res_dict['updated_at'])

        for k, v in fixture.iteritems():
            self.assertEqual(v, res_dict[k])

    def test_delete_image(self):
        """Tests that the registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'deleted': False}}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        orig_num_images = len(res_dict)

        # Delete image #2
        cmd = [{
            'command': 'image_destroy',
            'kwargs': {'image_id': UUID2}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        # Verify one less image
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'deleted': False}}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)[0]
        self.assertEqual(res.status_int, 200)

        new_num_images = len(res_dict)
        self.assertEqual(new_num_images, orig_num_images - 1)

    def test_delete_image_response(self):
        """Tests that the registry API delete returns the image metadata"""

        image = self.FIXTURES[0]
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        cmd = [{
            'command': 'image_destroy',
            'kwargs': {'image_id': image['id']}
        }]
        req.body = json.dumps(cmd)
        res = req.get_response(self.api)

        self.assertEqual(res.status_int, 200)
        deleted_image = json.loads(res.body)[0]

        self.assertEqual(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        cmd = [{
            'command': 'image_member_find',
            'kwargs': {'image_id': UUID2}
        }]
        req.body = json.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)

        memb_list = json.loads(res.body)[0]
        self.assertEqual(len(memb_list), 0)


class TestRegistryRPCDBPoolEnabled(TestRegistryRPC):
    def setUp(self):
        CONF.set_override('use_tpool', True)
        super(TestRegistryRPCDBPoolEnabled, self).setUp()

    def tearDown(self):
        super(TestRegistryRPCDBPoolEnabled, self).tearDown()
        CONF.set_override('use_tpool', False)
