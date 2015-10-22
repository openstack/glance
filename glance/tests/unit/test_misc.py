# Copyright 2010-2011 OpenStack Foundation
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

import six
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range

from glance.common import crypt
from glance.common import utils
from glance.tests import utils as test_utils


class UtilsTestCase(test_utils.BaseTestCase):

    def test_encryption(self):
        # Check that original plaintext and unencrypted ciphertext match
        # Check keys of the three allowed lengths
        key_list = ["1234567890abcdef",
                    "12345678901234567890abcd",
                    "1234567890abcdef1234567890ABCDEF"]
        plaintext_list = ['']
        blocksize = 64
        for i in range(3 * blocksize):
            text = os.urandom(i)
            if six.PY3:
                text = text.decode('latin1')
            plaintext_list.append(text)

        for key in key_list:
            for plaintext in plaintext_list:
                ciphertext = crypt.urlsafe_encrypt(key, plaintext, blocksize)
                self.assertIsInstance(ciphertext, str)
                self.assertNotEqual(ciphertext, plaintext)
                text = crypt.urlsafe_decrypt(key, ciphertext)
                self.assertIsInstance(text, str)
                self.assertEqual(plaintext, text)

    def test_empty_metadata_headers(self):
        """Ensure unset metadata is not encoded in HTTP headers"""

        metadata = {
            'foo': 'bar',
            'snafu': None,
            'bells': 'whistles',
            'unset': None,
            'empty': '',
            'properties': {
                'distro': '',
                'arch': None,
                'user': 'nobody',
            },
        }

        headers = utils.image_meta_to_http_headers(metadata)

        self.assertNotIn('x-image-meta-snafu', headers)
        self.assertNotIn('x-image-meta-uset', headers)
        self.assertNotIn('x-image-meta-snafu', headers)
        self.assertNotIn('x-image-meta-property-arch', headers)

        self.assertEqual('bar', headers.get('x-image-meta-foo'))
        self.assertEqual('whistles', headers.get('x-image-meta-bells'))
        self.assertEqual('', headers.get('x-image-meta-empty'))
        self.assertEqual('', headers.get('x-image-meta-property-distro'))
        self.assertEqual('nobody', headers.get('x-image-meta-property-user'))
