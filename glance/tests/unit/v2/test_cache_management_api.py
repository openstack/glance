# Copyright 2021 Red Hat Inc.
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
import threading
import time
from unittest import mock

from glance.api.v2 import cached_images
from glance import notifier
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'


class FakeImage(object):
    def __init__(self, id=None, status='active', container_format='ami',
                 disk_format='ami', locations=None):
        self.id = id or UUID1
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


class TestCacheManageAPI(test_utils.BaseTestCase):

    def setUp(self):
        super(TestCacheManageAPI, self).setUp()
        self.req = unit_test_utils.get_fake_request()

    def _main_test_helper(self, argv, status='active', image_mock=True):
        with mock.patch.object(notifier.ImageRepoProxy,
                               'get') as mock_get:
            image = FakeImage(status=status)
            mock_get.return_value = image
            with mock.patch.object(cached_images.CacheController,
                                   '_enforce') as e:
                with mock.patch('glance.image_cache.ImageCache') as ic:
                    cc = cached_images.CacheController()
                    cc.cache = ic
                    c_calls = []
                    c_calls += argv[0].split(',')
                    for call in c_calls:
                        mock.patch.object(ic, call)
                    test_call = getattr(cc, argv[1])
                    new_policy = argv[2]
                    args = []
                    if len(argv) == 4:
                        args = argv[3:]
                    test_call(self.req, *args)
                    if image_mock:
                        e.assert_called_once_with(self.req, image=image,
                                                  new_policy=new_policy)
                    else:
                        e.assert_called_once_with(self.req,
                                                  new_policy=new_policy)
                    mcs = []
                    for method in ic.method_calls:
                        mcs.append(str(method))
                    for call in c_calls:
                        if args == []:
                            args.append("")
                        elif args[0] and not args[0].endswith("'"):
                            args[0] = "'" + args[0] + "'"
                        self.assertIn("call." + call + "(" + args[0] + ")",
                                      mcs)
                    self.assertEqual(len(c_calls), len(mcs))

    def test_delete_cache_entry(self):
        self._main_test_helper(['delete_cached_image,delete_queued_image',
                                'delete_cache_entry',
                                'cache_delete',
                                UUID1])

    def test_clear_cache(self):
        self._main_test_helper(
            ['delete_all_cached_images,delete_all_queued_images',
             'clear_cache',
             'cache_delete'], image_mock=False)

    def test_get_cache_state(self):
        self._main_test_helper(['get_cached_images,get_queued_images',
                                'get_cache_state',
                                'cache_list'], image_mock=False)

    def test_clean_cache(self):
        self._main_test_helper(['clean',
                                'clean_cache',
                                'cache_clean'], image_mock=False)

    def test_prune_cache(self):
        with mock.patch.object(cached_images.CacheController,
                               '_enforce') as e:
            with mock.patch('glance.image_cache.ImageCache') as ic:
                cc = cached_images.CacheController()
                cc.cache = ic
                ic.prune.return_value = (5, 1048576)  # (files, bytes)
                cc.prune_cache(self.req)
                e.assert_called_once_with(self.req, new_policy='cache_prune')
                ic.prune.assert_called_once()

    @mock.patch.object(cached_images, 'WORKER')
    def test_queue_image_from_api(self, mock_worker):
        self._main_test_helper(['queue_image',
                                'queue_image_from_api',
                                'cache_image',
                                UUID1])
        mock_worker.submit.assert_called_once_with(UUID1)

    def test_clean_cache_concurrent_execution(self):
        """Test that concurrent clean_cache calls are serialized."""
        with mock.patch.object(cached_images.CacheController,
                               '_enforce'):
            with mock.patch('glance.image_cache.ImageCache') as ic:
                cc = cached_images.CacheController()
                cc.cache = ic

                # Track execution order to verify serialization
                execution_order = []
                execution_lock = threading.Lock()

                def track_clean():
                    with execution_lock:
                        execution_order.append('start')
                    time.sleep(0.05)  # Simulate work
                    with execution_lock:
                        execution_order.append('end')

                # Mock clean to track execution
                ic.clean.side_effect = track_clean

                # Start two threads calling clean_cache concurrently
                threads = []
                for i in range(2):
                    t = threading.Thread(target=cc.clean_cache,
                                         args=(self.req,))
                    threads.append(t)
                    t.start()

                # Wait for both threads to complete (with timeout)
                for t in threads:
                    t.join(timeout=5.0)
                    self.assertFalse(t.is_alive(), "Thread did not complete")

                # Verify clean was called exactly twice
                self.assertEqual(ic.clean.call_count, 2)
                # Verify both calls completed (start and end for each)
                self.assertEqual(len(execution_order), 4)
                # Verify calls were serialized (not interleaved)
                # Pattern should be: start, end, start, end
                # (not start, start, end, end)
                self.assertEqual(execution_order[0], 'start')
                self.assertEqual(execution_order[1], 'end')
                self.assertEqual(execution_order[2], 'start')
                self.assertEqual(execution_order[3], 'end')

    def test_prune_cache_concurrent_execution(self):
        """Test that concurrent prune_cache calls are serialized."""
        with mock.patch.object(cached_images.CacheController,
                               '_enforce'):
            with mock.patch('glance.image_cache.ImageCache') as ic:
                cc = cached_images.CacheController()
                cc.cache = ic

                # Track execution order to verify serialization
                execution_order = []
                execution_lock = threading.Lock()

                def track_prune():
                    with execution_lock:
                        execution_order.append('start')
                    time.sleep(0.05)  # Simulate work
                    with execution_lock:
                        execution_order.append('end')
                    return (5, 1048576)

                # Mock prune to track execution
                ic.prune.side_effect = track_prune

                # Start two threads calling prune_cache concurrently
                threads = []
                for i in range(2):
                    t = threading.Thread(target=cc.prune_cache,
                                         args=(self.req,))
                    threads.append(t)
                    t.start()

                # Wait for both threads to complete (with timeout)
                for t in threads:
                    t.join(timeout=5.0)
                    self.assertFalse(t.is_alive(), "Thread did not complete")

                # Verify prune was called exactly twice
                self.assertEqual(ic.prune.call_count, 2)
                # Verify both calls completed (start and end for each)
                self.assertEqual(len(execution_order), 4)
                # Verify calls were serialized (not interleaved)
                # Pattern should be: start, end, start, end
                # (not start, start, end, end)
                self.assertEqual(execution_order[0], 'start')
                self.assertEqual(execution_order[1], 'end')
                self.assertEqual(execution_order[2], 'start')
                self.assertEqual(execution_order[3], 'end')

    def test_init_no_config(self):
        # Make sure the worker was reset to uninitialized
        self.assertIsNone(cached_images.WORKER)
        self.config(image_cache_dir=None)
        cached_images.CacheController()

        # Make sure it is still None because image_cache_dir was not
        # set
        self.assertIsNone(cached_images.WORKER)

    def test_init_with_config(self):
        # Make sure the worker was reset to uninitialized
        self.assertIsNone(cached_images.WORKER)
        self.config(image_cache_dir='/tmp')
        cached_images.CacheController()

        # Make sure we initialized it because config told us to
        self.assertIsNotNone(cached_images.WORKER)
        self.assertTrue(cached_images.WORKER.is_alive())
        cached_images.WORKER.terminate()


class TestCacheWorker(test_utils.BaseTestCase):
    @mock.patch('glance.image_cache.prefetcher.Prefetcher')
    def test_worker_lifecycle(self, mock_pf):
        worker = cached_images.CacheWorker()
        self.assertFalse(worker.is_alive())
        worker.start()
        self.assertTrue(worker.is_alive())
        worker.submit('123')
        worker.submit('456')
        self.assertTrue(worker.is_alive())
        worker.terminate()
        self.assertFalse(worker.is_alive())
        mock_pf.return_value.fetch_image_into_cache.assert_has_calls([
            mock.call('123'), mock.call('456')])
