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

import copy
import datetime
import hashlib
import json
import StringIO

from oslo.config import cfg
import routes
import webob

import glance.api
import glance.api.common
from glance.api.v1 import filters
from glance.api.v1 import images
from glance.api.v1 import router
from glance.common import exception
import glance.common.config
import glance.context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils
import glance.store.filesystem
from glance.tests.unit import base
from glance.tests import utils as test_utils
import glance.tests.unit.utils as unit_test_utils

CONF = cfg.CONF

_gen_uuid = uuidutils.generate_uuid

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


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
             'checksum': 'abc123',
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
        self.assertEquals(res.status_int, 400)
        self.assertTrue('Invalid disk format' in res.body, res.body)

    def test_configured_disk_format_good(self):
        self.config(disk_formats=['foo'])
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'foo',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

    def test_configured_disk_format_bad(self):
        self.config(disk_formats=['foo'])
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'bar',
            'x-image-meta-container-format': 'bare',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)
        self.assertTrue('Invalid disk format' in res.body, res.body)

    def test_configured_container_format_good(self):
        self.config(container_formats=['foo'])
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'raw',
            'x-image-meta-container-format': 'foo',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

    def test_configured_container_format_bad(self):
        self.config(container_formats=['foo'])
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'raw',
            'x-image-meta-container-format': 'bar',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)
        self.assertTrue('Invalid container format' in res.body, res.body)

    def test_container_and_disk_amazon_format_differs(self):
        fixture_headers = {
            'x-image-meta-store': 'bad',
            'x-image-meta-name': 'bogus',
            'x-image-meta-location': 'http://localhost:0/image.tar.gz',
            'x-image-meta-disk-format': 'aki',
            'x-image-meta-container-format': 'ami'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        expected = ("Invalid mix of disk and container formats. "
                    "When setting a disk or container format to one of "
                    "'aki', 'ari', or 'ami', "
                    "the container and disk formats must match.")
        self.assertEquals(res.status_int, 400)
        self.assertTrue(expected in res.body, res.body)

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
        self.assertEquals(res.status_int, 400)
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
        self.assertEquals(res.status_int, 400)
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
        self.assertEquals(res.status_int, 400)
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
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 201)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])
        image_id = res_body['id']

        # Test that we are able to edit the Location field
        # per LP Bug #911599

        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'PUT'
        req.headers['x-image-meta-location'] = 'http://localhost:0/images/123'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

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
        self.assertEquals(res.status_int, 413)

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

    def test_add_image_size_header_exceed_quota(self):
        quota = 500
        self.config(user_storage_quota=quota)
        fixture_headers = {'x-image-meta-size': quota + 1,
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-container_format': 'bare',
                           'x-image-meta-disk_format': 'qcow2',
                           'content-type': 'application/octet-stream',
                           }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        req.body = 'X' * (quota + 1)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 413)

    def test_add_image_size_data_exceed_quota(self):
        quota = 500
        self.config(user_storage_quota=quota)
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'bare',
            'x-image-meta-disk_format': 'qcow2',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'

        req.body = 'X' * (quota + 1)
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 413)

    def test_add_image_size_data_exceed_quota_readd(self):
        quota = 500
        self.config(user_storage_quota=quota)
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
            'x-image-meta-container_format': 'bare',
            'x-image-meta-disk_format': 'qcow2',
            'content-type': 'application/octet-stream',
        }

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = 'X' * (quota + 1)
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 413)

        used_size = sum([f['size'] for f in self.FIXTURES])

        req = webob.Request.blank("/images")
        req.method = 'POST'
        req.body = 'X' * (quota - used_size)
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

    def _add_check_no_url_info(self):

        fixture_headers = {'x-image-meta-disk-format': 'ami',
                           'x-image-meta-container-format': 'ami',
                           'x-image-meta-size': '0',
                           'x-image-meta-name': 'empty image'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        res_body = json.loads(res.body)['image']
        self.assertFalse('locations' in res_body)
        self.assertFalse('direct_url' in res_body)
        image_id = res_body['id']

        # HEAD empty image
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertFalse('x-image-meta-locations' in res.headers)
        self.assertFalse('x-image-meta-direct_url' in res.headers)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

        res_body = json.loads(res.body)['image']
        self.assertEquals('active', res_body['status'])
        image_id = res_body['id']

        # GET empty image
        req = webob.Request.blank("/images/%s" % image_id)
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(len(res.body), 0)

    def _do_test_add_image_attribute_mismatch(self, attributes):
        fixture_headers = {
            'x-image-meta-name': 'fake image #3',
        }
        fixture_headers.update(attributes)

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "XXXX"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 400)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_add_publicize_image_authorized(self):
        rules = {"add_image": '@', "modify_image": '@',
                 "publicize_image": '@'}
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
        self.assertEquals(res.status_int, 201)

    def test_add_copy_from_image_unauthorized(self):
        rules = {"add_image": '@', "copy_from": '!'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': 'http://glance.com/i.ovf',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

    def test_add_copy_from_image_authorized(self):
        rules = {"add_image": '@', "copy_from": '@'}
        self.set_policy_rules(rules)
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-glance-api-copy-from': 'http://glance.com/i.ovf',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_add_location_with_conflict_image_size(self):
        """Tests creates an image from location and conflict image size"""

        self.stubs.Set(glance.api.v1.images, 'get_size_from_backend',
                       lambda *args, **kwargs: 2)

        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-location': 'http://a/b/c.tar.gz',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #F',
                           'x-image-meta-size': '1'}

        req = webob.Request.blank("/images")
        req.headers['Content-Type'] = 'application/octet-stream'
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 409)

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
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 403)
        self.assertTrue('Forbidden to update deleted image' in res.body)

    def test_delete_deleted_image(self):
        """Tests that exception raised trying to delete a deleted image"""
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        # Verify the status is deleted
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEqual("deleted", res.headers['x-image-meta-status'])

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)
        msg = "Image %s not found." % UUID2
        self.assertTrue(msg in res.body)

        # Verify the status is still deleted
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEqual("deleted", res.headers['x-image-meta-status'])

    def test_delete_pending_delete_image(self):
        """
        Tests that correct response returned when deleting
        a pending_delete image
        """
        # First deletion
        self.config(delayed_delete=True, scrubber_datadir='/tmp/scrubber')
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        # Verify the status is pending_delete
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEqual("pending_delete", res.headers['x-image-meta-status'])

        # Second deletion
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)
        self.assertTrue('Forbidden to delete a pending_delete image'
                        in res.body)

        # Verify the status is still pending_delete
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
        self.assertEqual("pending_delete", res.headers['x-image-meta-status'])

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
        self.assertEquals(res.status_int, 201)
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
        self.assertEquals(res.status_int, 200)

        # Verify the status is queued
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
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
        self.assertEquals(res.status_int, 201)
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
        self.assertEquals(res.status_int, 200)

        # Verify the original property no longer in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
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
        self.assertEquals(res.status_int, 200)

        # Verify the second and third property in headers
        req = webob.Request.blank("/images/%s" % image_id)
        req.method = 'HEAD'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 413)

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
        self.assertEqual(res.status_int, 404)

    def test_update_public_image(self):
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-is-public': 'true',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

        res_body = json.loads(res.body)['image']
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'PUT'
        req.headers['x-image-meta-name'] = 'updated public image'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

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

    def test_get_images_bad_urls(self):
        """Check that routes collections are not on (LP bug 1185828)"""
        req = webob.Request.blank('/images/detail.xxx')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

        req = webob.Request.blank('/images.xxx')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

        req = webob.Request.blank('/images/new')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

        req = webob.Request.blank("/images/%s/members" % UUID1)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/%s/members.xxx" % UUID1)
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 400)

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
        self.assertEquals(res.status_int, 404)

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
        self.assertEquals(res.body, '')

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404,
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
        self.assertEquals(res.status_int, 404)

    def test_delete_not_allowed(self):
        # Verify we can get the image data
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'GET'
        req.headers['X-Auth-Token'] = 'user:tenant:'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(len(res.body), 19)

        # Verify we cannot delete the image
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 403)

        # Verify the image data is still there
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(len(res.body), 19)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 201)

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
        self.assertEquals(res.status_int, 201)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/%s" % res_body['id'])
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 403)

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

    def test_get_image_members_allowed_by_policy(self):
        rules = {"get_members": '@'}
        self.set_policy_rules(rules)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        memb_list = json.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEquals(num_members, 0)

    def test_get_image_members_forbidden_by_policy(self):
        rules = {"get_members": '!'}
        self.set_policy_rules(rules)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)

    def test_get_image_members_not_existing(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image
        """
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

    def test_add_member(self):
        """
        Tests adding image members
        """
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=True)
        req = webob.Request.blank('/images/%s/members/test' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 201)

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
        test_router_api = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router_api, is_admin=False)
        fixture = dict(member_id='pattieblack')

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 401)

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
            for k, v in fixture_header.iteritems():
                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 200)
                orig_value = res.headers[k]

                req = webob.Request.blank('/images/%s' % UUID2)
                req.headers[k] = v
                req.method = 'PUT'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 403)
                prop = k[len('x-image-meta-'):]
                self.assertNotEqual(res.body.find("Forbidden to modify \'%s\' "
                                                  "of active "
                                                  "image" % prop), -1)

                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 200)
                self.assertEquals(orig_value, res.headers[k])

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
            for k, v in fixture_header.iteritems():
                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 200)
                orig_value = res.headers[k]

                req = webob.Request.blank('/images/%s' % UUID2)
                req.headers[k] = v
                req.method = 'PUT'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 200)

                req = webob.Request.blank('/images/%s' % UUID2)
                req.method = 'HEAD'
                res = req.get_response(self.api)
                self.assertEquals(res.status_int, 200)
                self.assertEquals(v, res.headers[k])

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
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)

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
        req.body = json.dumps(dict(image_memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

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
        req.body = json.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 204)

    def test_replace_members_forbidden_by_policy(self):
        rules = {"modify_member": '!'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]

        req = webob.Request.blank('/images/%s/members' % UUID1)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)

    def test_replace_members_allowed_by_policy(self):
        rules = {"modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]

        req = webob.Request.blank('/images/%s/members' % UUID1)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(memberships=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNoContent.code)

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=False)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 401)

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
        self.assertEquals(res.status_int, 404)

    def test_add_member_positive(self):
        """
        Tests adding image members
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_router, is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 204)

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
        req.body = json.dumps(dict(member=fixture))
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 204)

    def test_add_member_forbidden_by_policy(self):
        rules = {"modify_member": '!'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID1)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)

    def test_add_member_allowed_by_policy(self):
        rules = {"modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID1)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNoContent.code)

    def test_get_members_of_deleted_image_raises_404(self):
        """
        Tests members listing for deleted image raises 404.
        """
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'GET'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
        self.assertTrue(
            'Image with identifier %s has been deleted.' % UUID2 in res.body)

    def test_delete_member_of_deleted_image_raises_404(self):
        """
        Tests deleting members of deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
        self.assertTrue(
            'Image with identifier %s has been deleted.' % UUID2 in res.body)

    def test_update_members_of_deleted_image_raises_404(self):
        """
        Tests update members of deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 204)

        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        fixture = [{'member_id': 'pattieblack', 'can_share': 'false'}]
        req = webob.Request.blank('/images/%s/members' % UUID2)
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = json.dumps(dict(memberships=fixture))
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
        self.assertTrue(
            'Image with identifier %s has been deleted.' % UUID2 in res.body)

    def test_create_member_to_deleted_image_raises_404(self):
        """
        Tests adding members to deleted image raises 404.
        """
        test_router = router.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(test_router, is_admin=True)
        req = webob.Request.blank("/images/%s" % UUID2)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)
        self.assertTrue(
            'Image with identifier %s has been deleted.' % UUID2 in res.body)

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
        self.assertEquals(res.status_int, 401)

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
        self.assertEquals(res.status_int, 404)

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
        self.assertEquals(res.status_int, 404)

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
        req.body = json.dumps(dict(member=fixture))
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 204)

        # Delete member
        test_uri = '/images/%s/members/test_add_member_positive'
        req = webob.Request.blank(test_uri % UUID2)
        req.headers['X-Auth-Token'] = 'test1:test1:'
        req.method = 'DELETE'
        req.content_type = 'application/json'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 404)
        self.assertTrue('Forbidden' in res.body)

    def test_delete_member_allowed_by_policy(self):
        rules = {"delete_member": '@', "modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNoContent.code)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNoContent.code)

    def test_delete_member_forbidden_by_policy(self):
        rules = {"delete_member": '!', "modify_member": '@'}
        self.set_policy_rules(rules)
        self.api = test_utils.FakeAuthMiddleware(router.API(self.mapper),
                                                 is_admin=True)
        req = webob.Request.blank('/images/%s/members/pattieblack' % UUID2)
        req.method = 'PUT'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNoContent.code)
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPForbidden.code)


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

    def test_redact_location(self):
        """Ensure location redaction does not change original metadata"""
        image_meta = {'size': 3, 'id': '123', 'location': 'http://localhost'}
        redacted_image_meta = {'size': 3, 'id': '123'}
        copy_image_meta = copy.deepcopy(image_meta)
        tmp_image_meta = glance.api.v1.images.redact_loc(image_meta)

        self.assertEqual(image_meta, copy_image_meta)
        self.assertEqual(tmp_image_meta, redacted_image_meta)

    def test_noop_redact_location(self):
        """Check no-op location redaction does not change original metadata"""
        image_meta = {'size': 3, 'id': '123'}
        redacted_image_meta = {'size': 3, 'id': '123'}
        copy_image_meta = copy.deepcopy(image_meta)
        tmp_image_meta = glance.api.v1.images.redact_loc(image_meta)

        self.assertEqual(image_meta, copy_image_meta)
        self.assertEqual(tmp_image_meta, redacted_image_meta)
        self.assertEqual(image_meta, redacted_image_meta)


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
        db_api.setup_db_env()
        db_api.get_engine()
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def tearDown(self):
        """Clear the test environment"""
        super(TestAPIProtectedProps, self).tearDown()
        self.destroy_fixtures()

    def destroy_fixtures(self):
        # Easiest to just drop the models and re-create them...
        db_models.unregister_models(db_api._ENGINE)
        db_models.register_models(db_api._ENGINE)

    def _create_admin_image(self, props={}):
        request = unit_test_utils.get_fake_request(path='/images')
        headers = {'x-image-meta-disk-format': 'ami',
                   'x-image-meta-container-format': 'ami',
                   'x-image-meta-name': 'foo',
                   'x-image-meta-size': '0',
                   'x-auth-token': 'user:tenant:admin'}
        headers.update(props)
        for k, v in headers.iteritems():
            request.headers[k] = v
        created_image = request.get_response(self.api)
        res_body = json.loads(created_image.body)['image']
        image_id = res_body['id']
        return image_id

    def test_prop_protection_with_create_and_permitted_role(self):
        """
        As admin role, create and image and verify permitted role 'member' can
        create a protected property
        """
        image_id = self._create_admin_image()
        another_request = unit_test_utils.get_fake_request(
                path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_owner_foo': 'bar'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties']['x_owner_foo'], 'bar')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        another_request.get_response(self.api)
        output = another_request.get_response(self.api)
        self.assertEquals(output.status_int, webob.exc.HTTPForbidden.code)
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        res2 = another_request.get_response(self.api)
        self.assertEqual(res2.headers['x-image-meta-property-x_owner_foo'],
                         'bar')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        res2 = another_request.get_response(self.api)
        self.assertEqual(res2.headers['x-image-meta-property-x_owner_foo'],
                         'bar')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
        self.assertEqual('', output.body)
        self.assertNotIn('x-image-meta-property-x_owner_foo', output.headers)

    def test_prop_protection_with_detail_and_permitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'member' can read that protected property via
        /images/detail
        """
        image_id = self._create_admin_image(
                {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
                method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:member'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
        res_body = json.loads(output.body)['images'][0]
        self.assertEqual(res_body['properties']['x_owner_foo'], 'bar')

    def test_prop_protection_with_detail_and_unpermitted_role(self):
        """
        As admin role, create an image with a protected property, and verify
        permitted role 'fake_role' can *not* read that protected property via
        /images/detail
        """
        image_id = self._create_admin_image(
                {'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
                method='GET', path='/images/detail')
        headers = {'x-auth-token': 'user:tenant:fake_role'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
        res_body = json.loads(output.body)['images'][0]
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties']['x_owner_foo'], 'baz')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEquals(output.status_int, webob.exc.HTTPForbidden.code)
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEquals(output.status_int, webob.exc.HTTPForbidden.code)
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties']['spl_read_prop'], 'foo')
        self.assertEquals(output.status_int, 200)

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties'], {})

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEquals(output.status_int, 200)
        self.assertNotIn('x-image-meta-property-x_owner_foo', output.headers)

        another_request = unit_test_utils.get_fake_request(
                method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:admin'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
        self.assertEqual('', output.body)
        self.assertEqual(output.headers['x-image-meta-property-x_owner_foo'],
                         'bar')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEquals(output.status_int, 403)
        self.assertIn("Property '%s' is protected" %
                      "spl_update_prop", output.body)

        another_request = unit_test_utils.get_fake_request(
                method='HEAD', path='/images/%s' % image_id)
        headers = {'x-auth-token': 'user:tenant:admin'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 200)
        self.assertEqual('', output.body)
        self.assertEqual(
                output.headers['x-image-meta-property-spl_update_prop'], 'foo')

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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties']['spl_update_prop'], '1')
        self.assertNotIn('foo', res_body['properties'])

    def test_update_protected_props_mix_no_read(self):
        """
        Create an image with two props - one only readable by admin, and one
        readable/updatable by member.  Verify member can sucessfully update
        their property while the admin owned one is ignored transparently
        """
        image_id = self._create_admin_image(
                {'x-image-meta-property-admin_foo': 'bar',
                 'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
                path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'x-image-meta-property-x_owner_foo': 'baz'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(res_body['properties']['x_owner_foo'], 'baz')
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
        self.assertEqual(output.status_int, 200)
        self.assertEqual(res_body['properties']['spl_read_only_prop'], '1')
        self.assertEqual(res_body['properties']['spl_update_prop'], '1')

        # verify spl_role can not update admin controlled prop
        headers = {'x-auth-token': 'user:tenant:spl_role',
                   'x-image-meta-property-spl_read_only_prop': '2',
                   'x-image-meta-property-spl_update_prop': '1'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 403)

    def test_delete_protected_props_mix_no_read(self):
        """
        Create an image with two props - one only readable by admin, and one
        readable/deletable by member.  Verify member can sucessfully delete
        their property while the admin owned one is ignored transparently
        """
        image_id = self._create_admin_image(
                {'x-image-meta-property-admin_foo': 'bar',
                 'x-image-meta-property-x_owner_foo': 'bar'})
        another_request = unit_test_utils.get_fake_request(
                path='/images/%s' % image_id, method='PUT')
        headers = {'x-auth-token': 'user:tenant:member',
                   'X-Glance-Registry-Purge-Props': 'True'}
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        res_body = json.loads(output.body)['image']
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
        for k, v in headers.iteritems():
            another_request.headers[k] = v
        output = another_request.get_response(self.api)
        self.assertEqual(output.status_int, 403)
