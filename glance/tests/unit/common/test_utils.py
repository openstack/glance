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

import mock
import os
import tempfile

from oslo_log import log as logging
import six
import webob

from glance.common import exception
from glance.common import store_utils
from glance.common import utils
from glance.tests import utils as test_utils


class TestStoreUtils(test_utils.BaseTestCase):
    """Test glance.common.store_utils module"""

    def _test_update_store_in_location(self, metadata, store_id, expected,
                                       store_id_call_count=1,
                                       save_call_count=1):
        image = mock.Mock()
        image_repo = mock.Mock()
        image_repo.save = mock.Mock()
        locations = [{
            'url': 'rbd://aaaaaaaa/images/id',
            'metadata': metadata
        }]
        image.locations = locations
        with mock.patch.object(
                store_utils, '_get_store_id_from_uri') as mock_get_store_id:
            mock_get_store_id.return_value = store_id
            store_utils.update_store_in_locations(image, image_repo)
            self.assertEqual(image.locations[0]['metadata'].get(
                'store'), expected)
            self.assertEqual(store_id_call_count, mock_get_store_id.call_count)
            self.assertEqual(save_call_count, image_repo.save.call_count)

    def test_update_store_location_with_no_store(self):
        enabled_backends = {
            "rbd1": "rbd",
            "rbd2": "rbd"
        }
        self.config(enabled_backends=enabled_backends)
        self._test_update_store_in_location({}, 'rbd1', 'rbd1')

    def test_update_store_location_with_different_store(self):
        enabled_backends = {
            "ceph1": "rbd",
            "ceph2": "rbd"
        }
        self.config(enabled_backends=enabled_backends)
        self._test_update_store_in_location(
            {'store': 'rbd2'}, 'ceph1', 'ceph1')

    def test_update_store_location_with_same_store(self):
        enabled_backends = {
            "rbd1": "rbd",
            "rbd2": "rbd"
        }
        self.config(enabled_backends=enabled_backends)
        self._test_update_store_in_location({'store': 'rbd1'}, 'rbd1', 'rbd1',
                                            store_id_call_count=0,
                                            save_call_count=0)

    def test_update_store_location_with_store_none(self):
        enabled_backends = {
            "rbd1": "rbd",
            "rbd2": "rbd"
        }
        self.config(enabled_backends=enabled_backends)
        self._test_update_store_in_location({}, None, None,
                                            save_call_count=0)


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
        data = b'abcdefgh'
        data_list = [data[i:i + 1] * 3 for i in range(len(data))]
        reader = utils.CooperativeReader(data_list)
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == b'':
                break
        meat = b''.join(chunks)
        self.assertEqual(b'aaabbbcccdddeeefffggghhh', meat)

    def test_cooperative_reader_unbounded_read_on_iterator(self):
        """Ensure cooperative reader is happy with empty iterators"""
        data = b'abcdefgh'
        data_list = [data[i:i + 1] * 3 for i in range(len(data))]
        reader = utils.CooperativeReader(data_list)
        self.assertEqual(
            [chunk for chunk in iter(lambda: reader.read(), b'')],
            [b'aaa', b'bbb', b'ccc', b'ddd', b'eee', b'fff', b'ggg', b'hhh'])

    def test_cooperative_reader_on_iterator_with_buffer(self):
        """Ensure cooperative reader is happy with empty iterators"""
        data_list = [b'abcd', b'efgh']
        reader = utils.CooperativeReader(data_list)
        # read from part of a chunk, get the first item into the buffer
        self.assertEqual(b'ab', reader.read(2))
        # read purely from buffer
        self.assertEqual(b'c', reader.read(1))
        # unbounded read grabs the rest of the buffer
        self.assertEqual(b'd', reader.read())
        # then the whole next chunk
        self.assertEqual(b'efgh', reader.read())
        # past that, it's always empty
        self.assertEqual(b'', reader.read())

    def test_cooperative_reader_unbounded_read_on_empty_iterator(self):
        """Ensure cooperative reader is happy with empty iterators"""
        reader = utils.CooperativeReader([])
        self.assertEqual(b'', reader.read())

    def test_cooperative_reader_of_iterator_stop_iteration_err(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in ''])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == b'':
                break
        meat = b''.join(chunks)
        self.assertEqual(b'', meat)

    def _create_generator(self, chunk_size, max_iterations):
        chars = b'abc'
        iteration = 0
        while True:
            index = iteration % len(chars)
            chunk = chars[index:index + 1] * chunk_size
            yield chunk
            iteration += 1
            if iteration >= max_iterations:
                return

    def _test_reader_chunked(self, chunk_size, read_size, max_iterations=5):
        generator = self._create_generator(chunk_size, max_iterations)
        reader = utils.CooperativeReader(generator)
        result = bytearray()
        while True:
            data = reader.read(read_size)
            if len(data) == 0:
                break
            self.assertLessEqual(len(data), read_size)
            result += data
        expected = (b'a' * chunk_size +
                    b'b' * chunk_size +
                    b'c' * chunk_size +
                    b'a' * chunk_size +
                    b'b' * chunk_size)
        self.assertEqual(expected, bytes(result))

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
            self.assertGreater(port, 0)

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


