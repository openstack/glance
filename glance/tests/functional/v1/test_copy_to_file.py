# Copyright 2011 OpenStack Foundation
# Copyright 2012 Red Hat, Inc
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
Tests copying images to a Glance API server which uses a filesystem-
based storage backend.
"""

import hashlib
import tempfile
import time

import httplib2
from oslo_serialization import jsonutils
from oslo_utils import units
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.tests import functional
from glance.tests.functional.store_utils import get_http_uri
from glance.tests.functional.store_utils import setup_http
from glance.tests.utils import skip_if_disabled

FIVE_KB = 5 * units.Ki


class TestCopyToFile(functional.FunctionalTest):

    """
    Functional tests for copying images from the HTTP storage
    backend to file
    """

    def _do_test_copy_from(self, from_store, get_uri):
        """
        Ensure we can copy from an external image in from_store.
        """
        self.cleanup()

        self.start_servers(**self.__dict__.copy())
        setup_http(self)

        # POST /images with public image to be stored in from_store,
        # to stand in for the 'external' image
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'external',
                   'X-Image-Meta-Store': from_store,
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(201, response.status, content)
        data = jsonutils.loads(content)

        original_image_id = data['image']['id']

        copy_from = get_uri(self, original_image_id)

        # POST /images with public image copied from_store (to file)
        headers = {'X-Image-Meta-Name': 'copied',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Glance-API-Copy-From': copy_from}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status, content)
        data = jsonutils.loads(content)

        copy_image_id = data['image']['id']
        self.assertNotEqual(copy_image_id, original_image_id)

        # GET image and make sure image content is as expected
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              copy_image_id)

        def _await_status(expected_status):
            for i in range(100):
                time.sleep(0.01)
                http = httplib2.Http()
                response, content = http.request(path, 'HEAD')
                self.assertEqual(200, response.status)
                if response['x-image-meta-status'] == expected_status:
                    return
            self.fail('unexpected image status %s' %
                      response['x-image-meta-status'])
        _await_status('active')

        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual(str(FIVE_KB), response['content-length'])

        self.assertEqual("*" * FIVE_KB, content)
        self.assertEqual(hashlib.md5("*" * FIVE_KB).hexdigest(),
                         hashlib.md5(content).hexdigest())
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("copied", data['image']['name'])

        # DELETE original image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              original_image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        # GET image again to make sure the existence of the original
        # image in from_store is not depended on
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              copy_image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual(str(FIVE_KB), response['content-length'])

        self.assertEqual("*" * FIVE_KB, content)
        self.assertEqual(hashlib.md5("*" * FIVE_KB).hexdigest(),
                         hashlib.md5(content).hexdigest())
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("copied", data['image']['name'])

        # DELETE copied image
        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              copy_image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        self.stop_servers()

    @skip_if_disabled
    def test_copy_from_http_store(self):
        """
        Ensure we can copy from an external image in HTTP store.
        """
        self._do_test_copy_from('file', get_http_uri)

    @skip_if_disabled
    def test_copy_from_http_exists(self):
        """Ensure we can copy from an external image in HTTP."""
        self.cleanup()

        self.start_servers(**self.__dict__.copy())

        setup_http(self)

        copy_from = get_http_uri(self, 'foobar')

        # POST /images with public image copied from HTTP (to file)
        headers = {'X-Image-Meta-Name': 'copied',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Glance-API-Copy-From': copy_from}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status, content)
        data = jsonutils.loads(content)

        copy_image_id = data['image']['id']
        self.assertEqual('queued', data['image']['status'], content)

        path = "http://%s:%d/v1/images/%s" % ("127.0.0.1", self.api_port,
                                              copy_image_id)

        def _await_status(expected_status):
            for i in range(100):
                time.sleep(0.01)
                http = httplib2.Http()
                response, content = http.request(path, 'HEAD')
                self.assertEqual(200, response.status)
                if response['x-image-meta-status'] == expected_status:
                    return
            self.fail('unexpected image status %s' %
                      response['x-image-meta-status'])

        _await_status('active')

        # GET image and make sure image content is as expected
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(200, response.status)

        self.assertEqual(str(FIVE_KB), response['content-length'])
        self.assertEqual("*" * FIVE_KB, content)
        self.assertEqual(hashlib.md5("*" * FIVE_KB).hexdigest(),
                         hashlib.md5(content).hexdigest())

        # DELETE copied image
        http = httplib2.Http()
        response, content = http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

        self.stop_servers()

    @skip_if_disabled
    def test_copy_from_http_nonexistent_location_url(self):
        # Ensure HTTP 404 response returned when try to create
        # image with non-existent http location URL.
        self.cleanup()

        self.start_servers(**self.__dict__.copy())

        setup_http(self)

        uri = get_http_uri(self, 'foobar')
        copy_from = uri.replace('images', 'snafu')

        # POST /images with public image copied from HTTP (to file)
        headers = {'X-Image-Meta-Name': 'copied',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Glance-API-Copy-From': copy_from}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(404, response.status, content)

        expected = 'HTTP datastore could not find image at URI.'
        self.assertIn(expected, content)

        self.stop_servers()

    @skip_if_disabled
    def test_copy_from_file(self):
        """
        Ensure we can't copy from file
        """
        self.cleanup()

        self.start_servers(**self.__dict__.copy())

        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            copy_from = 'file://' + image_file.name

        # POST /images with public image copied from file (to file)
        headers = {'X-Image-Meta-Name': 'copied',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Glance-API-Copy-From': copy_from}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(400, response.status, content)

        expected = 'External sources are not supported: \'%s\'' % copy_from
        msg = 'expected "%s" in "%s"' % (expected, content)
        self.assertIn(expected, content, msg)

        self.stop_servers()

    @skip_if_disabled
    def test_copy_from_swift_config(self):
        """
        Ensure we can't copy from swift+config
        """
        self.cleanup()

        self.start_servers(**self.__dict__.copy())

        # POST /images with public image copied from file (to file)
        headers = {'X-Image-Meta-Name': 'copied',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Glance-API-Copy-From': 'swift+config://xxx'}
        path = "http://%s:%d/v1/images" % ("127.0.0.1", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(400, response.status, content)

        expected = 'External sources are not supported: \'swift+config://xxx\''
        msg = 'expected "%s" in "%s"' % (expected, content)
        self.assertIn(expected, content, msg)

        self.stop_servers()
