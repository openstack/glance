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

"""The s3 backend adapter"""

import glance.store


class S3Backend(glance.store.Backend):
    """An implementation of the s3 adapter."""

    EXAMPLE_URL = "s3://ACCESS_KEY:SECRET_KEY@s3_url/bucket/file.gz.0"

    @classmethod
    def get(cls, parsed_uri, expected_size, conn_class=None):
        """
        Takes a parsed_uri in the format of:
        s3://access_key:secret_key@s3.amazonaws.com/bucket/file.gz.0, connects
        to s3 and downloads the file. Returns the generator resp_body provided
        by get_object.
        """

        if conn_class:
            pass
        else:
            import boto.s3.connection
            conn_class = boto.s3.connection.S3Connection

        (access_key, secret_key, host, bucket, obj) = \
            cls._parse_s3_tokens(parsed_uri)

        # Close the connection when we're through.
        with conn_class(access_key, secret_key, host=host) as s3_conn:
            bucket = cls._get_bucket(s3_conn, bucket)

            # Close the key when we're through.
            with cls._get_key(bucket, obj) as key:
                if not key.size == expected_size:
                    raise glance.store.BackendException(
                        "Expected %s bytes, got %s" %
                        (expected_size, key.size))

                key.BufferSize = cls.CHUNKSIZE
                for chunk in key:
                    yield chunk

    @classmethod
    def delete(cls, parsed_uri, conn_class=None):
        """
        Takes a parsed_uri in the format of:
        s3://access_key:secret_key@s3.amazonaws.com/bucket/file.gz.0, connects
        to s3 and deletes the file. Returns whatever boto.s3.key.Key.delete()
        returns.
        """

        if conn_class:
            pass
        else:
            conn_class = boto.s3.connection.S3Connection

        (access_key, secret_key, host, bucket, obj) = \
            cls._parse_s3_tokens(parsed_uri)

        # Close the connection when we're through.
        with conn_class(access_key, secret_key, host=host) as s3_conn:
            bucket = cls._get_bucket(s3_conn, bucket)

            # Close the key when we're through.
            with cls._get_key(bucket, obj) as key:
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

    @classmethod
    def _parse_s3_tokens(cls, parsed_uri):
        """Parse tokens from the parsed_uri"""
        return glance.store.parse_uri_tokens(parsed_uri, cls.EXAMPLE_URL)
