# -*- coding: utf-8 -*-

# Copyright 2010-2011 OpenStack Foundation
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
import hashlib
import os
import signal
import uuid

import glance_store as store
import mock
from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils import timeutils
import routes
import six
import webob

import glance.api
import glance.api.common
from glance.api.v1 import router
from glance.api.v1 import upload_utils
import glance.common.config
from glance.common import exception
import glance.context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
import glance.registry.client.v1.api as registry
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
from glance.tests import utils as test_utils

CONF = cfg.CONF

_gen_uuid = lambda: str(uuid.uuid4())

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()
UUID3 = _gen_uuid()


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
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID1),
                            'metadata': {}, 'status': 'active'}],
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
             'checksum': 'abc123',
             'size': 19,
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID2),
                            'metadata': {}, 'status': 'active'}],
             'properties': {}},
            {'id': UUID3,
             'name': 'fake image #3',
             'status': 'deactivated',
             'disk_format': 'ami',
             'container_format': 'ami',
             'is_public': False,
             'created_at': timeutils.utcnow(),
             'updated_at': timeutils.utcnow(),
             'deleted_at': None,
             'deleted': False,
             'checksum': None,
             'size': 13,
             'locations': [{'url': "file:///%s/%s" % (self.test_dir, UUID1),
                            'metadata': {}, 'status': 'active'}],
             'properties': {}}]
        self.context = glance.context.RequestContext(is_admin=True)
        db_api.get_engine()
        self.destroy_fixtures()
        self.create_fixtures()
        # Used to store/track image status changes for post-analysis
        self.image_status = []
        ret = test_utils.start_http_server("foo_image_id", "foo_image")
        self.http_server_pid, self.http_port = ret

    def tearDown(self):
        """Clear the test environment"""
        super(TestGlanceAPI, self).tearDown()
        self.destroy_fixtures()
        if self.http_server_pid is not None:
            os.kill(self.http_server_pid, signal.SIGKILL)

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

    def _do_test_defaulted_format(self, format_key, format_value):
        fixture_headers = {'x-image-meta-name': 'defaulted',
                           'x-image-meta-location': 'http://localhost:0/image',
                           format_key: format_value}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)
            res_body = jsonutils.loads(res.body)['image']
            self.assertEqual(format_value, res_body['disk_format'])
            self.assertEqual(format_value, res_body['container_format'])

    def _http_loc_url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.http_port, path)

    def test_defaulted_amazon_format(self):
        for key in ('x-image-meta-disk-format',
                    'x-image-meta-container-format'):
            for value in ('aki', 'ari', 'ami'):
                self._do_test_defaulted_format(key, value)

    def test_bad_min_disk_size_create(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-min-disk': '-42',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid value', res.body)

    def test_bad_min_disk_size_update(self):
        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-min-disk'] = '-42'
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid value', res.body)

    def test_invalid_min_disk_size_update(self):
        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-min-disk'] = str(2 ** 31 + 1)
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_bad_min_ram_size_create(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-min-ram': '-42',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid value', res.body)

    def test_bad_min_ram_size_update(self):
        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-min-ram'] = '-42'
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid value', res.body)

    def test_invalid_min_ram_size_update(self):
        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-min-ram'] = str(2 ** 31 + 1)
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid disk format', res.body)

    def test_configured_disk_format_good(self):
        self.config(disk_formats=['foo'], group="image_format")
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'foo',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')
        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)

    def test_configured_disk_format_bad(self):
        self.config(disk_formats=['foo'], group="image_format")
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'bar',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid disk format', res.body)

    def test_configured_container_format_good(self):
        self.config(container_formats=['foo'], group="image_format")
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'raw',
            'x-image-meta-container-format': 'foo',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)

    def test_configured_container_format_bad(self):
        self.config(container_formats=['foo'], group="image_format")
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'raw',
            'x-image-meta-container-format': 'bar',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid container format', res.body)

    def test_container_and_disk_amazon_format_differs(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'aki',
            'x-image-meta-container-format': 'ami'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        expected = ("Invalid mix of disk and container formats. "
                    "When setting a disk or container format to one of "
                    "'aki', 'ari', or 'ami', "
                    "the container and disk formats must match.")
        self.assertEqual(400, res.status_int)
        self.assertIn(expected, res.body)

    def test_create_with_location_no_container_format(self):
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'vhd',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(400, res.status_int)
            self.assertIn('Container format is not specified', res.body)

    def test_create_with_location_no_disk_format(self):
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(400, res.status_int)
            self.assertIn('Disk format is not specified', res.body)

    def test_create_delayed_image_with_no_disk_and_container_formats(self):
        fixture_headers = {
            'x-image-meta-name': 'delayed',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)

    def test_create_with_bad_store_name(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-disk-format': 'qcow2',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Required store bad is invalid', res.body)

    @mock.patch.object(glance.api.v1.images.Controller, '_external_source')
    @mock.patch.object(store, 'get_store_from_location')
    def test_create_with_location_get_store_or_400_raises_exception(
            self, mock_get_store_from_location, mock_external_source):
        location = 'bad+scheme://localhost:0/image.qcow2'
        scheme = 'bad+scheme'
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': location,
            'x-image-meta-disk-format': 'qcow2',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        mock_external_source.return_value = location
        mock_get_store_from_location.return_value = scheme

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertEqual(1, mock_external_source.call_count)
        self.assertEqual(1, mock_get_store_from_location.call_count)
        self.assertIn('Store for scheme %s not found' % scheme, res.body)

    def test_create_with_location_unknown_scheme(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'bad+scheme://localhost:0/image.qcow2',
            'x-image-meta-disk-format': 'qcow2',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('External sources are not supported', res.body)

    def test_create_with_location_bad_store_uri(self):
        fixture_headers = {
            'x-image-meta-store': 'file',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://',
            'x-image-meta-disk-format': 'qcow2',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid location', res.body)

    def test_create_image_with_too_many_properties(self):
        self.config(image_property_quota=1)
        another_request = unit_test_utils.get_fake_request(
            path='/images', method='POST')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-image-meta-property-x_all_permitted': '1',
                   'x-image-meta-property-x_all_permitted_foo': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(413, output.status_int)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid container format', res.body)

    def test_bad_image_size(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': self._http_loc_url('/image.tar.gz'),
            'x-image-meta-disk-format': 'vhd',
            'x-image-meta-container-format': 'bare',
        }

        def exec_bad_size_test(bad_size, expected_substr):
            fixture_headers['x-image-meta-size'] = bad_size
            req = webob.Request.blank("/images",
                                      method='POST',
                                      headers=fixture_headers)
            res = req.get_response(self.api)
            self.assertEqual(400, res.status_int)
            self.assertIn(expected_substr, res.body)

        expected = "Cannot convert image size 'invalid' to an integer."
        exec_bad_size_test('invalid', expected)
        expected = "Cannot be a negative value."
        exec_bad_size_test(-10, expected)

    def test_bad_image_name(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'X' * 256,
            'x-image-meta-location': self._http_loc_url('/image.tar.gz'),
            'x-image-meta-disk-format': 'vhd',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_no_location_no_image_as_body(self):
        """Tests creates a queued image for no body and no loc header"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']

        # Test that we are able to edit the Location field
        # per LP Bug #911599

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-location'] = 'http://localhost:0/images/123'

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mocked_size:
            mocked_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(200, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        # Once the location is set, the image should be activated
        # see LP Bug #939484
        self.assertEqual('active', res_body['status'])
        self.assertNotIn('location', res_body)  # location never shown

    def test_add_image_no_location_no_content_type(self):
        """Tests creates a queued image for no body and no loc header"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = "chunk00000remainder"
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_size_header_too_big(self):
        """Tests raises BadRequest for supplied image size that is too big"""
        fixture_headers = {'x-image-meta-size': CONF.image_size_cap + 1,
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

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

        req.body_file = six.StringIO('X' * (CONF.image_size_cap + 1))
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_size_header_exceed_quota(self):
        quota = 500
        self.config(user_storage_quota=str(quota))
        fixture_headers = {'x-image-meta-size': quota + 1,
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-container_format': 'bare',
                           'x-image-meta-disk_format': 'qcow2',
                           'content-type': 'application/octet-stream',
                           }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        req.body = 'X' * (quota + 1)
        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

    def test_add_image_size_data_exceed_quota(self):
        quota = 500
        self.config(user_storage_quota=str(quota))
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'bare',
            'x-image-meta-disk_format': 'qcow2',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'

        req.body = 'X' * (quota + 1)
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

    def test_add_image_size_data_exceed_quota_readd(self):
        quota = 500
        self.config(user_storage_quota=str(quota))
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'bare',
            'x-image-meta-disk_format': 'qcow2',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = 'X' * (quota + 1)
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

        used_size = sum([f['size'] for f in self.FIXTURES])

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = 'X' * (quota - used_size)
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

    def _add_check_no_url_info(self):

        fixture_headers = {'x-image-meta-disk-format': 'ami',
                           'x-image-meta-container-format': 'ami',
                           'x-image-meta-size': '0',
                           'x-image-meta-name': 'empty image'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        res_body = jsonutils.loads(res.body)['image']
        self.assertNotIn('locations', res_body)
        self.assertNotIn('direct_url', res_body)
        image_id = res_body['id']

        # HEAD empty image
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertNotIn('x-image-meta-locations', res.headers)
        self.assertNotIn('x-image-meta-direct_url', res.headers)

    def test_add_check_no_url_info_ml(self):
        self.config(show_multiple_locations=True)
        self._add_check_no_url_info()

    def test_add_check_no_url_info_direct_url(self):
        self.config(show_image_direct_url=True)
        self._add_check_no_url_info()

    def test_add_check_no_url_info_both_on(self):
        self.config(show_image_direct_url=True)
        self.config(show_multiple_locations=True)
        self._add_check_no_url_info()

    def test_add_check_no_url_info_both_off(self):
        self._add_check_no_url_info()

    def test_add_image_zero_size(self):
        """Tests creating an active image with explicitly zero size"""
        fixture_headers = {'x-image-meta-disk-format': 'ami',
                           'x-image-meta-container-format': 'ami',
                           'x-image-meta-size': '0',
                           'x-image-meta-name': 'empty image'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('active', res_body['status'])
        image_id = res_body['id']

        # GET empty image
        req = webob.Request.blank("/images/%s" % image_id)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual(0, len(res.body))

    def _do_test_add_image_attribute_mismatch(self, attributes):
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
        }
        fixture_headers.update(attributes)

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "XXXX"
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_checksum_mismatch(self):
        attributes = {
            'x-image-meta-checksum': 'asdf',
        }
        self._do_test_add_image_attribute_mismatch(attributes)

    def test_add_image_size_mismatch(self):
        attributes = {
            'x-image-meta-size': str(len("XXXX") + 1),
        }
        self._do_test_add_image_attribute_mismatch(attributes)

    def test_add_image_checksum_and_size_mismatch(self):
        attributes = {
            'x-image-meta-checksum': 'asdf',
            'x-image-meta-size': str(len("XXXX") + 1),
        }
        self._do_test_add_image_attribute_mismatch(attributes)

    def test_add_image_bad_store(self):
        """Tests raises BadRequest for invalid store header"""
        fixture_headers = {'x-image-meta-store': 'bad',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_basic_file_store(self):
        """Tests to add a basic image in the file store"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        # Test that the Location: header is set to the URI to
        # edit the newly-created image, as required by APP.
        # See LP Bug #719825
        self.assertIn('location', res.headers,
                      "'location' not in response headers.\n"
                      "res.headerlist = %r" % res.headerlist)
        res_body = jsonutils.loads(res.body)['image']
        self.assertIn('/images/%s' % res_body['id'], res.headers['location'])
        self.assertEqual('active', res_body['status'])
        image_id = res_body['id']

        # Test that we are NOT able to edit the Location field
        # per LP Bug #911599

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        url = self._http_loc_url('/images/123')
        req.headers['x-image-meta-location'] = url
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_image_unauthorized(self):
        rules = {"add_image": '!'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_add_publicize_image_unauthorized(self):
        rules = {"add_image": '@', "modify_image": '@',
                 "publicize_image": '!'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-is-public': 'true',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_add_publicize_image_authorized(self):
        rules = {"add_image": '@', "modify_image": '@',
                 "publicize_image": '@', "upload_image": '@'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-is-public': 'true',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

    def test_add_copy_from_image_unauthorized(self):
        rules = {"add_image": '@', "copy_from": '!'}
        self.set_policy_rules(rules)
        url = self._http_loc_url('/i.ovf')
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': url,
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_add_copy_from_upload_image_unauthorized(self):
        rules = {"add_image": '@', "copy_from": '@', "upload_image": '!'}
        self.set_policy_rules(rules)
        url = self._http_loc_url('/i.ovf')
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': url,
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_add_copy_from_image_authorized_upload_image_authorized(self):
        rules = {"add_image": '@', "copy_from": '@', "upload_image": '@'}
        self.set_policy_rules(rules)
        url = self._http_loc_url('/i.ovf')
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': url,
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as mock_size:
            mock_size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)

    def test_upload_image_http_nonexistent_location_url(self):
        # Ensure HTTP 404 response returned when try to upload
        # image from non-existent http location URL.
        rules = {"add_image": '@', "copy_from": '@', "upload_image": '@'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from':
                               'http://example.com/i.ovf',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_add_copy_from_with_nonempty_body(self):
        """Tests creates an image from copy-from and nonempty body"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': 'http://a/b/c.ovf',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        req.body = "chunk00000remainder"
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_location_with_nonempty_body(self):
        """Tests creates an image from location and nonempty body"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'http://a/b/c.tar.gz',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        req.body = "chunk00000remainder"
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_location_with_conflict_image_size(self):
        """Tests creates an image from location and conflict image size"""

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'http://a/b/c.tar.gz',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F',
                           'x-image-meta-size': '1'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as size:
            size.return_value = 2

            for k, v in six.iteritems(fixture_headers):
                req.headers[k] = v

            res = req.get_response(self.api)
            self.assertEqual(res.status_int, 409)

    def test_add_location_with_invalid_location_on_conflict_image_size(self):
        """Tests creates an image from location and conflict image size"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'http://a/b/c.tar.gz',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F',
                           'x-image-meta-size': '1'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_location_with_invalid_location_on_restricted_sources(self):
        """Tests creates an image from location and restricted sources"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'file:///etc/passwd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'swift+config://xxx',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_create_image_with_nonexistent_location_url(self):
        # Ensure HTTP 404 response returned when try to create
        # image with non-existent http location URL.
        fixture_headers = {
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://example.com/images/123',
            'x-image-meta-disk-format': 'qcow2',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'

        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_add_copy_from_with_location(self):
        """Tests creates an image from copy-from and location"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': 'http://a/b/c.ovf',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F',
                           'x-image-meta-location': 'http://a/b/c.tar.gz'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_add_copy_from_with_restricted_sources(self):
        """Tests creates an image from copy-from with restricted sources"""
        header_template = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        schemas = ["file:///etc/passwd",
                   "swift+config:///xxx",
                   "filesystem:///etc/passwd"]

        for schema in schemas:
            req = webob.Request.blank("/images")
            req.method = 'POST'
            for k, v in six.iteritems(header_template):
                req.headers[k] = v
            req.headers['x-glance-api-copy-from'] = schema
            res = req.get_response(self.api)
            self.assertEqual(400, res.status_int)

    def test_add_copy_from_upload_image_unauthorized_with_body(self):
        rules = {"upload_image": '!', "modify_image": '@',
                 "add_image": '@'}
        self.set_policy_rules(rules)
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

        req.body_file = six.StringIO('X' * (CONF.image_size_cap))
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_update_data_upload_bad_store_uri(self):
        fixture_headers = {'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['x-image-disk-format'] = 'vhd'
        req.headers['x-image-container-format'] = 'ovf'
        req.headers['x-image-meta-location'] = 'http://'
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)
        self.assertIn('Invalid location', res.body)

    def test_update_data_upload_image_unauthorized(self):
        rules = {"upload_image": '!', "modify_image": '@',
                 "add_image": '@'}
        self.set_policy_rules(rules)
        """Tests creates a queued image for no body and no loc header"""
        self.config(image_size_cap=512)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['transfer-encoding'] = 'chunked'
        req.headers['x-image-disk-format'] = 'vhd'
        req.headers['x-image-container-format'] = 'ovf'
        req.body_file = six.StringIO('X' * (CONF.image_size_cap))
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_update_copy_from_upload_image_unauthorized(self):
        rules = {"upload_image": '!', "modify_image": '@',
                 "add_image": '@', "copy_from": '@'}
        self.set_policy_rules(rules)

        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['x-glance-api-copy-from'] = self._http_loc_url('/i.ovf')
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_update_copy_from_unauthorized(self):
        rules = {"upload_image": '@', "modify_image": '@',
                 "add_image": '@', "copy_from": '!'}
        self.set_policy_rules(rules)

        fixture_headers = {'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['x-glance-api-copy-from'] = self._http_loc_url('/i.ovf')
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])
        image_id = res_body['id']

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_put_image_content_missing_disk_format(self):
        """Tests delayed activation of image with missing disk format"""
        self._do_test_put_image_content_missing_format('disk_format')

    def test_put_image_content_missing_container_type(self):
        """Tests delayed activation of image with missing container format"""
        self._do_test_put_image_content_missing_format('container_format')

    def test_download_deactivated_images(self):
        """Tests exception raised trying to download a deactivated image"""
        req = webob.Request.blank("/images/%s" % UUID3)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_update_deleted_image(self):
        """Tests that exception raised trying to update a deleted image"""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        fixture = {'name': 'test_del_img'}
        req = webob.Request.blank('/images/%s' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)
        self.assertIn('Forbidden to update deleted image', res.body)

    def test_delete_deleted_image(self):
        """Tests that exception raised trying to delete a deleted image"""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        # Verify the status is 'deleted'
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual("deleted", res.headers['x-image-meta-status'])

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)
        msg = "Image %s not found." % UUID2
        self.assertIn(msg, res.body)

        # Verify the status is still 'deleted'
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual("deleted", res.headers['x-image-meta-status'])

    def test_image_status_when_delete_fails(self):
        """
        Tests that the image status set to active if deletion of image fails.
        """

        fs = store.get_store_from_scheme('file')

        with mock.patch.object(fs, 'delete') as mock_fsstore_delete:
            mock_fsstore_delete.side_effect = exception.Forbidden()

            # trigger the v1 delete api
            req = webob.Request.blank("/images/%s" % UUID2)
            req.method = 'DELETE'
            res = req.get_response(self.api)
            self.assertEqual(403, res.status_int)
            self.assertIn('Forbidden to delete image', res.body)

            # check image metadata is still there with active state
            req = webob.Request.blank("/images/%s" % UUID2)
            req.method = 'HEAD'
            res = req.get_response(self.api)
            self.assertEqual(200, res.status_int)
            self.assertEqual("active", res.headers['x-image-meta-status'])

    def test_delete_pending_delete_image(self):
        """
        Tests that correct response returned when deleting
        a pending_delete image
        """
        # First deletion
        self.config(delayed_delete=True)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        # Verify the status is 'pending_delete'
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual("pending_delete", res.headers['x-image-meta-status'])

        # Second deletion
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)
        self.assertIn('Forbidden to delete a pending_delete image', res.body)

        # Verify the status is still 'pending_delete'
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual("pending_delete", res.headers['x-image-meta-status'])

    def test_upload_to_image_status_saving(self):
        """Test image upload conflict.

        If an image is uploaded before an existing upload to the same image
        completes, the original upload should succeed and the conflicting
        one should fail and any data be deleted.
        """
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'some-foo-image'}

        # create an image but don't upload yet.
        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        image_id = res_body['id']
        self.assertIn('/images/%s' % image_id, res.headers['location'])

        # verify the status is 'queued'
        self.assertEqual('queued', res_body['status'])

        orig_get_image_metadata = registry.get_image_metadata
        orig_image_get = db_api._image_get
        orig_image_update = db_api._image_update
        orig_initiate_deletion = upload_utils.initiate_deletion

        # this will be used to track what is called and their order.
        call_sequence = []
        # use this to determine if we are within a db session i.e. atomic
        # operation, that is setting our active state.
        # We want first status check to be 'queued' so we get past the
        # first guard.
        test_status = {
            'activate_session_started': False,
            'queued_guard_passed': False
        }

        state_changes = []

        def mock_image_update(context, values, image_id, purge_props=False,
                              from_state=None):

            status = values.get('status')
            if status:
                state_changes.append(status)
                if status == 'active':
                    # We only expect this state to be entered once.
                    if test_status['activate_session_started']:
                        raise Exception("target session already started")

                    test_status['activate_session_started'] = True
                    call_sequence.append('update_active')

                else:
                    call_sequence.append('update')

            return orig_image_update(context, values, image_id,
                                     purge_props=purge_props,
                                     from_state=from_state)

        def mock_image_get(*args, **kwargs):
            """Force status to 'saving' if not within activate db session.

            If we are in the activate db session we return 'active' which we
            then expect to cause exception.Conflict to be raised since this
            indicates that another upload has succeeded.
            """
            image = orig_image_get(*args, **kwargs)
            if test_status['activate_session_started']:
                call_sequence.append('image_get_active')
                setattr(image, 'status', 'active')
            else:
                setattr(image, 'status', 'saving')

            return image

        def mock_get_image_metadata(*args, **kwargs):
            """Force image status sequence.
            """
            call_sequence.append('get_image_meta')
            meta = orig_get_image_metadata(*args, **kwargs)
            if not test_status['queued_guard_passed']:
                meta['status'] = 'queued'
                test_status['queued_guard_passed'] = True

            return meta

        def mock_initiate_deletion(*args, **kwargs):
            call_sequence.append('init_del')
            orig_initiate_deletion(*args, **kwargs)

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"

        with mock.patch.object(
                upload_utils, 'initiate_deletion') as mock_init_del:
            mock_init_del.side_effect = mock_initiate_deletion
            with mock.patch.object(
                    registry, 'get_image_metadata') as mock_get_meta:
                mock_get_meta.side_effect = mock_get_image_metadata
                with mock.patch.object(db_api, '_image_get') as mock_db_get:
                    mock_db_get.side_effect = mock_image_get
                    with mock.patch.object(
                            db_api, '_image_update') as mock_db_update:
                        mock_db_update.side_effect = mock_image_update

                        # Expect a 409 Conflict.
                        res = req.get_response(self.api)
                        self.assertEqual(409, res.status_int)

                        # Check expected call sequence
                        self.assertEqual(['get_image_meta', 'get_image_meta',
                                          'update', 'update_active',
                                          'image_get_active',
                                          'init_del'],
                                         call_sequence)

                        self.assertTrue(mock_get_meta.called)
                        self.assertTrue(mock_db_get.called)
                        self.assertTrue(mock_db_update.called)

                        # Ensure cleanup occurred.
                        self.assertEqual(1, mock_init_del.call_count)

                        self.assertEqual(state_changes, ['saving', 'active'])

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        self.assertIn('id', res_body)

        image_id = res_body['id']
        self.assertIn('/images/%s' % image_id, res.headers['location'])

        # Verify the status is queued
        self.assertIn('status', res_body)
        self.assertEqual('queued', res_body['status'])

        # Check properties are not deleted
        self.assertIn('properties', res_body)
        self.assertIn('key1', res_body['properties'])
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
        self.assertEqual(200, res.status_int)

        # Verify the status is 'queued'
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertIn('x-image-meta-property-key1', res.headers,
                      "Did not find required property in headers. "
                      "Got headers: %r" % res.headers)
        self.assertEqual("active", res.headers['x-image-meta-status'])

    def test_upload_image_raises_store_disabled(self):
        """Test that uploading an image file returns HTTTP 410 response"""
        # create image
        fs = store.get_store_from_scheme('file')
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-property-key1': 'value1'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        self.assertIn('id', res_body)

        image_id = res_body['id']
        self.assertIn('/images/%s' % image_id, res.headers['location'])

        # Verify the status is queued
        self.assertIn('status', res_body)
        self.assertEqual('queued', res_body['status'])

        # Now upload the image file
        with mock.patch.object(fs, 'add') as mock_fsstore_add:
            mock_fsstore_add.side_effect = store.StoreAddDisabled
            req = webob.Request.blank("/images/%s" % image_id)
            req.method = 'PUT'
            req.headers['Content-Type'] = 'application/octet-stream'
            req.body = "chunk00000remainder"
            res = req.get_response(self.api)
            self.assertEqual(410, res.status_int)
            self._verify_image_status(image_id, 'killed')

    def _get_image_status(self, image_id):
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'
        return req.get_response(self.api)

    def _verify_image_status(self, image_id, status, check_deleted=False,
                             use_cached=False):
        if not use_cached:
            res = self._get_image_status(image_id)
        else:
            res = self.image_status.pop(0)

        self.assertEqual(200, res.status_int)
        self.assertEqual(status, res.headers['x-image-meta-status'])
        self.assertEqual(str(check_deleted),
                         res.headers['x-image-meta-deleted'])

    def _upload_safe_kill_common(self, mocks):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-property-key1': 'value1'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        self.assertIn('id', res_body)

        self.image_id = res_body['id']
        self.assertIn('/images/%s' %
                      self.image_id, res.headers['location'])

        # Verify the status is 'queued'
        self.assertEqual('queued', res_body['status'])

        for m in mocks:
            m['mock'].side_effect = m['side_effect']

        # Now upload the image file along with some more metadata and
        # verify original metadata properties are not marked deleted
        req = webob.Request.blank("/images/%s" % self.image_id)
        req.method = 'PUT'
        req.headers['Content-Type'] = 'application/octet-stream'
        req.headers['x-image-meta-property-key2'] = 'value2'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        # We expect 500 since an exception occurred during upload.
        self.assertEqual(500, res.status_int)

    @mock.patch('glance_store.store_add_to_backend')
    def test_upload_safe_kill(self, mock_store_add_to_backend):

        def mock_store_add_to_backend_w_exception(*args, **kwargs):
            """Trigger mid-upload failure by raising an exception."""
            self.image_status.append(self._get_image_status(self.image_id))
            # Raise an exception to emulate failed upload.
            raise Exception("== UNIT TEST UPLOAD EXCEPTION ==")

        mocks = [{'mock': mock_store_add_to_backend,
                 'side_effect': mock_store_add_to_backend_w_exception}]

        self._upload_safe_kill_common(mocks)

        # Check we went from 'saving' -> 'killed'
        self._verify_image_status(self.image_id, 'saving', use_cached=True)
        self._verify_image_status(self.image_id, 'killed')

        self.assertEqual(1, mock_store_add_to_backend.call_count)

    @mock.patch('glance_store.store_add_to_backend')
    def test_upload_safe_kill_deleted(self, mock_store_add_to_backend):
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router_api,
                                                 is_admin=True)

        def mock_store_add_to_backend_w_exception(*args, **kwargs):
            """We now delete the image, assert status is 'deleted' then
            raise an exception to emulate a failed upload. This will be caught
            by upload_data_to_store() which will then try to set status to
            'killed' which will be ignored since the image has been deleted.
            """
            # expect 'saving'
            self.image_status.append(self._get_image_status(self.image_id))

            req = webob.Request.blank("/images/%s" % self.image_id)
            req.method = 'DELETE'
            res = req.get_response(self.api)
            self.assertEqual(200, res.status_int)

            # expect 'deleted'
            self.image_status.append(self._get_image_status(self.image_id))

            # Raise an exception to make the upload fail.
            raise Exception("== UNIT TEST UPLOAD EXCEPTION ==")

        mocks = [{'mock': mock_store_add_to_backend,
                 'side_effect': mock_store_add_to_backend_w_exception}]

        self._upload_safe_kill_common(mocks)

        # Check we went from 'saving' -> 'deleted' -> 'deleted'
        self._verify_image_status(self.image_id, 'saving', check_deleted=False,
                                  use_cached=True)

        self._verify_image_status(self.image_id, 'deleted', check_deleted=True,
                                  use_cached=True)

        self._verify_image_status(self.image_id, 'deleted', check_deleted=True)

        self.assertEqual(1, mock_store_add_to_backend.call_count)

    def _check_delete_during_image_upload(self, is_admin=False):

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-property-key1': 'value1'}

        req = unit_test_utils.get_fake_request(path="/images",
                                               is_admin=is_admin)
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        self.assertIn('id', res_body)

        image_id = res_body['id']
        self.assertIn('/images/%s' % image_id, res.headers['location'])

        # Verify the status is 'queued'
        self.assertEqual('queued', res_body['status'])

        called = {'initiate_deletion': False}

        def mock_initiate_deletion(*args, **kwargs):
            called['initiate_deletion'] = True

        self.stubs.Set(glance.api.v1.upload_utils, 'initiate_deletion',
                       mock_initiate_deletion)

        orig_update_image_metadata = registry.update_image_metadata

        data = "somedata"

        def mock_update_image_metadata(*args, **kwargs):

            if args[2].get('size', None) == len(data):
                path = "/images/%s" % image_id
                req = unit_test_utils.get_fake_request(path=path,
                                                       method='DELETE',
                                                       is_admin=is_admin)
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)

                self.stubs.Set(registry, 'update_image_metadata',
                               orig_update_image_metadata)

            return orig_update_image_metadata(*args, **kwargs)

        self.stubs.Set(registry, 'update_image_metadata',
                       mock_update_image_metadata)

        req = unit_test_utils.get_fake_request(path="/images/%s" % image_id,
                                               method='PUT')
        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = data
        res = req.get_response(self.api)
        self.assertEqual(412, res.status_int)
        self.assertFalse(res.location)

        self.assertTrue(called['initiate_deletion'])

        req = unit_test_utils.get_fake_request(path="/images/%s" % image_id,
                                               method='HEAD',
                                               is_admin=True)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual('True', res.headers['x-image-meta-deleted'])
        self.assertEqual('deleted', res.headers['x-image-meta-status'])

    def test_delete_during_image_upload_by_normal_user(self):
        self._check_delete_during_image_upload(is_admin=False)

    def test_delete_during_image_upload_by_admin(self):
        self._check_delete_during_image_upload(is_admin=True)

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)
        res_body = jsonutils.loads(res.body)['image']

        self.assertIn('id', res_body)

        image_id = res_body['id']
        self.assertIn('/images/%s' % image_id, res.headers['location'])

        # Verify the status is queued
        self.assertIn('status', res_body)
        self.assertEqual('active', res_body['status'])

        # Check properties are not deleted
        self.assertIn('properties', res_body)
        self.assertIn('key1', res_body['properties'])
        self.assertEqual('value1', res_body['properties']['key1'])

        # Now update the image, setting new properties without
        # passing the x-glance-registry-purge-props header and
        # verify that original properties are marked deleted.
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-property-key2'] = 'value2'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        # Verify the original property no longer in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertIn('x-image-meta-property-key2', res.headers,
                      "Did not find required property in headers. "
                      "Got headers: %r" % res.headers)
        self.assertNotIn('x-image-meta-property-key1', res.headers,
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
        self.assertEqual(200, res.status_int)

        # Verify the second and third property in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertIn('x-image-meta-property-key2', res.headers,
                      "Did not find required property in headers. "
                      "Got headers: %r" % res.headers)
        self.assertIn('x-image-meta-property-key3', res.headers,
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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'PUT'
        req.headers['x-image-meta-is-public'] = 'true'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_update_image_size_header_too_big(self):
        """Tests raises BadRequest for supplied image size that is too big"""
        fixture_headers = {'x-image-meta-size': CONF.image_size_cap + 1}

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'PUT'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_update_image_size_data_too_big(self):
        self.config(image_size_cap=512)

        fixture_headers = {'content-type': 'application/octet-stream'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'PUT'

        req.body = 'X' * (CONF.image_size_cap + 1)
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_update_image_size_chunked_data_too_big(self):
        self.config(image_size_cap=512)

        # Create new image that has no data
        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.headers['x-image-meta-name'] = 'something'
        req.headers['x-image-meta-container_format'] = 'ami'
        req.headers['x-image-meta-disk_format'] = 'ami'
        res = req.get_response(self.api)
        image_id = jsonutils.loads(res.body)['image']['id']

        fixture_headers = {
            'content-type': 'application/octet-stream',
            'transfer-encoding': 'chunked',
        }
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'

        req.body_file = six.StringIO('X' * (CONF.image_size_cap + 1))
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

    def test_update_non_existing_image(self):
        self.config(image_size_cap=100)

        req = webob.Request.blank("images/%s" % _gen_uuid)
        req.method = 'PUT'
        req.body = 'test'
        req.headers['x-image-meta-name'] = 'test'
        req.headers['x-image-meta-container_format'] = 'ami'
        req.headers['x-image-meta-disk_format'] = 'ami'
        req.headers['x-image-meta-is_public'] = 'False'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_update_public_image(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-is-public': 'true',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'PUT'
        req.headers['x-image-meta-name'] = 'updated public image'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

    def test_add_image_wrong_content_type(self):
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'ami',
            'x-image-meta-disk_format': 'ami',
            'transfer-encoding': 'chunked',
            'content-type': 'application/octet-st',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_get_index_sort_name_asc(self):
        """
        Tests that the /images API returns list of
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
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(3, len(images))
        self.assertEqual(UUID3, images[0]['id'])
        self.assertEqual(UUID2, images[1]['id'])
        self.assertEqual(UUID4, images[2]['id'])

    def test_get_details_filter_changes_since(self):
        """
        Tests that the /images/detail API returns list of
        images that changed since the time defined by changes-since
        """
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)

        date_only1 = dt1.strftime('%Y-%m-%d')
        date_only2 = dt1.strftime('%Y%m%d')
        date_only3 = dt1.strftime('%Y-%m%d')

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
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(2, len(images))
        self.assertEqual(UUID4, images[0]['id'])
        self.assertEqual(UUID2, images[1]['id'])

        # Expect 3 images (1 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso1)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(3, len(images))
        self.assertEqual(UUID4, images[0]['id'])
        self.assertEqual(UUID3, images[1]['id'])  # deleted
        self.assertEqual(UUID2, images[2]['id'])

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso2)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(1, len(images))
        self.assertEqual(UUID4, images[0]['id'])

        # Expect 1 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_before)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], UUID4)

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' %
                                  hour_after)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(0, len(images))

        # Expect 0 images (0 deleted)
        req = webob.Request.blank('/images/detail?changes-since=%s' % iso4)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        images = res_dict['images']
        self.assertEqual(0, len(images))

        for param in [date_only1, date_only2, date_only3]:
            # Expect 3 images (1 deleted)
            req = webob.Request.blank('/images/detail?changes-since=%s' %
                                      param)
            res = req.get_response(self.api)
            self.assertEqual(200, res.status_int)
            res_dict = jsonutils.loads(res.body)
            images = res_dict['images']
            self.assertEqual(3, len(images))
            self.assertEqual(images[0]['id'], UUID4)
            self.assertEqual(images[1]['id'], UUID3)  # deleted
            self.assertEqual(images[2]['id'], UUID2)

        # Bad request (empty changes-since param)
        req = webob.Request.blank('/images/detail?changes-since=')
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_get_images_bad_urls(self):
        """Check that routes collections are not on (LP bug 1185828)"""
        req = webob.Request.blank('/images/detail.xxx')
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

        req = webob.Request.blank('/images.xxx')
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

        req = webob.Request.blank('/images/new')
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

        req = webob.Request.blank("/images/%s/members" % UUID1)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank("/images/%s/members.xxx" % UUID1)
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_get_index_filter_on_user_defined_properties(self):
        """Check that image filtering works on user-defined properties"""

        image1_id = _gen_uuid()
        properties = {'distro': 'ubuntu', 'arch': 'i386'}
        extra_fixture = {'id': image1_id,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'image-extra-1',
                         'size': 18, 'properties': properties,
                         'checksum': None}
        db_api.image_create(self.context, extra_fixture)

        image2_id = _gen_uuid()
        properties = {'distro': 'ubuntu', 'arch': 'x86_64', 'foo': 'bar'}
        extra_fixture = {'id': image2_id,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'image-extra-2',
                         'size': 20, 'properties': properties,
                         'checksum': None}
        db_api.image_create(self.context, extra_fixture)

        # Test index with filter containing one user-defined property.
        # Filter is 'property-distro=ubuntu'.
        # Verify both image1 and image2 are returned
        req = webob.Request.blank('/images?property-distro=ubuntu')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(images[0]['id'], image2_id)
        self.assertEqual(images[1]['id'], image1_id)

        # Test index with filter containing one user-defined property but
        # non-existent value. Filter is 'property-distro=fedora'.
        # Verify neither images are returned
        req = webob.Request.blank('/images?property-distro=fedora')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing one user-defined property but
        # unique value. Filter is 'property-arch=i386'.
        # Verify only image1 is returned.
        req = webob.Request.blank('/images?property-arch=i386')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image1_id)

        # Test index with filter containing one user-defined property but
        # unique value. Filter is 'property-arch=x86_64'.
        # Verify only image1 is returned.
        req = webob.Request.blank('/images?property-arch=x86_64')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Test index with filter containing unique user-defined property.
        # Filter is 'property-foo=bar'.
        # Verify only image2 is returned.
        req = webob.Request.blank('/images?property-foo=bar')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Test index with filter containing unique user-defined property but
        # .value is non-existent. Filter is 'property-foo=baz'.
        # Verify neither images are returned.
        req = webob.Request.blank('/images?property-foo=baz')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties
        # Filter is 'property-arch=x86_64&property-distro=ubuntu'.
        # Verify only image2 is returned.
        req = webob.Request.blank('/images?property-arch=x86_64&'
                                  'property-distro=ubuntu')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image2_id)

        # Test index with filter containing multiple user-defined properties
        # Filter is 'property-arch=i386&property-distro=ubuntu'.
        # Verify only image1 is returned.
        req = webob.Request.blank('/images?property-arch=i386&'
                                  'property-distro=ubuntu')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['id'], image1_id)

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-arch=random&property-distro=ubuntu'.
        # Verify neither images are returned.
        req = webob.Request.blank('/images?property-arch=random&'
                                  'property-distro=ubuntu')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-arch=random&property-distro=random'.
        # Verify neither images are returned.
        req = webob.Request.blank('/images?property-arch=random&'
                                  'property-distro=random')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-boo=far&property-poo=far'.
        # Verify neither images are returned.
        req = webob.Request.blank('/images?property-boo=far&'
                                  'property-poo=far')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-foo=bar&property-poo=far'.
        # Verify neither images are returned.
        req = webob.Request.blank('/images?property-foo=bar&'
                                  'property-poo=far')
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

    def test_get_images_detailed_unauthorized(self):
        rules = {"get_images": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_get_images_unauthorized(self):
        rules = {"get_images": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_store_location_not_revealed(self):
        """
        Test that the internal store location is NOT revealed
        through the API server
        """
        # Check index and details...
        for url in ('/images', '/images/detail'):
            req = webob.Request.blank(url)
            res = req.get_response(self.api)
            self.assertEqual(200, res.status_int)
            res_dict = jsonutils.loads(res.body)

            images = res_dict['images']
            num_locations = sum([1 for record in images
                                if 'location' in record.keys()])
            self.assertEqual(0, num_locations, images)

        # Check GET
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertNotIn('X-Image-Meta-Location', res.headers)

        # Check HEAD
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertNotIn('X-Image-Meta-Location', res.headers)

        # Check PUT
        req = webob.Request.blank("/images/%s" % UUID2)
        req.body = res.body
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_body = jsonutils.loads(res.body)
        self.assertNotIn('location', res_body['image'])

        # Check POST
        req = webob.Request.blank("/images")
        headers = {'x-image-meta-location': 'http://localhost',
                   'x-image-meta-disk-format': 'vhd',
                   'x-image-meta-container-format': 'ovf',
                   'x-image-meta-name': 'fake image #3'}
        for k, v in six.iteritems(headers):
            req.headers[k] = v
        req.method = 'POST'

        http = store.get_store_from_scheme('http')

        with mock.patch.object(http, 'get_size') as size:
            size.return_value = 0
            res = req.get_response(self.api)
            self.assertEqual(201, res.status_int)
            res_body = jsonutils.loads(res.body)
            self.assertNotIn('location', res_body['image'])

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual(image_checksum, res_body['checksum'],
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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        image = jsonutils.loads(res.body)['image']

        # HEAD the image and check the ETag equals the checksum header...
        expected_headers = {'x-image-meta-checksum': image_checksum,
                            'etag': image_checksum}
        req = webob.Request.blank("/images/%s" % image['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        for key in expected_headers.keys():
            self.assertIn(key, res.headers,
                          "required header '%s' missing from "
                          "returned headers" % key)
        for key, value in six.iteritems(expected_headers):
            self.assertEqual(value, res.headers[key])

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

        # Test that only one image was returned (that already exists)
        req = webob.Request.blank("/images")
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))

    def test_image_meta(self):
        """Test for HEAD /images/<ID>"""
        expected_headers = {'x-image-meta-id': UUID2,
                            'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertFalse(res.location)

        for key, value in six.iteritems(expected_headers):
            self.assertEqual(value, res.headers[key])

    def test_image_meta_unauthorized(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_show_image_basic(self):
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertFalse(res.location)
        self.assertEqual('application/octet-stream', res.content_type)
        self.assertEqual('chunk00000remainder', res.body)

    def test_show_non_exists_image(self):
        req = webob.Request.blank("/images/%s" % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_show_image_unauthorized(self):
        rules = {"get_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_show_image_unauthorized_download(self):
        rules = {"download_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_show_image_restricted_download_for_core_property(self):
        rules = {
            "restricted":
            "not ('1024M':%(min_ram)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.headers['X-Auth-Token'] = 'user:tenant:_member_'
        req.headers['min_ram'] = '1024M'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_show_image_restricted_download_for_custom_property(self):
        rules = {
            "restricted":
            "not ('test_1234'==%(x_test_key)s and role:_member_)",
            "download_image": "role:admin or rule:restricted"
        }
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.headers['X-Auth-Token'] = 'user:tenant:_member_'
        req.headers['x_test_key'] = 'test_1234'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_download_service_unavailable(self):
        """Test image download returns HTTPServiceUnavailable."""
        image_fixture = self.FIXTURES[1]
        image_fixture.update({'location': 'http://netloc/path/to/file.tar.gz'})
        request = webob.Request.blank("/images/%s" % UUID2)
        request.context = self.context

        image_controller = glance.api.v1.images.Controller()
        with mock.patch.object(image_controller,
                               'get_active_image_meta_or_error'
                               ) as mocked_get_image:
            mocked_get_image.return_value = image_fixture
            self.assertRaises(webob.exc.HTTPServiceUnavailable,
                              image_controller.show,
                              request, mocked_get_image)

    @mock.patch('glance_store._drivers.filesystem.Store.get')
    def test_show_image_store_get_not_support(self, m_get):
        m_get.side_effect = store.StoreGetNotSupported()
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    @mock.patch('glance_store._drivers.filesystem.Store.get')
    def test_show_image_store_random_get_not_support(self, m_get):
        m_get.side_effect = store.StoreRandomGetNotSupported(chunk_size=0,
                                                             offset=0)
        req = webob.Request.blank("/images/%s" % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_delete_image(self):
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertFalse(res.location)
        self.assertEqual('', res.body)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int, res.body)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual('True', res.headers['x-image-meta-deleted'])
        self.assertEqual('deleted', res.headers['x-image-meta-status'])

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/%s" % _gen_uuid())
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_delete_not_allowed(self):
        # Verify we can get the image data
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.headers['X-Auth-Token'] = 'user:tenant:'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual(19, len(res.body))

        # Verify we cannot delete the image
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

        # Verify the image data is still there
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual(19, len(res.body))

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank('/images/%s' % res_body['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual('True', res.headers['x-image-meta-deleted'])
        self.assertEqual('deleted', res.headers['x-image-meta-status'])

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
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank('/images/%s' % res_body['id'])
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        self.assertEqual('True', res.headers['x-image-meta-deleted'])
        self.assertEqual('deleted', res.headers['x-image-meta-status'])

    def test_delete_protected_image(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-protected': 'True'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in six.iteritems(fixture_headers):
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEqual(201, res.status_int)

        res_body = jsonutils.loads(res.body)['image']
        self.assertEqual('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_delete_image_unauthorized(self):
        rules = {"delete_image": '!'}
        self.set_policy_rules(rules)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(403, res.status_int)

    def test_head_details(self):
        req = webob.Request.blank('/images/detail')
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(405, res.status_int)
        self.assertEqual('GET', res.headers.get('Allow'))
        self.assertEqual(('GET',), res.allow)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail API returns a 400
        when an invalid marker is provided
        """
        req = webob.Request.blank('/images/detail?marker=%s' % _gen_uuid())
        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEqual(0, num_members)

    def test_get_image_members_allowed_by_policy(self):
        rules = {"get_members": '@'}
        self.set_policy_rules(rules)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEqual(0, num_members)

    def test_get_image_members_forbidden_by_policy(self):
        rules = {"get_members": '!'}
        self.set_policy_rules(rules)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, res.status_int)

    def test_get_image_members_not_existing(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image
        """
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_add_member_positive(self):
        """
        Tests adding image members
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

    def test_get_member_images(self):
        """
        Tests image listing for members
        """
        req = webob.Request.blank('/shared-images/pattieblack')
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['shared_images'])
        self.assertEqual(0, num_members)

    def test_replace_members(self):
        """
        Tests replacing image members raises right exception
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=False)
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEqual(401, res.status_int)

    def test_active_image_immutable_props_for_user(self):
        """
        Tests user cannot update immutable props of active image
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=False)
        fixture_header_list = [{'x-image-meta-checksum': '1234'},
                               {'x-image-meta-size': '12345'}]
        for fixture_header in fixture_header_list:
            req = webob.Request.blank('/images/%s' % UUID2)
            req.method = 'PUT'
            for k, v in six.iteritems(fixture_header):
                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)
                orig_value = res.headers[k]

                req = webob.Request.blank('/images/%s' % UUID2)
                req.headers[k] = v
                req.method = 'PUT'
                res = req.get_response(self.api)
                self.assertEqual(403, res.status_int)
                prop = k[len('x-image-meta-'):]
                self.assertNotEqual(res.body.find("Forbidden to modify '%s' "
                                                  "of active "
                                                  "image" % prop), -1)

                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)
                self.assertEqual(orig_value, res.headers[k])

    def test_props_of_active_image_mutable_for_admin(self):
        """
        Tests admin can update 'immutable' props of active image
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        fixture_header_list = [{'x-image-meta-checksum': '1234'},
                               {'x-image-meta-size': '12345'}]
        for fixture_header in fixture_header_list:
            req = webob.Request.blank('/images/%s' % UUID2)
            req.method = 'PUT'
            for k, v in six.iteritems(fixture_header):
                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)

                req = webob.Request.blank('/images/%s' % UUID2)
                req.headers[k] = v
                req.method = 'PUT'
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)

                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEqual(200, res.status_int)
                self.assertEqual(v, res.headers[k])

    def test_replace_members_non_existing_image(self):
        """
        Tests replacing image members raises right exception
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        fixture = dict(member_id='pattieblack')
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_replace_members_bad_request(self):
        """
        Tests replacing image members raises bad request if body is wrong
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEqual(400, res.status_int)

    def test_replace_members_positive(self):
        """
        Tests replacing image members
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=True)

        fixture = [dict(member_id='pattieblack', can_share=False)]
        # Replace
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

    def test_replace_members_forbidden_by_policy(self):
        rules = {"modify_member": '!'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]

        req = webob.Request.blank('/images/%s/members' % UUID1)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(memberships=fixture))

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, res.status_int)

    def test_replace_members_allowed_by_policy(self):
        rules = {"modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]

        req = webob.Request.blank('/images/%s/members' % UUID1)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(memberships=fixture))

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNoContent.code, res.status_int)

    def test_add_member_unauthorized(self):
        """
        Tests adding image members raises right exception
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(401, res.status_int)

    def test_add_member_non_existing_image(self):
        """
        Tests adding image members raises right exception
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=True)
        test_uri = '/images/%s/members/pattieblack'
        req = webob.Request.blank(test_uri % _gen_uuid())
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)

    def test_add_member_with_body(self):
        """
        Tests adding image members
        """
        fixture = dict(can_share=True)
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        req.body = jsonutils.dumps(dict(member=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

    def test_add_member_overlimit(self):
        self.config(image_member_quota=0)
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

    def test_add_member_unlimited(self):
        self.config(image_member_quota=-1)
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

    def test_add_member_forbidden_by_policy(self):
        rules = {"modify_member": '!'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID1)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, res.status_int)

    def test_add_member_allowed_by_policy(self):
        rules = {"modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID1)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNoContent.code, res.status_int)

    def test_get_members_of_deleted_image_raises_404(self):
        """
        Tests members listing for deleted image raises 404.
        """
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNotFound.code, res.status_int)
        self.assertIn(
            'Image with identifier %s has been deleted.' % UUID2, res.body)

    def test_delete_member_of_deleted_image_raises_404(self):
        """
        Tests deleting members of deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNotFound.code, res.status_int)
        self.assertIn(
            'Image with identifier %s has been deleted.' % UUID2, res.body)

    def test_update_members_of_deleted_image_raises_404(self):
        """
        Tests update members of deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNotFound.code, res.status_int)
        self.assertIn(
            'Image with identifier %s has been deleted.' % UUID2, res.body)

    def test_replace_members_of_image(self):
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)

        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)
        self.assertEqual(1, len(memb_list))

    def test_replace_members_of_image_overlimit(self):
        # Set image_member_quota to 1
        self.config(image_member_quota=1)
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)

        # PUT an original member entry
        fixture = [{'member_id': 'baz', 'can_share': False}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

        # GET original image member list
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        original_members = jsonutils.loads(res.body)['members']
        self.assertEqual(1, len(original_members))

        # PUT 2 image members to replace existing (overlimit)
        fixture = [{'member_id': 'foo1', 'can_share': False},
                   {'member_id': 'foo2', 'can_share': False}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(413, res.status_int)

        # GET member list
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        # Assert the member list was not changed
        memb_list = jsonutils.loads(res.body)['members']
        self.assertEqual(original_members, memb_list)

    def test_replace_members_of_image_unlimited(self):
        self.config(image_member_quota=-1)
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)

        fixture = [{'member_id': 'foo1', 'can_share': False},
                   {'member_id': 'foo2', 'can_share': False}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.body = jsonutils.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        memb_list = jsonutils.loads(res.body)['members']
        self.assertEqual(fixture, memb_list)

    def test_create_member_to_deleted_image_raises_404(self):
        """
        Tests adding members to deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNotFound.code, res.status_int)
        self.assertIn(
            'Image with identifier %s has been deleted.' % UUID2, res.body)

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEqual(401, res.status_int)

    def test_delete_member_on_non_existing_image(self):
        """
        Tests deleting image members raises right exception
        """
        test_router = router.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)
        test_uri = '/images/%s/members/pattieblack'
        req = webob.Request.blank(test_uri % _gen_uuid())
        req.method = 'DELETE'

        res = req.get_response(api)
        self.assertEqual(404, res.status_int)

    def test_delete_non_exist_member(self):
        """
        Test deleting image members raises right exception
        """
        test_router = router.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=True)
        req = webob.Request.blank('/images/%s/members/test_user' % UUID2)
        req.method = 'DELETE'
        res = req.get_response(api)
        self.assertEqual(404, res.status_int)

    def test_delete_image_member(self):
        test_rserver = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_rserver, is_admin=True)

        # Add member to image:
        fixture = dict(can_share=True)
        test_uri = '/images/%s/members/test_add_member_positive'
        req = webob.Request.blank(test_uri % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(member=fixture))
        res = req.get_response(self.api)
        self.assertEqual(204, res.status_int)

        # Delete member
        test_uri = '/images/%s/members/test_add_member_positive'
        req = webob.Request.blank(test_uri % UUID2)
        req.headers['X-Auth-Token'] = 'test1:test1:'
        req.method = 'DELETE'
        req.content_type = 'application/json'
        res = req.get_response(self.api)
        self.assertEqual(404, res.status_int)
        self.assertIn('Forbidden', res.body)

    def test_delete_member_allowed_by_policy(self):
        rules = {"delete_member": '@', "modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNoContent.code, res.status_int)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNoContent.code, res.status_int)

    def test_delete_member_forbidden_by_policy(self):
        rules = {"delete_member": '!', "modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPNoContent.code, res.status_int)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, res.status_int)


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
        self.serializer = glance.api.v1.images.ImageSerializer()

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
        for key, value in six.iteritems(exp_headers):
            self.assertEqual(value, response.headers[key])

    def test_meta_utf8(self):
        # We get unicode strings from JSON, and therefore all strings in the
        # metadata will actually be unicode when handled internally. But we
        # want to output utf-8.
        FIXTURE = {
            'image_meta': {
                'id': six.text_type(UUID2),
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
                'owner': six.text_type(_gen_uuid()),
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
        self.assertEqual(FIXTURE['image_meta']['name'],
                         response.headers['x-image-meta-name'].decode('utf-8'))
        for key, value in six.iteritems(exp_headers):
            self.assertEqual(value, response.headers[key])

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
        for key, value in six.iteritems(exp_headers):
            self.assertEqual(value, response.headers[key])

        self.assertEqual('chunk67891123456789', response.body)

    def test_show_notify(self):
        """Make sure an eventlet posthook for notify_image_sent is added."""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.context = self.context
        response = webob.Response(request=req)
        response.request.environ['eventlet.posthooks'] = []

        self.serializer.show(response, self.FIXTURE)

        # just make sure the app_iter is called
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
            self.assertEqual(expected_payload, _payload)
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
            self.assertEqual(expected_payload, _payload)
            called['notified'] = True

        self.stubs.Set(self.serializer.notifier, 'error', fake_error)

        # expected and actually sent bytes differ
        glance.api.common.image_send_notification(17, 19, image_meta, req,
                                                  self.serializer.notifier)

        self.assertTrue(called['notified'])

    def test_redact_location(self):
        """Ensure location redaction does not change original metadata"""
        image_meta = {'size': 3, 'id': '123', 'location': 'http://localhost'}
        redacted_image_meta = {'size': 3, 'id': '123'}
        copy_image_meta = copy.deepcopy(image_meta)
        tmp_image_meta = glance.api.v1.images.redact_loc(image_meta)

        self.assertEqual(image_meta, copy_image_meta)
        self.assertEqual(redacted_image_meta, tmp_image_meta)

    def test_noop_redact_location(self):
        """Check no-op location redaction does not change original metadata"""
        image_meta = {'size': 3, 'id': '123'}
        redacted_image_meta = {'size': 3, 'id': '123'}
        copy_image_meta = copy.deepcopy(image_meta)
        tmp_image_meta = glance.api.v1.images.redact_loc(image_meta)

        self.assertEqual(image_meta, copy_image_meta)
        self.assertEqual(redacted_image_meta, tmp_image_meta)
        self.assertEqual(redacted_image_meta, image_meta)


class TestFilterValidator(base.IsolatedUnitTest):
    def test_filter_validator(self):
        self.assertFalse(glance.api.v1.filters.validate('size_max', -1))
        self.assertTrue(glance.api.v1.filters.validate('size_max', 1))
        self.assertTrue(glance.api.v1.filters.validate('protected', 'True'))
        self.assertTrue(glance.api.v1.filters.validate('protected', 'FALSE'))
        self.assertFalse(glance.api.v1.filters.validate('protected', '-1'))


class TestAPIProtectedProps(base.IsolatedUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestAPIProtectedProps, self).setUp()
        self.mapper = routes.Mapper()
        # turn on property protections
        self.set_property_protections()
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper))
        db_api.get_engine()
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def tearDown(self):
        """Clear the test environment"""
        super(TestAPIProtectedProps, self).tearDown()
        self.destroy_fixtures()

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def _create_admin_image(self, props=None):
        if props is None:
            props = {}
        request = unit_test_utils.get_fake_request(path='/images')
        headers = {'x-image-meta-disk-format': 'ami',
                   'x-image-meta-container-format': 'ami',
                   'x-image-meta-name': 'foo',
                   'x-image-meta-size': '0',
                   'x-auth-token': 'user:tenant:admin'}
        headers.update(props)
        for k, v in six.iteritems(headers):
            request.headers[k] = v
        created_image = request.get_response(self.api)
        res_body = jsonutils.loads(created_image.body)['image']
        image_id = res_body['id']
        return image_id

    def test_prop_protection_with_create_and_permitted_role(self):
        """
        As admin role, create an image and verify permitted role 'member' can
        create a protected property
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_owner_foo': 'bar'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('bar', res_body['properties']['x_owner_foo'])

    def test_prop_protection_with_permitted_policy_config(self):
        """
        As admin role, create an image and verify permitted role 'member' can
        create a protected property
        """
        self.set_property_protections(use_policies=True)
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:admin',
                   'x-image-meta-property-spl_create_prop_policy': 'bar'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('bar',
                         res_body['properties']['spl_create_prop_policy'])

    def test_prop_protection_with_create_and_unpermitted_role(self):
        """
        As admin role, create an image and verify unpermitted role
        'fake_member' can *not* create a protected property
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:fake_member',
                   'x-image-meta-property-x_owner_foo': 'bar'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        another_request.get_response(self.api)
        output = another_request.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, output.status_int)
        self.assertIn("Property '%s' is protected" %
                      "x_owner_foo", output.body)

    def test_prop_protection_with_show_and_permitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'member' can read that protected property via HEAD
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        res2 = another_request.get_response(self.api)
        self.assertEqual('bar',
                         res2.headers['x-image-meta-property-x_owner_foo'])

    def test_prop_protection_with_show_and_unpermitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'fake_role' can *not* read that protected property via
        HEAD
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:fake_role'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertNotIn('x-image-meta-property-x_owner_foo', output.headers)

    def test_prop_protection_with_get_and_permitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'member' can read that protected property via GET
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        res2 = another_request.get_response(self.api)
        self.assertEqual('bar',
                         res2.headers['x-image-meta-property-x_owner_foo'])

    def test_prop_protection_with_get_and_unpermitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'fake_role' can *not* read that protected property via
        GET
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:fake_role'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertNotIn('x-image-meta-property-x_owner_foo', output.headers)

    def test_prop_protection_with_detail_and_permitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'member' can read that protected property via
        /images/detail
        """
        self._create_admin_image({'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['images'][0]
        self.assertEqual('bar', res_body['properties']['x_owner_foo'])

    def test_prop_protection_with_detail_and_permitted_policy(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'member' can read that protected property via
        /images/detail
        """
        self.set_property_protections(use_policies=True)
        self._create_admin_image({'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['images'][0]
        self.assertEqual('bar', res_body['properties']['x_owner_foo'])

    def test_prop_protection_with_detail_and_unpermitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'fake_role' can *not* read that protected property via
        /images/detail
        """
        self._create_admin_image({'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:fake_role'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['images'][0]
        self.assertNotIn('x-image-meta-property-x_owner_foo',
                         res_body['properties'])

    def test_prop_protection_with_detail_and_unpermitted_policy(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'fake_role' can *not* read that protected property via
        /images/detail
        """
        self.set_property_protections(use_policies=True)
        self._create_admin_image({'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:fake_role'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['images'][0]
        self.assertNotIn('x-image-meta-property-x_owner_foo',
                         res_body['properties'])

    def test_prop_protection_with_update_and_permitted_role(self):
        """
        As admin role, create an image with protected property, and verify
        permitted role 'member' can update that protected property
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_owner_foo': 'baz'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('baz', res_body['properties']['x_owner_foo'])

    def test_prop_protection_with_update_and_permitted_policy(self):
        """
        As admin role, create an image with protected property, and verify
        permitted role 'admin' can update that protected property
        """
        self.set_property_protections(use_policies=True)
        image_id = self._create_admin_image(
            {'x-image-meta-property-spl_default_policy': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:admin',
                   'x-image-meta-property-spl_default_policy': 'baz'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('baz', res_body['properties']['spl_default_policy'])

    def test_prop_protection_with_update_and_unpermitted_role(self):
        """
        As admin role, create an image with protected property, and verify
        unpermitted role 'fake_role' can *not* update that protected property
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:fake_role',
                   'x-image-meta-property-x_owner_foo': 'baz'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, output.status_int)
        self.assertIn("Property '%s' is protected" %
                      "x_owner_foo", output.body)

    def test_prop_protection_with_update_and_unpermitted_policy(self):
        """
        As admin role, create an image with protected property, and verify
        unpermitted role 'fake_role' can *not* update that protected property
        """
        self.set_property_protections(use_policies=True)
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:fake_role',
                   'x-image-meta-property-x_owner_foo': 'baz'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, output.status_int)
        self.assertIn("Property '%s' is protected" %
                      "x_owner_foo", output.body)

    def test_prop_protection_update_without_read(self):
        """
        Test protected property cannot be updated without read permission
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-spl_update_only_prop': 'foo'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_update_only_prop': 'bar'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(webob.exc.HTTPForbidden.code, output.status_int)
        self.assertIn("Property '%s' is protected" %
                      "spl_update_only_prop", output.body)

    def test_prop_protection_update_noop(self):
        """
        Test protected property update is allowed as long as the user has read
        access and the value is unchanged
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-spl_read_prop': 'foo'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_read_prop': 'foo'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('foo', res_body['properties']['spl_read_prop'])
        self.assertEqual(200, output.status_int)

    def test_prop_protection_with_delete_and_permitted_role(self):
        """
        As admin role, create an image with protected property, and verify
        permitted role 'member' can can delete that protected property
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual({}, res_body['properties'])

    def test_prop_protection_with_delete_and_permitted_policy(self):
        """
        As admin role, create an image with protected property, and verify
        permitted role 'member' can can delete that protected property
        """
        self.set_property_protections(use_policies=True)
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual({}, res_body['properties'])

    def test_prop_protection_with_delete_and_unpermitted_read(self):
        """
        Test protected property cannot be deleted without read permission
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_owner_foo': 'bar'})

        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:fake_role',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertNotIn('x-image-meta-property-x_owner_foo', output.headers)

        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:admin'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertEqual('bar',
                         output.headers['x-image-meta-property-x_owner_foo'])

    def test_prop_protection_with_delete_and_unpermitted_delete(self):
        """
        Test protected property cannot be deleted without delete permission
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-spl_update_prop': 'foo'})

        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)
        self.assertIn("Property '%s' is protected" %
                      "spl_update_prop", output.body)

        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:admin'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertEqual(
            'foo', output.headers['x-image-meta-property-spl_update_prop'])

    def test_read_protected_props_leak_with_update(self):
        """
        Verify when updating props that ones we don't have read permission for
        are not disclosed
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-spl_update_prop': '0',
             'x-image-meta-property-foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_update_prop': '1',
                   'X-Glance-Registry-Purge-Props': 'False'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('1', res_body['properties']['spl_update_prop'])
        self.assertNotIn('foo', res_body['properties'])

    def test_update_protected_props_mix_no_read(self):
        """
        Create an image with two props - one only readable by admin, and one
        readable/updatable by member.  Verify member can successfully update
        their property while the admin owned one is ignored transparently
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-admin_foo': 'bar',
             'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_owner_foo': 'baz'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('baz', res_body['properties']['x_owner_foo'])
        self.assertNotIn('admin_foo', res_body['properties'])

    def test_update_protected_props_mix_read(self):
        """
        Create an image with two props - one readable/updatable by admin, but
        also readable by spl_role.  The other is readable/updatable by
        spl_role.  Verify spl_role can successfully update their property but
        not the admin owned one
        """
        custom_props = {
            'x-image-meta-property-spl_read_only_prop': '1',
            'x-image-meta-property-spl_update_prop': '2'
        }
        image_id = self._create_admin_image(custom_props)
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')

        # verify spl_role can update it's prop
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_read_only_prop': '1',
                   'x-image-meta-property-spl_update_prop': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual(200, output.status_int)
        self.assertEqual('1', res_body['properties']['spl_read_only_prop'])
        self.assertEqual('1', res_body['properties']['spl_update_prop'])

        # verify spl_role can not update admin controlled prop
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_read_only_prop': '2',
                   'x-image-meta-property-spl_update_prop': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)

    def test_delete_protected_props_mix_no_read(self):
        """
        Create an image with two props - one only readable by admin, and one
        readable/deletable by member.  Verify member can successfully delete
        their property while the admin owned one is ignored transparently
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-admin_foo': 'bar',
                'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertNotIn('x_owner_foo', res_body['properties'])
        self.assertNotIn('admin_foo', res_body['properties'])

    def test_delete_protected_props_mix_read(self):
        """
        Create an image with two props - one readable/deletable by admin, but
        also readable by spl_role.  The other is readable/deletable by
        spl_role.  Verify spl_role is forbidden to purge_props in this scenario
        without retaining the readable prop.
        """
        custom_props = {
            'x-image-meta-property-spl_read_only_prop': '1',
            'x-image-meta-property-spl_delete_prop': '2'
        }
        image_id = self._create_admin_image(custom_props)
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)

    def test_create_protected_prop_check_case_insensitive(self):
        """
        Verify that role check is case-insensitive i.e. the property
        marked with role Member is creatable by the member role
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_case_insensitive': '1'}
        for k, v in six.iteritems(headers):
                another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('1', res_body['properties']['x_case_insensitive'])

    def test_read_protected_prop_check_case_insensitive(self):
        """
        Verify that role check is case-insensitive i.e. the property
        marked with role Member is readable by the member role
        """
        custom_props = {
            'x-image-meta-property-x_case_insensitive': '1'
        }
        image_id = self._create_admin_image(custom_props)
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertEqual(
            '1', output.headers['x-image-meta-property-x_case_insensitive'])

    def test_update_protected_props_check_case_insensitive(self):
        """
        Verify that role check is case-insensitive i.e. the property
        marked with role Member is updatable by the member role
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_case_insensitive': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_case_insensitive': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('2', res_body['properties']['x_case_insensitive'])

    def test_delete_protected_props_check_case_insensitive(self):
        """
        Verify that role check is case-insensitive i.e. the property
        marked with role Member is deletable by the member role
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_case_insensitive': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual({}, res_body['properties'])

    def test_create_non_protected_prop(self):
        """
        Verify property marked with special char '@' is creatable by an unknown
        role
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-image-meta-property-x_all_permitted': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('1', res_body['properties']['x_all_permitted'])

    def test_read_non_protected_prop(self):
        """
        Verify property marked with special char '@' is readable by an unknown
        role
        """
        custom_props = {
            'x-image-meta-property-x_all_permitted': '1'
        }
        image_id = self._create_admin_image(custom_props)
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:joe_soap'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertEqual('', output.body)
        self.assertEqual(
            '1', output.headers['x-image-meta-property-x_all_permitted'])

    def test_update_non_protected_prop(self):
        """
        Verify property marked with special char '@' is updatable by an unknown
        role
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_all_permitted': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-image-meta-property-x_all_permitted': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('2', res_body['properties']['x_all_permitted'])

    def test_delete_non_protected_prop(self):
        """
        Verify property marked with special char '@' is deletable by an unknown
        role
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_all_permitted': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual({}, res_body['properties'])

    def test_create_locked_down_protected_prop(self):
        """
        Verify a property protected by special char '!' is creatable by no one
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_none_permitted': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)
        # also check admin can not create
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:admin',
                   'x-image-meta-property-x_none_permitted_admin': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)

    def test_read_locked_down_protected_prop(self):
        """
        Verify a property protected by special char '!' is readable by no one
        """
        custom_props = {
            'x-image-meta-property-x_none_read': '1'
        }
        image_id = self._create_admin_image(custom_props)
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertNotIn('x_none_read', output.headers)
        # also check admin can not read
        another_request = unit_test_utils.get_fake_request(
            method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:admin'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(200, output.status_int)
        self.assertNotIn('x_none_read', output.headers)

    def test_update_locked_down_protected_prop(self):
        """
        Verify a property protected by special char '!' is updatable by no one
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_none_update': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_none_update': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)
        # also check admin can't update property
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:admin',
                   'x-image-meta-property-x_none_update': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)

    def test_delete_locked_down_protected_prop(self):
        """
        Verify a property protected by special char '!' is deletable by no one
        """
        image_id = self._create_admin_image(
            {'x-image-meta-property-x_none_delete': '1'})
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)
        # also check admin can't delete
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:admin',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(403, output.status_int)


class TestAPIPropertyQuotas(base.IsolatedUnitTest):
    def setUp(self):
        """Establish a clean test environment"""
        super(TestAPIPropertyQuotas, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper))
        db_api.get_engine()
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def _create_admin_image(self, props=None):
        if props is None:
            props = {}
        request = unit_test_utils.get_fake_request(path='/images')
        headers = {'x-image-meta-disk-format': 'ami',
                   'x-image-meta-container-format': 'ami',
                   'x-image-meta-name': 'foo',
                   'x-image-meta-size': '0',
                   'x-auth-token': 'user:tenant:admin'}
        headers.update(props)
        for k, v in six.iteritems(headers):
            request.headers[k] = v
        created_image = request.get_response(self.api)
        res_body = jsonutils.loads(created_image.body)['image']
        image_id = res_body['id']
        return image_id

    def test_update_image_with_too_many_properties(self):
        """
        Ensure that updating image properties enforces the quota.
        """
        self.config(image_property_quota=1)
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-image-meta-property-x_all_permitted': '1',
                   'x-image-meta-property-x_all_permitted_foo': '2'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v

        output = another_request.get_response(self.api)

        self.assertEqual(413, output.status_int)
        self.assertIn("Attempted: 2, Maximum: 1", output.text)

    def test_update_image_with_too_many_properties_without_purge_props(self):
        """
        Ensure that updating image properties counts existing image propertys
        when enforcing property quota.
        """
        self.config(image_property_quota=1)
        request = unit_test_utils.get_fake_request(path='/images')
        headers = {'x-image-meta-disk-format': 'ami',
                   'x-image-meta-container-format': 'ami',
                   'x-image-meta-name': 'foo',
                   'x-image-meta-size': '0',
                   'x-image-meta-property-x_all_permitted_create': '1',
                   'x-auth-token': 'user:tenant:admin'}
        for k, v in six.iteritems(headers):
            request.headers[k] = v
        created_image = request.get_response(self.api)
        res_body = jsonutils.loads(created_image.body)['image']
        image_id = res_body['id']

        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-glance-registry-purge-props': 'False',
                   'x-image-meta-property-x_all_permitted': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v

        output = another_request.get_response(self.api)

        self.assertEqual(413, output.status_int)
        self.assertIn("Attempted: 2, Maximum: 1", output.text)

    def test_update_properties_without_purge_props_overwrite_value(self):
        """
        Ensure that updating image properties does not count against image
        property quota.
        """
        self.config(image_property_quota=2)
        request = unit_test_utils.get_fake_request(path='/images')
        headers = {'x-image-meta-disk-format': 'ami',
                   'x-image-meta-container-format': 'ami',
                   'x-image-meta-name': 'foo',
                   'x-image-meta-size': '0',
                   'x-image-meta-property-x_all_permitted_create': '1',
                   'x-auth-token': 'user:tenant:admin'}
        for k, v in six.iteritems(headers):
            request.headers[k] = v
        created_image = request.get_response(self.api)
        res_body = jsonutils.loads(created_image.body)['image']
        image_id = res_body['id']

        another_request = unit_test_utils.get_fake_request(
            path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:joe_soap',
                   'x-glance-registry-purge-props': 'False',
                   'x-image-meta-property-x_all_permitted_create': '3',
                   'x-image-meta-property-x_all_permitted': '1'}
        for k, v in six.iteritems(headers):
            another_request.headers[k] = v

        output = another_request.get_response(self.api)

        self.assertEqual(200, output.status_int)
        res_body = jsonutils.loads(output.body)['image']
        self.assertEqual('1', res_body['properties']['x_all_permitted'])
        self.assertEqual('3', res_body['properties']['x_all_permitted_create'])