class SplitFilterOpTestCase(test_utils.BaseTestCase):

    def test_less_than_operator(self):
        expr = 'lt:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('lt', 'bar'), returned)

    def test_less_than_equal_operator(self):
        expr = 'lte:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('lte', 'bar'), returned)

    def test_greater_than_operator(self):
        expr = 'gt:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('gt', 'bar'), returned)

    def test_greater_than_equal_operator(self):
        expr = 'gte:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('gte', 'bar'), returned)

    def test_not_equal_operator(self):
        expr = 'neq:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('neq', 'bar'), returned)

    def test_equal_operator(self):
        expr = 'eq:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('eq', 'bar'), returned)

    def test_in_operator(self):
        expr = 'in:bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('in', 'bar'), returned)

    def test_split_filter_value_for_quotes(self):
        expr = '\"fake\\\"name\",fakename,\"fake,name\"'
        returned = utils.split_filter_value_for_quotes(expr)
        list_values = ['fake\\"name', 'fakename', 'fake,name']
        self.assertEqual(list_values, returned)

    def test_validate_quotes(self):
        expr = '\"aaa\\\"aa\",bb,\"cc\"'
        returned = utils.validate_quotes(expr)
        self.assertIsNone(returned)

        invalid_expr = ['\"aa', 'ss\"', 'aa\"bb\"cc', '\"aa\"\"bb\"']
        for expr in invalid_expr:
            self.assertRaises(exception.InvalidParameterValue,
                              utils.validate_quotes,
                              expr)

    def test_default_operator(self):
        expr = 'bar'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('eq', expr), returned)

    def test_default_operator_with_datetime(self):
        expr = '2015-08-27T09:49:58Z'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('eq', expr), returned)

    def test_operator_with_datetime(self):
        expr = 'lt:2015-08-27T09:49:58Z'
        returned = utils.split_filter_op(expr)
        self.assertEqual(('lt', '2015-08-27T09:49:58Z'), returned)


