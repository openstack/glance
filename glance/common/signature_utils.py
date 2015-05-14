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

"""Support signature verification."""

import base64

from castellan import key_manager
from cryptography import exceptions as crypto_exception
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from oslo_log import log as logging
from oslo_utils import encodeutils

from glance.common import exception
from glance import i18n

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


# Note: This is the signature hash method, which is independent from the
# image data checksum hash method (which is handled elsewhere).
HASH_METHODS = {
    'SHA-224': hashes.SHA224(),
    'SHA-256': hashes.SHA256(),
    'SHA-384': hashes.SHA384(),
    'SHA-512': hashes.SHA512()
}

# These are the currently supported signature formats
(RSA_PSS,) = (
    'RSA-PSS',
)

SIGNATURE_KEY_TYPES = {
    RSA_PSS
}

# These are the currently supported certificate formats
(X_509,) = (
    'X.509',
)

CERTIFICATE_FORMATS = {
    X_509
}

# These are the currently supported MGF formats, used for RSA-PSS signatures
MASK_GEN_ALGORITHMS = {
    'MGF1': padding.MGF1
}

# Required image property names
(SIGNATURE, HASH_METHOD, KEY_TYPE, CERT_UUID) = (
    'signature',
    'signature_hash_method',
    'signature_key_type',
    'signature_certificate_uuid'
)

# Optional image property names for RSA-PSS
(MASK_GEN_ALG, PSS_SALT_LENGTH) = (
    'mask_gen_algorithm',
    'pss_salt_length'
)


def should_verify_signature(image_properties):
    """Determine whether a signature should be verified.

    Using the image properties, determine whether existing properties indicate
    that signature verification should be done.

    :param image_properties: the key-value properties about the image
    :return: True, if signature metadata properties exist, False otherwise
    """
    return (image_properties is not None and
            CERT_UUID in image_properties and
            HASH_METHOD in image_properties and
            SIGNATURE in image_properties and
            KEY_TYPE in image_properties)


def verify_signature(context, checksum_hash, image_properties):
    """Retrieve the image properties and use them to verify the signature.

    :param context: the user context for authentication
    :param checksum_hash: the 'checksum' hash of the image data
    :param image_properties: the key-value properties about the image
    :return: True if verification succeeds
    :raises: SignatureVerificationError if verification fails
    """
    if not should_verify_signature(image_properties):
        raise exception.SignatureVerificationError(
            'Required image properties for signature verification do not'
            ' exist. Cannot verify signature.')

    signature = get_signature(image_properties[SIGNATURE])
    hash_method = get_hash_method(image_properties[HASH_METHOD])
    signature_key_type = get_signature_key_type(
        image_properties[KEY_TYPE])
    public_key = get_public_key(context,
                                image_properties[CERT_UUID],
                                signature_key_type)

    # Initialize the verifier
    verifier = None

    # create the verifier based on the signature key type
    if signature_key_type == RSA_PSS:
        # retrieve other needed properties, or use defaults if not there
        if MASK_GEN_ALG in image_properties:
            mask_gen_algorithm = image_properties[MASK_GEN_ALG]
            if mask_gen_algorithm in MASK_GEN_ALGORITHMS:
                mgf = MASK_GEN_ALGORITHMS[mask_gen_algorithm](hash_method)
            else:
                raise exception.SignatureVerificationError(
                    'Invalid mask_gen_algorithm: %s' % mask_gen_algorithm)
        else:
            # default to MGF1
            mgf = padding.MGF1(hash_method)
        if PSS_SALT_LENGTH in image_properties:
            pss_salt_length = image_properties[PSS_SALT_LENGTH]
            try:
                salt_length = int(pss_salt_length)
            except ValueError:
                raise exception.SignatureVerificationError(
                    'Invalid pss_salt_length: %s' % pss_salt_length)
        else:
            # default to max salt length
            salt_length = padding.PSS.MAX_LENGTH
        # Create the verifier
        verifier = public_key.verifier(
            signature,
            padding.PSS(
                mgf=mgf,
                salt_length=salt_length
            ),
            hash_method
        )

    if verifier:
        # Verify the signature
        verifier.update(checksum_hash)
        try:
            verifier.verify()
            return True
        except crypto_exception.InvalidSignature:
            raise exception.SignatureVerificationError(
                'Signature verification failed.')
    else:
        # Error creating the verifier
        raise exception.SignatureVerificationError(
            'Error occurred while verifying the signature')


