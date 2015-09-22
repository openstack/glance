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

import datetime
import uuid

import mock
from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils import timeutils
import routes
import six
import webob

import glance.api.common
import glance.common.config
from glance.common import crypt
from glance import context
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import models as db_models
from glance.registry.api import v1 as rserver
from glance.tests.unit import base
from glance.tests import utils as test_utils

CONF = cfg.CONF

_gen_uuid = lambda: str(uuid.uuid4())

UUID1 = _gen_uuid()
UUID2 = _gen_uuid()


class TestRegistryAPI(base.IsolatedUnitTest, test_utils.RegistryAPIMixIn):

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryAPI, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)

        def _get_extra_fixture(id, name, **kwargs):
            return self.get_extra_fixture(
                id, name,
                locations=[{'url': "file:///%s/%s" % (self.test_dir, id),
                            'metadata': {}, 'status': 'active'}], **kwargs)

        self.FIXTURES = [
            _get_extra_fixture(UUID1, 'fake image #1', is_public=False,
                               disk_format='ami', container_format='ami',
                               min_disk=0, min_ram=0, owner=123,
                               size=13, properties={'type': 'kernel'}),
            _get_extra_fixture(UUID2, 'fake image #2',
                               min_disk=5, min_ram=256,
                               size=19, properties={})]
        self.context = context.RequestContext(is_admin=True)
        db_api.get_engine()
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryAPI, self).tearDown()
        self.destroy_fixtures()

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
        res = self.get_api_response_ext(200, '/images/%s' % UUID2)
        res_dict = jsonutils.loads(res.body)
        image = res_dict['image']
        for k, v in six.iteritems(fixture):
            self.assertEqual(v, image[k])

    def test_show_unknown(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for an unknown image id
        """
        self.get_api_response_ext(404, '/images/%s' % _gen_uuid())

    def test_show_invalid(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for an invalid (therefore unknown) image id
        """
        self.get_api_response_ext(404, '/images/%s' % _gen_uuid())

    def test_show_deleted_image_as_admin(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 200 for deleted image to admin user.
        """
        # Delete image #2
        self.get_api_response_ext(200, '/images/%s' % UUID2, method='DELETE')

        self.get_api_response_ext(200, '/images/%s' % UUID2)

    def test_show_deleted_image_as_nonadmin(self):
        """
        Tests that the /images/<id> registry API endpoint
        returns a 404 for deleted image to non-admin user.
        """
        # Delete image #2
        self.get_api_response_ext(200, '/images/%s' % UUID2, method='DELETE')

        api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                            is_admin=False)
        self.get_api_response_ext(404, '/images/%s' % UUID2, api=api)

    def test_show_private_image_with_no_admin_user(self):
        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, size=18, owner='test user',
                                         is_public=False)
        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(404, '/images/%s' % UUID4, api=api)

    def test_get_root(self):
        """
        Tests that the root registry API returns "index",
        which is a list of public images
        """
        fixture = {'id': UUID2, 'size': 19, 'checksum': None}
        res = self.get_api_response_ext(200, url='/')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, images[0][k])

    def test_get_index(self):
        """
        Tests that the /images registry API returns list of
        public images
        """
        fixture = {'id': UUID2, 'size': 19, 'checksum': None}
        res = self.get_api_response_ext(200)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, images[0][k])

    def test_get_index_marker(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a marker query param
        """
        time1 = timeutils.utcnow() + datetime.timedelta(seconds=5)
        time2 = timeutils.utcnow() + datetime.timedelta(seconds=4)
        time3 = timeutils.utcnow()

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=19, created_at=time1)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=time2)

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID5, created_at=time3)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images?marker=%s' % UUID4)
        self.assertEqualImages(res, (UUID5, UUID2))

    def test_get_index_unknown_marker(self):
        """
        Tests that the /images registry API returns a 400
        when an unknown marker is provided
        """
        self.get_api_response_ext(400, url='/images?marker=%s' % _gen_uuid())

    def test_get_index_malformed_marker(self):
        """
        Tests that the /images registry API returns a 400
        when a malformed marker is provided
        """
        res = self.get_api_response_ext(400, url='/images?marker=4')
        self.assertIn('marker', res.body)

    def test_get_index_forbidden_marker(self):
        """
        Tests that the /images registry API returns a 400
        when a forbidden marker is provided
        """
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(400, url='/images?marker=%s' % UUID1,
                                  api=api)

    def test_get_index_limit(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images?limit=1')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        # expect list to be sorted by created_at desc
        self.assertEqual(UUID4, images[0]['id'])

    def test_get_index_limit_negative(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        self.get_api_response_ext(400, url='/images?limit=-1')

    def test_get_index_limit_non_int(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to a limit query param
        """
        self.get_api_response_ext(400, url='/images?limit=a')

    def test_get_index_limit_marker(self):
        """
        Tests that the /images registry API returns list of
        public images that conforms to limit and marker query params
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid())

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(
            200, url='/images?marker=%s&limit=1' % UUID3)
        self.assertEqualImages(res, (UUID2,))

    def test_get_index_filter_on_user_defined_properties(self):
        """
        Tests that /images registry API returns list of public images based
        a filter on user-defined properties.
        """
        image1_id = _gen_uuid()
        properties = {'distro': 'ubuntu', 'arch': 'i386'}
        extra_fixture = self.get_fixture(id=image1_id, name='image-extra-1',
                                         properties=properties)
        db_api.image_create(self.context, extra_fixture)

        image2_id = _gen_uuid()
        properties = {'distro': 'ubuntu', 'arch': 'x86_64', 'foo': 'bar'}
        extra_fixture = self.get_fixture(id=image2_id, name='image-extra-2',
                                         properties=properties)
        db_api.image_create(self.context, extra_fixture)

        # Test index with filter containing one user-defined property.
        # Filter is 'property-distro=ubuntu'.
        # Verify both image1 and image2 are returned
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-distro=ubuntu')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(2, len(images))
        self.assertEqual(image2_id, images[0]['id'])
        self.assertEqual(image1_id, images[1]['id'])

        # Test index with filter containing one user-defined property but
        # non-existent value. Filter is 'property-distro=fedora'.
        # Verify neither images are returned
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-distro=fedora')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing one user-defined property but
        # unique value. Filter is 'property-arch=i386'.
        # Verify only image1 is returned.
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-arch=i386')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image1_id, images[0]['id'])

        # Test index with filter containing one user-defined property but
        # unique value. Filter is 'property-arch=x86_64'.
        # Verify only image1 is returned.
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-arch=x86_64')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Test index with filter containing unique user-defined property.
        # Filter is 'property-foo=bar'.
        # Verify only image2 is returned.
        res = self.get_api_response_ext(200, url='/images?property-foo=bar')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Test index with filter containing unique user-defined property but
        # .value is non-existent. Filter is 'property-foo=baz'.
        # Verify neither images are returned.
        res = self.get_api_response_ext(200, url='/images?property-foo=baz')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties
        # Filter is 'property-arch=x86_64&property-distro=ubuntu'.
        # Verify only image2 is returned.
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-arch=x86_64&'
                                                 'property-distro=ubuntu')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image2_id, images[0]['id'])

        # Test index with filter containing multiple user-defined properties
        # Filter is 'property-arch=i386&property-distro=ubuntu'.
        # Verify only image1 is returned.
        res = self.get_api_response_ext(200, url='/images?property-arch=i386&'
                                                 'property-distro=ubuntu')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image1_id, images[0]['id'])

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-arch=random&property-distro=ubuntu'.
        # Verify neither images are returned.
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-arch=random&'
                                                 'property-distro=ubuntu')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-arch=random&property-distro=random'.
        # Verify neither images are returned.
        res = self.get_api_response_ext(200, url='/images?'
                                                 'property-arch=random&'
                                                 'property-distro=random')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-boo=far&property-poo=far'.
        # Verify neither images are returned.
        res = self.get_api_response_ext(200, url='/images?property-boo=far&'
                                                 'property-poo=far')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

        # Test index with filter containing multiple user-defined properties.
        # Filter is 'property-foo=bar&property-poo=far'.
        # Verify neither images are returned.
        res = self.get_api_response_ext(200, url='/images?property-foo=bar&'
                                                 'property-poo=far')
        images = jsonutils.loads(res.body)['images']
        self.assertEqual(0, len(images))

    def test_get_index_filter_name(self):
        """
        Tests that the /images registry API returns list of
        public images that have a specific name. This is really a sanity
        check, filtering is tested more in-depth using /images/detail
        """

        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123', size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), name='new name! #123')
        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images?name=new name! #123')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

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
        extra_fixture = self.get_fixture(id=UUID3, size=19, created_at=time1)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=time2)

        db_api.image_create(self.context, extra_fixture)

        UUID5 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID5, created_at=time3)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images')
        self.assertEqualImages(res, (UUID3, UUID4, UUID5, UUID2))

    def test_get_index_bad_sort_key(self):
        """Ensure a 400 is returned when a bad sort_key is provided."""
        self.get_api_response_ext(400, url='/images?sort_key=asdf')

    def test_get_index_bad_sort_dir(self):
        """Ensure a 400 is returned when a bad sort_dir is provided."""
        self.get_api_response_ext(400, url='/images?sort_dir=asdf')

    def test_get_index_null_name(self):
        """Check 200 is returned when sort_key is null name

        Check 200 is returned when sort_key is name and name is null
        for specified marker
        """
        UUID6 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID6, name=None)

        db_api.image_create(self.context, extra_fixture)
        self.get_api_response_ext(
            200, url='/images?sort_key=name&marker=%s' % UUID6)

    def test_get_index_null_disk_format(self):
        """Check 200 is returned when sort_key is null disk_format

        Check 200 is returned when sort_key is disk_format and
        disk_format is null for specified marker
        """
        UUID6 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID6, disk_format=None, size=19)

        db_api.image_create(self.context, extra_fixture)
        self.get_api_response_ext(
            200, url='/images?sort_key=disk_format&marker=%s' % UUID6)

    def test_get_index_null_container_format(self):
        """Check 200 is returned when sort_key is null container_format

        Check 200 is returned when sort_key is container_format and
        container_format is null for specified marker
        """
        UUID6 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID6, container_format=None)

        db_api.image_create(self.context, extra_fixture)
        self.get_api_response_ext(
            200, url='/images?sort_key=container_format&marker=%s' % UUID6)

    def test_get_index_sort_name_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by name in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf', size=19)
        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz')

        db_api.image_create(self.context, extra_fixture)

        url = '/images?sort_key=name&sort_dir=asc'
        res = self.get_api_response_ext(200, url=url)
        self.assertEqualImages(res, (UUID3, UUID2, UUID4))

    def test_get_index_sort_status_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by status in
        descending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, status='queued', size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images?sort_key=status&sort_dir=desc'))
        self.assertEqualImages(res, (UUID3, UUID4, UUID2))

    def test_get_index_sort_disk_format_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by disk_format in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, disk_format='ami',
                                         container_format='ami', size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, disk_format='vdi')

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images?sort_key=disk_format&sort_dir=asc'))
        self.assertEqualImages(res, (UUID3, UUID4, UUID2))

    def test_get_index_sort_container_format_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted alphabetically by container_format in
        descending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=19, disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, disk_format='iso',
                                         container_format='bare')

        db_api.image_create(self.context, extra_fixture)

        url = '/images?sort_key=container_format&sort_dir=desc'
        res = self.get_api_response_ext(200, url=url)
        self.assertEqualImages(res, (UUID2, UUID4, UUID3))

    def test_get_index_sort_size_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by size in ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, disk_format='ami',
                                         container_format='ami', size=100)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, disk_format='iso',
                                         container_format='bare', size=2)

        db_api.image_create(self.context, extra_fixture)

        url = '/images?sort_key=size&sort_dir=asc'
        res = self.get_api_response_ext(200, url=url)
        self.assertEqualImages(res, (UUID4, UUID2, UUID3))

    def test_get_index_sort_created_at_asc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by created_at in ascending order.
        """
        now = timeutils.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, created_at=time1, size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=time2)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images?sort_key=created_at&sort_dir=asc'))
        self.assertEqualImages(res, (UUID2, UUID4, UUID3))

    def test_get_index_sort_updated_at_desc(self):
        """
        Tests that the /images registry API returns list of
        public images sorted by updated_at in descending order.
        """
        now = timeutils.utcnow()
        time1 = now + datetime.timedelta(seconds=5)
        time2 = now

        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=19, created_at=None,
                                         updated_at=time1)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, created_at=None,
                                         updated_at=time2)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images?sort_key=updated_at&sort_dir=desc'))
        self.assertEqualImages(res, (UUID3, UUID4, UUID2))

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

        res = self.get_api_response_ext(200, url='/images/detail')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, images[0][k])

    def test_get_details_limit_marker(self):
        """
        Tests that the /images/details registry API returns list of
        public images that conforms to limit and marker query params.
        This functionality is tested more thoroughly on /images, this is
        just a sanity check
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, size=20)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid())

        db_api.image_create(self.context, extra_fixture)

        url = '/images/detail?marker=%s&limit=1' % UUID3
        res = self.get_api_response_ext(200, url=url)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        # expect list to be sorted by created_at desc
        self.assertEqual(UUID2, images[0]['id'])

    def test_get_details_invalid_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when an invalid marker is provided
        """
        url = '/images/detail?marker=%s' % _gen_uuid()
        self.get_api_response_ext(400, url=url)

    def test_get_details_malformed_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when a malformed marker is provided
        """
        res = self.get_api_response_ext(400, url='/images/detail?marker=4')
        self.assertIn('marker', res.body)

    def test_get_details_forbidden_marker(self):
        """
        Tests that the /images/detail registry API returns a 400
        when a forbidden marker is provided
        """
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(400, api=api,
                                  url='/images/detail?marker=%s' % UUID1)

    def test_get_details_filter_name(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific name
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123', size=20)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         name='new name! #123')

        db_api.image_create(self.context, extra_fixture)

        url = '/images/detail?name=new name! #123'
        res = self.get_api_response_ext(200, url=url)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_details_filter_status(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific status
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), status='saving')

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), size=19,
                                         status='active')

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?status=saving')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual('saving', image['status'])

    def test_get_details_filter_container_format(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific container_format
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='vdi',
                                         size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami', size=19)

        db_api.image_create(self.context, extra_fixture)

        url = '/images/detail?container_format=ovf'
        res = self.get_api_response_ext(200, url=url)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertEqual('ovf', image['container_format'])

    def test_get_details_filter_min_disk(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific min_disk
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), min_disk=7, size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami', size=19)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images/detail?min_disk=7')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual(7, image['min_disk'])

    def test_get_details_filter_min_ram(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific min_ram
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), min_ram=514, size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami', size=19)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images/detail?min_ram=514')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual(514, image['min_ram'])

    def test_get_details_filter_disk_format(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific disk_format
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=19)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami', size=19)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?disk_format=vhd')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertEqual('vhd', image['disk_format'])

    def test_get_details_filter_size_min(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size greater than or equal to size_min
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=18)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images/detail?size_min=19')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertTrue(image['size'] >= 19)

    def test_get_details_filter_size_max(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=18)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url='/images/detail?size_max=19')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertTrue(image['size'] <= 19)

    def test_get_details_filter_size_min_max(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        and greater than or equal to size_min
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=18)

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), disk_format='ami',
                                         container_format='ami')

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), size=6)

        db_api.image_create(self.context, extra_fixture)

        url = '/images/detail?size_min=18&size_max=19'
        res = self.get_api_response_ext(200, url=url)
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertTrue(18 <= image['size'] <= 19)

    def test_get_details_filter_changes_since(self):
        """
        Tests that the /images/detail registry API returns list of
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
        extra_fixture = self.get_fixture(id=UUID3, size=18)

        db_api.image_create(self.context, extra_fixture)
        db_api.image_destroy(self.context, UUID3)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4,
                                         disk_format='ami',
                                         container_format='ami',
                                         created_at=image_ts,
                                         updated_at=image_ts)

        db_api.image_create(self.context, extra_fixture)

        # Check a standard list, 4 images in db (2 deleted)
        res = self.get_api_response_ext(200, url='/images/detail')
        self.assertEqualImages(res, (UUID4, UUID2))

        # Expect 3 images (1 deleted)
        res = self.get_api_response_ext(200, url=(
            '/images/detail?changes-since=%s' % iso1))
        self.assertEqualImages(res, (UUID4, UUID3, UUID2))

        # Expect 1 images (0 deleted)
        res = self.get_api_response_ext(200, url=(
            '/images/detail?changes-since=%s' % iso2))
        self.assertEqualImages(res, (UUID4,))

        # Expect 1 images (0 deleted)
        res = self.get_api_response_ext(200, url=(
            '/images/detail?changes-since=%s' % hour_before))
        self.assertEqualImages(res, (UUID4,))

        # Expect 0 images (0 deleted)
        res = self.get_api_response_ext(200, url=(
            '/images/detail?changes-since=%s' % hour_after))
        self.assertEqualImages(res, ())

        # Expect 0 images (0 deleted)
        res = self.get_api_response_ext(200, url=(
            '/images/detail?changes-since=%s' % iso4))
        self.assertEqualImages(res, ())

        for param in [date_only1, date_only2, date_only3]:
            # Expect 3 images (1 deleted)
            res = self.get_api_response_ext(200, url=(
                '/images/detail?changes-since=%s' % param))
            self.assertEqualImages(res, (UUID4, UUID3, UUID2))

        # Bad request (empty changes-since param)
        self.get_api_response_ext(400,
                                  url='/images/detail?changes-since=')

    def test_get_details_filter_property(self):
        """
        Tests that the /images/detail registry API returns list of
        public images that have a specific custom property
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=19,
                                         properties={'prop_123': 'v a'})

        db_api.image_create(self.context, extra_fixture)

        extra_fixture = self.get_fixture(id=_gen_uuid(), size=19,
                                         disk_format='ami',
                                         container_format='ami',
                                         properties={'prop_123': 'v b'})

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images/detail?property-prop_123=v%20a'))
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for image in images:
            self.assertEqual('v a', image['properties']['prop_123'])

    def test_get_details_filter_public_none(self):
        """
        Tests that the /images/detail registry API returns list of
        all images if is_public none is passed
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         is_public=False, size=18)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?is_public=None')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(3, len(images))

    def test_get_details_filter_public_false(self):
        """
        Tests that the /images/detail registry API returns list of
        private images if is_public false is passed
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         is_public=False, size=18)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?is_public=False')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(2, len(images))

        for image in images:
            self.assertEqual(False, image['is_public'])

    def test_get_details_filter_public_true(self):
        """
        Tests that the /images/detail registry API returns list of
        public images if is_public true is passed (same as default)
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         is_public=False, size=18)

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?is_public=True')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))

        for image in images:
            self.assertTrue(image['is_public'])

    def test_get_details_filter_public_string_format(self):
        """
        Tests that the /images/detail registry
        API returns 400 Bad error for filter is_public with wrong format
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         is_public='true', size=18)

        db_api.image_create(self.context, extra_fixture)

        self.get_api_response_ext(400, url='/images/detail?is_public=public')

    def test_get_details_filter_deleted_false(self):
        """
        Test that the /images/detail registry
        API return list of images with deleted filter = false

        """
        extra_fixture = {'id': _gen_uuid(),
                         'status': 'active',
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'test deleted filter 1',
                         'size': 18,
                         'deleted': False,
                         'checksum': None}

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200,
                                        url='/images/detail?deleted=False')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']

        for image in images:
            self.assertFalse(image['deleted'])

    def test_get_filter_no_public_with_no_admin(self):
        """
        Tests that the /images/detail registry API returns list of
        public images if is_public true is passed (same as default)
        """
        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4,
                                         is_public=False, size=18)

        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        res = self.get_api_response_ext(200, api=api,
                                        url='/images/detail?is_public=False')
        res_dict = jsonutils.loads(res.body)

        images = res_dict['images']
        self.assertEqual(1, len(images))
        # Check that for non admin user only is_public = True images returns
        for image in images:
            self.assertTrue(image['is_public'])

    def test_get_filter_protected_with_None_value(self):
        """
        Tests that the /images/detail registry API returns 400 error
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(), size=18,
                                         protected="False")

        db_api.image_create(self.context, extra_fixture)
        self.get_api_response_ext(400, url='/images/detail?protected=')

    def test_get_filter_protected_with_True_value(self):
        """
        Tests that the /images/detail registry API returns 400 error
        """
        extra_fixture = self.get_fixture(id=_gen_uuid(),
                                         size=18, protected="True")

        db_api.image_create(self.context, extra_fixture)
        self.get_api_response_ext(200, url='/images/detail?protected=True')

    def test_get_details_sort_name_asc(self):
        """
        Tests that the /images/details registry API returns list of
        public images sorted alphabetically by name in
        ascending order.
        """
        UUID3 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID3, name='asdf', size=19)

        db_api.image_create(self.context, extra_fixture)

        UUID4 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID4, name='xyz')

        db_api.image_create(self.context, extra_fixture)

        res = self.get_api_response_ext(200, url=(
            '/images/detail?sort_key=name&sort_dir=asc'))
        self.assertEqualImages(res, (UUID3, UUID2, UUID4))

    def test_create_image(self):
        """Tests that the /images POST registry API creates the image"""

        fixture = self.get_minimal_fixture()
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, body=body,
                                        method='POST', content_type='json')
        res_dict = jsonutils.loads(res.body)

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, res_dict['image'][k])

        # Test status was updated properly
        self.assertEqual('active', res_dict['image']['status'])

    def test_create_image_with_min_disk(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = self.get_minimal_fixture(min_disk=5)
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, body=body,
                                        method='POST', content_type='json')
        res_dict = jsonutils.loads(res.body)

        self.assertEqual(5, res_dict['image']['min_disk'])

    def test_create_image_with_min_ram(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = self.get_minimal_fixture(min_ram=256)
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, body=body,
                                        method='POST', content_type='json')
        res_dict = jsonutils.loads(res.body)

        self.assertEqual(256, res_dict['image']['min_ram'])

    def test_create_image_with_min_ram_default(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = self.get_minimal_fixture()
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, body=body,
                                        method='POST', content_type='json')
        res_dict = jsonutils.loads(res.body)

        self.assertEqual(0, res_dict['image']['min_ram'])

    def test_create_image_with_min_disk_default(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = self.get_minimal_fixture()
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, body=body,
                                        method='POST', content_type='json')
        res_dict = jsonutils.loads(res.body)

        self.assertEqual(0, res_dict['image']['min_disk'])

    def test_create_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = self.get_minimal_fixture(id=_gen_uuid(), status='bad status')
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(400, body=body,
                                        method='POST', content_type='json')
        self.assertIn('Invalid image status', res.body)

    def test_create_image_with_bad_id(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = self.get_minimal_fixture(id='asdf')

        self.get_api_response_ext(400, content_type='json', method='POST',
                                  body=jsonutils.dumps(dict(image=fixture)))

    def test_create_image_with_image_id_in_log(self):
        """Tests correct image id in log message when creating image"""
        fixture = self.get_minimal_fixture(
            id='0564c64c-3545-4e34-abfb-9d18e5f2f2f9')
        self.log_image_id = False

        def fake_log_info(msg):
            if ('Successfully created image '
               '0564c64c-3545-4e34-abfb-9d18e5f2f2f9' in msg):
                self.log_image_id = True
        self.stubs.Set(rserver.images.LOG, 'info', fake_log_info)

        self.get_api_response_ext(200, content_type='json', method='POST',
                                  body=jsonutils.dumps(dict(image=fixture)))
        self.assertTrue(self.log_image_id)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'min_disk': 5,
                   'min_ram': 256,
                   'disk_format': 'raw'}
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(200, url='/images/%s' % UUID2,
                                        body=body, method='PUT',
                                        content_type='json')

        res_dict = jsonutils.loads(res.body)

        self.assertNotEqual(res_dict['image']['created_at'],
                            res_dict['image']['updated_at'])

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, res_dict['image'][k])

    @mock.patch.object(rserver.images.LOG, 'debug')
    def test_update_image_not_log_sensitive_info(self, log_debug):
        """
        Tests that there is no any sensitive info of image location
        was logged in glance during the image update operation.
        """

        def fake_log_debug(fmt_str, image_meta):
            self.assertNotIn("'locations'", fmt_str % image_meta)

        fixture = {'name': 'fake public image #2',
                   'min_disk': 5,
                   'min_ram': 256,
                   'disk_format': 'raw',
                   'location': 'fake://image'}
        body = jsonutils.dumps(dict(image=fixture))

        log_debug.side_effect = fake_log_debug

        res = self.get_api_response_ext(200, url='/images/%s' % UUID2,
                                        body=body, method='PUT',
                                        content_type='json')

        res_dict = jsonutils.loads(res.body)

        self.assertNotEqual(res_dict['image']['created_at'],
                            res_dict['image']['updated_at'])

        for k, v in six.iteritems(fixture):
            self.assertEqual(v, res_dict['image'][k])

    def test_update_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to update
        non-existing image
        """
        fixture = {'status': 'killed'}
        body = jsonutils.dumps(dict(image=fixture))

        self.get_api_response_ext(404, url='/images/%s' % _gen_uuid(),
                                  method='PUT', body=body, content_type='json')

    def test_update_image_with_bad_status(self):
        """Tests that exception raised trying to set a bad status"""
        fixture = {'status': 'invalid'}
        body = jsonutils.dumps(dict(image=fixture))

        res = self.get_api_response_ext(400, method='PUT', body=body,
                                        url='/images/%s' % UUID2,
                                        content_type='json')
        self.assertIn('Invalid image status', res.body)

    def test_update_private_image_no_admin(self):
        """
        Tests proper exception is raised if attempt to update
        private image with non admin user, that not belongs to it
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, is_public=False,
                                         protected=True, owner='test user')

        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        body = jsonutils.dumps(dict(image=extra_fixture))
        self.get_api_response_ext(404, body=body, api=api,
                                  url='/images/%s' % UUID8, method='PUT',
                                  content_type='json')

    def test_delete_image(self):
        """Tests that the /images DELETE registry API deletes the image"""

        # Grab the original number of images
        res = self.get_api_response_ext(200)
        res_dict = jsonutils.loads(res.body)

        orig_num_images = len(res_dict['images'])

        # Delete image #2
        self.get_api_response_ext(200, url='/images/%s' % UUID2,
                                  method='DELETE')

        # Verify one less image
        res = self.get_api_response_ext(200)
        res_dict = jsonutils.loads(res.body)

        new_num_images = len(res_dict['images'])
        self.assertEqual(new_num_images, orig_num_images - 1)

    def test_delete_image_response(self):
        """Tests that the registry API delete returns the image metadata"""

        image = self.FIXTURES[0]
        res = self.get_api_response_ext(200, url='/images/%s' % image['id'],
                                        method='DELETE')
        deleted_image = jsonutils.loads(res.body)['image']

        self.assertEqual(image['id'], deleted_image['id'])
        self.assertTrue(deleted_image['deleted'])
        self.assertTrue(deleted_image['deleted_at'])

    def test_delete_image_not_existing(self):
        """
        Tests proper exception is raised if attempt to delete
        non-existing image
        """
        self.get_api_response_ext(404, url='/images/%s' % _gen_uuid(),
                                  method='DELETE')

    def test_delete_public_image_no_admin(self):
        """
        Tests proper exception is raised if attempt to delete
        public image with non admin user
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=True,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(403, url='/images/%s' % UUID8,
                                  method='DELETE', api=api)

    def test_delete_private_image_no_admin(self):
        """
        Tests proper exception is raised if attempt to delete
        private image with non admin user, that not belongs to it
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, is_public=False, size=19,
                                         protected=True, owner='test user')

        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(404, url='/images/%s' % UUID8,
                                  method='DELETE', api=api)

    def test_get_image_members(self):
        """
        Tests members listing for existing images
        """
        res = self.get_api_response_ext(200, url='/images/%s/members' % UUID2,
                                        method='GET')

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEqual(num_members, 0)

    def test_get_image_members_not_existing(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image
        """
        self.get_api_response_ext(404, method='GET',
                                  url='/images/%s/members' % _gen_uuid())

    def test_get_image_members_forbidden(self):
        """
        Tests proper exception is raised if attempt to get members of
        non-existing image

        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, is_public=False, size=19,
                                         protected=True, owner='test user')

        db_api.image_create(self.context, extra_fixture)
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        self.get_api_response_ext(404, url='/images/%s/members' % UUID8,
                                  method='GET', api=api)

    def test_get_member_images(self):
        """
        Tests image listing for members
        """
        res = self.get_api_response_ext(200, url='/shared-images/pattieblack',
                                        method='GET')

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['shared_images'])
        self.assertEqual(num_members, 0)

    def test_replace_members(self):
        """
        Tests replacing image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        fixture = dict(member_id='pattieblack')
        body = jsonutils.dumps(dict(image_memberships=fixture))

        self.get_api_response_ext(401, method='PUT', body=body,
                                  url='/images/%s/members' % UUID2,
                                  content_type='json')

    def test_update_all_image_members_non_existing_image_id(self):
        """
        Test update image members raises right exception
        """
        # Update all image members
        fixture = dict(member_id='test1')
        req = webob.Request.blank('/images/%s/members' % _gen_uuid())
        req.method = 'PUT'
        self.context.tenant = 'test2'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image_memberships=fixture))
        res = req.get_response(self.api)
        self.assertEqual(res.status_int, 404)

    def test_update_all_image_members_invalid_membership_association(self):
        """
        Test update image members raises right exception
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)

        # Add several members to image
        req = webob.Request.blank('/images/%s/members/test1' % UUID8)
        req.method = 'PUT'
        res = req.get_response(self.api)
        # Get all image members:
        res = self.get_api_response_ext(200, url='/images/%s/members' % UUID8,
                                        method='GET')

        memb_list = jsonutils.loads(res.body)
        num_members = len(memb_list['members'])
        self.assertEqual(num_members, 1)

        fixture = dict(member_id='test1')
        body = jsonutils.dumps(dict(image_memberships=fixture))
        self.get_api_response_ext(400, url='/images/%s/members' % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_update_all_image_members_non_shared_image_forbidden(self):
        """
        Test update image members raises right exception
        """
        test_rserv = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(test_rserv, is_admin=False)
        UUID9 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID9, size=19, protected=False)

        db_api.image_create(self.context, extra_fixture)
        fixture = dict(member_id='test1')
        req = webob.Request.blank('/images/%s/members' % UUID9)
        req.headers['X-Auth-Token'] = 'test1:test1:'
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image_memberships=fixture))

        res = req.get_response(api)
        self.assertEqual(res.status_int, 403)

    def test_update_all_image_members(self):
        """
        Test update non existing image members
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)

        # Add several members to image
        req = webob.Request.blank('/images/%s/members/test1' % UUID8)
        req.method = 'PUT'
        req.get_response(self.api)

        fixture = [dict(member_id='test2', can_share=True)]
        body = jsonutils.dumps(dict(memberships=fixture))
        self.get_api_response_ext(204, url='/images/%s/members' % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_update_all_image_members_bad_request(self):
        """
        Test that right exception is raises
        in case if wrong memberships association is supplied
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)

        # Add several members to image
        req = webob.Request.blank('/images/%s/members/test1' % UUID8)
        req.method = 'PUT'
        req.get_response(self.api)
        fixture = dict(member_id='test3')
        body = jsonutils.dumps(dict(memberships=fixture))
        self.get_api_response_ext(400, url='/images/%s/members' % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_update_all_image_existing_members(self):
        """
        Test update existing image members
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)

        # Add several members to image
        req = webob.Request.blank('/images/%s/members/test1' % UUID8)
        req.method = 'PUT'
        req.get_response(self.api)

        fixture = [dict(member_id='test1', can_share=False)]
        body = jsonutils.dumps(dict(memberships=fixture))
        self.get_api_response_ext(204, url='/images/%s/members' % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_add_member(self):
        """
        Tests adding image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        self.get_api_response_ext(401, method='PUT',
                                  url=('/images/%s/members/pattieblack' %
                                       UUID2))

    def test_add_member_to_image_positive(self):
        """
        Test check that member can be successfully added
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)
        fixture = dict(can_share=True)
        test_uri = '/images/%s/members/test_add_member_positive'
        body = jsonutils.dumps(dict(member=fixture))
        self.get_api_response_ext(204, url=test_uri % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_add_member_to_non_exist_image(self):
        """
        Test check that member can't be added for
        non exist image
        """
        fixture = dict(can_share=True)
        test_uri = '/images/%s/members/test_add_member_positive'
        body = jsonutils.dumps(dict(member=fixture))
        self.get_api_response_ext(404, url=test_uri % _gen_uuid(),
                                  method='PUT', body=body,
                                  content_type='json')

    def test_add_image_member_non_shared_image_forbidden(self):
        """
        Test update image members raises right exception
        """
        test_rserver_api = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(
            test_rserver_api, is_admin=False)
        UUID9 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID9, size=19, protected=False)
        db_api.image_create(self.context, extra_fixture)
        fixture = dict(can_share=True)
        test_uri = '/images/%s/members/test_add_member_to_non_share_image'
        req = webob.Request.blank(test_uri % UUID9)
        req.headers['X-Auth-Token'] = 'test1:test1:'
        req.method = 'PUT'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(member=fixture))

        res = req.get_response(api)
        self.assertEqual(res.status_int, 403)

    def test_add_member_to_image_bad_request(self):
        """
        Test check right status code is returned
        """
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)

        fixture = [dict(can_share=True)]
        test_uri = '/images/%s/members/test_add_member_bad_request'
        body = jsonutils.dumps(dict(member=fixture))
        self.get_api_response_ext(400, url=test_uri % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')

    def test_delete_member(self):
        """
        Tests deleting image members raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        self.get_api_response_ext(401, method='DELETE',
                                  url=('/images/%s/members/pattieblack' %
                                       UUID2))

    def test_delete_member_invalid(self):
        """
        Tests deleting a invalid/non existing member raises right exception
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)
        res = self.get_api_response_ext(404, method='DELETE',
                                        url=('/images/%s/members/pattieblack' %
                                             UUID2))
        self.assertIn('Membership could not be found', res.body)

    def test_delete_member_from_non_exist_image(self):
        """
        Tests deleting image members raises right exception
        """
        test_rserver_api = rserver.API(self.mapper)
        self.api = test_utils.FakeAuthMiddleware(
            test_rserver_api, is_admin=True)
        test_uri = '/images/%s/members/pattieblack'
        self.get_api_response_ext(404, method='DELETE',
                                  url=test_uri % _gen_uuid())

    def test_delete_image_member_non_shared_image_forbidden(self):
        """
        Test delete image members raises right exception
        """
        test_rserver_api = rserver.API(self.mapper)
        api = test_utils.FakeAuthMiddleware(
            test_rserver_api, is_admin=False)
        UUID9 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID9, size=19, protected=False)

        db_api.image_create(self.context, extra_fixture)
        test_uri = '/images/%s/members/test_add_member_to_non_share_image'
        req = webob.Request.blank(test_uri % UUID9)
        req.headers['X-Auth-Token'] = 'test1:test1:'
        req.method = 'DELETE'
        req.content_type = 'application/json'

        res = req.get_response(api)
        self.assertEqual(res.status_int, 403)

    def test_add_member_delete_create(self):
        """
        Test check that the same member can be successfully added after delete
        it, and the same record will be reused for the same membership.
        """
        # add a member
        UUID8 = _gen_uuid()
        extra_fixture = self.get_fixture(id=UUID8, size=19, protected=False,
                                         owner='test user')

        db_api.image_create(self.context, extra_fixture)
        fixture = dict(can_share=True)
        test_uri = '/images/%s/members/test_add_member_delete_create'
        body = jsonutils.dumps(dict(member=fixture))
        self.get_api_response_ext(204, url=test_uri % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')
        memb_list = db_api.image_member_find(self.context, image_id=UUID8)
        self.assertEqual(1, len(memb_list))
        memb_list2 = db_api.image_member_find(self.context,
                                              image_id=UUID8,
                                              include_deleted=True)
        self.assertEqual(1, len(memb_list2))
        # delete the member
        self.get_api_response_ext(204, method='DELETE',
                                  url=test_uri % UUID8)
        memb_list = db_api.image_member_find(self.context, image_id=UUID8)
        self.assertEqual(0, len(memb_list))
        memb_list2 = db_api.image_member_find(self.context,
                                              image_id=UUID8,
                                              include_deleted=True)
        self.assertEqual(1, len(memb_list2))
        # create it again
        self.get_api_response_ext(204, url=test_uri % UUID8,
                                  method='PUT', body=body,
                                  content_type='json')
        memb_list = db_api.image_member_find(self.context, image_id=UUID8)
        self.assertEqual(1, len(memb_list))
        memb_list2 = db_api.image_member_find(self.context,
                                              image_id=UUID8,
                                              include_deleted=True)
        self.assertEqual(1, len(memb_list2))

    def test_get_on_image_member(self):
        """
        Test GET on image members raises 405 and produces correct Allow headers
        """
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=False)
        uri = '/images/%s/members/123' % UUID1
        req = webob.Request.blank(uri)
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEqual(405, res.status_int)
        self.assertIn(('Allow', 'PUT, DELETE'), res.headerlist)

    def test_get_images_bad_urls(self):
        """Check that routes collections are not on (LP bug 1185828)"""
        self.get_api_response_ext(404, url='/images/detail.xxx')

        self.get_api_response_ext(404, url='/images.xxx')

        self.get_api_response_ext(404, url='/images/new')

        self.get_api_response_ext(200, url='/images/%s/members' % UUID1)

        self.get_api_response_ext(404, url='/images/%s/members.xxx' % UUID1)


