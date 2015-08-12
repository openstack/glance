# Copyright 2011 OpenStack Foundation
# Copyright 2015 Mirantis, Inc
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

        self.assertEqual(BYTES, bytes_read)

        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            reader = utils.CooperativeReader(tmp_fd)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertEqual(BYTES, bytes_read)

    def test_cooperative_reader_of_iterator(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in 'abcdefgh'])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == '':
                break
        meat = ''.join(chunks)
        self.assertEqual('aaabbbcccdddeeefffggghhh', meat)

    def test_cooperative_reader_of_iterator_stop_iteration_err(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in ''])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == '':
                break
        meat = ''.join(chunks)
        self.assertEqual('', meat)

    def _create_generator(self, chunk_size, max_iterations):
        chars = 'abc'
        iteration = 0
        while True:
            chunk = chars[iteration % len(chars)] * chunk_size
            yield chunk
            iteration += 1
            if iteration >= max_iterations:
                raise StopIteration()

    def _test_reader_chunked(self, chunk_size, read_size, max_iterations=5):
        generator = self._create_generator(chunk_size, max_iterations)
        reader = utils.CooperativeReader(generator)
        result = ''
        while True:
            data = reader.read(read_size)
            if len(data) == 0:
                break
            self.assertLessEqual(len(data), read_size)
            result += data
        expected = ('a' * chunk_size +
                    'b' * chunk_size +
                    'c' * chunk_size +
                    'a' * chunk_size +
                    'b' * chunk_size)
        self.assertEqual(expected, result)

    def test_cooperative_reader_preserves_size_chunk_less_then_read(self):
        self._test_reader_chunked(43, 101)

    def test_cooperative_reader_preserves_size_chunk_equals_read(self):
        self._test_reader_chunked(1024, 1024)

    def test_cooperative_reader_preserves_size_chunk_more_then_read(self):
        chunk_size = 16 * 1024 * 1024  # 16 Mb, as in remote http source
        read_size = 8 * 1024           # 8k, as in httplib
        self._test_reader_chunked(chunk_size, read_size)

    def test_limiting_reader(self):
        """Ensure limiting reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        data = six.StringIO("*" * BYTES)
        for chunk in utils.LimitingReader(data, BYTES):
            bytes_read += len(chunk)

        self.assertEqual(BYTES, bytes_read)

        bytes_read = 0
        data = six.StringIO("*" * BYTES)
        reader = utils.LimitingReader(data, BYTES)
        byte = reader.read(1)
        while len(byte) != 0:
            bytes_read += 1
            byte = reader.read(1)

        self.assertEqual(BYTES, bytes_read)

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
        resp.headers = {"x-image-meta-name": 'test',
                        'x-image-meta-virtual-size': 80}
        result = utils.get_image_meta_from_headers(resp)
        self.assertEqual({'name': 'test', 'properties': {},
                          'virtual_size': 80}, result)

    def test_get_meta_from_headers_none_virtual_size(self):
        resp = webob.Response()
        resp.headers = {"x-image-meta-name": 'test',
                        'x-image-meta-virtual-size': 'None'}
        result = utils.get_image_meta_from_headers(resp)
        self.assertEqual({'name': 'test', 'properties': {},
                          'virtual_size': None}, result)

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

    def test_image_meta(self):
        image_meta = {'x-image-meta-size': 'test'}
        image_meta_properties = {'properties': {'test': "test"}}
        actual = utils.image_meta_to_http_headers(image_meta)
        actual_test2 = utils.image_meta_to_http_headers(
            image_meta_properties)
        self.assertEqual({'x-image-meta-x-image-meta-size': u'test'}, actual)
        self.assertEqual({'x-image-meta-property-test': u'test'},
                         actual_test2)

    def test_create_mashup_dict_with_different_core_custom_properties(self):
        image_meta = {
            'id': 'test-123',
            'name': 'fake_image',
            'status': 'active',
            'created_at': '',
            'min_disk': '10G',
            'min_ram': '1024M',
            'protected': False,
            'locations': '',
            'checksum': 'c1234',
            'owner': '',
            'disk_format': 'raw',
            'container_format': 'bare',
            'size': '123456789',
            'virtual_size': '123456789',
            'is_public': 'public',
            'deleted': True,
            'updated_at': '',
            'properties': {'test_key': 'test_1234'},
        }

        mashup_dict = utils.create_mashup_dict(image_meta)
        self.assertNotIn('properties', mashup_dict)
        self.assertEqual(image_meta['properties']['test_key'],
                         mashup_dict['test_key'])

    def test_create_mashup_dict_with_same_core_custom_properties(self):
        image_meta = {
            'id': 'test-123',
            'name': 'fake_image',
            'status': 'active',
            'created_at': '',
            'min_disk': '10G',
            'min_ram': '1024M',
            'protected': False,
            'locations': '',
            'checksum': 'c1234',
            'owner': '',
            'disk_format': 'raw',
            'container_format': 'bare',
            'size': '123456789',
            'virtual_size': '123456789',
            'is_public': 'public',
            'deleted': True,
            'updated_at': '',
            'properties': {'min_ram': '2048M'},
        }

        mashup_dict = utils.create_mashup_dict(image_meta)
        self.assertNotIn('properties', mashup_dict)
        self.assertNotEqual(image_meta['properties']['min_ram'],
                            mashup_dict['min_ram'])
        self.assertEqual(image_meta['min_ram'], mashup_dict['min_ram'])

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
        class FakeContext(object):
            def __init__(self):
                self.read_only = False

        class Fake(object):
            def __init__(self):
                self.context = FakeContext()

        def fake_function(req, context):
            return 'test passed'

        req = webob.Request.blank('/some_request')
        result = utils.mutating(fake_function)
        self.assertEqual("test passed", result(req, Fake()))

    def test_validate_key_cert_key(self):
        self.config(digest_algorithm='sha256')
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
            with tempfile.NamedTemporaryFile('w+') as certf:
                os.chmod(keyf.name, 0)
                self.assertRaises(RuntimeError,
                                  utils.validate_key_cert,
                                  keyf.name, certf.name)

    def test_invalid_digest_algorithm(self):
        self.config(digest_algorithm='fake_algorithm')
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../../', 'var'))
        keyfile = os.path.join(var_dir, 'privatekey.key')
        certfile = os.path.join(var_dir, 'certificate.crt')
        self.assertRaises(ValueError,
                          utils.validate_key_cert,
                          keyfile, certfile)

    def test_valid_hostname(self):
        valid_inputs = ['localhost',
                        'glance04-a'
                        'G',
                        '528491']

        for input_str in valid_inputs:
            self.assertTrue(utils.is_valid_hostname(input_str))

    def test_valid_hostname_fail(self):
        invalid_inputs = ['localhost.localdomain',
                          '192.168.0.1',
                          u'\u2603',
                          'glance02.stack42.local']

        for input_str in invalid_inputs:
            self.assertFalse(utils.is_valid_hostname(input_str))

    def test_valid_fqdn(self):
        valid_inputs = ['localhost.localdomain',
                        'glance02.stack42.local'
                        'glance04-a.stack47.local',
                        'img83.glance.xn--penstack-r74e.org']

        for input_str in valid_inputs:
            self.assertTrue(utils.is_valid_fqdn(input_str))

    def test_valid_fqdn_fail(self):
        invalid_inputs = ['localhost',
                          '192.168.0.1',
                          '999.88.77.6',
                          u'\u2603.local',
                          'glance02.stack42']

        for input_str in invalid_inputs:
            self.assertFalse(utils.is_valid_fqdn(input_str))

    def test_valid_host_port_string(self):
        valid_pairs = ['10.11.12.13:80',
                       '172.17.17.1:65535',
                       '[fe80::a:b:c:d]:9990',
                       'localhost:9990',
                       'localhost.localdomain:9990',
                       'glance02.stack42.local:1234',
                       'glance04-a.stack47.local:1234',
                       'img83.glance.xn--penstack-r74e.org:13080']

        for pair_str in valid_pairs:
            host, port = utils.parse_valid_host_port(pair_str)

            escaped = pair_str.startswith('[')
            expected_host = '%s%s%s' % ('[' if escaped else '', host,
                                        ']' if escaped else '')

            self.assertTrue(pair_str.startswith(expected_host))
            self.assertTrue(port > 0)

            expected_pair = '%s:%d' % (expected_host, port)
            self.assertEqual(expected_pair, pair_str)

    def test_valid_host_port_string_fail(self):
        invalid_pairs = ['',
                         '10.11.12.13',
                         '172.17.17.1:99999',
                         '290.12.52.80:5673',
                         'absurd inputs happen',
                         u'\u2601',
                         u'\u2603:8080',
                         'fe80::1',
                         '[fe80::2]',
                         '<fe80::3>:5673',
                         '[fe80::a:b:c:d]9990',
                         'fe80:a:b:c:d:e:f:1:2:3:4',
                         'fe80:a:b:c:d:e:f:g',
                         'fe80::1:8080',
                         '[fe80:a:b:c:d:e:f:g]:9090',
                         '[a:b:s:u:r:d]:fe80']

        for pair in invalid_pairs:
            self.assertRaises(ValueError,
                              utils.parse_valid_host_port,
                              pair)


class UUIDTestCase(test_utils.BaseTestCase):

    def test_is_uuid_like(self):
        self.assertTrue(utils.is_uuid_like(str(uuid.uuid4())))

    def test_id_is_uuid_like(self):
        self.assertFalse(utils.is_uuid_like(1234567))

    def test_name_is_uuid_like(self):
        self.assertFalse(utils.is_uuid_like('zhongyueluo'))
