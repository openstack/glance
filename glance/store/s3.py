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
import glance.store.location

logger = logging.getLogger('glance.store.s3')

glance.store.location.add_scheme_map({'s3': 's3',
                                      's3+http': 's3',
                                      's3+https': 's3'})


class StoreLocation(glance.store.location.StoreLocation):

    """
    Class describing an S3 URI. An S3 URI can look like any of
    the following:

        s3://accesskey:secretkey@s3service.com/bucket/key-id
        s3+http://accesskey:secretkey@s3service.com/bucket/key-id
        s3+https://accesskey:secretkey@s3service.com/bucket/key-id

    The s3+https:// URIs indicate there is an HTTPS s3service URL
    """

    def process_specs(self):
        self.scheme = self.specs.get('scheme', 's3')
        self.accesskey = self.specs.get('accesskey')
        self.secretkey = self.specs.get('secretkey')
        s3_host = self.specs.get('s3serviceurl')
        self.bucket = self.specs.get('bucket')
        self.key = self.specs.get('key')

        if s3_host.startswith('https://'):
            self.scheme = 's3+https'
            s3_host = s3_host[8:].strip('/')
        elif s3_host.startswith('http://'):
            s3_host = s3_host[7:].strip('/')
        self.s3serviceurl = s3_host

    def _get_credstring(self):
        if self.accesskey:
            return '%s:%s@' % (self.accesskey, self.secretkey)
        return ''

    def get_uri(self):
        return "%s://%s%s/%s/%s" % (
            self.scheme,
            self._get_credstring(),
            self.s3serviceurl,
            self.bucket,
            self.key)

    def parse_uri(self, uri):
        """
        Parse URLs. This method fixes an issue where credentials specified
        in the URL are interpreted differently in Python 2.6.1+ than prior
        versions of Python.

        Note that an Amazon AWS secret key can contain the forward slash,
        which is entirely retarded, and breaks urlparse miserably.
        This function works around that issue.
        """
        pieces = urlparse.urlparse(uri)
        assert pieces.scheme in ('s3', 's3+http', 's3+https')
        self.scheme = pieces.scheme
        path = pieces.path.strip('/')
        netloc = pieces.netloc.strip('/')
        entire_path = (netloc + '/' + path).strip('/')

        if '@' in uri:
            creds, path = entire_path.split('@')
            cred_parts = creds.split(':')

            try:
                access_key = cred_parts[0]
                secret_key = cred_parts[1]
                # NOTE(jaypipes): Need to encode to UTF-8 here because of a
                # bug in the HMAC library that boto uses.
                # See: http://bugs.python.org/issue5285
                # See: http://trac.edgewall.org/ticket/8083
                access_key = access_key.encode('utf-8')
                secret_key = secret_key.encode('utf-8')
                self.accesskey = access_key
                self.secretkey = secret_key
            except IndexError:
                reason = "Badly formed S3 credentials %s" % creds
                raise exception.BadStoreUri(uri, reason)
        else:
            self.accesskey = None
            path = entire_path
        try:
            path_parts = path.split('/')
            self.key = path_parts.pop()
            self.bucket = path_parts.pop()
            if len(path_parts) > 0:
                self.s3serviceurl = '/'.join(path_parts)
            else:
                reason = "Badly formed S3 URI. Missing s3 service URL."
                raise exception.BadStoreUri(uri, reason)
        except IndexError:
            reason = "Badly formed S3 URI"
            raise exception.BadStoreUri(uri, reason)


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
    def get(cls, location, expected_size=None, options=None):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator from S3
        provided by S3's key object

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        loc = location.store_location
        from boto.s3.connection import S3Connection

        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl)
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        key = get_key(bucket_obj, loc.key)

        logger.debug("Retrieved image object from S3 using "
                     "(s3_host=%s, access_key=%s, "
                     "bucket=%s, key=%s)" % (loc.s3serviceurl, loc.accesskey,
                                             loc.bucket, loc.key))

        if expected_size and (key.size != expected_size):
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
        # NOTE(jaypipes): Need to encode to UTF-8 here because of a
        # bug in the HMAC library that boto uses.
        # See: http://bugs.python.org/issue5285
        # See: http://trac.edgewall.org/ticket/8083
        access_key = access_key.encode('utf-8')
        secret_key = secret_key.encode('utf-8')
        bucket = cls._option_get(options, 's3_store_bucket')

        scheme = 's3'
        if s3_host.startswith('https://'):
            scheme = 'swift+https'
            full_s3_host = s3_host
        elif s3_host.startswith('http://'):
            full_s3_host = s3_host
        else:
            full_s3_host = 'http://' + s3_host  # Defaults http

        loc = StoreLocation({'scheme': scheme,
                             'bucket': bucket,
                             'key': id,
                             's3serviceurl': full_s3_host,
                             'accesskey': access_key,
                             'secretkey': secret_key})

        s3_conn = S3Connection(access_key, secret_key, host=loc.s3serviceurl)

        create_bucket_if_missing(bucket, s3_conn, options)

        bucket_obj = get_bucket(s3_conn, bucket)
        obj_name = str(id)

        key = bucket_obj.get_key(obj_name)
        if key and key.exists():
            raise exception.Duplicate("S3 already has an image at "
                                      "location %s" % loc.get_uri())

        logger.debug("Adding image object to S3 using "
                     "(s3_host=%(s3_host)s, access_key=%(access_key)s, "
                     "bucket=%(bucket)s, key=%(obj_name)s)" % locals())

        key = bucket_obj.new_key(obj_name)

        # OK, now upload the data into the key
        obj_md5, _base64_digest = key.compute_md5(data)
        key.set_contents_from_file(data, replace=False)
        size = key.size

        return (loc.get_uri(), size, obj_md5)

    @classmethod
    def delete(cls, location, options=None):
        """
        Delete an object in a specific location

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        loc = location.store_location
        from boto.s3.connection import S3Connection
        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl)
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        # Close the key when we're through.
        key = get_key(bucket_obj, loc.key)

        logger.debug("Deleting image object from S3 using "
                     "(s3_host=%s, access_key=%s, "
                     "bucket=%s, key=%s)" % (loc.s3serviceurl, loc.accesskey,
                                             loc.bucket, loc.key))

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


def create_bucket_if_missing(bucket, s3_conn, options):
    """
    Creates a missing bucket in S3 if the
    ``s3_store_create_bucket_on_put`` option is set.

    :param bucket: Name of bucket to create
    :param s3_conn: Connection to S3
    :param options: Option mapping
    """
    from boto.exception import S3ResponseError
    try:
        s3_conn.get_bucket(bucket)
    except S3ResponseError, e:
        if e.status == httplib.NOT_FOUND:
            add_bucket = config.get_option(options,
                                's3_store_create_bucket_on_put',
                                type='bool', default=False)
            if add_bucket:
                try:
                    s3_conn.create_bucket(bucket)
                except S3ResponseError, e:
                    msg = ("Failed to add bucket to S3.\n"
                           "Got error from S3: %(e)s" % locals())
                    raise glance.store.BackendException(msg)
            else:
                msg = ("The bucket %(bucket)s does not exist in "
                       "S3. Please set the "
                       "s3_store_create_bucket_on_put option"
                       "to add bucket to S3 automatically."
                       % locals())
                raise glance.store.BackendException(msg)


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
