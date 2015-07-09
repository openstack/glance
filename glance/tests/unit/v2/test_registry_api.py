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
import uuid

from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils import timeutils
import routes
import six
import webob

import glance.api.common
import glance.common.config
import glance.context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.registry.api import v2 as rserver
from glance.tests.unit import base
from glance.tests import utils as test_utils

CONF = cfg.CONF

_gen_uuid = lambda: str(uuid.uuid4())

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


class TestRegistryRPC(base.IsolatedUnitTest):

    def setUp(self):
        super(TestRegistryRPC, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)

        uuid1_time = timeutils.utcnow()
        uuid2_time = uuid1_time + datetime.timedelta(seconds=5)

        self.FIXTURES = [
            {'id': UUID1,
             'name': 'fake image #1',
             'status': 'active',
             'disk_format': 'ami',
             'container_format': 'ami',
             'is_public': False,
             'created_at': uuid1_time,
             'updated_at': uuid1_time,
             'deleted_at': None,
             'deleted': False,
             'checksum': None,
             'min_disk': 0,
             'min_ram': 0,
             'size': 13,
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID1),
                            'metadata': {}, 'status': 'active'}],
             'properties': {'type': 'kernel'}},
            {'id': UUID2,
             'name': 'fake image #2',
             'status': 'active',
             'disk_format': 'vhd',
             'container_format': 'ovf',
             'is_public': True,
             'created_at': uuid2_time,
             'updated_at': uuid2_time,
             'deleted_at': None,
             'deleted': False,
             'checksum': None,
             'min_disk': 5,
             'min_ram': 256,
             'size': 19,
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID2),
                            'metadata': {}, 'status': 'active'}],
             'properties': {}}]

        self.context = glance.context.RequestContext(is_admin=True)
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
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def _compare_images_and_uuids(self, uuids, images):
        self.assertListEqual(uuids, [image['id'] for image in images])

    def test_show(self):
        """Tests that registry API endpoint returns the expected image."""
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
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]
        image = res_dict
        for k, v in six.iteritems(fixture):
            self.assertEqual(v, image[k])

    def test_show_unknown(self):
        """Tests the registry API endpoint returns 404 for an unknown id."""
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get',
            'kwargs': {'image_id': _gen_uuid()},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual('glance.common.exception.ImageNotFound',
                         res_dict["_error"]["cls"])

    def test_get_index(self):
        """Tests that the image_get_all command returns list of images."""
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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        images = jsonutils.loads(res.body)[0]
        self.assertEqual(1, len(images))

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, images[0][k])

    def test_get_index_marker(self):
        """Tests that the registry API returns list of public images.

        Must conforms to a marker query param.
        """
        uuid5_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid4_time = uuid5_time + datetime.timedelta(seconds=5)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

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
                         'created_at': uuid5_time,
                         'updated_at': uuid5_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID4, "is_public": True},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        images = jsonutils.loads(res.body)[0]
        # should be sorted by created_at desc, id desc
        # page should start after marker 4
        uuid_list = [UUID5, UUID2]
        self._compare_images_and_uuids(uuid_list, images)

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
            'kwargs': {'marker': UUID3, 'sort_key': ['name'],
                       'sort_dir': ['asc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(2, len(images))

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
            'kwargs': {'marker': UUID3, 'sort_key': ['name'],
                       'sort_dir': ['desc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

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
            'kwargs': {'marker': UUID3, 'sort_key': ['disk_format'],
                       'sort_dir': ['asc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(2, len(images))

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
            'kwargs': {'marker': UUID3, 'sort_key': ['disk_format'],
                       'sort_dir': ['desc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

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
            'kwargs': {'marker': UUID3, 'sort_key': ['container_format'],
                       'sort_dir': ['asc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(2, len(images))

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
            'kwargs': {'marker': UUID3, 'sort_key': ['container_format'],
                       'sort_dir': ['desc']},
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

    def test_get_index_unknown_marker(self):
        """Tests the registry API returns a NotFound with unknown marker."""
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': _gen_uuid()},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        result = jsonutils.loads(res.body)[0]

        self.assertIn("_error", result)
        self.assertIn("NotFound", result["_error"]["cls"])

    def test_get_index_limit(self):
        """Tests that the registry API returns list of public images.

        Must conforms to a limit query param.
        """
        uuid3_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid4_time = uuid3_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'limit': 1},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

        self._compare_images_and_uuids([UUID4], images)

    def test_get_index_limit_marker(self):
        """Tests that the registry API returns list of public images.

        Must conforms to limit and marker query params.
        """
        uuid3_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid4_time = uuid3_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'marker': UUID3, 'limit': 1},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

        images = res_dict
        self._compare_images_and_uuids([UUID2], images)

    def test_get_index_filter_name(self):
        """Tests that the registry API returns list of public images.

        Use a specific name. This is really a sanity check, filtering is
        tested more in-depth using /images/detail

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
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

        images = res_dict
        self.assertEqual(2, len(images))

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_index_filter_on_user_defined_properties(self):
        """Tests that the registry API returns list of public images.

        Use a specific user-defined properties.
        """
        properties = {'distro': 'ubuntu', 'arch': 'i386', 'type': 'kernel'}
        extra_id = _gen_uuid()
        extra_fixture = {'id': extra_id,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'image-extra-1',
                         'size': 19, 'properties': properties,
                         'checksum': None}
        db_api.image_create(self.context, extra_fixture)

        # testing with a common property.
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'kernel'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(2, len(images))
        self.assertEqual(extra_id, images[0]['id'])
        self.assertEqual(UUID1, images[1]['id'])

        # testing with a non-existent value for a common property.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

        # testing with a non-existent value for a common property.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

        # testing with a non-existent property.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'poo': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

        # testing with multiple existing properties.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'kernel', 'distro': 'ubuntu'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(1, len(images))
        self.assertEqual(extra_id, images[0]['id'])

        # testing with multiple existing properties but non-existent values.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'random', 'distro': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

        # testing with multiple non-existing properties.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'typo': 'random', 'poo': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

        # testing with one existing property and the other non-existing.
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'type': 'kernel', 'poo': 'random'}},
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(images))

    def test_get_index_sort_default_created_at_desc(self):
        """Tests that the registry API returns list of public images.

        Must conforms to a default sort key/dir.
        """
        uuid5_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid4_time = uuid5_time + datetime.timedelta(seconds=5)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

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
                         'created_at': uuid5_time,
                         'updated_at': uuid5_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

        images = res_dict
        # (flaper87)registry's v1 forced is_public to True
        # when no value was specified. This is not
        # the default behaviour anymore.
        uuid_list = [UUID3, UUID4, UUID5, UUID2, UUID1]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_name_asc(self):
        """Tests that the registry API returns list of public images.

        Must be  sorted alphabetically by name in ascending order.
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
            'kwargs': {'sort_key': ['name'], 'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID5, UUID3, UUID1, UUID2, UUID4]

        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_status_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by status in descending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)

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
                         'checksum': None,
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['status'], 'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID1, UUID2, UUID4, UUID3]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_disk_format_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by disk_format in ascending order.
        """
        uuid3_time = timeutils.utcnow() + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
            'kwargs': {'sort_key': ['disk_format'], 'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID1, UUID3, UUID4, UUID2]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_container_format_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted alphabetically by container_format in descending order.
        """
        uuid3_time = timeutils.utcnow() + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
            'kwargs': {'sort_key': ['container_format'],
                       'sort_dir': ['desc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID2, UUID4, UUID3, UUID1]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_size_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by size in ascending order.
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
            'kwargs': {'sort_key': ['size'],
                       'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID4, UUID1, UUID2, UUID3]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_created_at_asc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by created_at in ascending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': uuid3_time,
                         'updated_at': uuid3_time}

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
                         'created_at': uuid4_time,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['created_at'],
                       'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID1, UUID2, UUID4, UUID3]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_updated_at_desc(self):
        """Tests that the registry API returns list of public images.

        Must be sorted by updated_at in descending order.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

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
                         'updated_at': uuid3_time}

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
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['updated_at'],
                       'sort_dir': ['desc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID3, UUID4, UUID2, UUID1]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_multiple_keys_one_sort_dir(self):
        """
        Tests that the registry API returns list of
        public images sorted by name-size and size-name with ascending
        sort direction.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid3_time}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 20,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['name', 'size'],
                       'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID3, UUID5, UUID1, UUID2, UUID4]
        self._compare_images_and_uuids(uuid_list, images)

        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['size', 'name'],
                       'sort_dir': ['asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID1, UUID3, UUID2, UUID5, UUID4]
        self._compare_images_and_uuids(uuid_list, images)

    def test_get_index_sort_multiple_keys_multiple_sort_dirs(self):
        """
        Tests that the registry API returns list of
        public images sorted by name-size and size-name
        with ascending and descending directions.
        """
        uuid4_time = timeutils.utcnow() + datetime.timedelta(seconds=10)
        uuid3_time = uuid4_time + datetime.timedelta(seconds=5)

        UUID3 = _gen_uuid()
        extra_fixture = {'id': UUID3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 19,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid3_time}

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = {'id': UUID4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'xyz',
                         'size': 20,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = {'id': UUID5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'asdf',
                         'size': 20,
                         'checksum': None,
                         'created_at': None,
                         'updated_at': uuid4_time}

        db_api.image_create(self.context, extra_fixture)

        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['name', 'size'],
                       'sort_dir': ['desc', 'asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID4, UUID2, UUID1, UUID3, UUID5]
        self._compare_images_and_uuids(uuid_list, images)

        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['size', 'name'],
                       'sort_dir': ['desc', 'asc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID5, UUID4, UUID3, UUID2, UUID1]
        self._compare_images_and_uuids(uuid_list, images)

        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['name', 'size'],
                       'sort_dir': ['asc', 'desc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID5, UUID3, UUID1, UUID2, UUID4]
        self._compare_images_and_uuids(uuid_list, images)

        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'sort_key': ['size', 'name'],
                       'sort_dir': ['asc', 'desc']}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)[0]

        images = res_dict
        uuid_list = [UUID1, UUID2, UUID3, UUID4, UUID5]
        self._compare_images_and_uuids(uuid_list, images)

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
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)

        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

        for k, v in six.iteritems(fixture):
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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

        self.assertEqual(fixture['min_disk'], res_dict['min_disk'])

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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

        self.assertEqual(fixture['min_ram'], res_dict['min_ram'])

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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

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
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        res_dict = jsonutils.loads(res.body)[0]

        self.assertNotEqual(res_dict['created_at'],
                            res_dict['updated_at'])

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, res_dict[k])

    def _send_request(self, command, kwargs, method):
        req = webob.Request.blank('/rpc')
        req.method = method
        cmd = [{'command': command, 'kwargs': kwargs}]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        return res.status_int, res_dict

    def _expect_fail(self, command, kwargs, error_cls, method='POST'):
        # on any exception status_int is always 200, so have to check _error
        # dict
        code, res_dict = self._send_request(command, kwargs, method)
        self.assertIn('_error', res_dict)
        self.assertEqual(error_cls, res_dict['_error']['cls'])
        return res_dict

    def _expect_ok(self, command, kwargs, method, expected_status=200):
        code, res_dict = self._send_request(command, kwargs)
        self.assertEqual(expected_status, code)
        return res_dict

    def test_create_image_bad_name(self):
        fixture = {'name': u'A bad name \U0001fff2', 'status': 'queued'}
        self._expect_fail('image_create',
                          {'values': fixture},
                          'glance.common.exception.Invalid')

    def test_create_image_bad_location(self):
        fixture = {'status': 'queued',
                   'locations': [{'url': u'file:///tmp/tests/\U0001fee2',
                                  'metadata': {},
                                  'status': 'active'}]}
        self._expect_fail('image_create',
                          {'values': fixture},
                          'glance.common.exception.Invalid')

    def test_create_image_bad_property(self):
        fixture = {'status': 'queued',
                   'properties': {'ok key': u' bad value \U0001f2aa'}}
        self._expect_fail('image_create',
                          {'values': fixture},
                          'glance.common.exception.Invalid')
        fixture = {'status': 'queued',
                   'properties': {u'invalid key \U00010020': 'ok value'}}
        self._expect_fail('image_create',
                          {'values': fixture},
                          'glance.common.exception.Invalid')

    def test_update_image_bad_tag(self):
        self._expect_fail('image_tag_create',
                          {'value': u'\U0001fff2', 'image_id': UUID2},
                          'glance.common.exception.Invalid')

    def test_update_image_bad_name(self):
        fixture = {'name': u'A bad name \U0001fff2'}
        self._expect_fail('image_update',
                          {'values': fixture, 'image_id': UUID1},
                          'glance.common.exception.Invalid')

    def test_update_image_bad_location(self):
        fixture = {'locations':
                   [{'url': u'file:///tmp/glance-tests/\U0001fee2',
                     'metadata': {},
                     'status': 'active'}]}
        self._expect_fail('image_update',
                          {'values': fixture, 'image_id': UUID1},
                          'glance.common.exception.Invalid')

    def test_update_bad_property(self):
        fixture = {'properties': {'ok key': u' bad value \U0001f2aa'}}
        self._expect_fail('image_update',
                          {'values': fixture, 'image_id': UUID2},
                          'glance.common.exception.Invalid')
        fixture = {'properties': {u'invalid key \U00010020': 'ok value'}}
        self._expect_fail('image_update',
                          {'values': fixture, 'image_id': UUID2},
                          'glance.common.exception.Invalid')

    def test_delete_image(self):
        """Tests that the registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/rpc')
        req.method = "POST"
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'deleted': False}}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

        orig_num_images = len(res_dict)

        # Delete image #2
        cmd = [{
            'command': 'image_destroy',
            'kwargs': {'image_id': UUID2}
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        # Verify one less image
        cmd = [{
            'command': 'image_get_all',
            'kwargs': {'filters': {'deleted': False}}
        }]
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)
        res_dict = jsonutils.loads(res.body)[0]
        self.assertEqual(200, res.status_int)

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
        req.body = jsonutils.dumps(cmd)
        res = req.get_response(self.api)

        self.assertEqual(200, res.status_int)
        deleted_image = jsonutils.loads(res.body)[0]

        self.assertEqual(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

    def test_get_image_members(self):
        """Tests members listing for existing images."""
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        cmd = [{
            'command': 'image_member_find',
            'kwargs': {'image_id': UUID2}
        }]
        req.body = jsonutils.dumps(cmd)

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)[0]
        self.assertEqual(0, len(memb_list))
