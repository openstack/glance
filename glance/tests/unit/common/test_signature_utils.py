# Copyright (c) The Johns Hopkins University/Applied Physics Laboratory
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

import base64
import datetime
import mock

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from debtcollector import removals

from glance.common import exception
from glance.common import signature_utils
from glance.tests import utils as test_utils

TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=3,
                                            key_size=1024,
                                            backend=default_backend())

# Required image property names
# TODO(bpoulos): remove when 'sign-the-hash' approach is no longer supported
(OLD_SIGNATURE, OLD_HASH_METHOD, OLD_KEY_TYPE, OLD_CERT_UUID) = (
    signature_utils.OLD_SIGNATURE,
    signature_utils.OLD_HASH_METHOD,
    signature_utils.OLD_KEY_TYPE,
    signature_utils.OLD_CERT_UUID
)

# Optional image property names for RSA-PSS
(MASK_GEN_ALG, PSS_SALT_LENGTH) = (
    signature_utils.MASK_GEN_ALG,
    signature_utils.PSS_SALT_LENGTH
)


class FakeKeyManager(object):

    def __init__(self):
        self.certs = {'invalid_format_cert':
                      FakeCastellanCertificate('A' * 256, 'BLAH'),
                      'valid_format_cert':
                      FakeCastellanCertificate('A' * 256, 'X.509')}

    def get(self, context, cert_uuid):
        cert = self.certs.get(cert_uuid)

        if cert is None:
            raise Exception("No matching certificate found.")

        return cert


class FakeCastellanCertificate(object):

    def __init__(self, data, cert_format):
        self.data = data
        self.cert_format = cert_format

    @property
    def format(self):
        return self.cert_format

    def get_encoded(self):
        return self.data


class FakeCryptoCertificate(object):

    def __init__(self, pub_key=TEST_PRIVATE_KEY.public_key(),
                 not_valid_before=(datetime.datetime.utcnow() -
                                   datetime.timedelta(hours=1)),
                 not_valid_after=(datetime.datetime.utcnow() +
                                  datetime.timedelta(hours=1))):
        self.pub_key = pub_key
        self.cert_not_valid_before = not_valid_before
        self.cert_not_valid_after = not_valid_after

    def public_key(self):
        return self.pub_key

    @property
    def not_valid_before(self):
        return self.cert_not_valid_before

    @property
    def not_valid_after(self):
        return self.cert_not_valid_after


class BadPublicKey(object):

    def verifier(self, signature, padding, hash_method):
        return None


