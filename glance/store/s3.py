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
import hashlib
import httplib
import tempfile
import urlparse

from glance.common import config
from glance.common import exception
import glance.store
import glance.store.base
import glance.store.location

logger = logging.getLogger('glance.store.s3')


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
        self.s3serviceurl = s3_host.strip('/')

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
        # Make sure that URIs that contain multiple schemes, such as:
        # swift://user:pass@http://authurl.com/v1/container/obj
        # are immediately rejected.
        if uri.count('://') != 1:
            reason = _("URI Cannot contain more than one occurrence of a "
                      "scheme. If you have specified a "
                      "URI like s3://user:pass@https://s3.amazonaws.com/"
                      "bucket/key, you need to change it to use the "
                      "s3+https:// scheme, like so: "
                      "s3+https://user:pass@s3.amazonaws.com/bucket/key")
            raise exception.BadStoreUri(uri, reason)

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
                reason = _("Badly formed S3 credentials %s") % creds
                raise exception.BadStoreUri(uri, reason)
        else:
            self.accesskey = None
            path = entire_path
        try:
            path_parts = path.split('/')
            self.key = path_parts.pop()
            self.bucket = path_parts.pop()
            if len(path_parts) > 0:
                self.s3serviceurl = '/'.join(path_parts).strip('/')
            else:
                reason = _("Badly formed S3 URI. Missing s3 service URL.")
                raise exception.BadStoreUri(uri, reason)
        except IndexError:
            reason = _("Badly formed S3 URI")
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

    def getvalue(self):
        """Return entire string value... used in testing"""
        data = ""
        self.len = 0
        for chunk in self:
            read_bytes = len(chunk)
            data = data + chunk
            self.len = self.len + read_bytes
        return data

    def close(self):
        """Close the internal file pointer"""
        if self.fp:
            self.fp.close()
            self.fp = None


