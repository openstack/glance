# Copyright 2013 OpenStack Foundation
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

import stubout

from cinderclient.v2 import client as cinderclient

from glance.common import exception
from glance.openstack.common import units
import glance.store.cinder as cinder
from glance.store.location import get_location_from_uri
from glance.tests.unit import base


class FakeObject(object):
    def __init__(self, **kwargs):
        for name, value in kwargs.iteritems():
            setattr(self, name, value)


class TestCinderStore(base.StoreClearingUnitTest):

    def setUp(self):
        self.config(default_store='cinder',
                    known_stores=['glance.store.cinder.Store'])
        super(TestCinderStore, self).setUp()
        self.stubs = stubout.StubOutForTesting()

    def test_cinder_configure_add(self):
        store = cinder.Store()
        self.assertRaises(exception.BadStoreConfiguration,
                          store.configure_add)
        store = cinder.Store(context=None)
        self.assertRaises(exception.BadStoreConfiguration,
                          store.configure_add)
        store = cinder.Store(context=FakeObject(service_catalog=None))
        self.assertRaises(exception.BadStoreConfiguration,
                          store.configure_add)
        store = cinder.Store(context=FakeObject(service_catalog=
                                                'fake_service_catalog'))
        store.configure_add()

    def test_cinder_get_size(self):
        fake_client = FakeObject(auth_token=None, management_url=None)
        fake_volumes = {'12345678-9012-3455-6789-012345678901':
                        FakeObject(size=5)}

        class FakeCinderClient(FakeObject):
            def __init__(self, *args, **kwargs):
                super(FakeCinderClient, self).__init__(client=fake_client,
                                                       volumes=fake_volumes)

        self.stubs.Set(cinderclient, 'Client', FakeCinderClient)

        fake_sc = [{u'endpoints': [{u'publicURL': u'foo_public_url'}],
                    u'endpoints_links': [],
                    u'name': u'cinder',
                    u'type': u'volume'}]
        fake_context = FakeObject(service_catalog=fake_sc,
                                  user='fake_uer',
                                  auth_tok='fake_token',
                                  tenant='fake_tenant')

        uri = 'cinder://%s' % fake_volumes.keys()[0]
        loc = get_location_from_uri(uri)
        store = cinder.Store(context=fake_context)
        image_size = store.get_size(loc)
        self.assertEqual(image_size,
                         fake_volumes.values()[0].size * units.Gi)
        self.assertEqual(fake_client.auth_token, 'fake_token')
        self.assertEqual(fake_client.management_url, 'foo_public_url')
