# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011-2012 OpenStack, LLC
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

import httplib2
import json
import nose
import os
import time

from glance.tests import functional
from glance.tests.functional.store.test_swift import parse_config
from glance.tests.functional.store.test_swift import read_config
from glance.tests.utils import execute


TEST_IMAGE_DATA = '*' * 5 * 1024
TEST_IMAGE_META = {
    'name': 'test_image',
    'is_public': False,
    'disk_format': 'raw',
    'container_format': 'ovf',
}


class TestScrubber(functional.FunctionalTest):

    """Test that delayed_delete works and the scrubber deletes"""

    def test_delayed_delete(self):
        """
        test that images don't get deleted immediatly and that the scrubber
        scrubs them
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=True)

        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(response.status, 201)
        image = json.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # NOTE(jkoelker) The build servers sometimes take longer than
        #                15 seconds to scrub. Give it up to 5 min, checking
        #                checking every 15 seconds. When/if it flips to
        #                deleted, bail immediatly.
        for _ in xrange(3):
            time.sleep(5)

            response, content = http.request(path, 'HEAD')
            if (response['x-image-meta-status'] == 'deleted' and
                response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')

        self.stop_servers()

    def test_scrubber_app(self):
        """
        test that the glance-scrubber script runs successfully when not in
        daemon mode
        """
        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False)

        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        self.assertEqual(response.status, 201)
        image = json.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # scrub images and make sure they get deleted
        cmd = ("bin/glance-scrubber --config-file %s" %
               self.scrubber_daemon.conf_file_name)
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        # NOTE(jkoelker) The build servers sometimes take longer than
        #                15 seconds to scrub. Give it up to 5 min, checking
        #                checking every 15 seconds. When/if it flips to
        #                deleted, bail immediatly.
        for _ in xrange(3):
            time.sleep(5)

            response, content = http.request(path, 'HEAD')
            if (response['x-image-meta-status'] == 'deleted' and
                response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')

        self.stop_servers()

    def test_scrubber_app_against_swift(self):
        """
        test that the glance-scrubber script runs successfully against a swift
        backend when not in daemon mode
        """
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            raise nose.SkipTest(msg)

        raw_config = read_config(config_path)
        swift_config = parse_config(raw_config)

        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=False,
                           default_store='swift', **swift_config)

        # add an image
        headers = {
            'x-image-meta-name': 'test_image',
            'x-image-meta-is_public': 'true',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'content-type': 'application/octet-stream',
        }
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', body='XXX',
                                         headers=headers)
        # ensure the request was successful and the image is active
        self.assertEqual(response.status, 201)
        image = json.loads(content)['image']
        self.assertEqual('active', image['status'])
        image_id = image['id']

        # delete the image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(response.status, 200)

        # ensure the image is marked pending delete
        response, content = http.request(path, 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertEqual('pending_delete', response['x-image-meta-status'])

        # wait for the scrub time on the image to pass
        time.sleep(self.api_server.scrub_time)

        # call the scrubber to scrub images
        cmd = ("bin/glance-scrubber --config-file %s" %
               self.scrubber_daemon.conf_file_name)
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        # ensure the image has been successfully deleted
        # NOTE(jkoelker) The build servers sometimes take longer than
        #                15 seconds to scrub. Give it up to 5 min, checking
        #                checking every 15 seconds. When/if it flips to
        #                deleted, bail immediately.
        for _ in xrange(3):
            time.sleep(5)
            response, content = http.request(path, 'HEAD')
            if (response['x-image-meta-status'] == 'deleted' and
                    response['x-image-meta-deleted'] == 'True'):
                break
            else:
                continue
        else:
            self.fail('image was never scrubbed')

        self.stop_servers()
