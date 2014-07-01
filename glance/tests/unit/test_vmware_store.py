# Copyright 2014 OpenStack, LLC
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

"""Tests the VMware Datastore backend store"""

import hashlib
import uuid

import mock
import six

from glance.common import exception
from glance.openstack.common import units
from glance.store.location import get_location_from_uri
import glance.store.vmware_datastore as vm_store
from glance.store.vmware_datastore import Store
from glance.tests.unit import base
from glance.tests import utils


FAKE_UUID = str(uuid.uuid4())

FIVE_KB = 5 * units.Ki

VMWARE_DATASTORE_CONF = {
    'verbose': True,
    'debug': True,
    'known_stores': ['glance.store.vmware_datastore.Store'],
    'default_store': 'vsphere',
    'vmware_server_host': '127.0.0.1',
    'vmware_server_username': 'username',
    'vmware_server_password': 'password',
    'vmware_datacenter_path': 'dc1',
    'vmware_datastore_name': 'ds1',
    'vmware_store_image_dir': '/openstack_glance',
    'vmware_api_insecure': 'True',
    'vmware_api_retry_count': 10
}


def format_location(host_ip, folder_name,
                    image_id, datacenter_path, datastore_name):
    """
    Helper method that returns a VMware Datastore store URI given
    the component pieces.
    """
    scheme = 'vsphere'
    return ("%s://%s/folder%s/%s?dsName=%s&dcPath=%s"
            % (scheme, host_ip, folder_name,
               image_id, datastore_name, datacenter_path))


class FakeHTTPConnection(object):

    def __init__(self, status=200, *args, **kwargs):
        self.status = status
        pass

    def getresponse(self):
        return utils.FakeHTTPResponse(status=self.status)

    def request(self, *_args, **_kwargs):
        pass

    def close(self):
        pass


