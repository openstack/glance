# Copyright 2011-2012 OpenStack Foundation
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

import os
import sys
import time

from oslo_config import cfg
from oslo_utils import units

from glance import context
import glance.db as db_api
from glance.tests import functional
from glance.tests import utils as test_utils
from glance.tests.utils import execute

CONF = cfg.CONF


class TestScrubber(functional.SynchronousAPIBase):

    """Test that delayed_delete works and the scrubber deletes"""

    def setUp(self):
        super(TestScrubber, self).setUp()
        self.admin_context = context.get_admin_context(show_deleted=True)

    def _get_pending_delete_image(self, image_id):
        # In Glance V2, there is no way to get the 'pending_delete' image from
        # API. So we get the image from db here for testing.
        # Clean the session cache first to avoid connecting to the old db data.
        db_api.get_api()._FACADE = None
        image = db_api.get_api().image_get(self.admin_context, image_id)
        return image

    def test_delayed_delete(self):
        """
        test that images don't get deleted immediately and that the scrubber
        scrubs them
        """
        self.config(delayed_delete=True)
        self.start_server()
        self.scrubber = self.start_scrubber(daemon=True, wakeup_time=2)[3]

        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

        path = '/v2/images/%s' % image_id
        self.api_delete(path)

        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        if self.scrubber:
            self.wait_for_scrub(image['id'])
            self.scrubber.terminate()
            self.scrubber.wait()
            # Give the scrubber some time to stop.
            time.sleep(5)

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.config(delayed_delete=True)
        self.start_server()

        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

        path = '/v2/images/%s' % image_id
        self.api_delete(path)

        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        # scrub images and make sure they get deleted
        self.start_scrubber(daemon=False, wakeup_time=2)
        self.wait_for_scrub(image['id'])

    def test_scrubber_delete_handles_exception(self):
        """
        Test that the scrubber handles the case where an
        exception occurs when _delete() is called. The scrubber
        should not write out queue files in this case.
        """
        self.config(delayed_delete=True)
        self.start_server()

        # add an image
        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

        # delete the image
        path = '/v2/images/%s' % image_id
        self.api_delete(path)

        # ensure the image is marked pending delete.
        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        # Remove the file from the backend.
        store_path = os.path.join(self.test_dir, 'store1')
        file_path = os.path.join(store_path, image['id'])
        os.remove(file_path)

        # run the scrubber app, and ensure it doesn't fall over
        self.start_scrubber(daemon=False, wakeup_time=2)
        self.wait_for_scrub(image['id'])

    def test_scrubber_restore_image(self):
        self.config(delayed_delete=True)
        self.start_server()

        # add an image
        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

        # delete the image
        path = '/v2/images/%s' % image_id
        self.api_delete(path)

        # ensure the image is marked pending delete.
        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        def _test_content():
            return self.start_scrubber(daemon=False, wakeup_time=2,
                                       restore=image['id'])

        exitcode, out, err = self.wait_for_scrubber_shutdown(
            _test_content)
        self.assertEqual(0, exitcode)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

    def test_scrubber_restore_active_image_raise_error(self):
        self.config(delayed_delete=True)
        self.start_server()

        # add an image
        data = test_utils.FakeData(1 * units.Mi)
        image_id = self._create_and_upload(data_iter=data)

        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual('active', image['status'])

        def _test_content():
            return self.start_scrubber(daemon=False, wakeup_time=2,
                                       restore=image['id'], raise_error=False)

        exitcode, out, err = self.wait_for_scrubber_shutdown(
            _test_content)
        self.assertEqual(1, exitcode)
        self.assertIn('cannot restore the image from active to active '
                      '(wanted from_state=pending_delete)', str(err))

    def test_scrubber_restore_image_non_exist(self):
        def _test_content():
            return self.start_scrubber(
                daemon=False, wakeup_time=2, restore='fake_image_id',
                raise_error=False)

        exitcode, out, err = self.wait_for_scrubber_shutdown(
            _test_content)
        self.assertEqual(1, exitcode)
        self.assertIn('No image found with ID fake_image_id', str(err))

    def test_scrubber_restore_image_with_daemon_raise_error(self):
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --daemon --restore fake_image_id" % exe_cmd)
        exitcode, out, err = execute(cmd, raise_error=False)

        self.assertEqual(1, exitcode)
        self.assertIn('The restore and daemon options should not be set '
                      'together', str(err))

    def test_scrubber_restore_image_with_daemon_running(self):
        self.scrubber = self.start_scrubber(daemon=True, wakeup_time=2)[3]
        # Give the scrubber some time to start.
        time.sleep(5)

        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --restore fake_image_id" % exe_cmd)
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(1, exitcode)
        self.assertIn('glance-scrubber is already running', str(err))

        # terminate daemon process
        if self.scrubber:
            self.scrubber.terminate()
            self.scrubber.wait()
            # Give the scrubber some time to stop.
            time.sleep(5)

    def wait_for_scrubber_shutdown(self, func):
        # NOTE(wangxiyuan, rosmaita): The image-restore functionality contains
        # a check to make sure the scrubber isn't also running in daemon mode
        # to prevent a race condition between a delete and a restore.
        # Sometimes the glance-scrubber process which is setup by the
        # previous test can't be shutdown immediately, so if we get the "daemon
        # running" message we sleep and try again.
        not_down_msg = 'glance-scrubber is already running'
        total_wait = 15
        for _ in range(total_wait):
            exitcode, out, err = func()
            if exitcode == 1 and not_down_msg in str(err):
                time.sleep(1)
                continue
            return exitcode, out, err
        else:
            self.fail('Scrubber did not shut down within {} sec'.format(
                total_wait))

    def wait_for_scrub(self, image_id):
        """
        NOTE(jkoelker) The build servers sometimes take longer than 15 seconds
        to scrub. Give it up to 5 min, checking checking every 15 seconds.
        When/if it flips to deleted, bail immediately.
        """
        wait_for = 300    # seconds
        check_every = 15  # seconds
        for _ in range(wait_for // check_every):
            time.sleep(check_every)
            image = db_api.get_api().image_get(self.admin_context, image_id)
            if (image['status'] == 'deleted' and
                    image['deleted'] == True):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')