class EvaluateFilterOpTestCase(test_utils.BaseTestCase):

    def test_less_than_operator(self):
        self.assertTrue(utils.evaluate_filter_op(9, 'lt', 10))
        self.assertFalse(utils.evaluate_filter_op(10, 'lt', 10))
        self.assertFalse(utils.evaluate_filter_op(11, 'lt', 10))

    def test_less_than_equal_operator(self):
        self.assertTrue(utils.evaluate_filter_op(9, 'lte', 10))
        self.assertTrue(utils.evaluate_filter_op(10, 'lte', 10))
        self.assertFalse(utils.evaluate_filter_op(11, 'lte', 10))

    def test_greater_than_operator(self):
        self.assertFalse(utils.evaluate_filter_op(9, 'gt', 10))
        self.assertFalse(utils.evaluate_filter_op(10, 'gt', 10))
        self.assertTrue(utils.evaluate_filter_op(11, 'gt', 10))

    def test_greater_than_equal_operator(self):
        self.assertFalse(utils.evaluate_filter_op(9, 'gte', 10))
        self.assertTrue(utils.evaluate_filter_op(10, 'gte', 10))
        self.assertTrue(utils.evaluate_filter_op(11, 'gte', 10))

    def test_not_equal_operator(self):
        self.assertTrue(utils.evaluate_filter_op(9, 'neq', 10))
        self.assertFalse(utils.evaluate_filter_op(10, 'neq', 10))
        self.assertTrue(utils.evaluate_filter_op(11, 'neq', 10))

    def test_equal_operator(self):
        self.assertFalse(utils.evaluate_filter_op(9, 'eq', 10))
        self.assertTrue(utils.evaluate_filter_op(10, 'eq', 10))
        self.assertFalse(utils.evaluate_filter_op(11, 'eq', 10))

    def test_invalid_operator(self):
        self.assertRaises(exception.InvalidFilterOperatorValue,
                          utils.evaluate_filter_op, '10', 'bar', '8')


class ImportURITestCase(test_utils.BaseTestCase):

    def test_validate_import_uri(self):
        self.assertTrue(utils.validate_import_uri("http://foo.com"))

        self.config(allowed_schemes=['http'],
                    group='import_filtering_opts')
        self.config(allowed_hosts=['example.com'],
                    group='import_filtering_opts')
        self.assertTrue(utils.validate_import_uri("http://example.com"))

        self.config(allowed_ports=['8080'],
                    group='import_filtering_opts')
        self.assertTrue(utils.validate_import_uri("http://example.com:8080"))

    def test_invalid_import_uri(self):
        self.assertFalse(utils.validate_import_uri(""))

        self.assertFalse(utils.validate_import_uri("fake_uri"))
        self.config(disallowed_schemes=['ftp'],
                    group='import_filtering_opts')
        self.assertFalse(utils.validate_import_uri("ftp://example.com"))

        self.config(disallowed_hosts=['foo.com'],
                    group='import_filtering_opts')
        self.assertFalse(utils.validate_import_uri("ftp://foo.com"))

        self.config(disallowed_ports=['8484'],
                    group='import_filtering_opts')
        self.assertFalse(utils.validate_import_uri("http://localhost:8484"))

    def test_ignored_filtering_options(self):
        LOG = logging.getLogger('glance.common.utils')
        with mock.patch.object(LOG, 'debug') as mock_run:
            self.config(allowed_schemes=['https', 'ftp'],
                        group='import_filtering_opts')
            self.config(disallowed_schemes=['ftp'],
                        group='import_filtering_opts')
            self.assertTrue(utils.validate_import_uri("ftp://foo.com"))
            mock_run.assert_called_once()
        with mock.patch.object(LOG, 'debug') as mock_run:
            self.config(allowed_schemes=[],
                        group='import_filtering_opts')
            self.config(disallowed_schemes=[],
                        group='import_filtering_opts')
            self.config(allowed_hosts=['example.com', 'foo.com'],
                        group='import_filtering_opts')
            self.config(disallowed_hosts=['foo.com'],
                        group='import_filtering_opts')
            self.assertTrue(utils.validate_import_uri("ftp://foo.com"))
            mock_run.assert_called_once()
        with mock.patch.object(LOG, 'debug') as mock_run:
            self.config(allowed_hosts=[],
                        group='import_filtering_opts')
            self.config(disallowed_hosts=[],
                        group='import_filtering_opts')
            self.config(allowed_ports=[8080, 8484],
                        group='import_filtering_opts')
            self.config(disallowed_ports=[8484],
                        group='import_filtering_opts')
            self.assertTrue(utils.validate_import_uri("ftp://foo.com:8484"))
            mock_run.assert_called_once()