class TestRegistryAPILocations(base.IsolatedUnitTest,
                               test_utils.RegistryAPIMixIn):

    def setUp(self):
        """Establish a clean test environment"""
        super(TestRegistryAPILocations, self).setUp()
        self.mapper = routes.Mapper()
        self.api = test_utils.FakeAuthMiddleware(rserver.API(self.mapper),
                                                 is_admin=True)

        def _get_extra_fixture(id, name, **kwargs):
            return self.get_extra_fixture(
                id, name,
                locations=[{'url': "file:///%s/%s" % (self.test_dir, id),
                            'metadata': {}, 'status': 'active'}], **kwargs)

        self.FIXTURES = [
            _get_extra_fixture(UUID1, 'fake image #1', is_public=False,
                               disk_format='ami', container_format='ami',
                               min_disk=0, min_ram=0, owner=123,
                               size=13, properties={'type': 'kernel'}),
            _get_extra_fixture(UUID2, 'fake image #2',
                               min_disk=5, min_ram=256,
                               size=19, properties={})]
        self.context = context.RequestContext(is_admin=True)
        db_api.get_engine()
        self.destroy_fixtures()
        self.create_fixtures()

    def tearDown(self):
        """Clear the test environment"""
        super(TestRegistryAPILocations, self).tearDown()
        self.destroy_fixtures()

    def test_show_from_locations(self):
        req = webob.Request.blank('/images/%s' % UUID1)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        image = res_dict['image']
        self.assertIn('id', image['location_data'][0])
        image['location_data'][0].pop('id')
        self.assertEqual(self.FIXTURES[0]['locations'][0],
                         image['location_data'][0])
        self.assertEqual(self.FIXTURES[0]['locations'][0]['url'],
                         image['location_data'][0]['url'])
        self.assertEqual(self.FIXTURES[0]['locations'][0]['metadata'],
                         image['location_data'][0]['metadata'])

    def test_show_from_location_data(self):
        req = webob.Request.blank('/images/%s' % UUID2)
        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        image = res_dict['image']
        self.assertIn('id', image['location_data'][0])
        image['location_data'][0].pop('id')
        self.assertEqual(self.FIXTURES[1]['locations'][0],
                         image['location_data'][0])
        self.assertEqual(self.FIXTURES[1]['locations'][0]['url'],
                         image['location_data'][0]['url'])
        self.assertEqual(self.FIXTURES[1]['locations'][0]['metadata'],
                         image['location_data'][0]['metadata'])

    def test_create_from_location_data_with_encryption(self):
        encryption_key = '1234567890123456'
        location_url1 = "file:///%s/%s" % (self.test_dir, _gen_uuid())
        location_url2 = "file:///%s/%s" % (self.test_dir, _gen_uuid())
        encrypted_location_url1 = crypt.urlsafe_encrypt(encryption_key,
                                                        location_url1, 64)
        encrypted_location_url2 = crypt.urlsafe_encrypt(encryption_key,
                                                        location_url2, 64)
        fixture = {'name': 'fake image #3',
                   'status': 'active',
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'is_public': True,
                   'checksum': None,
                   'min_disk': 5,
                   'min_ram': 256,
                   'size': 19,
                   'location': encrypted_location_url1,
                   'location_data': [{'url': encrypted_location_url1,
                                      'metadata': {'key': 'value'},
                                      'status': 'active'},
                                     {'url': encrypted_location_url2,
                                      'metadata': {'key': 'value'},
                                      'status': 'active'}]}

        self.config(metadata_encryption_key=encryption_key)
        req = webob.Request.blank('/images')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = jsonutils.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEqual(200, res.status_int)
        res_dict = jsonutils.loads(res.body)
        image = res_dict['image']
        # NOTE(zhiyan) _normalize_image_location_for_db() function will
        # not re-encrypted the url within location.
        self.assertEqual(fixture['location'], image['location'])
        self.assertEqual(2, len(image['location_data']))
        self.assertEqual(fixture['location_data'][0]['url'],
                         image['location_data'][0]['url'])
        self.assertEqual(fixture['location_data'][0]['metadata'],
                         image['location_data'][0]['metadata'])
        self.assertEqual(fixture['location_data'][1]['url'],
                         image['location_data'][1]['url'])
        self.assertEqual(fixture['location_data'][1]['metadata'],
                         image['location_data'][1]['metadata'])

        image_entry = db_api.image_get(self.context, image['id'])
        self.assertEqual(image_entry['locations'][0]['url'],
                         encrypted_location_url1)
        self.assertEqual(image_entry['locations'][1]['url'],
                         encrypted_location_url2)
        decrypted_location_url1 = crypt.urlsafe_decrypt(
            encryption_key, image_entry['locations'][0]['url'])
        decrypted_location_url2 = crypt.urlsafe_decrypt(
            encryption_key, image_entry['locations'][1]['url'])
        self.assertEqual(location_url1, decrypted_location_url1)
        self.assertEqual(location_url2, decrypted_location_url2)


