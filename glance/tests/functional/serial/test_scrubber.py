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

import http.client
import os
import sys
import time

import httplib2
from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids

from glance import context
import glance.db as db_api
from glance.tests import functional
from glance.tests.utils import execute

CONF = cfg.CONF


class TestScrubber(functional.FunctionalTest):

    """Test that delayed_delete works and the scrubber deletes"""

    def setUp(self):
        super(TestScrubber, self).setUp()
        self.api_server.deployment_flavor = 'noauth'
        self.admin_context = context.get_admin_context(show_deleted=True)
        CONF.set_override('connection', self.api_server.sql_connection,
                          group='database')

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': uuids.TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _send_create_image_http_request(self, path, body=None):
        headers = {
            "Content-Type": "application/json",
            "X-Roles": "admin",
        }
        body = body or {'container_format': 'ovf',
                        'disk_format': 'raw',
                        'name': 'test_image',
                        'visibility': 'public'}
        body = jsonutils.dumps(body)
        return httplib2.Http().request(path, 'POST', body,
                                       self._headers(headers))

    def _send_upload_image_http_request(self, path, body=None):
        headers = {
            "Content-Type": "application/octet-stream"
        }
        return httplib2.Http().request(path, 'PUT', body,
                                       self._headers(headers))

    def _send_http_request(self, path, method):
        headers = {
            "Content-Type": "application/json"
        }
        return httplib2.Http().request(path, method, None,
                                       self._headers(headers))

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
        self.cleanup()
        kwargs = self.__dict__.copy()
        self.start_servers(delayed_delete=True, daemon=True,
                           metadata_encryption_key='', **kwargs)
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_create_image_http_request(path)
        self.assertEqual(http.client.CREATED, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('queued', image['status'])

        file_path = "%s/%s/file" % (path, image['id'])
        response, content = self._send_upload_image_http_request(file_path,
                                                                 body='XXX')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        path = "%s/%s" % (path, image['id'])
        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])

        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        self.wait_for_scrub(image['id'])

        self.stop_servers()

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.cleanup()
        kwargs = self.__dict__.copy()
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='', **kwargs)
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_create_image_http_request(path)
        self.assertEqual(http.client.CREATED, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('queued', image['status'])

        file_path = "%s/%s/file" % (path, image['id'])
        response, content = self._send_upload_image_http_request(file_path,
                                                                 body='XXX')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        path = "%s/%s" % (path, image['id'])
        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])

        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # scrub images and make sure they get deleted
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        self.wait_for_scrub(image['id'])

        self.stop_servers()

    def test_scrubber_delete_handles_exception(self):
        """
        Test that the scrubber handles the case where an
        exception occurs when _delete() is called. The scrubber
        should not write out queue files in this case.
        """

        # Start servers.
        self.cleanup()
        kwargs = self.__dict__.copy()
        self.start_servers(delayed_delete=True, daemon=False,
                           default_store='file', **kwargs)

        # Check that we are using a file backend.
        self.assertEqual(self.api_server.default_store, 'file')

        # add an image
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_create_image_http_request(path)
        self.assertEqual(http.client.CREATED, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('queued', image['status'])

        file_path = "%s/%s/file" % (path, image['id'])
        response, content = self._send_upload_image_http_request(file_path,
                                                                 body='XXX')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        path = "%s/%s" % (path, image['id'])
        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])
        # delete the image
        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(http.client.NO_CONTENT, response.status)
        # ensure the image is marked pending delete.
        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        # Remove the file from the backend.
        file_path = os.path.join(self.api_server.image_dir, image['id'])
        os.remove(file_path)

        # Wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # run the scrubber app, and ensure it doesn't fall over
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        self.wait_for_scrub(image['id'])

        self.stop_servers()

    def test_scrubber_app_queue_errors_not_daemon(self):
        """
        test that the glance-scrubber exits with an exit code > 0 when it
        fails to lookup images, indicating a configuration error when not
        in daemon mode.

        Related-Bug: #1548289
        """
        # Don't start the registry server to cause intended failure
        # Don't start the api server to save time
        exitcode, out, err = self.scrubber_daemon.start(
            delayed_delete=True, daemon=False)
        self.assertEqual(0, exitcode,
                         "Failed to spin up the Scrubber daemon. "
                         "Got: %s" % err)

        # Run the Scrubber
        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)

        self.assertEqual(1, exitcode)
        self.assertIn('Can not get scrub jobs from queue', str(err))

        self.stop_server(self.scrubber_daemon)

    def test_scrubber_restore_image(self):
        self.cleanup()
        kwargs = self.__dict__.copy()
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='', **kwargs)
        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_create_image_http_request(path)
        self.assertEqual(http.client.CREATED, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('queued', image['status'])

        file_path = "%s/%s/file" % (path, image['id'])
        response, content = self._send_upload_image_http_request(file_path,
                                                                 body='XXX')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        path = "%s/%s" % (path, image['id'])
        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])

        response, content = self._send_http_request(path, 'DELETE')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        image = self._get_pending_delete_image(image['id'])
        self.assertEqual('pending_delete', image['status'])

        def _test_content():
            exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
            cmd = ("%s --config-file %s --restore %s" %
                   (exe_cmd, self.scrubber_daemon.conf_file_name, image['id']))
            return execute(cmd, raise_error=False)

        exitcode, out, err = self.wait_for_scrubber_shutdown(_test_content)
        self.assertEqual(0, exitcode)

        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])

        self.stop_servers()

    def test_scrubber_restore_active_image_raise_error(self):
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           metadata_encryption_key='')

        path = "http://%s:%d/v2/images" % ("127.0.0.1", self.api_port)
        response, content = self._send_create_image_http_request(path)
        self.assertEqual(http.client.CREATED, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('queued', image['status'])

        file_path = "%s/%s/file" % (path, image['id'])
        response, content = self._send_upload_image_http_request(file_path,
                                                                 body='XXX')
        self.assertEqual(http.client.NO_CONTENT, response.status)

        path = "%s/%s" % (path, image['id'])
        response, content = self._send_http_request(path, 'GET')
        image = jsonutils.loads(content)
        self.assertEqual('active', image['status'])

        def _test_content():
            exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
            cmd = ("%s --config-file %s --restore %s" %
                   (exe_cmd, self.scrubber_daemon.conf_file_name, image['id']))
            return execute(cmd, raise_error=False)

        exitcode, out, err = self.wait_for_scrubber_shutdown(_test_content)
        self.assertEqual(1, exitcode)
        self.assertIn('cannot restore the image from active to active '
                      '(wanted from_state=pending_delete)', str(err))

        self.stop_servers()

    def test_scrubber_restore_image_non_exist(self):

        def _test_content():
            scrubber = functional.ScrubberDaemon(self.test_dir,
                                                 self.policy_file)
            scrubber.write_conf(daemon=False)
            scrubber.needs_database = True
            scrubber.create_database()
            exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
            cmd = ("%s --config-file %s --restore fake_image_id" %
                   (exe_cmd, scrubber.conf_file_name))
            return execute(cmd, raise_error=False)

        exitcode, out, err = self.wait_for_scrubber_shutdown(_test_content)
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
        self.cleanup()
        self.scrubber_daemon.start(daemon=True)
        # Give the scrubber some time to start.
        time.sleep(5)

        exe_cmd = "%s -m glance.cmd.scrubber" % sys.executable
        cmd = ("%s --restore fake_image_id" % exe_cmd)
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(1, exitcode)
        self.assertIn('glance-scrubber is already running', str(err))

        self.stop_server(self.scrubber_daemon)

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
