# Copyright 2020 Red Hat, Inc.
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

import datetime
from testtools import content as ttc
import time
from unittest import mock
import uuid

from oslo_log import log as logging
from oslo_utils import fixture as time_fixture
from oslo_utils import units

from glance.tests import functional
from glance.tests import utils as test_utils


LOG = logging.getLogger(__name__)


class TestImageImportLocking(functional.SynchronousAPIBase):
    def _get_image_import_task(self, image_id, task_id=None):
        if task_id is None:
            image = self.api_get('/v2/images/%s' % image_id).json
            task_id = image['os_glance_import_task']

        return self.api_get('/v2/tasks/%s' % task_id).json

    def _test_import_copy(self, warp_time=False):
        self.start_server()
        state = {'want_run': True}

        # Create and import an image with no pipeline stall
        image_id = self._create_and_import(stores=['store1'])

        # Set up a fake data pipeline that will stall until we are ready
        # to unblock it
        def slow_fake_set_data(data_iter, size=None, backend=None,
                               set_active=True):
            me = str(uuid.uuid4())
            while state['want_run'] == True:
                LOG.info('fake_set_data running %s', me)
                state['running'] = True
                time.sleep(0.1)
            LOG.info('fake_set_data ended %s', me)

        # Constrain oslo timeutils time so we can manipulate it
        tf = time_fixture.TimeFixture()
        self.useFixture(tf)

        # Turn on the delayed data pipeline and start a copy-image
        # import which will hang out for a while
        with mock.patch('glance.location.ImageProxy.set_data') as mock_sd:
            mock_sd.side_effect = slow_fake_set_data

            resp = self._import_copy(image_id, ['store2'])
            self.addDetail('First import response',
                           ttc.text_content(str(resp)))
            self.assertEqual(202, resp.status_code)

            # Wait to make sure the data stream gets started
            for i in range(0, 10):
                if 'running' in state:
                    break
                time.sleep(0.1)

        # Make sure the first import got to the point where the
        # hanging loop will hold it in processing state
        self.assertTrue(state.get('running', False),
                        'slow_fake_set_data() never ran')

        # Make sure the task is available and in the right state
        first_import_task = self._get_image_import_task(image_id)
        self.assertEqual('processing', first_import_task['status'])

        # If we're warping time, then advance the clock by two hours
        if warp_time:
            tf.advance_time_delta(datetime.timedelta(hours=2))

        # Try a second copy-image import. If we are warping time,
        # expect the lock to be busted. If not, then we should get
        # a 409 Conflict. We should make sure to wait until it gets started
        # before looking for the task id.
        with mock.patch('glance.location.ImageProxy.set_data') as mock_sd:
            mock_sd.side_effect = slow_fake_set_data
            resp = self._import_copy(image_id, ['store3'])

            # Wait to make sure the data stream gets started
            for i in range(0, 10):
                if 'running' in state:
                    break
                time.sleep(0.1)

        self.addDetail('Second import response',
                       ttc.text_content(str(resp)))
        if warp_time:
            self.assertEqual(202, resp.status_code)
        else:
            self.assertEqual(409, resp.status_code)

        self.addDetail('First task', ttc.text_content(str(first_import_task)))

        # Grab the current import task for our image, and also
        # refresh our first task object
        second_import_task = self._get_image_import_task(image_id)
        first_import_task = self._get_image_import_task(
            image_id, first_import_task['id'])

        if warp_time:
            # If we warped time and busted the lock, then we expect the
            # current task to be different than the original task
            self.assertNotEqual(first_import_task['id'],
                                second_import_task['id'])
            # The original task should be failed with the expected message
            self.assertEqual('failure', first_import_task['status'])
            self.assertEqual('Expired lock preempted',
                             first_import_task['message'])
            # The new task should be off and running
            self.assertEqual('processing', second_import_task['status'])
        else:
            # We didn't bust the lock, so we didn't start another
            # task, so confirm it hasn't changed
            self.assertEqual(first_import_task['id'],
                             second_import_task['id'])

        return image_id, state

    def test_import_copy_locked(self):
        self._test_import_copy(warp_time=False)

    def test_import_copy_bust_lock(self):
        image_id, state = self._test_import_copy(warp_time=True)

        # After the import has busted the lock, wait for our
        # new import to start. We used a different store than
        # the stalled task so we can tell the difference.
        for i in range(0, 10):
            image = self.api_get('/v2/images/%s' % image_id).json
            if image['stores'] == 'store1,store3':
                break
            time.sleep(0.1)

        # After completion, we expect store1 (original) and store3 (new)
        # and that the other task is still stuck importing
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('store1,store3', image['stores'])
        self.assertEqual('', image['os_glance_failed_import'])

        # Free up the stalled task and give eventlet time to let it
        # play out the rest of the task
        state['want_run'] = False
        for i in range(0, 10):
            image = self.api_get('/v2/images/%s' % image_id).json
            time.sleep(0.1)

        # After that, we expect everything to be cleaned up and in the
        # terminal state that we expect.
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('', image.get('os_glance_import_task', ''))
        self.assertEqual('', image['os_glance_importing_to_stores'])
        self.assertEqual('', image['os_glance_failed_import'])
        self.assertEqual('store1,store3', image['stores'])

    @mock.patch('oslo_utils.timeutils.StopWatch.expired', new=lambda x: True)
    def test_import_task_status(self):
        self.start_server()

        # Generate 3 MiB of data for the image, enough to get a few
        # status messages
        limit = 3 * units.Mi
        image_id = self._create_and_stage(data_iter=test_utils.FakeData(limit))

        # This utility function will grab the current task status at
        # any time and stash it into a list of statuses if it finds a
        # new one
        statuses = []

        def grab_task_status():
            image = self.api_get('/v2/images/%s' % image_id).json
            task_id = image['os_glance_import_task']
            task = self.api_get('/v2/tasks/%s' % task_id).json
            msg = task['message']
            if msg not in statuses:
                statuses.append(msg)

        # This is the only real thing we have mocked out, which is the
        # "upload this to glance_store" part, which we override so we
        # can control the block size and check our task status
        # synchronously and not depend on timers. It just reads the
        # source data in 64KiB chunks and throws it away.
        def fake_upload(data, *a, **k):
            while True:
                grab_task_status()

                if not data.read(65536):
                    break
                time.sleep(0.1)

        with mock.patch('glance.location.ImageProxy._upload_to_store') as mu:
            mu.side_effect = fake_upload

            # Start the import...
            resp = self._import_direct(image_id, ['store2'])
            self.assertEqual(202, resp.status_code)

            # ...and wait until it finishes
            for i in range(0, 100):
                image = self.api_get('/v2/images/%s' % image_id).json
                if not image.get('os_glance_import_task'):
                    break
                time.sleep(0.1)

        # Image should be in active state and we should have gotten a
        # new message every 1MiB in the process. We mocked StopWatch
        # to always be expired so that we fire the callback every
        # time.
        self.assertEqual('active', image['status'])
        self.assertEqual(['', 'Copied 0 MiB', 'Copied 1 MiB', 'Copied 2 MiB',
                          'Copied 3 MiB'],
                         statuses)
