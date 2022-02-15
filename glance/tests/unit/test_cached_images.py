# Copyright (C) 2013 Yahoo! Inc.
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

from unittest import mock

import webob

from glance.api.v2 import cached_images
import glance.gateway
from glance import image_cache
from glance import notifier
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'


class FakeImage(object):
    def __init__(self, id=None, status='active', container_format='ami',
                 disk_format='ami', locations=None):
        self.id = id or UUID4
        self.status = status
        self.container_format = container_format
        self.disk_format = disk_format
        self.locations = locations
        self.owner = unit_test_utils.TENANT1
        self.created_at = ''
        self.updated_at = ''
        self.min_disk = ''
        self.min_ram = ''
        self.protected = False
        self.checksum = ''
        self.os_hash_algo = ''
        self.os_hash_value = ''
        self.size = 0
        self.virtual_size = 0
        self.visibility = 'public'
        self.os_hidden = False
        self.name = 'foo'
        self.tags = []
        self.extra_properties = {}
        self.member = self.owner

        # NOTE(danms): This fixture looks more like the db object than
        # the proxy model. This needs fixing all through the tests
        # below.
        self.image_id = self.id


class FakeCache(image_cache.ImageCache):
    def __init__(self):
        self.init_driver()
        self.deleted_images = []

    def init_driver(self):
        pass

    def get_cached_images(self):
        return [{'image_id': 'test'}]

    def delete_cached_image(self, image_id):
        self.deleted_images.append(image_id)

    def delete_all_cached_images(self):
        self.delete_cached_image(
            self.get_cached_images()[0].get('image_id'))
        return 1

    def get_queued_images(self):
        return {'test': 'passed'}

    def queue_image(self, image_id):
        return 'pass'

    def delete_queued_image(self, image_id):
        self.deleted_images.append(image_id)

    def delete_all_queued_images(self):
        self.delete_queued_image('deleted_img')
        return 1


class FakeController(cached_images.CacheController):
    def __init__(self):
        self.cache = FakeCache()
        self.db = unit_test_utils.FakeDB(initialize=False)
        self.policy = unit_test_utils.FakePolicyEnforcer()
        self.notifier = unit_test_utils.FakeNotifier()
        self.store = unit_test_utils.FakeStoreAPI()
        self.gateway = glance.gateway.Gateway(self.db, self.store,
                                              self.notifier, self.policy)


class TestController(test_utils.BaseTestCase):
    def test_initialization_without_conf(self):
        # NOTE(abhishekk): Since we are initializing cache driver only
        # if image_cache_dir is set, here we are checking that cache
        # object is None when it is not set
        caching_controller = cached_images.CacheController()
        self.assertIsNone(caching_controller.cache)


class TestCachedImages(test_utils.BaseTestCase):
    def setUp(self):
        super(TestCachedImages, self).setUp()
        test_controller = FakeController()
        self.controller = test_controller

    def test_get_cached_images(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = webob.Request.blank('')
        req.context = 'test'
        result = self.controller.get_cached_images(req)
        self.assertEqual({'cached_images': [{'image_id': 'test'}]}, result)

    def test_delete_cached_image(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.controller.delete_cached_image(req, image_id=UUID4)
            self.assertEqual([UUID4], self.controller.cache.deleted_images)

    def test_delete_cached_images(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertEqual({'num_deleted': 1},
                         self.controller.delete_cached_images(req))
        self.assertEqual(['test'], self.controller.cache.deleted_images)

    def test_get_queued_images(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = webob.Request.blank('')
        req.context = 'test'
        result = self.controller.get_queued_images(req)
        self.assertEqual({'queued_images': {'test': 'passed'}}, result)

    def test_queue_image(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.controller.queue_image(req, image_id=UUID4)

    def test_delete_queued_image(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.controller.delete_queued_image(req, UUID4)
            self.assertEqual([UUID4],
                             self.controller.cache.deleted_images)

    def test_delete_queued_images(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertEqual({'num_deleted': 1},
                         self.controller.delete_queued_images(req))
        self.assertEqual(['deleted_img'],
                         self.controller.cache.deleted_images)


class TestCachedImagesNegative(test_utils.BaseTestCase):
    def setUp(self):
        super(TestCachedImagesNegative, self).setUp()
        test_controller = FakeController()
        self.controller = test_controller

    def test_get_cached_images_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get_cached_images, req)

    def test_get_cached_images_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.get_cached_images,
                              req)

    def test_delete_cached_image_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_cached_image, req,
                          image_id='test')

    def test_delete_cached_image_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.delete_cached_image,
                              req, image_id=UUID4)

    def test_delete_cached_images_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_cached_images, req)

    def test_delete_cached_images_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.delete_cached_images,
                              req)

    def test_get_queued_images_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get_queued_images, req)

    def test_get_queued_images_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.get_queued_images,
                              req)

    def test_queue_image_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.queue_image,
                          req, image_id='test1')

    def test_queue_image_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.queue_image,
                              req, image_id=UUID4)

    def test_delete_queued_image_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_queued_image,
                          req, image_id='test1')

    def test_delete_queued_image_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.delete_queued_image,
                              req, image_id=UUID4)

    def test_delete_queued_images_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_queued_images, req)

    def test_delete_queued_images_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"manage_image_cache": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.delete_queued_images,
                              req)

    def test_delete_cache_entry_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"cache_delete": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.delete_cache_entry,
                              req, image_id=UUID4)

    def test_delete_cache_entry_disabled(self):
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_cache_entry,
                          req, image_id=UUID4)

    def test_delete_non_existing_cache_entries(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete_cache_entry,
                          req, image_id='non-existing-queued-image')

    def test_clear_cache_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"cache_delete": False}
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.clear_cache,
                          req)

    def test_clear_cache_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.clear_cache, req)

    def test_cache_clear_invalid_target(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        req.headers.update({'x-image-cache-clear-target': 'invalid'})
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.clear_cache,
                          req)

    def test_get_cache_state_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.get_cache_state, req)

    def test_get_cache_state_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"cache_list": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.get_cache_state,
                              req)

    def test_queue_image_from_api_disabled(self):
        req = webob.Request.blank('')
        req.context = 'test'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.queue_image_from_api,
                          req, image_id='test1')

    def test_queue_image_from_api_forbidden(self):
        self.config(image_cache_dir='fake_cache_directory')
        self.controller.policy.rules = {"cache_image": False}
        req = unit_test_utils.get_fake_request()
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            mock_get.return_value = FakeImage()
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.queue_image_from_api,
                              req, image_id=UUID4)

    def test_non_active_image_for_queue_api(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        for status in ('saving', 'queued', 'pending_delete',
                       'deactivated', 'importing', 'uploading'):
            with mock.patch.object(notifier.ImageRepoProxy,
                                   'get') as mock_get:
                mock_get.return_value = FakeImage(status=status)
                self.assertRaises(webob.exc.HTTPBadRequest,
                                  self.controller.queue_image_from_api,
                                  req, image_id=UUID4)

    def test_queue_api_non_existing_image_(self):
        self.config(image_cache_dir='fake_cache_directory')
        req = unit_test_utils.get_fake_request()
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.queue_image_from_api,
                          req, image_id='non-existing-image-id')