class TestSignatureUtils(test_utils.BaseTestCase):
    """Test methods of signature_utils"""

    @removals.remove(message="This will be removed in the N cycle.")
    def test_old_should_verify_signature(self):
        image_props = {OLD_CERT_UUID: 'OLD_CERT_UUID',
                       OLD_HASH_METHOD: 'OLD_HASH_METHOD',
                       OLD_SIGNATURE: 'OLD_SIGNATURE',
                       OLD_KEY_TYPE: 'SIG_KEY_TYPE'}
        self.assertTrue(signature_utils.should_verify_signature(image_props))

    @removals.remove(message="This will be removed in the N cycle.")
    def test_old_should_verify_signature_fail(self):
        bad_image_properties = [{OLD_CERT_UUID: 'OLD_CERT_UUID',
                                 OLD_HASH_METHOD: 'OLD_HASH_METHOD',
                                 OLD_SIGNATURE: 'OLD_SIGNATURE'},
                                {OLD_CERT_UUID: 'OLD_CERT_UUID',
                                 OLD_HASH_METHOD: 'OLD_HASH_METHOD',
                                 OLD_KEY_TYPE: 'SIG_KEY_TYPE'},
                                {OLD_CERT_UUID: 'OLD_CERT_UUID',
                                 OLD_SIGNATURE: 'OLD_SIGNATURE',
                                 OLD_KEY_TYPE: 'SIG_KEY_TYPE'},
                                {OLD_HASH_METHOD: 'OLD_HASH_METHOD',
                                 OLD_SIGNATURE: 'OLD_SIGNATURE',
                                 OLD_KEY_TYPE: 'SIG_KEY_TYPE'}]

        for bad_props in bad_image_properties:
            result = signature_utils.should_verify_signature(bad_props)
            self.assertFalse(result)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_PSS(self, mock_get_pub_key):
        checksum_hash = b'224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        for hash_name, hash_alg in signature_utils.HASH_METHODS.items():
            signer = TEST_PRIVATE_KEY.signer(
                padding.PSS(
                    mgf=padding.MGF1(hash_alg),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hash_alg
            )
            signer.update(checksum_hash)
            signature = base64.b64encode(signer.finalize())
            image_props = {OLD_CERT_UUID:
                           'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                           OLD_HASH_METHOD: hash_name,
                           OLD_KEY_TYPE: 'RSA-PSS',
                           MASK_GEN_ALG: 'MGF1',
                           OLD_SIGNATURE: signature}
            self.assertTrue(signature_utils.verify_signature(None,
                                                             checksum_hash,
                                                             image_props))

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_custom_PSS_salt(self, mock_get_pub_key):
        checksum_hash = b'224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        custom_salt_length = 32
        for hash_name, hash_alg in signature_utils.HASH_METHODS.items():
            signer = TEST_PRIVATE_KEY.signer(
                padding.PSS(
                    mgf=padding.MGF1(hash_alg),
                    salt_length=custom_salt_length
                ),
                hash_alg
            )
            signer.update(checksum_hash)
            signature = base64.b64encode(signer.finalize())
            image_props = {OLD_CERT_UUID:
                           'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                           OLD_HASH_METHOD: hash_name,
                           OLD_KEY_TYPE: 'RSA-PSS',
                           MASK_GEN_ALG: 'MGF1',
                           PSS_SALT_LENGTH: custom_salt_length,
                           OLD_SIGNATURE: signature}
            self.assertTrue(signature_utils.verify_signature(None,
                                                             checksum_hash,
                                                             image_props))

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_bad_signature(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'RSA-PSS',
                            MASK_GEN_ALG: 'MGF1',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Signature verification failed.',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.should_verify_signature')
    def test_old_verify_signature_invalid_image_props(self, mock_should):
        mock_should.return_value = False
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Required image properties for signature'
                                ' verification do not exist. Cannot verify'
                                ' signature.',
                                signature_utils.verify_signature,
                                None, None, None)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_bad_sig_key_type(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'BLAH',
                            MASK_GEN_ALG: 'MGF1',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid signature key type: .*',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_RSA_no_mask_gen(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'RSA-PSS',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Signature verification failed.',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_RSA_bad_mask_gen(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'RSA-PSS',
                            MASK_GEN_ALG: 'BLAH',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid mask_gen_algorithm: .*',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_bad_pss_salt(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = TEST_PRIVATE_KEY.public_key()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'RSA-PSS',
                            MASK_GEN_ALG: 'MGF1',
                            PSS_SALT_LENGTH: 'BLAH',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid pss_salt_length: .*',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    @removals.remove(message="This will be removed in the N cycle.")
    @mock.patch('glance.common.signature_utils.get_public_key')
    def test_old_verify_signature_verifier_none(self, mock_get_pub_key):
        checksum_hash = '224626ae19824466f2a7f39ab7b80f7f'
        mock_get_pub_key.return_value = BadPublicKey()
        image_properties = {OLD_CERT_UUID:
                            'fea14bc2-d75f-4ba5-bccc-b5c924ad0693',
                            OLD_HASH_METHOD: 'SHA-256',
                            OLD_KEY_TYPE: 'RSA-PSS',
                            MASK_GEN_ALG: 'MGF1',
                            OLD_SIGNATURE: 'BLAH'}
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Error occurred while verifying'
                                ' the signature',
                                signature_utils.verify_signature,
                                None, checksum_hash, image_properties)

    def test_get_signature(self):
        signature = b'A' * 256
        data = base64.b64encode(signature)
        self.assertEqual(signature,
                         signature_utils.get_signature(data))

    def test_get_signature_fail(self):
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'The signature data was not properly'
                                ' encoded using base64',
                                signature_utils.get_signature, '///')

    def test_get_hash_method(self):
        hash_dict = signature_utils.HASH_METHODS
        for hash_name in hash_dict.keys():
            hash_class = signature_utils.get_hash_method(hash_name).__class__
            self.assertIsInstance(hash_dict[hash_name], hash_class)

    def test_get_hash_method_fail(self):
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid signature hash method: .*',
                                signature_utils.get_hash_method, 'SHA-2')

    def test_get_signature_key_type(self):
        for sig_format in signature_utils.SIGNATURE_KEY_TYPES:
            result = signature_utils.get_signature_key_type(sig_format)
            self.assertEqual(sig_format, result)

    def test_get_signature_key_type_fail(self):
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid signature key type: .*',
                                signature_utils.get_signature_key_type,
                                'RSB-PSS')

    @mock.patch('glance.common.signature_utils.get_certificate')
    def test_get_public_key(self, mock_get_cert):
        fake_cert = FakeCryptoCertificate()
        mock_get_cert.return_value = fake_cert
        result_pub_key = signature_utils.get_public_key(None, None, 'RSA-PSS')
        self.assertEqual(fake_cert.public_key(), result_pub_key)

    @mock.patch('glance.common.signature_utils.get_certificate')
    def test_get_public_key_invalid_key(self, mock_get_certificate):
        bad_pub_key = 'A' * 256
        mock_get_certificate.return_value = FakeCryptoCertificate(bad_pub_key)
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid public key type for '
                                'signature key type: .*',
                                signature_utils.get_public_key, None,
                                None, 'RSA-PSS')

    @mock.patch('cryptography.x509.load_der_x509_certificate')
    @mock.patch('castellan.key_manager.API', return_value=FakeKeyManager())
    def test_get_certificate(self, mock_key_manager_API, mock_load_cert):
        cert_uuid = 'valid_format_cert'
        x509_cert = FakeCryptoCertificate()
        mock_load_cert.return_value = x509_cert
        self.assertEqual(x509_cert,
                         signature_utils.get_certificate(None, cert_uuid))

    @mock.patch('cryptography.x509.load_der_x509_certificate')
    @mock.patch('castellan.key_manager.API', return_value=FakeKeyManager())
    def test_get_expired_certificate(self, mock_key_manager_API,
                                     mock_load_cert):
        cert_uuid = 'valid_format_cert'
        x509_cert = FakeCryptoCertificate(
            not_valid_after=datetime.datetime.utcnow() -
            datetime.timedelta(hours=1))
        mock_load_cert.return_value = x509_cert
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Certificate is not valid after: .*',
                                signature_utils.get_certificate, None,
                                cert_uuid)

    @mock.patch('cryptography.x509.load_der_x509_certificate')
    @mock.patch('castellan.key_manager.API', return_value=FakeKeyManager())
    def test_get_not_yet_valid_certificate(self, mock_key_manager_API,
                                           mock_load_cert):
        cert_uuid = 'valid_format_cert'
        x509_cert = FakeCryptoCertificate(
            not_valid_before=datetime.datetime.utcnow() +
            datetime.timedelta(hours=1))
        mock_load_cert.return_value = x509_cert
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Certificate is not valid before: .*',
                                signature_utils.get_certificate, None,
                                cert_uuid)

    @mock.patch('castellan.key_manager.API', return_value=FakeKeyManager())
    def test_get_certificate_key_manager_fail(self, mock_key_manager_API):
        bad_cert_uuid = 'fea14bc2-d75f-4ba5-bccc-b5c924ad0695'
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Unable to retrieve certificate with ID: .*',
                                signature_utils.get_certificate, None,
                                bad_cert_uuid)

    @mock.patch('castellan.key_manager.API', return_value=FakeKeyManager())
    def test_get_certificate_invalid_format(self, mock_API):
        cert_uuid = 'invalid_format_cert'
        self.assertRaisesRegexp(exception.SignatureVerificationError,
                                'Invalid certificate format: .*',
                                signature_utils.get_certificate, None,
                                cert_uuid)
