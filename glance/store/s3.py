# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

"""Storage backend for S3 or Storage Servers that follow the S3 Protocol"""

import logging
import urlparse

from glance.common import exception
import glance.store

DEFAULT_S3_BUCKET = 'glance'

logger = logging.getLogger('glance.store.s3')


class ChunkedFile(object):

    """
    We send this back to the Glance API server as
    something that can iterate over a ``boto.s3.key.Key``
    """

    CHUNKSIZE = 65536

    def __init__(self, fp):
        self.fp = fp

    def __iter__(self):
        """Return an iterator over the image file"""
        try:
            while True:
                chunk = self.fp.read(ChunkedFile.CHUNKSIZE)
                if chunk:
                    yield chunk
                else:
                    break
        finally:
            self.close()

    def close(self):
        """Close the internal file pointer"""
        if self.fp:
            self.fp.close()
            self.fp = None


class S3Backend(glance.store.Backend):
    """An implementation of the s3 adapter."""

    EXAMPLE_URL = "s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>"

    @classmethod
    def _option_get(cls, options, param):
        result = options.get(param)
        if not result:
            msg = ("Could not find %s in configuration options." % param)
            logger.error(msg)
            raise glance.store.BackendException(msg)
        return result

    @classmethod
    def get(cls, parsed_uri, expected_size=None, options=None):
        """
        Takes a parsed_uri in the format of:
        s3://access_key:secret_key@s3.amazonaws.com/bucket/file.gz.0, connects
        to s3 and downloads the file. Returns the generator resp_body provided
        by get_object.
        """
        from boto.s3.connection import S3Connection

        (access_key, secret_key, s3_host, bucket, obj_name) = \
            parse_s3_tokens(parsed_uri)

        # This is annoying. If I pass http://s3.amazonaws.com to Boto, it
        # dies. If I pass s3.amazonaws.com it works fine. :(
        s3_host_only = urlparse.urlparse(s3_host).netloc

        s3_conn = S3Connection(access_key, secret_key, host=s3_host_only)
        bucket_obj = get_bucket(s3_conn, bucket)

        key = get_key(bucket_obj, obj_name)

        logger.debug("Retrieved image object from S3 using "
                     "(s3_host=%(s3_host)s, access_key=%(access_key)s, "
                     "bucket=%(bucket)s, key=%(obj_name)s)" % locals())

        if expected_size and key.size != expected_size:
            msg = "Expected %s bytes, got %s" % (expected_size, key.size)
            logger.error(msg)
            raise glance.store.BackendException(msg)

        key.BufferSize = cls.CHUNKSIZE
        return ChunkedFile(key)

    @classmethod
    def add(cls, id, data, options):
        """
        Stores image data to S3 and returns a location that the image was
        written to.

        S3 writes the image data using the scheme:
            s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>
        where:
            <USER> = ``s3_store_user``
            <KEY> = ``s3_store_key``
            <S3_HOST> = ``s3_store_host``
            <BUCKET> = ``s3_store_bucket``
            <ID> = The id of the image being added

        :param id: The opaque image identifier
        :param data: The image data to write, as a file-like object
        :param options: Conf mapping

        :retval Tuple with (location, size)
                The location that was written,
                and the size in bytes of the data written
        """
        from boto.s3.connection import S3Connection

        # TODO(jaypipes): This needs to be checked every time
        # because of the decision to make glance.store.Backend's
        # interface all @classmethods. This is inefficient. Backend
        # should be a stateful object with options parsed once in
        # a constructor.
        s3_host = cls._option_get(options, 's3_store_host')
        access_key = cls._option_get(options, 's3_store_access_key')
        secret_key = cls._option_get(options, 's3_store_secret_key')
        bucket = options.get('s3_store_bucket', DEFAULT_S3_BUCKET)

        full_s3_host = s3_host
        if not full_s3_host.startswith('http'):
            full_s3_host = 'https://' + full_s3_host

        s3_conn = S3Connection(access_key, secret_key, host=s3_host)

        bucket_obj = get_bucket(s3_conn, bucket)
        obj_name = str(id)
        location = format_s3_location(access_key, secret_key, s3_host,
                                      bucket, obj_name)

        key = bucket_obj.get_key(obj_name)
        if key and key.exists():
            raise exception.Duplicate("S3 already has an image at "
                                      "location %(location)s" % locals())

        logger.debug("Adding image object to S3 using "
                     "(s3_host=%(s3_host)s, access_key=%(access_key)s, "
                     "bucket=%(bucket)s, key=%(obj_name)s)" % locals())

        key = bucket_obj.new_key(obj_name)

        # OK, now upload the data into the key
        obj_md5, _base64_digest = key.compute_md5(data)
        key.set_contents_from_file(data, replace=False)
        size = key.size

        return (location, size, obj_md5)

    @classmethod
    def delete(cls, parsed_uri, options=None):
        """
        Takes a parsed_uri in the format of:
        s3://access_key:secret_key@s3.amazonaws.com/bucket/file.gz.0, connects
        to s3 and deletes the file. Returns whatever boto.s3.key.Key.delete()
        returns.
        """
        from boto.s3.connection import S3Connection

        (access_key, secret_key, s3_host, bucket, obj_name) = \
            parse_s3_tokens(parsed_uri)

        # Close the connection when we're through.
        s3_conn = S3Connection(access_key, secret_key, host=s3_host)
        bucket_obj = get_bucket(s3_conn, bucket)

        # Close the key when we're through.
        key = get_key(bucket_obj, obj_name)

        logger.debug("Deleting image object from S3 using "
                     "(s3_host=%(s3_host)s, user=%(access_key)s, "
                     "bucket=%(bucket)s, key=%(obj_name)s)" % locals())

        return key.delete()


