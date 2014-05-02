# Copyright 2011-2013 OpenStack Foundation
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

from glance.common import exception
from glance import store
from glance.store import base as store_base
from glance.tests.unit import base as test_base


class FakeUnconfigurableStoreDriver(store_base.Store):
    def configure(self):
        raise exception.BadStoreConfiguration("Unconfigurable store driver.")


class TestStoreBase(test_base.StoreClearingUnitTest):

    class UnconfiguredStore(store_base.Store):
        def add(self, image_id, image_file, image_size):
            return True

        def delete(self, location):
            return True

        def set_acls(self, location, public=False, read_tenants=None,
                     write_tenants=None):
            return True

        def get_size(self, location):
            return True

        def get(self, location):
            return True

        def add_disabled(self, *args, **kwargs):
            return True

    def setUp(self):
        self.config(default_store='file')
        super(TestStoreBase, self).setUp()

    def test_create_store_exclude_unconfigurable_drivers(self):
        self.config(known_stores=[
            "glance.tests.unit.test_store_base.FakeUnconfigurableStoreDriver",
            "glance.store.filesystem.Store"])
        count = store.create_stores()
        self.assertEqual(9, count)

    def test_create_store_not_configured(self):
        store = self.UnconfiguredStore(configure=False)
        self.assertRaises(exception.StoreNotConfigured, store.add)
        self.assertRaises(exception.StoreNotConfigured, store.get)
        self.assertRaises(exception.StoreNotConfigured, store.get_size)
        self.assertRaises(exception.StoreNotConfigured, store.add_disabled)
        self.assertRaises(exception.StoreNotConfigured, store.delete)
        self.assertRaises(exception.StoreNotConfigured, store.set_acls)

    def test_create_store_configured(self):
        store = self.UnconfiguredStore(configure=True)
        self.assertTrue(store.add)
        self.assertTrue(store.get)
        self.assertTrue(store.get_size)
        self.assertTrue(store.add_disabled)
        self.assertTrue(store.delete)
        self.assertTrue(store.set_acls)
