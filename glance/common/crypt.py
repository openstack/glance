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

"""
Routines for URL-safe encrypting/decrypting
"""

import base64
import os
import random

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import modes
from oslo_utils import encodeutils
import six
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range


def urlsafe_encrypt(key, plaintext, blocksize=16):
    """
    Encrypts plaintext. Resulting ciphertext will contain URL-safe characters.
    If plaintext is Unicode, encode it to UTF-8 before encryption.

    :param key: AES secret key
    :param plaintext: Input text to be encrypted
    :param blocksize: Non-zero integer multiple of AES blocksize in bytes (16)

    :returns: Resulting ciphertext
    """
    def pad(text):
        """
        Pads text to be encrypted
        """
        pad_length = (blocksize - len(text) % blocksize)
        # NOTE(rosmaita): I know this looks stupid, but we can't just
        # use os.urandom() to get the bytes because we use char(0) as
        # a delimiter
        pad = b''.join(six.int2byte(random.SystemRandom().randint(1, 0xFF))
                       for i in range(pad_length - 1))
        # We use chr(0) as a delimiter between text and padding
        return text + b'\0' + pad

    plaintext = encodeutils.to_utf8(plaintext)
    key = encodeutils.to_utf8(key)
    # random initial 16 bytes for CBC
    init_vector = os.urandom(16)
    backend = default_backend()
    cypher = Cipher(algorithms.AES(key), modes.CBC(init_vector),
                    backend=backend)
    encryptor = cypher.encryptor()
    padded = encryptor.update(
        pad(six.binary_type(plaintext))) + encryptor.finalize()
    encoded = base64.urlsafe_b64encode(init_vector + padded)
    if six.PY3:
        encoded = encoded.decode('ascii')
    return encoded


def urlsafe_decrypt(key, ciphertext):
    """
    Decrypts URL-safe base64 encoded ciphertext.
    On Python 3, the result is decoded from UTF-8.

    :param key: AES secret key
    :param ciphertext: The encrypted text to decrypt

    :returns: Resulting plaintext
    """
    # Cast from unicode
    ciphertext = encodeutils.to_utf8(ciphertext)
    key = encodeutils.to_utf8(key)
    ciphertext = base64.urlsafe_b64decode(ciphertext)
    backend = default_backend()
    cypher = Cipher(algorithms.AES(key), modes.CBC(ciphertext[:16]),
                    backend=backend)
    decryptor = cypher.decryptor()
    padded = decryptor.update(ciphertext[16:]) + decryptor.finalize()
    text = padded[:padded.rfind(b'\0')]
    if six.PY3:
        text = text.decode('utf-8')
    return text
