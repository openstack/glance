# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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
import unittest

import stubout

from glance import image_cache


def stub_out_image_cache(stubs):
    def fake_make_cache_directory_if_needed(*args, **kwargs):
        pass

    stubs.Set(image_cache.ImageCache,
        '_make_cache_directory_if_needed', fake_make_cache_directory_if_needed)


class TestImageCache(unittest.TestCase):
    def setUp(self):
        self.stubs = stubout.StubOutForTesting()
        stub_out_image_cache(self.stubs)

    def tearDown(self):
        self.stubs.UnsetAll()

    def test_enabled_defaults_to_false(self):
        options = {}
        cache = image_cache.ImageCache(options)
        self.assertEqual(cache.enabled, False)

    def test_can_be_disabled(self):
        options = {'image_cache_enabled': 'False',
                   'image_cache_datadir': '/some/place'}
        cache = image_cache.ImageCache(options)
        self.assertEqual(cache.enabled, False)

    def test_can_be_enabled(self):
        options = {'image_cache_enabled': 'True',
                   'image_cache_datadir': '/some/place'}
        cache = image_cache.ImageCache(options)
        self.assertEqual(cache.enabled, True)
