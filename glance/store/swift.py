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

from __future__ import absolute_import
import glance.store


class SwiftBackend(glance.store.Backend):
    """
    An implementation of the swift backend adapter.
    """
    EXAMPLE_URL = "swift://user:password@auth_url/container/file.gz.0"

    CHUNKSIZE = 65536

    @classmethod
    def get(cls, parsed_uri, expected_size, conn_class=None):
        """
        Takes a parsed_uri in the format of:
        swift://user:password@auth_url/container/file.gz.0, connects to the
        swift instance at auth_url and downloads the file. Returns the
        generator resp_body provided by get_object.
        """
        (user, key, authurl, container, obj) = \
            cls._parse_swift_tokens(parsed_uri)

        # TODO(sirp): snet=False for now, however, if the instance of
        # swift we're talking to is within our same region, we should set
        # snet=True
        connection_class = get_connection_class(conn_class)

        swift_conn = conn_class(
            authurl=authurl, user=user, key=key, snet=False)

        (resp_headers, resp_body) = swift_conn.get_object(
            container=container, obj=obj, resp_chunk_size=cls.CHUNKSIZE)

        obj_size = int(resp_headers['content-length'])
        if  obj_size != expected_size:
            raise glance.store.BackendException(
                "Expected %s byte file, Swift has %s bytes" %
                (expected_size, obj_size))

        return resp_body

    @classmethod
    def delete(cls, parsed_uri, conn_class=None):
        """
        Deletes the swift object(s) at the parsed_uri location
        """
        (user, key, authurl, container, obj) = \
            cls._parse_swift_tokens(parsed_uri)

        # TODO(sirp): snet=False for now, however, if the instance of
        # swift we're talking to is within our same region, we should set
        # snet=True
        connection_class = get_connection_class(conn_class)

        swift_conn = conn_class(
            authurl=authurl, user=user, key=key, snet=False)

        (resp_headers, resp_body) = swift_conn.delete_object(
            container=container, obj=obj)

        # TODO(jaypipes): What to return here?  After reading the docs
        # at swift.common.client, I'm not sure what to check for...

    @classmethod
    def _parse_swift_tokens(cls, parsed_uri):
        """
        Parsing the swift uri is three phases:
            1) urlparse to split the tokens
            2) use RE to split on @ and /
            3) reassemble authurl
        """
        path = parsed_uri.path.lstrip('//')
        netloc = parsed_uri.netloc

        try:
            try:
                creds, netloc = netloc.split('@')
                path = '/'.join([netloc, path])
            except ValueError:
                # Python 2.6.1 compat
                # see lp659445 and Python issue7904
                creds, path = path.split('@')

            user, key = creds.split(':')
            path_parts = path.split('/')
            obj = path_parts.pop()
            container = path_parts.pop()
        except (ValueError, IndexError):
            raise glance.store.BackendException(
                 "Expected four values to unpack in: swift:%s. "
                 "Should have received something like: %s."
                 % (parsed_uri.path, cls.EXAMPLE_URL))

        authurl = "https://%s" % '/'.join(path_parts)

        return user, key, authurl, container, obj


def get_connection_class(conn_class):
    if not conn_class:
        import swift.common.client
        conn_class = swift.common.client.Connection
    return conn_class
