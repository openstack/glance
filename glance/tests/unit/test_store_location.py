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
import mock

from glance.common import exception
from glance import context
import glance.store
import glance.store.filesystem
import glance.store.http
import glance.store.location as location
import glance.store.s3
import glance.store.swift
import glance.store.vmware_datastore
from glance.tests.unit import base


class TestStoreLocation(base.StoreClearingUnitTest):

    def setUp(self):
        self.config(default_store='file')

        # NOTE(flaper87): Each store should test
        # this in their test suite.
        self.config(known_stores=[
            "glance.store.filesystem.Store",
            "glance.store.http.Store",
            "glance.store.rbd.Store",
            "glance.store.s3.Store",
            "glance.store.swift.Store",
            "glance.store.sheepdog.Store",
            "glance.store.cinder.Store",
            "glance.store.gridfs.Store",
            "glance.store.vmware_datastore.Store",
        ])
        super(TestStoreLocation, self).setUp()

    def test_get_location_from_uri_back_to_uri(self):
        """
        Test that for various URIs, the correct Location
        object can be contructed and then the original URI
        returned via the get_store_uri() method.
        """
        good_store_uris = [
            'https://user:pass@example.com:80/images/some-id',
            'http://images.oracle.com/123456',
            'swift://account%3Auser:pass@authurl.com/container/obj-id',
            'swift://storeurl.com/container/obj-id',
            'swift+https://account%3Auser:pass@authurl.com/container/obj-id',
            's3://accesskey:secretkey@s3.amazonaws.com/bucket/key-id',
            's3://accesskey:secretwith/aslash@s3.amazonaws.com/bucket/key-id',
            's3+http://accesskey:secret@s3.amazonaws.com/bucket/key-id',
            's3+https://accesskey:secretkey@s3.amazonaws.com/bucket/key-id',
            'file:///var/lib/glance/images/1',
            'rbd://imagename',
            'rbd://fsid/pool/image/snap',
            'rbd://%2F/%2F/%2F/%2F',
            'sheepdog://244e75f1-9c69-4167-9db7-1aa7d1973f6c',
            'cinder://12345678-9012-3455-6789-012345678901',
            'vsphere://ip/folder/openstack_glance/2332298?dcPath=dc&dsName=ds',
        ]

        for uri in good_store_uris:
            loc = location.get_location_from_uri(uri)
            # The get_store_uri() method *should* return an identical URI
            # to the URI that is passed to get_location_from_uri()
            self.assertEqual(loc.get_store_uri(), uri)

    def test_bad_store_scheme(self):
        """
        Test that a URI with a non-existing scheme triggers exception
        """
        bad_uri = 'unknown://user:pass@example.com:80/images/some-id'

        self.assertRaises(exception.UnknownScheme,
                          location.get_location_from_uri,
                          bad_uri)

    def test_filesystem_store_location(self):
        """
        Test the specific StoreLocation for the Filesystem store
        """
        uri = 'file:///var/lib/glance/images/1'
        loc = glance.store.filesystem.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual("file", loc.scheme)
        self.assertEqual("/var/lib/glance/images/1", loc.path)
        self.assertEqual(uri, loc.get_uri())

        bad_uri = 'fil://'
        self.assertRaises(AssertionError, loc.parse_uri, bad_uri)

        bad_uri = 'file://'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_http_store_location(self):
        """
        Test the specific StoreLocation for the HTTP store
        """
        uri = 'http://example.com/images/1'
        loc = glance.store.http.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual("http", loc.scheme)
        self.assertEqual("example.com", loc.netloc)
        self.assertEqual("/images/1", loc.path)
        self.assertEqual(uri, loc.get_uri())

        uri = 'https://example.com:8080/images/container/1'
        loc.parse_uri(uri)

        self.assertEqual("https", loc.scheme)
        self.assertEqual("example.com:8080", loc.netloc)
        self.assertEqual("/images/container/1", loc.path)
        self.assertEqual(uri, loc.get_uri())

        uri = 'https://user:password@example.com:8080/images/container/1'
        loc.parse_uri(uri)

        self.assertEqual("https", loc.scheme)
        self.assertEqual("example.com:8080", loc.netloc)
        self.assertEqual("user", loc.user)
        self.assertEqual("password", loc.password)
        self.assertEqual("/images/container/1", loc.path)
        self.assertEqual(uri, loc.get_uri())

        uri = 'https://user:@example.com:8080/images/1'
        loc.parse_uri(uri)

        self.assertEqual("https", loc.scheme)
        self.assertEqual("example.com:8080", loc.netloc)
        self.assertEqual("user", loc.user)
        self.assertEqual("", loc.password)
        self.assertEqual("/images/1", loc.path)
        self.assertEqual(uri, loc.get_uri())

        bad_uri = 'htt://'
        self.assertRaises(AssertionError, loc.parse_uri, bad_uri)

        bad_uri = 'http://'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'http://user@example.com:8080/images/1'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_swift_store_location(self):
        """
        Test the specific StoreLocation for the Swift store
        """
        uri = 'swift://example.com/images/1'
        loc = glance.store.swift.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual("swift", loc.scheme)
        self.assertEqual("example.com", loc.auth_or_store_url)
        self.assertEqual("https://example.com", loc.swift_url)
        self.assertEqual("images", loc.container)
        self.assertEqual("1", loc.obj)
        self.assertIsNone(loc.user)
        self.assertEqual(uri, loc.get_uri())

        uri = 'swift+https://user:pass@authurl.com/images/1'
        loc.parse_uri(uri)

        self.assertEqual("swift+https", loc.scheme)
        self.assertEqual("authurl.com", loc.auth_or_store_url)
        self.assertEqual("https://authurl.com", loc.swift_url)
        self.assertEqual("images", loc.container)
        self.assertEqual("1", loc.obj)
        self.assertEqual("user", loc.user)
        self.assertEqual("pass", loc.key)
        self.assertEqual(uri, loc.get_uri())

        uri = 'swift+https://user:pass@authurl.com/v1/container/12345'
        loc.parse_uri(uri)

        self.assertEqual("swift+https", loc.scheme)
        self.assertEqual("authurl.com/v1", loc.auth_or_store_url)
        self.assertEqual("https://authurl.com/v1", loc.swift_url)
        self.assertEqual("container", loc.container)
        self.assertEqual("12345", loc.obj)
        self.assertEqual("user", loc.user)
        self.assertEqual("pass", loc.key)
        self.assertEqual(uri, loc.get_uri())

        uri = ('swift+http://a%3Auser%40example.com:p%40ss@authurl.com/'
               'v1/container/12345')
        loc.parse_uri(uri)

        self.assertEqual("swift+http", loc.scheme)
        self.assertEqual("authurl.com/v1", loc.auth_or_store_url)
        self.assertEqual("http://authurl.com/v1", loc.swift_url)
        self.assertEqual("container", loc.container)
        self.assertEqual("12345", loc.obj)
        self.assertEqual("a:user@example.com", loc.user)
        self.assertEqual("p@ss", loc.key)
        self.assertEqual(uri, loc.get_uri())

        # multitenant puts store URL in the location (not auth)
        uri = ('swift+http://storeurl.com/v1/container/12345')
        loc.parse_uri(uri)

        self.assertEqual("swift+http", loc.scheme)
        self.assertEqual("storeurl.com/v1", loc.auth_or_store_url)
        self.assertEqual("http://storeurl.com/v1", loc.swift_url)
        self.assertEqual("container", loc.container)
        self.assertEqual("12345", loc.obj)
        self.assertIsNone(loc.user)
        self.assertIsNone(loc.key)
        self.assertEqual(uri, loc.get_uri())

        bad_uri = 'swif://'
        self.assertRaises(AssertionError, loc.parse_uri, bad_uri)

        bad_uri = 'swift://'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'swift://user@example.com:8080/images/1'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'swift://user:pass@http://example.com:8080/images/1'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_s3_store_location(self):
        """
        Test the specific StoreLocation for the S3 store
        """
        uri = 's3://example.com/images/1'
        loc = glance.store.s3.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual("s3", loc.scheme)
        self.assertEqual("example.com", loc.s3serviceurl)
        self.assertEqual("images", loc.bucket)
        self.assertEqual("1", loc.key)
        self.assertIsNone(loc.accesskey)
        self.assertEqual(uri, loc.get_uri())

        uri = 's3+https://accesskey:pass@s3serviceurl.com/images/1'
        loc.parse_uri(uri)

        self.assertEqual("s3+https", loc.scheme)
        self.assertEqual("s3serviceurl.com", loc.s3serviceurl)
        self.assertEqual("images", loc.bucket)
        self.assertEqual("1", loc.key)
        self.assertEqual("accesskey", loc.accesskey)
        self.assertEqual("pass", loc.secretkey)
        self.assertEqual(uri, loc.get_uri())

        uri = 's3+https://accesskey:pass@s3serviceurl.com/v1/bucket/12345'
        loc.parse_uri(uri)

        self.assertEqual("s3+https", loc.scheme)
        self.assertEqual("s3serviceurl.com/v1", loc.s3serviceurl)
        self.assertEqual("bucket", loc.bucket)
        self.assertEqual("12345", loc.key)
        self.assertEqual("accesskey", loc.accesskey)
        self.assertEqual("pass", loc.secretkey)
        self.assertEqual(uri, loc.get_uri())

        uri = 's3://accesskey:pass/withslash@s3serviceurl.com/v1/bucket/12345'
        loc.parse_uri(uri)

        self.assertEqual("s3", loc.scheme)
        self.assertEqual("s3serviceurl.com/v1", loc.s3serviceurl)
        self.assertEqual("bucket", loc.bucket)
        self.assertEqual("12345", loc.key)
        self.assertEqual("accesskey", loc.accesskey)
        self.assertEqual("pass/withslash", loc.secretkey)
        self.assertEqual(uri, loc.get_uri())

        bad_uri = 's://'
        self.assertRaises(AssertionError, loc.parse_uri, bad_uri)

        bad_uri = 's3://'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 's3://accesskey@example.com:8080/images/1'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 's3://user:pass@http://example.com:8080/images/1'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_rbd_store_location(self):
        """
        Test the specific StoreLocation for the RBD store
        """
        uri = 'rbd://imagename'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('imagename', loc.image)
        self.assertIsNone(loc.fsid)
        self.assertIsNone(loc.pool)
        self.assertIsNone(loc.snapshot)

        uri = u'rbd://imagename'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('imagename', loc.image)
        self.assertIsNone(loc.fsid)
        self.assertIsNone(loc.pool)
        self.assertIsNone(loc.snapshot)

        uri = 'rbd://fsid/pool/image/snap'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('image', loc.image)
        self.assertEqual('fsid', loc.fsid)
        self.assertEqual('pool', loc.pool)
        self.assertEqual('snap', loc.snapshot)

        uri = u'rbd://fsid/pool/image/snap'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('image', loc.image)
        self.assertEqual('fsid', loc.fsid)
        self.assertEqual('pool', loc.pool)
        self.assertEqual('snap', loc.snapshot)

        uri = 'rbd://%2f/%2f/%2f/%2f'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('/', loc.image)
        self.assertEqual('/', loc.fsid)
        self.assertEqual('/', loc.pool)
        self.assertEqual('/', loc.snapshot)

        uri = u'rbd://%2f/%2f/%2f/%2f'
        loc = glance.store.rbd.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual('/', loc.image)
        self.assertEqual('/', loc.fsid)
        self.assertEqual('/', loc.pool)
        self.assertEqual('/', loc.snapshot)

        bad_uri = 'rbd:/image'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'rbd://image/extra'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'rbd://image/'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'http://image'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'http://fsid/pool/image/snap'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'rbd://fsid/pool/image/'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'rbd://fsid/pool/image/snap/'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'http://///'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'rbd://' + unichr(300)
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_sheepdog_store_location(self):
        """
        Test the specific StoreLocation for the Sheepdog store
        """
        uri = 'sheepdog://244e75f1-9c69-4167-9db7-1aa7d1973f6c'
        loc = glance.store.sheepdog.StoreLocation({})
        loc.parse_uri(uri)
        self.assertEqual('244e75f1-9c69-4167-9db7-1aa7d1973f6c', loc.image)

        bad_uri = 'sheepdog:/244e75f1-9c69-4167-9db7-1aa7d1973f6c'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'http://244e75f1-9c69-4167-9db7-1aa7d1973f6c'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = 'image; name'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_vmware_store_location(self):
        """
        Test the specific StoreLocation for the VMware store
        """
        ds_url_prefix = glance.store.vmware_datastore.DS_URL_PREFIX
        image_dir = glance.store.vmware_datastore.DEFAULT_STORE_IMAGE_DIR
        uri = ('vsphere://127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds' %
               (ds_url_prefix, image_dir))
        loc = glance.store.vmware_datastore.StoreLocation({})
        loc.parse_uri(uri)

        self.assertEqual("vsphere", loc.scheme)
        self.assertEqual("127.0.0.1", loc.server_host)
        self.assertEqual("%s%s/29038321" %
                         (ds_url_prefix, image_dir), loc.path)
        self.assertEqual("dcPath=my-dc&dsName=my-ds", loc.query)
        self.assertEqual(uri, loc.get_uri())

        bad_uri = 'vphere://'
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = ('vspheer://127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds'
                   % (ds_url_prefix, image_dir))
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = ('http://127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds'
                   % (ds_url_prefix, image_dir))
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = ('vsphere:/127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds'
                   % (ds_url_prefix, image_dir))
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = ('vsphere://127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds'
                   % (ds_url_prefix, "/folder_not_in_configuration"))
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

        bad_uri = ('vsphere://127.0.0.1%s%s/29038321?dcPath=my-dc&dsName=my-ds'
                   % ("/wrong_folder_path", image_dir))
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_cinder_store_good_location(self):
        """
        Test the specific StoreLocation for the Cinder store
        """
        good_uri = 'cinder://12345678-9012-3455-6789-012345678901'
        loc = glance.store.cinder.StoreLocation({})
        loc.parse_uri(good_uri)
        self.assertEqual('12345678-9012-3455-6789-012345678901', loc.volume_id)

    def test_cinder_store_bad_location(self):
        """
        Test the specific StoreLocation for the Cinder store
        """
        bad_uri = 'cinder://volume-id-is-a-uuid'
        loc = glance.store.cinder.StoreLocation({})
        self.assertRaises(exception.BadStoreUri, loc.parse_uri, bad_uri)

    def test_get_store_from_scheme(self):
        """
        Test that the backend returned by glance.store.get_backend_class
        is correct or raises an appropriate error.
        """
        good_results = {
            'swift': glance.store.swift.SingleTenantStore,
            'swift+http': glance.store.swift.SingleTenantStore,
            'swift+https': glance.store.swift.SingleTenantStore,
            's3': glance.store.s3.Store,
            's3+http': glance.store.s3.Store,
            's3+https': glance.store.s3.Store,
            'file': glance.store.filesystem.Store,
            'filesystem': glance.store.filesystem.Store,
            'http': glance.store.http.Store,
            'https': glance.store.http.Store,
            'rbd': glance.store.rbd.Store,
            'sheepdog': glance.store.sheepdog.Store,
            'cinder': glance.store.cinder.Store,
            'vsphere': glance.store.vmware_datastore.Store}

        ctx = context.RequestContext()
        for scheme, store in good_results.items():
            store_obj = glance.store.get_store_from_scheme(ctx, scheme)
            self.assertEqual(store_obj.__class__, store)

        bad_results = ['fil', 'swift+h', 'unknown']

        for store in bad_results:
            self.assertRaises(exception.UnknownScheme,
                              glance.store.get_store_from_scheme,
                              ctx,
                              store)

    def test_add_location_for_image_without_size(self):
        class FakeImageProxy():
            size = None
            context = None
            store_api = mock.Mock()

        def fake_get_size_from_backend(context, uri):
            return 1

        self.stubs.Set(glance.store, 'get_size_from_backend',
                       fake_get_size_from_backend)
        with mock.patch('glance.store._check_image_location'):
            loc1 = {'url': 'file:///fake1.img.tar.gz', 'metadata': {}}
            loc2 = {'url': 'file:///fake2.img.tar.gz', 'metadata': {}}

            # Test for insert location
            image1 = FakeImageProxy()
            locations = glance.store.StoreLocations(image1, [])
            locations.insert(0, loc2)
            self.assertEqual(image1.size, 1)

            # Test for set_attr of _locations_proxy
            image2 = FakeImageProxy()
            locations = glance.store.StoreLocations(image2, [loc1])
            locations[0] = loc2
            self.assertTrue(loc2 in locations)
            self.assertEqual(image2.size, 1)