class TestSharability(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSharability, self).setUp()
        self.setup_db()
        self.controller = glance.registry.api.v1.members.Controller()

    def setup_db(self):
        db_api.get_engine()
        db_models.unregister_models(db_api.get_engine())
        db_models.register_models(db_api.get_engine())

    def test_is_image_sharable_as_admin(self):
        TENANT1 = str(uuid.uuid4())
        TENANT2 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=True, user=TENANT2,
                                       auth_token='user:%s:admin' % TENANT2,
                                       owner_is_tenant=False)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        result = self.controller.is_image_sharable(ctxt2, image)
        self.assertTrue(result)

    def test_is_image_sharable_owner_can_share(self):
        TENANT1 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        result = self.controller.is_image_sharable(ctxt1, image)
        self.assertTrue(result)

    def test_is_image_sharable_non_owner_cannot_share(self):
        TENANT1 = str(uuid.uuid4())
        TENANT2 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, user=TENANT2,
                                       auth_token='user:%s:user' % TENANT2,
                                       owner_is_tenant=False)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        result = self.controller.is_image_sharable(ctxt2, image)
        self.assertFalse(result)

    def test_is_image_sharable_non_owner_can_share_as_image_member(self):
        TENANT1 = str(uuid.uuid4())
        TENANT2 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, user=TENANT2,
                                       auth_token='user:%s:user' % TENANT2,
                                       owner_is_tenant=False)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        membership = {'can_share': True,
                      'member': TENANT2,
                      'image_id': UUIDX}

        db_api.image_member_create(ctxt1, membership)

        result = self.controller.is_image_sharable(ctxt2, image)
        self.assertTrue(result)

    def test_is_image_sharable_non_owner_as_image_member_without_sharing(self):
        TENANT1 = str(uuid.uuid4())
        TENANT2 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, user=TENANT2,
                                       auth_token='user:%s:user' % TENANT2,
                                       owner_is_tenant=False)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        membership = {'can_share': False,
                      'member': TENANT2,
                      'image_id': UUIDX}

        db_api.image_member_create(ctxt1, membership)

        result = self.controller.is_image_sharable(ctxt2, image)
        self.assertFalse(result)

    def test_is_image_sharable_owner_is_none(self):
        TENANT1 = str(uuid.uuid4())
        ctxt1 = context.RequestContext(is_admin=False, tenant=TENANT1,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        ctxt2 = context.RequestContext(is_admin=False, tenant=None,
                                       auth_token='user:%s:user' % TENANT1,
                                       owner_is_tenant=True)
        UUIDX = str(uuid.uuid4())
        # We need private image and context.owner should not match image
        # owner
        image = db_api.image_create(ctxt1, {'id': UUIDX,
                                            'status': 'queued',
                                            'is_public': False,
                                            'owner': TENANT1})

        result = self.controller.is_image_sharable(ctxt2, image)
        self.assertFalse(result)
