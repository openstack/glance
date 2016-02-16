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

import binascii
import datetime

from castellan import key_manager
from cryptography import exceptions as crypto_exception
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography import x509
import debtcollector
from oslo_log import log as logging
from oslo_serialization import base64
from oslo_utils import encodeutils

from glance.common import exception
from glance.i18n import _LE

LOG = logging.getLogger(__name__)


# Note: This is the signature hash method, which is independent from the
# image data checksum hash method (which is handled elsewhere).
HASH_METHODS = {
    'SHA-224': hashes.SHA224(),
    'SHA-256': hashes.SHA256(),
    'SHA-384': hashes.SHA384(),
    'SHA-512': hashes.SHA512()
}

# These are the currently supported signature key types
(RSA_PSS,) = (
    'RSA-PSS',
)

# This includes the supported public key type for the signature key type
SIGNATURE_KEY_TYPES = {
    RSA_PSS: rsa.RSAPublicKey
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
# TODO(bpoulos): remove when 'sign-the-hash' approach is no longer supported
(OLD_SIGNATURE, OLD_HASH_METHOD, OLD_KEY_TYPE, OLD_CERT_UUID) = (
    'signature',
    'signature_hash_method',
    'signature_key_type',
    'signature_certificate_uuid'
)

# Optional image property names for RSA-PSS
# TODO(bpoulos): remove when 'sign-the-hash' approach is no longer supported
(MASK_GEN_ALG, PSS_SALT_LENGTH) = (
    'mask_gen_algorithm',
    'pss_salt_length'
)


# each key type will require its own verifier
def create_verifier_for_pss(signature, hash_method, public_key,
                            image_properties):
    """Create the verifier to use when the key type is RSA-PSS.

    :param signature: the decoded signature to use
    :param hash_method: the hash method to use, as a cryptography object
    :param public_key: the public key to use, as a cryptography object
    :param image_properties: the key-value properties about the image
    :returns: the verifier to use to verify the signature for RSA-PSS
    :raises: SignatureVerificationError if the RSA-PSS specific properties
                                        are invalid
    """
    # retrieve other needed properties, or use defaults if not there
    if MASK_GEN_ALG in image_properties:
        mask_gen_algorithm = image_properties[MASK_GEN_ALG]
        if mask_gen_algorithm not in MASK_GEN_ALGORITHMS:
            raise exception.SignatureVerificationError(
                'Invalid mask_gen_algorithm: %s' % mask_gen_algorithm)
        mgf = MASK_GEN_ALGORITHMS[mask_gen_algorithm](hash_method)
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

    # return the verifier
    return public_key.verifier(
        signature,
        padding.PSS(mgf=mgf, salt_length=salt_length),
        hash_method
    )


# map the key type to the verifier function to use
KEY_TYPE_METHODS = {
    RSA_PSS: create_verifier_for_pss
}


@debtcollector.removals.remove(message="This will be removed in the N cycle.")
def should_verify_signature(image_properties):
    """Determine whether a signature should be verified.

    Using the image properties, determine whether existing properties indicate
    that signature verification should be done.

    :param image_properties: the key-value properties about the image
    :returns: True, if signature metadata properties exist, False otherwise
    """
    return (image_properties is not None and
            OLD_CERT_UUID in image_properties and
            OLD_HASH_METHOD in image_properties and
            OLD_SIGNATURE in image_properties and
            OLD_KEY_TYPE in image_properties)


@debtcollector.removals.remove(
    message="Starting with the Mitaka release, this approach to signature "
            "verification using the image 'checksum' and signature metadata "
            "properties that do not start with 'img' will not be supported. "
            "This functionality will be removed in the N release. This "
            "approach is being replaced with a signature of the data "
            "directly, instead of a signature of the hash method, and the new "
            "approach uses properties that start with 'img_'.")
def verify_signature(context, checksum_hash, image_properties):
    """Retrieve the image properties and use them to verify the signature.

    :param context: the user context for authentication
    :param checksum_hash: the 'checksum' hash of the image data
    :param image_properties: the key-value properties about the image
    :returns: True if verification succeeds
    :raises: SignatureVerificationError if verification fails
    """
    if not should_verify_signature(image_properties):
        raise exception.SignatureVerificationError(
            'Required image properties for signature verification do not'
            ' exist. Cannot verify signature.')

    checksum_hash = encodeutils.to_utf8(checksum_hash)

    signature = get_signature(image_properties[OLD_SIGNATURE])
    hash_method = get_hash_method(image_properties[OLD_HASH_METHOD])
    signature_key_type = get_signature_key_type(
        image_properties[OLD_KEY_TYPE])
    public_key = get_public_key(context,
                                image_properties[OLD_CERT_UUID],
                                signature_key_type)

    # create the verifier based on the signature key type
    try:
        verifier = KEY_TYPE_METHODS[signature_key_type](signature,
                                                        hash_method,
                                                        public_key,
                                                        image_properties)
    except crypto_exception.UnsupportedAlgorithm as e:
        msg = (_LE("Unable to create verifier since algorithm is "
                   "unsupported: %(e)s")
               % {'e': encodeutils.exception_to_unicode(e)})
        LOG.error(msg)
        raise exception.SignatureVerificationError(
            'Unable to verify signature since the algorithm is unsupported '
            'on this system')

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
    :returns: the decoded signature
    :raises: SignatureVerificationError if the signature data is malformatted
    """
    try:
        signature = base64.decode_as_bytes(signature_data)
    except (TypeError, binascii.Error):
        raise exception.SignatureVerificationError(
            'The signature data was not properly encoded using base64')

    return signature


def get_hash_method(hash_method_name):
    """Verify the hash method name and create the hash method.

    :param hash_method_name: the name of the hash method to retrieve
    :returns: the hash method, a cryptography object
    :raises: SignatureVerificationError if the hash method name is invalid
    """
    if hash_method_name not in HASH_METHODS:
        raise exception.SignatureVerificationError(
            'Invalid signature hash method: %s' % hash_method_name)

    return HASH_METHODS[hash_method_name]


def get_signature_key_type(signature_key_type):
    """Verify the signature key type.

    :param signature_key_type: the key type of the signature
    :returns: the validated signature key type
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
    :returns: the public key cryptography object
    :raises: SignatureVerificationError if public key format is invalid
    """
    certificate = get_certificate(context, signature_certificate_uuid)

    # Note that this public key could either be
    # RSAPublicKey, DSAPublicKey, or EllipticCurvePublicKey
    public_key = certificate.public_key()

    # Confirm the type is of the type expected based on the signature key type
    if not isinstance(public_key, SIGNATURE_KEY_TYPES[signature_key_type]):
        raise exception.SignatureVerificationError(
            'Invalid public key type for signature key type: %s'
            % signature_key_type)

    return public_key


def get_certificate(context, signature_certificate_uuid):
    """Create the certificate object from the retrieved certificate data.

    :param context: the user context for authentication
    :param signature_certificate_uuid: the uuid to use to retrieve the
                                       certificate
    :returns: the certificate cryptography object
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
    else:
        raise exception.SignatureVerificationError(
            'Certificate format not supported: %s' % cert.format)

    # verify the certificate
    verify_certificate(certificate)

    return certificate


def verify_certificate(certificate):
    """Verify that the certificate has not expired.

    :param certificate: the cryptography certificate object
    :raises: SignatureVerificationError if the certificate valid time range
             does not include now
    """
    # Get now in UTC, since certificate returns times in UTC
    now = datetime.datetime.utcnow()

    # Confirm the certificate valid time range includes now
    if now < certificate.not_valid_before:
        raise exception.SignatureVerificationError(
            'Certificate is not valid before: %s UTC'
            % certificate.not_valid_before)
    elif now > certificate.not_valid_after:
        raise exception.SignatureVerificationError(
            'Certificate is not valid after: %s UTC'
            % certificate.not_valid_after)
