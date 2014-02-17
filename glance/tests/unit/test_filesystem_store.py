# Copyright 2011 OpenStack Foundation
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

"""Tests the filesystem backend store"""

import __builtin__
import errno
import hashlib
import json
import os
import uuid

import fixtures
import mox
from oslo.config import cfg
import six

from glance.common import exception
from glance.openstack.common import units

from glance.store.filesystem import ChunkedFile
from glance.store.filesystem import Store
from glance.store.location import get_location_from_uri
from glance.tests.unit import base

CONF = cfg.CONF


class TestStore(base.IsolatedUnitTest):

    def setUp(self):
        """Establish a clean test environment"""
        super(TestStore, self).setUp()
        self.orig_chunksize = ChunkedFile.CHUNKSIZE
        ChunkedFile.CHUNKSIZE = 10
        self.store = Store()

    def tearDown(self):
        """Clear the test environment"""
        super(TestStore, self).tearDown()
        ChunkedFile.CHUNKSIZE = self.orig_chunksize

    def test_configure_add_single_datadir(self):
        """
        Tests filesystem specified by filesystem_store_datadir
        are parsed correctly.
        """
        store = self.useFixture(fixtures.TempDir()).path
        CONF.set_override('filesystem_store_datadir', store)
        self.store.configure_add()
        self.assertEqual(self.store.datadir, store)

    def test_configure_add_with_single_and_multi_datadirs(self):
        """
        Tests BadStoreConfiguration exception is raised if both
        filesystem_store_datadir and filesystem_store_datadirs are specified.
        """
        store_map = [self.useFixture(fixtures.TempDir()).path,
                     self.useFixture(fixtures.TempDir()).path]
        CONF.set_override('filesystem_store_datadirs',
                          [store_map[0] + ":100",
                           store_map[1] + ":200"])
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_configure_add_without_single_and_multi_datadirs(self):
        """
        Tests BadStoreConfiguration exception is raised if neither
        filesystem_store_datadir nor filesystem_store_datadirs are specified.
        """
        CONF.clear_override('filesystem_store_datadir')
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_configure_add_with_multi_datadirs(self):
        """
        Tests multiple filesystem specified by filesystem_store_datadirs
        are parsed correctly.
        """
        store_map = [self.useFixture(fixtures.TempDir()).path,
                     self.useFixture(fixtures.TempDir()).path]
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs',
                          [store_map[0] + ":100",
                           store_map[1] + ":200"])
        self.store.configure_add()

        expected_priority_map = {100: [store_map[0]], 200: [store_map[1]]}
        expected_priority_list = [200, 100]
        self.assertEqual(self.store.priority_data_map, expected_priority_map)
        self.assertEqual(self.store.priority_list, expected_priority_list)

    def test_configure_add_invalid_priority(self):
        """
        Tests invalid priority specified by filesystem_store_datadirs
        param raises BadStoreConfiguration exception.
        """
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs',
                          [self.useFixture(fixtures.TempDir()).path + ":100",
                           self.useFixture(fixtures.TempDir()).path +
                           ":invalid"])
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_configure_add_same_dir_multiple_times(self):
        """
        Tests BadStoreConfiguration exception is raised if same directory
        is specified multiple times in filesystem_store_datadirs.
        """
        store_map = [self.useFixture(fixtures.TempDir()).path,
                     self.useFixture(fixtures.TempDir()).path]
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs',
                          [store_map[0] + ":100",
                           store_map[1] + ":200",
                           store_map[0] + ":300"])
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_configure_add_with_empty_datadir_path(self):
        """
        Tests BadStoreConfiguration exception is raised if empty directory
        path is specified in filesystem_store_datadirs.
        """
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs', [''])
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_configure_add_with_readonly_datadir_path(self):
        """
        Tests BadStoreConfiguration exception is raised if directory
        path specified in filesystem_store_datadirs is readonly.
        """
        readonly_dir = self.useFixture(fixtures.TempDir()).path
        os.chmod(readonly_dir, 0o444)
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs', [readonly_dir])
        self.assertRaises(exception.BadStoreConfiguration,
                          self.store.configure_add)

    def test_get(self):
        """Test a "normal" retrieval of an image in chunks"""
        # First add an image...
        image_id = str(uuid.uuid4())
        file_contents = "chunk00000remainder"
        image_file = six.StringIO(file_contents)

        location, size, checksum, _ = self.store.add(image_id,
                                                     image_file,
                                                     len(file_contents))

        # Now read it back...
        uri = "file:///%s/%s" % (self.test_dir, image_id)
        loc = get_location_from_uri(uri)
        (image_file, image_size) = self.store.get(loc)

        expected_data = "chunk00000remainder"
        expected_num_chunks = 2
        data = ""
        num_chunks = 0

        for chunk in image_file:
            num_chunks += 1
            data += chunk
        self.assertEqual(expected_data, data)
        self.assertEqual(expected_num_chunks, num_chunks)

    def test_get_non_existing(self):
        """
        Test that trying to retrieve a file that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("file:///%s/non-existing" % self.test_dir)
        self.assertRaises(exception.NotFound,
                          self.store.get,
                          loc)

    def test_add(self):
        """Test that we can add an image via the filesystem backend"""
        ChunkedFile.CHUNKSIZE = 1024
        expected_image_id = str(uuid.uuid4())
        expected_file_size = 5 * units.Ki  # 5K
        expected_file_contents = "*" * expected_file_size
        expected_checksum = hashlib.md5(expected_file_contents).hexdigest()
        expected_location = "file://%s/%s" % (self.test_dir,
                                              expected_image_id)
        image_file = six.StringIO(expected_file_contents)

        location, size, checksum, _ = self.store.add(expected_image_id,
                                                     image_file,
                                                     expected_file_size)

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_file_size, size)
        self.assertEqual(expected_checksum, checksum)

        uri = "file:///%s/%s" % (self.test_dir, expected_image_id)
        loc = get_location_from_uri(uri)
        (new_image_file, new_image_size) = self.store.get(loc)
        new_image_contents = ""
        new_image_file_size = 0

        for chunk in new_image_file:
            new_image_file_size += len(chunk)
            new_image_contents += chunk

        self.assertEqual(expected_file_contents, new_image_contents)
        self.assertEqual(expected_file_size, new_image_file_size)

    def test_add_with_multiple_dirs(self):
        """Test adding multiple filesystem directories."""
        store_map = [self.useFixture(fixtures.TempDir()).path,
                     self.useFixture(fixtures.TempDir()).path]
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs',
                          [store_map[0] + ":100",
                           store_map[1] + ":200"])
        self.store.configure_add()

        """Test that we can add an image via the filesystem backend"""
        ChunkedFile.CHUNKSIZE = 1024
        expected_image_id = str(uuid.uuid4())
        expected_file_size = 5 * units.Ki  # 5K
        expected_file_contents = "*" * expected_file_size
        expected_checksum = hashlib.md5(expected_file_contents).hexdigest()
        expected_location = "file://%s/%s" % (store_map[1],
                                              expected_image_id)
        image_file = six.StringIO(expected_file_contents)

        location, size, checksum, _ = self.store.add(expected_image_id,
                                                     image_file,
                                                     expected_file_size)

        self.assertEqual(expected_location, location)
        self.assertEqual(expected_file_size, size)
        self.assertEqual(expected_checksum, checksum)

        loc = get_location_from_uri(expected_location)
        (new_image_file, new_image_size) = self.store.get(loc)
        new_image_contents = ""
        new_image_file_size = 0

        for chunk in new_image_file:
            new_image_file_size += len(chunk)
            new_image_contents += chunk

        self.assertEqual(expected_file_contents, new_image_contents)
        self.assertEqual(expected_file_size, new_image_file_size)

    def test_add_with_multiple_dirs_storage_full(self):
        """
        Test StorageFull exception is raised if no filesystem directory
        is found that can store an image.
        """
        store_map = [self.useFixture(fixtures.TempDir()).path,
                     self.useFixture(fixtures.TempDir()).path]
        CONF.clear_override('filesystem_store_datadir')
        CONF.set_override('filesystem_store_datadirs',
                          [store_map[0] + ":100",
                           store_map[1] + ":200"])
        self.store.configure_add()

        def fake_get_capacity_info(mount_point):
            return 0

        self.stubs.Set(self.store, '_get_capacity_info',
                       fake_get_capacity_info)
        ChunkedFile.CHUNKSIZE = 1024
        expected_image_id = str(uuid.uuid4())
        expected_file_size = 5 * units.Ki  # 5K
        expected_file_contents = "*" * expected_file_size
        image_file = six.StringIO(expected_file_contents)

        self.assertRaises(exception.StorageFull, self.store.add,
                          expected_image_id, image_file, expected_file_size)

    def test_add_check_metadata_success(self):
        expected_image_id = str(uuid.uuid4())
        in_metadata = {'akey': u'some value', 'list': [u'1', u'2', u'3']}
        jsonfilename = os.path.join(self.test_dir,
                                    "storage_metadata.%s" % expected_image_id)

        self.config(filesystem_store_metadata_file=jsonfilename)
        with open(jsonfilename, 'w') as fptr:
            json.dump(in_metadata, fptr)
        expected_file_size = 10
        expected_file_contents = "*" * expected_file_size
        image_file = six.StringIO(expected_file_contents)

        location, size, checksum, metadata = self.store.add(expected_image_id,
                                                            image_file,
                                                            expected_file_size)

        self.assertEqual(metadata, in_metadata)

    def test_add_check_metadata_bad_data(self):
        expected_image_id = str(uuid.uuid4())
        in_metadata = {'akey': 10}  # only unicode is allowed
        jsonfilename = os.path.join(self.test_dir,
                                    "storage_metadata.%s" % expected_image_id)

        self.config(filesystem_store_metadata_file=jsonfilename)
        with open(jsonfilename, 'w') as fptr:
            json.dump(in_metadata, fptr)
        expected_file_size = 10
        expected_file_contents = "*" * expected_file_size
        image_file = six.StringIO(expected_file_contents)

        location, size, checksum, metadata = self.store.add(expected_image_id,
                                                            image_file,
                                                            expected_file_size)

        self.assertEqual(metadata, {})

    def test_add_check_metadata_bad_nosuch_file(self):
        expected_image_id = str(uuid.uuid4())
        jsonfilename = os.path.join(self.test_dir,
                                    "storage_metadata.%s" % expected_image_id)

        self.config(filesystem_store_metadata_file=jsonfilename)
        expected_file_size = 10
        expected_file_contents = "*" * expected_file_size
        image_file = six.StringIO(expected_file_contents)

        location, size, checksum, metadata = self.store.add(expected_image_id,
                                                            image_file,
                                                            expected_file_size)

        self.assertEqual(metadata, {})

    def test_add_already_existing(self):
        """
        Tests that adding an image with an existing identifier
        raises an appropriate exception
        """
        ChunkedFile.CHUNKSIZE = 1024
        image_id = str(uuid.uuid4())
        file_size = 5 * units.Ki  # 5K
        file_contents = "*" * file_size
        image_file = six.StringIO(file_contents)

        location, size, checksum, _ = self.store.add(image_id,
                                                     image_file,
                                                     file_size)
        image_file = six.StringIO("nevergonnamakeit")
        self.assertRaises(exception.Duplicate,
                          self.store.add,
                          image_id, image_file, 0)

    def _do_test_add_write_failure(self, errno, exception):
        ChunkedFile.CHUNKSIZE = 1024
        image_id = str(uuid.uuid4())
        file_size = 5 * units.Ki  # 5K
        file_contents = "*" * file_size
        path = os.path.join(self.test_dir, image_id)
        image_file = six.StringIO(file_contents)

        m = mox.Mox()
        m.StubOutWithMock(__builtin__, 'open')
        e = IOError()
        e.errno = errno
        open(path, 'wb').AndRaise(e)
        m.ReplayAll()

        try:
            self.assertRaises(exception,
                              self.store.add,
                              image_id, image_file, 0)
            self.assertFalse(os.path.exists(path))
        finally:
            m.VerifyAll()
            m.UnsetStubs()

    def test_add_storage_full(self):
        """
        Tests that adding an image without enough space on disk
        raises an appropriate exception
        """
        self._do_test_add_write_failure(errno.ENOSPC, exception.StorageFull)

    def test_add_file_too_big(self):
        """
        Tests that adding an excessively large image file
        raises an appropriate exception
        """
        self._do_test_add_write_failure(errno.EFBIG, exception.StorageFull)

    def test_add_storage_write_denied(self):
        """
        Tests that adding an image with insufficient filestore permissions
        raises an appropriate exception
        """
        self._do_test_add_write_failure(errno.EACCES,
                                        exception.StorageWriteDenied)

    def test_add_other_failure(self):
        """
        Tests that a non-space-related IOError does not raise a
        StorageFull exception.
        """
        self._do_test_add_write_failure(errno.ENOTDIR, IOError)

    def test_add_cleanup_on_read_failure(self):
        """
        Tests the partial image file is cleaned up after a read
        failure.
        """
        ChunkedFile.CHUNKSIZE = 1024
        image_id = str(uuid.uuid4())
        file_size = 5 * units.Ki  # 5K
        file_contents = "*" * file_size
        path = os.path.join(self.test_dir, image_id)
        image_file = six.StringIO(file_contents)

        def fake_Error(size):
            raise AttributeError()

        self.stubs.Set(image_file, 'read', fake_Error)

        self.assertRaises(AttributeError,
                          self.store.add,
                          image_id, image_file, 0)
        self.assertFalse(os.path.exists(path))

    def test_delete(self):
        """
        Test we can delete an existing image in the filesystem store
        """
        # First add an image
        image_id = str(uuid.uuid4())
        file_size = 5 * units.Ki  # 5K
        file_contents = "*" * file_size
        image_file = six.StringIO(file_contents)

        location, size, checksum, _ = self.store.add(image_id,
                                                     image_file,
                                                     file_size)

        # Now check that we can delete it
        uri = "file:///%s/%s" % (self.test_dir, image_id)
        loc = get_location_from_uri(uri)
        self.store.delete(loc)

        self.assertRaises(exception.NotFound, self.store.get, loc)

    def test_delete_non_existing(self):
        """
        Test that trying to delete a file that doesn't exist
        raises an error
        """
        loc = get_location_from_uri("file:///tmp/glance-tests/non-existing")
        self.assertRaises(exception.NotFound,
                          self.store.delete,
                          loc)
