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

import cloudfiles
import httplib
import re
import urlparse


class BackendException(Exception):
    pass


class UnsupportedBackend(BackendException):
    pass


class Backend(object):
    CHUNKSIZE = 4096


class TestStrBackend(Backend):
    @classmethod
    def get(cls, parsed_uri):
        """
        teststr://data
        """
        yield parsed_uri.netloc


class FilesystemBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, opener=lambda p: open(p, "b")):
        """
        file:///path/to/file.tar.gz.0
        """
        def sanitize_path(p):
            #FIXME: must prevent attacks using ".." and "." paths
            return p

        with opener(sanitize_path(parsed_uri.path)) as f:
            chunk = f.read(cls.CHUNKSIZE)
            while chunk:
                yield chunk
                chunk = f.read(cls.CHUNKSIZE)
         

class HTTPBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, conn_class=None):
        """
        http://netloc/path/to/file.tar.gz.0
        https://netloc/path/to/file.tar.gz.0
        """
        if conn_class:
            pass # use the conn_class passed in
        elif parsed_uri.scheme == "http":
            conn_class = httplib.HTTPConnection
        elif parsed_uri.scheme == "https":
            conn_class = httplib.HTTPSConnection
        else:
            raise BackendException("scheme '%s' not supported for HTTPBackend")
        conn = conn_class(parsed_uri.netloc)
        conn.request("GET", parsed_uri.path, "", {})
        try:
            response = conn.getresponse()
            chunk = response.read(cls.CHUNKSIZE)
            while chunk:
                yield chunk
                chunk = response.read(cls.CHUNKSIZE)
        finally:
            conn.close()

class SwiftBackend(Backend):
    """
    An implementation of the swift backend adapter.
    """

    RE_SWIFT_TOKENS = re.compile(r":|@|/")
    EXAMPLE_URL="swift://user:password@auth_url/container/file.gz.0"

    @classmethod
    def get(cls, parsed_uri, conn_class=None):
        """
        Takes a parsed_uri in the format of: 
        swift://user:password@auth_url/container/file.gz.0, connects to the 
        swift instance at auth_url and downloads the file. Returns the generator
        provided by stream() on the swift object representing the file.
        """
        if conn_class:
            pass # Use the provided conn_class
        else:
            conn_class = cloudfiles

        try:
            split_url = parsed_uri.path[2:]
            swift_tokens = cls.RE_SWIFT_TOKENS.split(split_url)
            user, api_key, authurl, container, file = swift_tokens
        except ValueError:
            raise BackendException(
                 "Expected four values to unpack in: swift:%s. "
                 "Should have received something like: %s."
                 % (parsed_uri.path, cls.EXAMPLE_URL))

        swift_conn = conn_class.get_connection(username=user, api_key=api_key,
                                               authurl=authurl)

        container = swift_conn.get_container(container)
        obj = container.get_object(file)

        # Return the generator provided from obj.stream()
        return obj.stream(chunksize=cls.CHUNKSIZE)


def _scheme2backend(scheme):
    return {
        "file": FilesystemBackend,
        "http": HTTPBackend,
        "https": HTTPBackend,
        "swift": SwiftBackend,
        "teststr": TestStrBackend
    }[scheme]


def get_from_backend(uri, **kwargs):
    """
    Yields chunks of data from backend specified by uri
    """
    parsed_uri = urlparse.urlparse(uri)
    try:
        return _scheme2backend(parsed_uri.scheme).get(parsed_uri, **kwargs)
    except KeyError:
        raise UnsupportedBackend("No backend found for '%s'" % parsed_uri.scheme)


