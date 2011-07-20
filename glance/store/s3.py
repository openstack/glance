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

"""The s3 backend adapter"""

import urlparse

from glance.common import exception
import glance.store
import glance.store.location

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
        self.s3serviceurl = self.specs.get('s3serviceurl')
        self.bucket = self.specs.get('bucket')
        self.key = self.specs.get('key')

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


class S3Backend(glance.store.Backend):
    """An implementation of the s3 adapter."""

    EXAMPLE_URL = "s3://ACCESS_KEY:SECRET_KEY@s3_url/bucket/file.gz.0"

    @classmethod
    def get(cls, location, expected_size, conn_class=None):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator from S3
        provided by S3's key object

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        if conn_class:
            pass
        else:
            import boto.s3.connection
            conn_class = boto.s3.connection.S3Connection

        loc = location.store_location

        # Close the connection when we're through.
        with conn_class(loc.accesskey, loc.secretkey,
                        host=loc.s3serviceurl) as s3_conn:
            bucket = cls._get_bucket(s3_conn, loc.bucket)

            # Close the key when we're through.
            with cls._get_key(bucket, loc.obj) as key:
                if not key.size == expected_size:
                    raise glance.store.BackendException(
                        "Expected %s bytes, got %s" %
                        (expected_size, key.size))

                key.BufferSize = cls.CHUNKSIZE
                for chunk in key:
                    yield chunk

    @classmethod
    def delete(cls, location, conn_class=None):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        if conn_class:
            pass
        else:
            conn_class = boto.s3.connection.S3Connection

        loc = location.store_location

        # Close the connection when we're through.
        with conn_class(loc.accesskey, loc.secretkey,
                        host=loc.s3serviceurl) as s3_conn:
            bucket = cls._get_bucket(s3_conn, loc.bucket)

            # Close the key when we're through.
            with cls._get_key(bucket, loc.obj) as key:
                return key.delete()

    @classmethod
    def _get_bucket(cls, conn, bucket_id):
        """Get a bucket from an s3 connection"""

        bucket = conn.get_bucket(bucket_id)
        if not bucket:
            raise glance.store.BackendException("Could not find bucket: %s" %
                bucket_id)

        return bucket

    @classmethod
    def _get_key(cls, bucket, obj):
        """Get a key from a bucket"""

        key = bucket.get_key(obj)
        if not key:
            raise glance.store.BackendException("Could not get key: %s" % key)
        return key