def get_signature(signature_data):
    """Decode the signature data and returns the signature.

    :param siganture_data: the base64-encoded signature data
    :return: the decoded signature
    :raises: SignatureVerificationError if the signature data is malformatted
    """
    try:
        signature = base64.b64decode(signature_data)
    except TypeError:
        raise exception.SignatureVerificationError(
            'The signature data was not properly encoded using base64')

    return signature


def get_hash_method(hash_method_name):
    """Verify the hash method name and create the hash method.

    :param hash_method_name: the name of the hash method to retrieve
    :return: the hash method, a cryptography object
    :raises: SignatureVerificationError if the hash method name is invalid
    """
    if hash_method_name not in HASH_METHODS:
        raise exception.SignatureVerificationError(
            'Invalid signature hash method: %s' % hash_method_name)

    return HASH_METHODS[hash_method_name]


def get_signature_key_type(signature_key_type):
    """Verify the signature key type.

    :param signature_key_type: the key type of the signature
    :return: the validated signature key type
    :raises: SignatureVerificationError if the signature key type is invalid
    """
    if signature_key_type not in SIGNATURE_KEY_TYPES:
        raise exception.SignatureVerificationError(
            'Invalid signature key type: %s' % signature_key_type)

    return signature_key_type


def get_public_key(context, signature_certificate_uuid, signature_key_type):
    """Create the public key object from a retrieved certificate.

    :param context: the user context for authentication
    :param signature_certificate_uuid: the uuid to use to retrieve the
                                       certificate
    :param signature_key_type: the key type of the signature
    :return: the public key cryptography object
    :raises: SignatureVerificationError if public key format is invalid
    """
    certificate = get_certificate(context, signature_certificate_uuid)

    # Note that this public key could either be
    # RSAPublicKey, DSAPublicKey, or EllipticCurvePublicKey
    public_key = certificate.public_key()

    # Confirm the type is of the type expected based on the signature key type
    if signature_key_type == RSA_PSS:
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise exception.SignatureVerificationError(
                'Invalid public key type for signature key type: %s'
                % signature_key_type)

    return public_key


def get_certificate(context, signature_certificate_uuid):
    """Create the certificate object from the retrieved certificate data.

    :param context: the user context for authentication
    :param signature_certificate_uuid: the uuid to use to retrieve the
                                       certificate
    :return: the certificate cryptography object
    :raises: SignatureVerificationError if the retrieval fails or the format
             is invalid
    """
    keymgr_api = key_manager.API()

    try:
        # The certificate retrieved here is a castellan certificate object
        cert = keymgr_api.get(context, signature_certificate_uuid)
    except Exception as e:
        # The problem encountered may be backend-specific, since castellan
        # can use different backends.  Rather than importing all possible
        # backends here, the generic "Exception" is used.
        msg = (_LE("Unable to retrieve certificate with ID %(id)s: %(e)s")
               % {'id': signature_certificate_uuid,
                  'e': encodeutils.exception_to_unicode(e)})
        LOG.error(msg)
        raise exception.SignatureVerificationError(
            'Unable to retrieve certificate with ID: %s'
            % signature_certificate_uuid)

    if cert.format not in CERTIFICATE_FORMATS:
        raise exception.SignatureVerificationError(
            'Invalid certificate format: %s' % cert.format)

    if cert.format == X_509:
        # castellan always encodes certificates in DER format
        cert_data = cert.get_encoded()
        certificate = x509.load_der_x509_certificate(cert_data,
                                                     default_backend())

    return certificate
