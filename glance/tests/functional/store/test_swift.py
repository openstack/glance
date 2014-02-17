# Copyright 2012 OpenStack Foundation
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
"""
Functional tests for the Swift store interface

Set the GLANCE_TEST_SWIFT_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
Swift backend
"""

import ConfigParser
import hashlib
import os
import os.path
import random
import string
import uuid

import oslo.config.cfg
import six
import six.moves.urllib.parse as urlparse
import testtools

from glance.common import exception
import glance.common.utils as common_utils

import glance.store.swift
import glance.tests.functional.store as store_tests

try:
    import swiftclient
except ImportError:
    swiftclient = None


class SwiftStoreError(RuntimeError):
    pass


def _uniq(value):
    return '%s.%d' % (value, random.randint(0, 99999))


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        'swift_store_auth_address',
        'swift_store_auth_version',
        'swift_store_user',
        'swift_store_key',
        'swift_store_container',
    ]

    for option in options:
        out[option] = config.defaults()[option]

    return out


def swift_connect(auth_url, auth_version, user, key):
    try:
        return swiftclient.Connection(authurl=auth_url,
                                      auth_version=auth_version,
                                      user=user,
                                      key=key,
                                      snet=False,
                                      retries=1)
    except AttributeError:
        raise SwiftStoreError("Could not find swiftclient module")


def swift_list_containers(swift_conn):
    try:
        _, containers = swift_conn.get_account()
    except Exception as e:
        msg = ("Failed to list containers (get_account) "
               "from Swift. Got error: %s" % e)
        raise SwiftStoreError(msg)
    else:
        return containers


def swift_create_container(swift_conn, container_name):
    try:
        swift_conn.put_container(container_name)
    except swiftclient.ClientException as e:
        msg = "Failed to create container. Got error: %s" % e
        raise SwiftStoreError(msg)


def swift_get_container(swift_conn, container_name, **kwargs):
    return swift_conn.get_container(container_name, **kwargs)


def swift_delete_container(swift_conn, container_name):
    try:
        swift_conn.delete_container(container_name)
    except swiftclient.ClientException as e:
        msg = "Failed to delete container from Swift. Got error: %s" % e
        raise SwiftStoreError(msg)


def swift_put_object(swift_conn, container_name, object_name, contents):
    return swift_conn.put_object(container_name, object_name, contents)


def swift_head_object(swift_conn, container_name, obj_name):
    return swift_conn.head_object(container_name, obj_name)


def keystone_authenticate(auth_url, auth_version, tenant_name,
                          username, password):
    assert int(auth_version) == 2, 'Only auth version 2 is supported'

    import keystoneclient.v2_0.client
    ksclient = keystoneclient.v2_0.client.Client(tenant_name=tenant_name,
                                                 username=username,
                                                 password=password,
                                                 auth_url=auth_url)

    auth_resp = ksclient.service_catalog.catalog
    tenant_id = auth_resp['token']['tenant']['id']
    service_catalog = auth_resp['serviceCatalog']
    return tenant_id, ksclient.auth_token, service_catalog


class TestSwiftStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.swift.Store'
    store_cls = glance.store.swift.Store
    store_name = 'swift'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])

        raw_config = read_config(config_path)
        config = parse_config(raw_config)

        swift = swift_connect(config['swift_store_auth_address'],
                              config['swift_store_auth_version'],
                              config['swift_store_user'],
                              config['swift_store_key'])

        #NOTE(bcwaldon): Ensure we have a functional swift connection
        swift_list_containers(swift)

        self.swift_client = swift
        self.swift_config = config

        self.swift_config['swift_store_create_container_on_put'] = True

        super(TestSwiftStore, self).setUp()

    def get_store(self, **kwargs):
        store = glance.store.swift.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def test_object_chunking(self):
        """Upload an image that is split into multiple swift objects.

        We specifically check the case that
        image_size % swift_store_large_object_chunk_size != 0 to
        ensure we aren't losing image data.
        """
        self.config(
            swift_store_large_object_size=2,  # 2 MB
            swift_store_large_object_chunk_size=2,  # 2 MB
        )
        store = self.get_store()
        image_id = str(uuid.uuid4())
        image_size = 5242880  # 5 MB
        image_data = six.StringIO('X' * image_size)
        image_checksum = 'eb7f8c3716b9f059cee7617a4ba9d0d3'
        uri, add_size, add_checksum, _ = store.add(image_id,
                                                   image_data,
                                                   image_size)

        self.assertEqual(image_size, add_size)
        self.assertEqual(image_checksum, add_checksum)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        # Store interface should still be respected even though
        # we are storing images in multiple Swift objects
        (get_iter, get_size) = store.get(location)
        self.assertEqual(5242880, get_size)
        self.assertEqual('X' * 5242880, ''.join(get_iter))

        # The object should have a manifest pointing to the chunks
        # of image data
        swift_location = location.store_location
        headers = swift_head_object(self.swift_client,
                                    swift_location.container,
                                    swift_location.obj)
        manifest = headers.get('x-object-manifest')
        self.assertTrue(manifest)

        # Verify the objects in the manifest exist
        manifest_container, manifest_prefix = manifest.split('/', 1)
        container = swift_get_container(self.swift_client,
                                        manifest_container,
                                        prefix=manifest_prefix)
        segments = [segment['name'] for segment in container[1]]

        for segment in segments:
            headers = swift_head_object(self.swift_client,
                                        manifest_container,
                                        segment)
            self.assertTrue(headers.get('content-length'))

        # Since we used a 5 MB image with a 2 MB chunk size, we should
        # expect to see three data objects
        self.assertEqual(3, len(segments), 'Got segments %s' % segments)

        # Add an object that should survive the delete operation
        non_image_obj = image_id + '0'
        swift_put_object(self.swift_client,
                         manifest_container,
                         non_image_obj,
                         'XXX')

        store.delete(location)

        # Verify the segments in the manifest are all gone
        for segment in segments:
            self.assertRaises(swiftclient.ClientException,
                              swift_head_object,
                              self.swift_client,
                              manifest_container,
                              segment)

        # Verify the manifest is gone too
        self.assertRaises(swiftclient.ClientException,
                          swift_head_object,
                          self.swift_client,
                          manifest_container,
                          swift_location.obj)

        # Verify that the non-image object was not deleted
        headers = swift_head_object(self.swift_client,
                                    manifest_container,
                                    non_image_obj)
        self.assertTrue(headers.get('content-length'))

        # Clean up
        self.swift_client.delete_object(manifest_container,
                                        non_image_obj)

        # Simulate exceeding 'image_size_cap' setting
        image_data = six.StringIO('X' * image_size)
        image_data = common_utils.LimitingReader(image_data, image_size - 1)
        image_id = str(uuid.uuid4())
        self.assertRaises(exception.ImageSizeLimitExceeded,
                          store.add,
                          image_id,
                          image_data,
                          image_size)

        # Verify written segments have been deleted
        container = swift_get_container(self.swift_client,
                                        manifest_container,
                                        prefix=image_id)
        segments = [segment['name'] for segment in container[1]]
        self.assertEqual(0, len(segments), 'Got segments %s' % segments)

    def test_retries_fail_start_of_download(self):
        """
        Get an object from Swift where Swift does not complete the request
        in one attempt. Fails at the start of the download.
        """
        self.config(
            swift_store_retry_get_count=1,
        )
        store = self.get_store()
        image_id = str(uuid.uuid4())
        image_size = 1024 * 1024 * 5  # 5 MB
        chars = string.ascii_uppercase + string.digits
        image_data = ''.join(random.choice(chars) for x in range(image_size))
        image_checksum = hashlib.md5(image_data)
        uri, add_size, add_checksum, _ = store.add(image_id,
                                                   image_data,
                                                   image_size)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        def iter_wrapper(iterable):
            # raise StopIteration as soon as iteration begins
            yield ''

        (get_iter, get_size) = store.get(location)
        get_iter.wrapped = glance.store.swift.swift_retry_iter(
            iter_wrapper(get_iter.wrapped), image_size,
            store, location.store_location)
        self.assertEqual(image_size, get_size)
        received_data = ''.join(get_iter.wrapped)
        self.assertEqual(image_data, received_data)
        self.assertEqual(image_checksum.hexdigest(),
                         hashlib.md5(received_data).hexdigest())

    def test_retries_fail_partway_through_download(self):
        """
        Get an object from Swift where Swift does not complete the request
        in one attempt. Fails partway through the download.
        """
        self.config(
            swift_store_retry_get_count=1,
        )
        store = self.get_store()
        image_id = str(uuid.uuid4())
        image_size = 1024 * 1024 * 5  # 5 MB
        chars = string.ascii_uppercase + string.digits
        image_data = ''.join(random.choice(chars) for x in range(image_size))
        image_checksum = hashlib.md5(image_data)
        uri, add_size, add_checksum, _ = store.add(image_id,
                                                   image_data,
                                                   image_size)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        def iter_wrapper(iterable):
            bytes_received = 0
            for chunk in iterable:
                yield chunk
                bytes_received += len(chunk)
                if bytes_received > (image_size / 2):
                    raise StopIteration

        (get_iter, get_size) = store.get(location)
        get_iter.wrapped = glance.store.swift.swift_retry_iter(
            iter_wrapper(get_iter.wrapped), image_size,
            store, location.store_location)
        self.assertEqual(image_size, get_size)
        received_data = ''.join(get_iter.wrapped)
        self.assertEqual(image_data, received_data)
        self.assertEqual(image_checksum.hexdigest(),
                         hashlib.md5(received_data).hexdigest())

    def test_retries_fail_end_of_download(self):
        """
        Get an object from Swift where Swift does not complete the request
        in one attempt. Fails at the end of the download
        """
        self.config(
            swift_store_retry_get_count=1,
        )
        store = self.get_store()
        image_id = str(uuid.uuid4())
        image_size = 1024 * 1024 * 5  # 5 MB
        chars = string.ascii_uppercase + string.digits
        image_data = ''.join(random.choice(chars) for x in range(image_size))
        image_checksum = hashlib.md5(image_data)
        uri, add_size, add_checksum, _ = store.add(image_id,
                                                   image_data,
                                                   image_size)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        def iter_wrapper(iterable):
            bytes_received = 0
            for chunk in iterable:
                yield chunk
                bytes_received += len(chunk)
                if bytes_received == image_size:
                    raise StopIteration

        (get_iter, get_size) = store.get(location)
        get_iter.wrapped = glance.store.swift.swift_retry_iter(
            iter_wrapper(get_iter.wrapped), image_size,
            store, location.store_location)
        self.assertEqual(image_size, get_size)
        received_data = ''.join(get_iter.wrapped)
        self.assertEqual(image_data, received_data)
        self.assertEqual(image_checksum.hexdigest(),
                         hashlib.md5(received_data).hexdigest())

    def stash_image(self, image_id, image_data):
        container_name = self.swift_config['swift_store_container']
        swift_put_object(self.swift_client,
                         container_name,
                         image_id,
                         'XXX')

        #NOTE(bcwaldon): This is a hack until we find a better way to
        # build this URL
        auth_url = self.swift_config['swift_store_auth_address']
        auth_url = urlparse.urlparse(auth_url)
        user = urlparse.quote(self.swift_config['swift_store_user'])
        key = self.swift_config['swift_store_key']
        netloc = ''.join(('%s:%s' % (user, key), '@', auth_url.netloc))
        path = os.path.join(auth_url.path, container_name, image_id)

        # This is an auth url with /<CONTAINER>/<OBJECT> on the end
        return 'swift+http://%s%s' % (netloc, path)

    def test_multitenant(self):
        """Ensure an image is properly configured when using multitenancy."""
        self.config(
            swift_store_multi_tenant=True,
        )

        swift_store_user = self.swift_config['swift_store_user']
        tenant_name, username = swift_store_user.split(':')
        tenant_id, auth_token, service_catalog = keystone_authenticate(
            self.swift_config['swift_store_auth_address'],
            self.swift_config['swift_store_auth_version'],
            tenant_name,
            username,
            self.swift_config['swift_store_key'])

        context = glance.context.RequestContext(
            tenant=tenant_id,
            service_catalog=service_catalog,
            auth_tok=auth_token)
        store = self.get_store(context=context)

        image_id = str(uuid.uuid4())
        image_data = six.StringIO('XXX')
        uri, _, _, _ = store.add(image_id, image_data, 3)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        read_tenant = str(uuid.uuid4())
        write_tenant = str(uuid.uuid4())
        store.set_acls(location,
                       public=False,
                       read_tenants=[read_tenant],
                       write_tenants=[write_tenant])

        container_name = location.store_location.container
        container, _ = swift_get_container(self.swift_client, container_name)
        self.assertEqual(read_tenant + ':*',
                         container.get('x-container-read'))
        self.assertEqual(write_tenant + ':*',
                         container.get('x-container-write'))

        store.set_acls(location, public=True, read_tenants=[read_tenant])

        container_name = location.store_location.container
        container, _ = swift_get_container(self.swift_client, container_name)
        self.assertEqual('.r:*,.rlistings', container.get('x-container-read'))
        self.assertEqual('', container.get('x-container-write', ''))

        (get_iter, get_size) = store.get(location)
        self.assertEqual(3, get_size)
        self.assertEqual('XXX', ''.join(get_iter))

        store.delete(location)

    def test_delayed_delete_with_auth(self):
        """Ensure delete works with delayed delete and auth

        Reproduces LP bug 1238604.
        """
        swift_store_user = self.swift_config['swift_store_user']
        tenant_name, username = swift_store_user.split(':')
        tenant_id, auth_token, service_catalog = keystone_authenticate(
            self.swift_config['swift_store_auth_address'],
            self.swift_config['swift_store_auth_version'],
            tenant_name,
            username,
            self.swift_config['swift_store_key'])

        context = glance.context.RequestContext(
            tenant=tenant_id,
            service_catalog=service_catalog,
            auth_tok=auth_token)
        store = self.get_store(context=context)

        image_id = str(uuid.uuid4())
        image_data = six.StringIO('data')
        uri, _, _, _ = store.add(image_id, image_data, 4)

        location = glance.store.location.Location(
            self.store_name,
            store.get_store_location_class(),
            uri=uri,
            image_id=image_id)

        container_name = location.store_location.container
        container, _ = swift_get_container(self.swift_client, container_name)

        (get_iter, get_size) = store.get(location)
        self.assertEqual(4, get_size)
        self.assertEqual('data', ''.join(get_iter))

        glance.store.schedule_delayed_delete_from_backend(context,
                                                          uri,
                                                          image_id)
        store.delete(location)
