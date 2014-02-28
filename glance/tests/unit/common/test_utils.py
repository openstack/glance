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

import os
import tempfile
import uuid

import six
import webob

from glance.common import exception
from glance.common import utils
from glance.tests import utils as test_utils


class TestUtils(test_utils.BaseTestCase):
    """Test routines in glance.utils"""

    def test_cooperative_reader(self):
        """Ensure cooperative reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            for chunk in utils.CooperativeReader(tmp_fd):
                bytes_read += len(chunk)

        self.assertEqual(bytes_read, BYTES)

        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            reader = utils.CooperativeReader(tmp_fd)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertEqual(bytes_read, BYTES)

    def test_cooperative_reader_of_iterator(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in 'abcdefgh'])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == '':
                break
        meat = ''.join(chunks)
        self.assertEqual(meat, 'aaabbbcccdddeeefffggghhh')

    def test_cooperative_reader_of_iterator_stop_iteration_err(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in ''])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == '':
                break
        meat = ''.join(chunks)
        self.assertEqual(meat, '')

    def test_limiting_reader(self):
        """Ensure limiting reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        data = six.StringIO("*" * BYTES)
        for chunk in utils.LimitingReader(data, BYTES):
            bytes_read += len(chunk)

        self.assertEqual(bytes_read, BYTES)

        bytes_read = 0
        data = six.StringIO("*" * BYTES)
        reader = utils.LimitingReader(data, BYTES)
        byte = reader.read(1)
        while len(byte) != 0:
            bytes_read += 1
            byte = reader.read(1)

        self.assertEqual(bytes_read, BYTES)

    def test_limiting_reader_fails(self):
        """Ensure limiting reader class throws exceptions if limit exceeded"""
        BYTES = 1024

        def _consume_all_iter():
            bytes_read = 0
            data = six.StringIO("*" * BYTES)
            for chunk in utils.LimitingReader(data, BYTES - 1):
                bytes_read += len(chunk)

        self.assertRaises(exception.ImageSizeLimitExceeded, _consume_all_iter)

        def _consume_all_read():
            bytes_read = 0
            data = six.StringIO("*" * BYTES)
            reader = utils.LimitingReader(data, BYTES - 1)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertRaises(exception.ImageSizeLimitExceeded, _consume_all_read)

    def test_get_meta_from_headers(self):
        resp = webob.Response()
        resp.headers = {"x-image-meta-name": 'test'}
        result = utils.get_image_meta_from_headers(resp)
        self.assertEqual({'name': 'test', 'properties': {}}, result)

    def test_get_meta_from_headers_bad_headers(self):
        resp = webob.Response()
        resp.headers = {"x-image-meta-bad": 'test'}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          utils.get_image_meta_from_headers, resp)
        resp.headers = {"x-image-meta-": 'test'}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          utils.get_image_meta_from_headers, resp)
        resp.headers = {"x-image-meta-*": 'test'}
        self.assertRaises(webob.exc.HTTPBadRequest,
                          utils.get_image_meta_from_headers, resp)

    def test_add_features_to_http_headers(self):
        features_test1 = {'x-image-meta-size': 'test'}
        url = ("http://glance.example.com/v1/"
               "images/71c675ab-d94f-49cd-a114-e12490b328d9")
        headers = {"x-image-meta-uri": url}
        self.assertRaises(exception.UnsupportedHeaderFeature,
                          utils.add_features_to_http_headers,
                          features_test1, headers)

    def test_image_meta(self):
        image_meta = {'x-image-meta-size': 'test'}
        image_meta_properties = {'properties': {'test': "test"}}
        actual = utils.image_meta_to_http_headers(image_meta)
        actual_test2 = utils.image_meta_to_http_headers(
            image_meta_properties)
        self.assertEqual({'x-image-meta-x-image-meta-size': u'test'}, actual)
        self.assertEqual({'x-image-meta-property-test': u'test'},
                         actual_test2)

    def test_create_pretty_table(self):
        class MyPrettyTable(utils.PrettyTable):
            def __init__(self):
                self.columns = []

        # Test add column
        my_pretty_table = MyPrettyTable()
        my_pretty_table.add_column(1, label='test')
        # Test make header
        test_res = my_pretty_table.make_header()
        self.assertEqual('t\n-', test_res)
        # Test make row
        result = my_pretty_table.make_row('t')
        self.assertEqual("t", result)
        result = my_pretty_table._clip_and_justify(
            data='test', width=4, just=1)
        self.assertEqual("test", result)

    def test_mutating(self):
        class FakeContext():
            def __init__(self):
                self.read_only = False

        class Fake():
            def __init__(self):
                self.context = FakeContext()

        def fake_function(req, context):
            return 'test passed'

        req = webob.Request.blank('/some_request')
        result = utils.mutating(fake_function)
        self.assertEqual("test passed", result(req, Fake()))

    def test_validate_key_cert_key(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../../', 'var'))
        keyfile = os.path.join(var_dir, 'privatekey.key')
        certfile = os.path.join(var_dir, 'certificate.crt')
        utils.validate_key_cert(keyfile, certfile)

    def test_validate_key_cert_no_private_key(self):
        with tempfile.NamedTemporaryFile('w+') as tmpf:
            self.assertRaises(RuntimeError,
                              utils.validate_key_cert,
                              "/not/a/file", tmpf.name)

    def test_validate_key_cert_cert_cant_read(self):
        with tempfile.NamedTemporaryFile('w+') as keyf:
            with tempfile.NamedTemporaryFile('w+') as certf:
                os.chmod(certf.name, 0)
                self.assertRaises(RuntimeError,
                                  utils.validate_key_cert,
                                  keyf.name, certf.name)

    def test_validate_key_cert_key_cant_read(self):
        with tempfile.NamedTemporaryFile('w+') as keyf:
            with tempfile.NamedTemporaryFile('w+') as keyf:
                os.chmod(keyf.name, 0)
                self.assertRaises(RuntimeError,
                                  utils.validate_key_cert,
                                  keyf.name, keyf.name)


class UUIDTestCase(test_utils.BaseTestCase):

    def test_is_uuid_like(self):
        self.assertTrue(utils.is_uuid_like(str(uuid.uuid4())))

    def test_id_is_uuid_like(self):
        self.assertFalse(utils.is_uuid_like(1234567))

    def test_name_is_uuid_like(self):
        self.assertFalse(utils.is_uuid_like('zhongyueluo'))