class TestStore(base.StoreClearingUnitTest):

    @mock.patch('oslo.vmware.api.VMwareAPISession', autospec=True)
    def setUp(self, mock_session):
        """Establish a clean test environment"""

        self.config(default_store='file')

        # NOTE(flaper87): Each store should test
        # this in their test suite.
        self.config(known_stores=VMWARE_DATASTORE_CONF['known_stores'])

        super(TestStore, self).setUp()

        Store.READ_CHUNKSIZE = 2
        self.store = Store()

        class FakeSession:
            def __init__(self):
                self.vim = FakeVim()

        class FakeVim:
            def __init__(self):
                self.client = FakeClient()

        class FakeClient:
            def __init__(self):
                self.options = FakeOptions()

        class FakeOptions:
            def __init__(self):
                self.transport = FakeTransport()

        class FakeTransport:
            def __init__(self):
                self.cookiejar = FakeCookieJar()

        class FakeCookieJar:
            pass

        self.store.scheme = VMWARE_DATASTORE_CONF['default_store']
        self.store.server_host = (
            VMWARE_DATASTORE_CONF['vmware_server_host'])
        self.store.datacenter_path = (
            VMWARE_DATASTORE_CONF['vmware_datacenter_path'])
        self.store.datastore_name = (
            VMWARE_DATASTORE_CONF['vmware_datastore_name'])
        self.store.api_insecure = (
            VMWARE_DATASTORE_CONF['vmware_api_insecure'])
        self.store.api_retry_count = (
            VMWARE_DATASTORE_CONF['vmware_api_retry_count'])
        self.store._session = FakeSession()
        self.store._session.invoke_api = mock.Mock()
        self.store._session.wait_for_task = mock.Mock()

        self.store.store_image_dir = (
            VMWARE_DATASTORE_CONF['vmware_store_image_dir'])
        Store._build_vim_cookie_header = mock.Mock()
        self.addCleanup(self.stubs.UnsetAll)

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        expected_image_size = 31
        expected_returns = ['I ', 'am', ' a', ' t', 'ea', 'po', 't,', ' s',
                            'ho', 'rt', ' a', 'nd', ' s', 'to', 'ut', '\n']
        loc = get_location_from_uri(
            "vsphere://127.0.0.1/folder/openstack_glance/%s"
            "?dsName=ds1&dcPath=dc1" % FAKE_UUID)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection()
            (image_file, image_size) = self.store.get(loc)
        self.assertEqual(image_size, expected_image_size)
        chunks = [c for c in image_file]
        self.assertEqual(chunks, expected_returns)

    def test_get_non_existing(self):
        """
        Test that trying to retrieve an image that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("vsphere://127.0.0.1/folder/openstack_glan"
                                    "ce/%s?dsName=ds1&dcPath=dc1" % FAKE_UUID)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection(status=404)
            self.assertRaises(exception.NotFound, self.store.get, loc)

    @mock.patch.object(vm_store._Reader, 'size')
    def test_add(self, fake_size):
        """Test that we can add an image via the VMware backend"""
        expected_image_id = str(uuid.uuid4())
        expected_size = FIVE_KB
        expected_contents = "*" * expected_size
        hash_code = hashlib.md5(expected_contents)
        expected_checksum = hash_code.hexdigest()
        fake_size.__get__ = mock.Mock(return_value=expected_size)
        with mock.patch('hashlib.md5') as md5:
            md5.return_value = hash_code
            expected_location = format_location(
                VMWARE_DATASTORE_CONF['vmware_server_host'],
                VMWARE_DATASTORE_CONF['vmware_store_image_dir'],
                expected_image_id,
                VMWARE_DATASTORE_CONF['vmware_datacenter_path'],
                VMWARE_DATASTORE_CONF['vmware_datastore_name'])
            image = six.StringIO(expected_contents)
            with mock.patch('httplib.HTTPConnection') as HttpConn:
                HttpConn.return_value = FakeHTTPConnection()
                location, size, checksum, _ = self.store.add(expected_image_id,
                                                             image,
                                                             expected_size)
        self.assertEqual(expected_location, location)
        self.assertEqual(expected_size, size)
        self.assertEqual(expected_checksum, checksum)

    @mock.patch.object(vm_store._Reader, 'size')
    def test_add_size_zero(self, fake_size):
        """
        Test that when specifying size zero for the image to add,
        the actual size of the image is returned.
        """
        expected_image_id = str(uuid.uuid4())
        expected_size = FIVE_KB
        expected_contents = "*" * expected_size
        hash_code = hashlib.md5(expected_contents)
        expected_checksum = hash_code.hexdigest()
        fake_size.__get__ = mock.Mock(return_value=expected_size)
        with mock.patch('hashlib.md5') as md5:
            md5.return_value = hash_code
            expected_location = format_location(
                VMWARE_DATASTORE_CONF['vmware_server_host'],
                VMWARE_DATASTORE_CONF['vmware_store_image_dir'],
                expected_image_id,
                VMWARE_DATASTORE_CONF['vmware_datacenter_path'],
                VMWARE_DATASTORE_CONF['vmware_datastore_name'])
            image = six.StringIO(expected_contents)
            with mock.patch('httplib.HTTPConnection') as HttpConn:
                HttpConn.return_value = FakeHTTPConnection()
                location, size, checksum, _ = self.store.add(expected_image_id,
                                                             image, 0)
        self.assertEqual(expected_location, location)
        self.assertEqual(expected_size, size)
        self.assertEqual(expected_checksum, checksum)

    def test_delete(self):
        """Test we can delete an existing image in the VMware store"""
        loc = get_location_from_uri(
            "vsphere://127.0.0.1/folder/openstack_glance/%s?"
            "dsName=ds1&dcPath=dc1" % FAKE_UUID)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection()
            Store._service_content = mock.Mock()
            self.store.delete(loc)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection(status=404)
            self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_get_size(self):
        """Test we can get the size of an existing image in the VMware store"""
        loc = get_location_from_uri(
            "vsphere://127.0.0.1/folder/openstack_glance/%s"
            "?dsName=ds1&dcPath=dc1" % FAKE_UUID)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection()
            image_size = self.store.get_size(loc)
        self.assertEqual(image_size, 31)

    def test_get_size_non_existing(self):
        """
        Test that trying to retrieve an image size that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("vsphere://127.0.0.1/folder/openstack_glan"
                                    "ce/%s?dsName=ds1&dcPath=dc1" % FAKE_UUID)
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection(status=404)
            self.assertRaises(exception.NotFound, self.store.get_size, loc)

    def test_reader_image_fits_in_blocksize(self):
        """
        Test that the image file reader returns the expected chunk of data
        when the block size is larger than the image.
        """
        content = 'XXX'
        image = six.StringIO(content)
        expected_checksum = hashlib.md5(content).hexdigest()
        checksum = hashlib.md5()
        reader = vm_store._Reader(image, checksum)
        ret = reader.read()
        expected_chunk = '%x\r\n%s\r\n' % (len(content), content)
        last_chunk = '0\r\n\r\n'
        self.assertEqual('%s%s' % (expected_chunk, last_chunk), ret)
        self.assertEqual(image.len, reader.size)
        self.assertEqual(expected_checksum, reader.checksum.hexdigest())
        self.assertTrue(reader.closed)
        ret = reader.read()
        self.assertEqual(image.len, reader.size)
        self.assertEqual(expected_checksum, reader.checksum.hexdigest())
        self.assertTrue(reader.closed)
        self.assertEqual('', ret)

    def test_reader_image_larger_blocksize(self):
        """
        Test that the image file reader returns the expected chunks when
        the block size specified is smaller than the image.
        """
        content = 'XXX'
        image = six.StringIO(content)
        expected_checksum = hashlib.md5(content).hexdigest()
        checksum = hashlib.md5()
        last_chunk = '0\r\n\r\n'
        reader = vm_store._Reader(image, checksum, blocksize=1)
        ret = reader.read()
        expected_chunk = '1\r\nX\r\n'
        self.assertEqual('%s%s%s%s' % (expected_chunk, expected_chunk,
                                       expected_chunk, last_chunk), ret)
        self.assertEqual(expected_checksum, reader.checksum.hexdigest())
        self.assertEqual(image.len, reader.size)
        self.assertTrue(reader.closed)

    def test_reader_size(self):
        """Test that the image reader takes into account the specified size."""
        content = 'XXX'
        image = six.StringIO(content)
        expected_checksum = hashlib.md5(content).hexdigest()
        checksum = hashlib.md5()
        reader = vm_store._Reader(image, checksum, blocksize=1)
        ret = reader.read(size=3)
        self.assertEqual('1\r\n', ret)
        ret = reader.read(size=1)
        self.assertEqual('X', ret)
        ret = reader.read()
        self.assertEqual(expected_checksum, reader.checksum.hexdigest())
        self.assertEqual(image.len, reader.size)
        self.assertTrue(reader.closed)

    def test_sanity_check_api_retry_count(self):
        """Test that sanity check raises if api_retry_count is <= 0."""
        vm_store.CONF.vmware_api_retry_count = -1
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store._sanity_check)
        vm_store.CONF.vmware_api_retry_count = 0
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store._sanity_check)
        vm_store.CONF.vmware_api_retry_count = 1
        try:
            self.store._sanity_check()
        except exception.BadStoreConfiguration:
            self.fail()

    def test_sanity_check_task_poll_interval(self):
        """Test that sanity check raises if task_poll_interval is <= 0."""
        vm_store.CONF.vmware_task_poll_interval = -1
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store._sanity_check)
        vm_store.CONF.vmware_task_poll_interval = 0
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store._sanity_check)
        vm_store.CONF.vmware_task_poll_interval = 1
        try:
            self.store._sanity_check()
        except exception.BadStoreConfiguration:
            self.fail()

    def test_retry_count(self):
        expected_image_id = str(uuid.uuid4())
        expected_size = FIVE_KB
        expected_contents = "*" * expected_size
        image = six.StringIO(expected_contents)
        self.store._create_session = mock.Mock()
        with mock.patch('httplib.HTTPConnection') as HttpConn:
            HttpConn.return_value = FakeHTTPConnection(status=401)
            try:
                location, size, checksum, _ = self.store.add(expected_image_id,
                                                             image,
                                                             expected_size)
            except exception.NotAuthenticated:
                pass
        self.assertEqual(VMWARE_DATASTORE_CONF['vmware_api_retry_count'] + 1,
                         self.store._create_session.call_count)