class Store(glance.store.base.Store):
    """An implementation of the s3 adapter."""

    EXAMPLE_URL = "s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>"

    def configure(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.s3_host = self._option_get('s3_store_host')
        access_key = self._option_get('s3_store_access_key')
        secret_key = self._option_get('s3_store_secret_key')
        # NOTE(jaypipes): Need to encode to UTF-8 here because of a
        # bug in the HMAC library that boto uses.
        # See: http://bugs.python.org/issue5285
        # See: http://trac.edgewall.org/ticket/8083
        self.access_key = access_key.encode('utf-8')
        self.secret_key = secret_key.encode('utf-8')
        self.bucket = self._option_get('s3_store_bucket')

        self.scheme = 's3'
        if self.s3_host.startswith('https://'):
            self.scheme = 'swift+https'
            self.full_s3_host = self.s3_host
        elif self.s3_host.startswith('http://'):
            self.full_s3_host = self.s3_host
        else:  # Defaults http
            self.full_s3_host = 'http://' + self.s3_host

    def _option_get(self, param):
        result = self.options.get(param)
        if not result:
            reason = _("Could not find %(param)s in configuration "
                       "options.") % locals()
            logger.error(reason)
            raise exception.BadStoreConfiguration(store_name="s3",
                                                  reason=reason)
        return result

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        loc = location.store_location
        from boto.s3.connection import S3Connection

        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'))
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        key = get_key(bucket_obj, loc.key)

        msg = _("Retrieved image object from S3 using (s3_host=%(s3_host)s, "
                "access_key=%(accesskey)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': loc.s3serviceurl,
                'accesskey': loc.accesskey, 'bucket': loc.bucket,
                'obj_name': loc.key})
        logger.debug(msg)

        #if expected_size and (key.size != expected_size):
        #   msg = "Expected %s bytes, got %s" % (expected_size, key.size)
        #   logger.error(msg)
        #   raise glance.store.BackendException(msg)

        key.BufferSize = self.CHUNKSIZE
        return (ChunkedFile(key), None)

    def add(self, image_id, image_file, image_size):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns an `glance.store.ImageAddResult` object
        containing information about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes

        :retval `glance.store.ImageAddResult` object
        :raises `glance.common.exception.Duplicate` if the image already
                existed

        S3 writes the image data using the scheme:
            s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>
        where:
            <USER> = ``s3_store_user``
            <KEY> = ``s3_store_key``
            <S3_HOST> = ``s3_store_host``
            <BUCKET> = ``s3_store_bucket``
            <ID> = The id of the image being added
        """
        from boto.s3.connection import S3Connection

        loc = StoreLocation({'scheme': self.scheme,
                             'bucket': self.bucket,
                             'key': image_id,
                             's3serviceurl': self.full_s3_host,
                             'accesskey': self.access_key,
                             'secretkey': self.secret_key})

        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'))

        create_bucket_if_missing(self.bucket, s3_conn, self.options)

        bucket_obj = get_bucket(s3_conn, self.bucket)
        obj_name = str(image_id)

        key = bucket_obj.get_key(obj_name)
        if key and key.exists():
            raise exception.Duplicate(_("S3 already has an image at "
                                      "location %s") % loc.get_uri())

        msg = _("Adding image object to S3 using (s3_host=%(s3_host)s, "
                "access_key=%(access_key)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': self.s3_host,
                'access_key': self.access_key, 'bucket': self.bucket,
                'obj_name': obj_name})
        logger.debug(msg)

        key = bucket_obj.new_key(obj_name)

        # We need to wrap image_file, which is a reference to the
        # webob.Request.body_file, with a seekable file-like object,
        # otherwise the call to set_contents_from_file() will die
        # with an error about Input object has no method 'seek'. We
        # might want to call webob.Request.make_body_seekable(), but
        # unfortunately, that method copies the entire image into
        # memory and results in LP Bug #818292 occurring. So, here
        # we write temporary file in as memory-efficient manner as
        # possible and then supply the temporary file to S3. We also
        # take this opportunity to calculate the image checksum while
        # writing the tempfile, so we don't need to call key.compute_md5()

        msg = _("Writing request body file to temporary file "
                "for %s") % loc.get_uri()
        logger.debug(msg)
        temp_file = tempfile.NamedTemporaryFile()

        checksum = hashlib.md5()
        chunk = image_file.read(self.CHUNKSIZE)
        while chunk:
            checksum.update(chunk)
            temp_file.write(chunk)
            chunk = image_file.read(self.CHUNKSIZE)
        temp_file.flush()

        msg = _("Uploading temporary file to S3 for %s") % loc.get_uri()
        logger.debug(msg)

        # OK, now upload the data into the key
        key.set_contents_from_file(open(temp_file.name, 'r+b'), replace=False)
        size = key.size
        checksum_hex = checksum.hexdigest()

        logger.debug(_("Wrote %(size)d bytes to S3 key named %(obj_name)s "
                       "with checksum %(checksum_hex)s") % locals())

        return (loc.get_uri(), size, checksum_hex)

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """
        loc = location.store_location
        from boto.s3.connection import S3Connection
        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'))
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        # Close the key when we're through.
        key = get_key(bucket_obj, loc.key)

        msg = _("Deleting image object from S3 using (s3_host=%(s3_host)s, "
                "access_key=%(accesskey)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': loc.s3serviceurl,
                'accesskey': loc.accesskey, 'bucket': loc.bucket,
                'obj_name': loc.key})
        logger.debug(msg)

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
        msg = _("Could not find bucket with ID %(bucket_id)s") % locals()
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
                       "s3_store_create_bucket_on_put option "
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
    if not key or not key.exists():
        msg = _("Could not find key %(obj)s in bucket %(bucket)s") % locals()
        logger.error(msg)
        raise exception.NotFound(msg)
    return key


glance.store.register_store(__name__, ['s3', 's3+http', 's3+https'])
