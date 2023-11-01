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

from contextlib import contextmanager
import datetime
import errno
import io
import os
import tempfile
import time
from unittest import mock

import fixtures
import glance_store as store
from oslo_config import cfg
from oslo_utils import fileutils
from oslo_utils import secretutils
from oslo_utils import units

from glance import async_
from glance.common import exception
from glance import context
from glance import gateway as glance_gateway
from glance import image_cache
from glance.image_cache import prefetcher
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils as test_utils
from glance.tests.utils import skip_if_disabled
from glance.tests.utils import xattr_writes_supported

FIXTURE_LENGTH = 1024
FIXTURE_DATA = b'*' * FIXTURE_LENGTH
CONF = cfg.CONF


class ImageCacheTestCase(object):

    def _setup_fixture_file(self):
        FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)

        self.assertFalse(self.cache.is_cached(1))

        self.assertTrue(self.cache.cache_image_file(1, FIXTURE_FILE))

        self.assertTrue(self.cache.is_cached(1))

    @skip_if_disabled
    def test_is_cached(self):
        """Verify is_cached(1) returns 0, then add something to the cache
        and verify is_cached(1) returns 1.
        """
        self._setup_fixture_file()

    @skip_if_disabled
    def test_read(self):
        """Verify is_cached(1) returns 0, then add something to the cache
        and verify after a subsequent read from the cache that
        is_cached(1) returns 1.
        """
        self._setup_fixture_file()

        buff = io.BytesIO()
        with self.cache.open_for_read(1) as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.assertEqual(FIXTURE_DATA, buff.getvalue())

    @skip_if_disabled
    def test_open_for_read(self):
        """Test convenience wrapper for opening a cache file via
        its image identifier.
        """
        self._setup_fixture_file()

        buff = io.BytesIO()
        with self.cache.open_for_read(1) as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.assertEqual(FIXTURE_DATA, buff.getvalue())

    @skip_if_disabled
    def test_get_image_size(self):
        """Test convenience wrapper for querying cache file size via
        its image identifier.
        """
        self._setup_fixture_file()

        size = self.cache.get_image_size(1)

        self.assertEqual(FIXTURE_LENGTH, size)

    @skip_if_disabled
    def test_delete(self):
        """Test delete method that removes an image from the cache."""
        self._setup_fixture_file()

        self.cache.delete_cached_image(1)

        self.assertFalse(self.cache.is_cached(1))

    @skip_if_disabled
    def test_delete_all(self):
        """Test delete method that removes an image from the cache."""
        for image_id in (1, 2):
            self.assertFalse(self.cache.is_cached(image_id))

        for image_id in (1, 2):
            FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)
            self.assertTrue(self.cache.cache_image_file(image_id,
                                                        FIXTURE_FILE))

        for image_id in (1, 2):
            self.assertTrue(self.cache.is_cached(image_id))

        self.cache.delete_all_cached_images()

        for image_id in (1, 2):
            self.assertFalse(self.cache.is_cached(image_id))

    def _test_clean_invalid_path(self, failure=False):
        invalid_file_path = os.path.join(self.cache_dir, 'invalid', '1')
        invalid_file = open(invalid_file_path, 'wb')
        invalid_file.write(FIXTURE_DATA)
        invalid_file.close()

        self.assertTrue(os.path.exists(invalid_file_path))

        self.delay_inaccurate_clock()
        if failure:
            with mock.patch.object(
                    fileutils, 'delete_if_exists') as mock_delete:
                mock_delete.side_effect = OSError(errno.ENOENT, '')
                try:
                    self.cache.clean()
                except OSError:
                    self.assertTrue(os.path.exists(invalid_file_path))
        else:
            self.cache.clean()
            self.assertFalse(os.path.exists(invalid_file_path))

    @skip_if_disabled
    def test_clean_invalid_path(self):
        """Test the clean method removes expected image from invalid path."""
        self._test_clean_invalid_path()

    @skip_if_disabled
    def test_clean_stalled(self):
        """Test the clean method removes expected images."""
        incomplete_file_path = os.path.join(self.cache_dir, 'incomplete', '1')
        incomplete_file = open(incomplete_file_path, 'wb')
        incomplete_file.write(FIXTURE_DATA)
        incomplete_file.close()

        self.assertTrue(os.path.exists(incomplete_file_path))

        self.delay_inaccurate_clock()
        self.cache.clean(stall_time=0)

        self.assertFalse(os.path.exists(incomplete_file_path))

    def _test_clean_stall_time(self, stall_time=None, days=2,
                               stall_failed=False):
        """
        Test the clean method removes the stalled images as expected
        """
        incomplete_file_path_1 = os.path.join(self.cache_dir,
                                              'incomplete', '1')
        incomplete_file_path_2 = os.path.join(self.cache_dir,
                                              'incomplete', '2')
        for f in (incomplete_file_path_1, incomplete_file_path_2):
            incomplete_file = open(f, 'wb')
            incomplete_file.write(FIXTURE_DATA)
            incomplete_file.close()

        mtime = os.path.getmtime(incomplete_file_path_1)
        pastday = (datetime.datetime.fromtimestamp(mtime) -
                   datetime.timedelta(days=days))
        atime = int(time.mktime(pastday.timetuple()))
        mtime = atime
        os.utime(incomplete_file_path_1, (atime, mtime))

        self.assertTrue(os.path.exists(incomplete_file_path_1))
        self.assertTrue(os.path.exists(incomplete_file_path_2))

        # If stall_time is None then it will wait for default time
        # of `image_cache_stall_time` which is 24 hours
        if stall_failed:
            with mock.patch.object(
                    fileutils, 'delete_if_exists') as mock_delete:
                mock_delete.side_effect = OSError(errno.ENOENT, '')
                self.cache.clean(stall_time=stall_time)
                self.assertTrue(os.path.exists(incomplete_file_path_1))
        else:
            self.cache.clean(stall_time=stall_time)
            self.assertFalse(os.path.exists(incomplete_file_path_1))

        self.assertTrue(os.path.exists(incomplete_file_path_2))

    @skip_if_disabled
    def test_clean_stalled_none_stall_time(self):
        self._test_clean_stall_time()

    @skip_if_disabled
    def test_clean_stalled_nonzero_stall_time(self):
        """Test the clean method removes expected images."""
        self._test_clean_stall_time(stall_time=3600, days=1)

    @skip_if_disabled
    def test_prune(self):
        """
        Test that pruning the cache works as expected...
        """
        self.assertEqual(0, self.cache.get_cache_size())

        # Add a bunch of images to the cache. The max cache size for the cache
        # is set to 5KB and each image is 1K. We use 11 images in this test.
        # The first 10 are added to and retrieved from cache in the same order.
        # Then, the 11th image is added to cache but not retrieved before we
        # prune. We should see only 5 images left after pruning, and the
        # images that are least recently accessed should be the ones pruned...
        for x in range(10):
            FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)
            self.assertTrue(self.cache.cache_image_file(x, FIXTURE_FILE))

        self.assertEqual(10 * units.Ki, self.cache.get_cache_size())

        # OK, hit the images that are now cached...
        for x in range(10):
            buff = io.BytesIO()
            with self.cache.open_for_read(x) as cache_file:
                for chunk in cache_file:
                    buff.write(chunk)

        # Add a new image to cache.
        # This is specifically to test the bug: 1438564
        FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)
        self.assertTrue(self.cache.cache_image_file(99, FIXTURE_FILE))

        self.cache.prune()

        self.assertEqual(5 * units.Ki, self.cache.get_cache_size())

        # Ensure images 0, 1, 2, 3, 4 & 5 are not cached anymore
        for x in range(0, 6):
            self.assertFalse(self.cache.is_cached(x),
                             "Image %s was cached!" % x)

        # Ensure images 6, 7, 8 and 9 are still cached
        for x in range(6, 10):
            self.assertTrue(self.cache.is_cached(x),
                            "Image %s was not cached!" % x)

        # Ensure the newly added image, 99, is still cached
        self.assertTrue(self.cache.is_cached(99), "Image 99 was not cached!")

    @skip_if_disabled
    def test_prune_to_zero(self):
        """Test that an image_cache_max_size of 0 doesn't kill the pruner

        This is a test specifically for LP #1039854
        """
        self.assertEqual(0, self.cache.get_cache_size())

        FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)
        self.assertTrue(self.cache.cache_image_file('xxx', FIXTURE_FILE))

        self.assertEqual(1024, self.cache.get_cache_size())

        # OK, hit the image that is now cached...
        buff = io.BytesIO()
        with self.cache.open_for_read('xxx') as cache_file:
            for chunk in cache_file:
                buff.write(chunk)

        self.config(image_cache_max_size=0)
        self.cache.prune()

        self.assertEqual(0, self.cache.get_cache_size())
        self.assertFalse(self.cache.is_cached('xxx'))

    @skip_if_disabled
    def test_queue(self):
        """
        Test that queueing works properly
        """

        self.assertFalse(self.cache.is_cached(1))
        self.assertFalse(self.cache.is_queued(1))

        FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)

        self.assertTrue(self.cache.queue_image(1))

        self.assertTrue(self.cache.is_queued(1))
        self.assertFalse(self.cache.is_cached(1))

        # Should not return True if the image is already
        # queued for caching...
        self.assertFalse(self.cache.queue_image(1))

        self.assertFalse(self.cache.is_cached(1))

        # Test that we return False if we try to queue
        # an image that has already been cached

        self.assertTrue(self.cache.cache_image_file(1, FIXTURE_FILE))

        self.assertFalse(self.cache.is_queued(1))
        self.assertTrue(self.cache.is_cached(1))

        self.assertFalse(self.cache.queue_image(1))

        self.cache.delete_cached_image(1)

        # Test that we return false if image is being cached
        incomplete_file_path = os.path.join(self.cache_dir, 'incomplete', '1')
        incomplete_file = open(incomplete_file_path, 'wb')
        incomplete_file.write(FIXTURE_DATA)
        incomplete_file.close()

        self.assertFalse(self.cache.is_queued(1))
        self.assertFalse(self.cache.is_cached(1))
        self.assertTrue(self.cache.driver.is_being_cached(1))

        self.assertFalse(self.cache.queue_image(1))
        self.cache.clean(stall_time=0)

        for x in range(3):
            self.assertTrue(self.cache.queue_image(x))

        self.assertEqual(['0', '1', '2'],
                         self.cache.get_queued_images())

    @skip_if_disabled
    def test_open_for_write_good(self):
        """
        Test to see if open_for_write works in normal case
        """

        # test a good case
        image_id = '1'
        self.assertFalse(self.cache.is_cached(image_id))
        with self.cache.driver.open_for_write(image_id) as cache_file:
            cache_file.write(b'a')
        self.assertTrue(self.cache.is_cached(image_id),
                        "Image %s was NOT cached!" % image_id)
        # make sure it has tidied up
        incomplete_file_path = os.path.join(self.cache_dir,
                                            'incomplete', image_id)
        invalid_file_path = os.path.join(self.cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertFalse(os.path.exists(invalid_file_path))

    @skip_if_disabled
    def test_open_for_write_with_exception(self):
        """
        Test to see if open_for_write works in a failure case for each driver
        This case is where an exception is raised while the file is being
        written. The image is partially filled in cache and filling won't
        resume so verify the image is moved to invalid/ directory
        """
        # test a case where an exception is raised while the file is open
        image_id = '1'
        self.assertFalse(self.cache.is_cached(image_id))
        try:
            with self.cache.driver.open_for_write(image_id):
                raise IOError
        except Exception as e:
            self.assertIsInstance(e, IOError)
        self.assertFalse(self.cache.is_cached(image_id),
                         "Image %s was cached!" % image_id)
        # make sure it has tidied up
        incomplete_file_path = os.path.join(self.cache_dir,
                                            'incomplete', image_id)
        invalid_file_path = os.path.join(self.cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertTrue(os.path.exists(invalid_file_path))

    @skip_if_disabled
    def test_caching_iterator(self):
        """
        Test to see if the caching iterator interacts properly with the driver
        When the iterator completes going through the data the driver should
        have closed the image and placed it correctly
        """
        # test a case where an exception NOT raised while the file is open,
        # and a consuming iterator completes
        def consume(image_id):
            data = [b'a', b'b', b'c', b'd', b'e', b'f']
            checksum = None
            caching_iter = self.cache.get_caching_iter(image_id, checksum,
                                                       iter(data))
            self.assertEqual(data, list(caching_iter))

        image_id = '1'
        self.assertFalse(self.cache.is_cached(image_id))
        consume(image_id)
        self.assertTrue(self.cache.is_cached(image_id),
                        "Image %s was NOT cached!" % image_id)
        # make sure it has tidied up
        incomplete_file_path = os.path.join(self.cache_dir,
                                            'incomplete', image_id)
        invalid_file_path = os.path.join(self.cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertFalse(os.path.exists(invalid_file_path))

    @skip_if_disabled
    def test_caching_iterator_handles_backend_failure(self):
        """
        Test that when the backend fails, caching_iter does not continue trying
        to consume data, and rolls back the cache.
        """
        def faulty_backend():
            data = [b'a', b'b', b'c', b'Fail', b'd', b'e', b'f']
            for d in data:
                if d == b'Fail':
                    raise exception.GlanceException('Backend failure')
                yield d

        def consume(image_id):
            caching_iter = self.cache.get_caching_iter(image_id, None,
                                                       faulty_backend())
            # exercise the caching_iter
            list(caching_iter)

        image_id = '1'
        self.assertRaises(exception.GlanceException, consume, image_id)
        # make sure bad image was not cached
        self.assertFalse(self.cache.is_cached(image_id))

    @skip_if_disabled
    def test_caching_iterator_falloffend(self):
        """
        Test to see if the caching iterator interacts properly with the driver
        in a case where the iterator is only partially consumed. In this case
        the image is only partially filled in cache and filling won't resume.
        When the iterator goes out of scope the driver should have closed the
        image and moved it from incomplete/ to invalid/
        """
        # test a case where a consuming iterator just stops.
        def falloffend(image_id):
            data = [b'a', b'b', b'c', b'd', b'e', b'f']
            checksum = None
            caching_iter = self.cache.get_caching_iter(image_id, checksum,
                                                       iter(data))
            self.assertEqual(b'a', next(caching_iter))

        image_id = '1'
        self.assertFalse(self.cache.is_cached(image_id))
        falloffend(image_id)
        self.assertFalse(self.cache.is_cached(image_id),
                         "Image %s was cached!" % image_id)
        # make sure it has tidied up
        incomplete_file_path = os.path.join(self.cache_dir,
                                            'incomplete', image_id)
        invalid_file_path = os.path.join(self.cache_dir, 'invalid', image_id)
        self.assertFalse(os.path.exists(incomplete_file_path))
        self.assertTrue(os.path.exists(invalid_file_path))

    @skip_if_disabled
    def test_gate_caching_iter_good_checksum(self):
        image = b"12345678990abcdefghijklmnop"
        image_id = 123

        md5 = secretutils.md5(usedforsecurity=False)
        md5.update(image)
        checksum = md5.hexdigest()

        with mock.patch('glance.db.get_api') as mock_get_db:
            db = unit_test_utils.FakeDB(initialize=False)
            mock_get_db.return_value = db
            cache = image_cache.ImageCache()

        img_iter = cache.get_caching_iter(image_id, checksum, [image])
        for chunk in img_iter:
            pass
        # checksum is valid, fake image should be cached:
        self.assertTrue(cache.is_cached(image_id))

    @skip_if_disabled
    def test_gate_caching_iter_bad_checksum(self):
        image = b"12345678990abcdefghijklmnop"
        image_id = 123
        checksum = "foobar"  # bad.

        with mock.patch('glance.db.get_api') as mock_get_db:
            db = unit_test_utils.FakeDB(initialize=False)
            mock_get_db.return_value = db
            cache = image_cache.ImageCache()

        img_iter = cache.get_caching_iter(image_id, checksum, [image])

        def reader():
            for chunk in img_iter:
                pass
        self.assertRaises(exception.GlanceException, reader)
        # checksum is invalid, caching will fail:
        self.assertFalse(cache.is_cached(image_id))


class TestImageCacheXattr(test_utils.BaseTestCase,
                          ImageCacheTestCase):

    """Tests image caching when xattr is used in cache"""

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-xattr installed and xattr support on the
        filesystem)
        """
        super(TestImageCacheXattr, self).setUp()

        if getattr(self, 'disable', False):
            return

        self.cache_dir = self.useFixture(fixtures.TempDir()).path

        if not getattr(self, 'inited', False):
            try:
                import xattr  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.config(image_cache_dir=self.cache_dir,
                    image_cache_driver='xattr',
                    image_cache_max_size=5 * units.Ki)
        self.cache = image_cache.ImageCache()

        if not xattr_writes_supported(self.cache_dir):
            self.inited = True
            self.disabled = True
            self.disabled_message = ("filesystem does not support xattr")
            return


class TestImageCacheCentralizedDb(test_utils.BaseTestCase,
                                  ImageCacheTestCase):

    """Tests image caching when Centralized DB is used in cache"""

    def setUp(self):
        super(TestImageCacheCentralizedDb, self).setUp()

        self.inited = True
        self.disabled = False
        self.cache_dir = self.useFixture(fixtures.TempDir()).path
        self.config(image_cache_dir=self.cache_dir,
                    image_cache_driver='centralized_db',
                    image_cache_max_size=5 * units.Ki,
                    worker_self_reference_url='http://workerx')

        with mock.patch('glance.db.get_api') as mock_get_db:
            self.db = unit_test_utils.FakeDB(initialize=False)
            mock_get_db.return_value = self.db
            self.cache = image_cache.ImageCache()

    def test_node_reference_create_duplicate(self):
        with mock.patch('glance.db.get_api') as mock_get_db:
            self.db = unit_test_utils.FakeDB(initialize=False)
            mock_get_db.return_value = self.db
            with mock.patch.object(
                    self.db, 'node_reference_create') as mock_node_create:
                mock_node_create.side_effect = exception.Duplicate
                with mock.patch.object(
                        image_cache.drivers.centralized_db, 'LOG') as mock_log:
                    image_cache.ImageCache()
                    expected_calls = [
                        mock.call('Node reference is already recorded, '
                                  'ignoring it')
                    ]
                    mock_log.debug.assert_has_calls(expected_calls)

    def test_get_least_recently_accessed_os_error(self):
        self.assertEqual(0, self.cache.get_cache_size())
        for x in range(10):
            FIXTURE_FILE = io.BytesIO(FIXTURE_DATA)
            self.assertTrue(self.cache.cache_image_file(x, FIXTURE_FILE))

        self.assertEqual(10 * units.Ki, self.cache.get_cache_size())

        with mock.patch.object(os, 'stat') as mock_stat:
            mock_stat.side_effect = OSError
            image_id, size = self.cache.driver.get_least_recently_accessed()
            self.assertEqual(0, size)

    @skip_if_disabled
    def test_clean_stalled_fails(self):
        """Test the clean method fails to delete file, ignores the failure"""
        self._test_clean_stall_time(stall_time=3600, days=1,
                                    stall_failed=True)

    @skip_if_disabled
    def test_clean_invalid_path_fails(self):
        """Test the clean method fails to remove image from invalid path."""
        self._test_clean_invalid_path(failure=True)


class TestImageCacheSqlite(test_utils.BaseTestCase,
                           ImageCacheTestCase):

    """Tests image caching when SQLite is used in cache"""

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-sqlite3 installed)
        """
        super(TestImageCacheSqlite, self).setUp()

        if getattr(self, 'disable', False):
            return

        if not getattr(self, 'inited', False):
            try:
                import sqlite3  # noqa
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-sqlite3 not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_dir = self.useFixture(fixtures.TempDir()).path
        self.config(image_cache_dir=self.cache_dir,
                    image_cache_driver='sqlite',
                    image_cache_max_size=5 * units.Ki)
        self.cache = image_cache.ImageCache()

    @mock.patch('glance.db.get_api')
    def _test_prefetcher(self, mock_get_db):
        self.config(enabled_backends={'cheap': 'file'})
        store.register_store_opts(CONF)
        self.config(filesystem_store_datadir='/tmp', group='cheap')
        store.create_multi_stores(CONF)

        tempf = tempfile.NamedTemporaryFile()
        tempf.write(b'foo')

        db = unit_test_utils.FakeDB(initialize=False)
        mock_get_db.return_value = db

        ctx = context.RequestContext(is_admin=True, roles=['admin'])
        gateway = glance_gateway.Gateway()
        image_factory = gateway.get_image_factory(ctx)
        image_repo = gateway.get_repo(ctx)
        fetcher = prefetcher.Prefetcher()

        # Create an image with no values set and queue it
        image = image_factory.new_image()
        image_repo.add(image)
        fetcher.cache.queue_image(image.image_id)

        # Image is not active, so it should fail to cache, but remain queued
        self.assertFalse(fetcher.run())
        self.assertFalse(fetcher.cache.is_cached(image.image_id))
        self.assertTrue(fetcher.cache.is_queued(image.image_id))

        # Set the disk/container format and give it a location
        image.disk_format = 'raw'
        image.container_format = 'bare'
        image.status = 'active'
        loc = {'url': 'file://%s' % tempf.name, 'metadata': {'store': 'cheap'}}
        with mock.patch('glance.location._check_image_location'):
            # FIXME(danms): Why do I have to do this?
            image.locations = [loc]
        image_repo.save(image)

        # Image is now active and has a location, so it should cache
        self.assertTrue(fetcher.run())
        self.assertTrue(fetcher.cache.is_cached(image.image_id))
        self.assertFalse(fetcher.cache.is_queued(image.image_id))

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_prefetcher_greenthread(self):
        async_.set_threadpool_model('eventlet')
        self._test_prefetcher()

    @mock.patch('glance.async_._THREADPOOL_MODEL', new=None)
    def test_prefetcher_native(self):
        async_.set_threadpool_model('native')
        self._test_prefetcher()


class TestImageCacheNoDep(test_utils.BaseTestCase):

    def setUp(self):
        super(TestImageCacheNoDep, self).setUp()

        self.driver = None

        def init_driver(self2):
            self2.driver = self.driver

        self.mock_object(image_cache.ImageCache, 'init_driver', init_driver)

    def test_get_caching_iter_when_write_fails(self):

        class FailingFile(object):

            def write(self, data):
                if data == "Fail":
                    raise IOError

        class FailingFileDriver(object):

            def is_cacheable(self, *args, **kwargs):
                return True

            @contextmanager
            def open_for_write(self, *args, **kwargs):
                yield FailingFile()

        self.driver = FailingFileDriver()
        cache = image_cache.ImageCache()
        data = [b'a', b'b', b'c', b'Fail', b'd', b'e', b'f']

        caching_iter = cache.get_caching_iter('dummy_id', None, iter(data))
        self.assertEqual(data, list(caching_iter))

    def test_get_caching_iter_when_open_fails(self):

        class OpenFailingDriver(object):

            def is_cacheable(self, *args, **kwargs):
                return True

            @contextmanager
            def open_for_write(self, *args, **kwargs):
                raise IOError

        self.driver = OpenFailingDriver()
        cache = image_cache.ImageCache()
        data = [b'a', b'b', b'c', b'd', b'e', b'f']

        caching_iter = cache.get_caching_iter('dummy_id', None, iter(data))
        self.assertEqual(data, list(caching_iter))


class TestImagePrefetcher(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImagePrefetcher, self).setUp()
        self.cache_dir = self.useFixture(fixtures.TempDir()).path
        self.config(image_cache_dir=self.cache_dir,
                    image_cache_driver='xattr',
                    image_cache_max_size=5 * units.Ki)
        self.prefetcher = prefetcher.Prefetcher()

    def test_fetch_image_into_cache_without_auth(self):
        with mock.patch.object(self.prefetcher.gateway,
                               'get_repo') as mock_get:
            self.prefetcher.fetch_image_into_cache('fake-image-id')
            mock_get.assert_called_once_with(mock.ANY)
