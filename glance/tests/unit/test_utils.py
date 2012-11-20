# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

import StringIO
import tempfile

from glance.common import exception
from glance.common import utils
from glance.tests import utils as test_utils


class TestUtils(test_utils.BaseTestCase):
    """Test routines in glance.utils"""

    def test_generate_uuid_format(self):
        """Check the format of a uuid"""
        uuid = utils.generate_uuid()
        self.assertTrue(isinstance(uuid, basestring))
        self.assertTrue(len(uuid), 36)
        # make sure there are 4 dashes
        self.assertTrue(len(uuid.replace('-', '')), 36)

    def test_generate_uuid_unique(self):
        """Ensure generate_uuid will return unique values"""
        uuids = [utils.generate_uuid() for i in range(5)]
        # casting to set will drop duplicate values
        unique = set(uuids)
        self.assertEqual(len(uuids), len(list(unique)))

    def test_is_uuid_like_success(self):
        fixture = 'b694bf02-6b01-4905-a50e-fcf7bce7e4d2'
        self.assertTrue(utils.is_uuid_like(fixture))

    def test_is_uuid_like_fails(self):
        fixture = 'pants'
        self.assertFalse(utils.is_uuid_like(fixture))

    def test_cooperative_reader(self):
        """Ensure cooperative reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            for chunk in utils.CooperativeReader(tmp_fd):
                bytes_read += len(chunk)

        self.assertEquals(bytes_read, BYTES)

        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            reader = utils.CooperativeReader(tmp_fd)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertEquals(bytes_read, BYTES)

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

    def test_limiting_reader(self):
        """Ensure limiting reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        data = StringIO.StringIO("*" * BYTES)
        for chunk in utils.LimitingReader(data, BYTES):
            bytes_read += len(chunk)

        self.assertEquals(bytes_read, BYTES)

        bytes_read = 0
        data = StringIO.StringIO("*" * BYTES)
        reader = utils.LimitingReader(data, BYTES)
        byte = reader.read(1)
        while len(byte) != 0:
            bytes_read += 1
            byte = reader.read(1)

        self.assertEquals(bytes_read, BYTES)

    def test_limiting_reader_fails(self):
        """Ensure limiting reader class throws exceptions if limit exceeded"""
        BYTES = 1024

        def _consume_all_iter():
            bytes_read = 0
            data = StringIO.StringIO("*" * BYTES)
            for chunk in utils.LimitingReader(data, BYTES - 1):
                bytes_read += len(chunk)

        self.assertRaises(exception.ImageSizeLimitExceeded, _consume_all_iter)

        def _consume_all_read():
            bytes_read = 0
            data = StringIO.StringIO("*" * BYTES)
            reader = utils.LimitingReader(data, BYTES - 1)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertRaises(exception.ImageSizeLimitExceeded, _consume_all_read)