def get_bucket(conn, bucket_id):
    """
    Get a bucket from an s3 connection

    :param conn: The ``boto.s3.connection.S3Connection``
    :param bucket_id: ID of the bucket to fetch
    :raises ``glance.exception.NotFound`` if bucket is not found.
    """

    bucket = conn.get_bucket(bucket_id)
    if not bucket:
        msg = ("Could not find bucket with ID %(bucket_id)s") % locals()
        logger.error(msg)
        raise exception.NotFound(msg)

    return bucket


def get_key(bucket, obj):
    """
    Get a key from a bucket

    :param bucket: The ``boto.s3.Bucket``
    :param obj: Object to get the key for
    :raises ``glance.exception.NotFound`` if key is not found.
    """

    key = bucket.get_key(obj)
    if not key.exists():
        msg = ("Could not find key %(obj)s in bucket %(bucket)s") % locals()
        logger.error(msg)
        raise exception.NotFound(msg)
    return key


def format_s3_location(user, key, s3_host, bucket, obj_name):
    """
    Returns the s3 URI in the format:
        s3://<USER_KEY>:<SECRET_KEY>@<S3_HOST>/<BUCKET>/<OBJNAME>

    :param user: The s3 user key to authenticate with
    :param key: The s3 secret key for the authenticating user
    :param s3_host: The base URL for the s3 service
    :param bucket: The name of the bucket
    :param obj_name: The name of the object
    """
    return "s3://%(user)s:%(key)s@%(s3_host)s/"\
           "%(bucket)s/%(obj_name)s" % locals()


def parse_s3_tokens(parsed_uri):
    """
    Return the various tokens used by S3.

    Note that an Amazon AWS secret key can contain the forward slash,
    which is entirely retarded, and breaks urlparse miserably.
    This function works around that issue.

    :param parsed_uri: The pieces of a URI returned by urlparse
    :retval A tuple of (user, key, s3_host, bucket, obj_name)
    """

    # TODO(jaypipes): Do parsing in the stores. Don't call urlparse in the
    #                 base get_backend_class routine...
    entire_path = "%s%s" % (parsed_uri.netloc, parsed_uri.path)

    try:
        creds, path = entire_path.split('@')
        cred_parts = creds.split(':')

        user = cred_parts[0]
        key = cred_parts[1]
        path_parts = path.split('/')
        obj = path_parts.pop()
        bucket = path_parts.pop()
    except (ValueError, IndexError):
        raise glance.store.BackendException(
             "Expected four values to unpack in: s3:%s. "
             "Should have received something like: %s."
             % (parsed_uri.path, S3Backend.EXAMPLE_URL))

    s3_host = "https://%s" % '/'.join(path_parts)

    return user, key, s3_host, bucket, obj
