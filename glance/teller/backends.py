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


def _file_iter(f, size):
    """ Return an iterator for a file-like object """
    chunk = f.read(size)
    while chunk:
        yield chunk
        chunk = f.read(size)


class BackendException(Exception):
    pass


class UnsupportedBackend(BackendException):
    pass


class Backend(object):
    CHUNKSIZE = 4096


class TestStrBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, expected_size):
        """
        teststr://data
        """
        yield parsed_uri.path


class FilesystemBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, expected_size, opener=lambda p: open(p, "b")):
        """
        file:///path/to/file.tar.gz.0
        """
        def sanitize_path(p):
            #FIXME: must prevent attacks using ".." and "." paths
            return p

        with opener(sanitize_path(parsed_uri.path)) as f:
            return _file_iter(f, cls.CHUNKSIZE)
         

class HTTPBackend(Backend):
    """ An implementation of the HTTP Backend Adapter """

    @classmethod
    def get(cls, parsed_uri, expected_size, conn_class=None):
        """Takes a parsed uri for an HTTP resource, fetches it, ane yields the
        data.
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
            return _file_iter(conn.getresponse(), cls.CHUNKSIZE)
        finally:
            conn.close()

class SwiftBackend(Backend):
    """
    An implementation of the swift backend adapter.
    """

    RE_SWIFT_TOKENS = re.compile(r":|@|/")
    EXAMPLE_URL = "swift://user:password@auth_url/container/file.gz.0"

    @classmethod
    def get(cls, parsed_uri, expected_size, conn_class=None):
        """
        Takes a parsed_uri in the format of: 
        swift://user:password@auth_url/container/file.gz.0, connects to the 
        swift instance at auth_url and downloads the file. Returns the generator
        provided by stream() on the swift object representing the file.
        """
        (user, api_key, authurl, container, file) = \
            cls.parse_swift_tokens(parsed_uri)

        if conn_class:
            pass # Use the provided conn_class
        else:
            conn_class = cloudfiles

        swift_conn = conn_class.get_connection(username=user, api_key=api_key,
                                               authurl=authurl)

        container = swift_conn.get_container(container)

        obj = container.get_object(file)

        if obj.size != expected_size:
            raise BackendException("Expected %s size file, Swift has %s"
                                   % (expected_size, obj.size))

        # Return the generator provided from obj.stream()
        return obj.stream(chunksize=cls.CHUNKSIZE)

    @classmethod
    def parse_swift_tokens(cls, parsed_uri):
        """
        Parsing the swift uri is three phases:
            1) urlparse to split the tokens
            2) use RE to split on @ and /
            3) reassemble authurl
        """
        try:
            split_url = parsed_uri.path[2:]
            swift_tokens = cls.RE_SWIFT_TOKENS.split(split_url)
            
            (user, api_key) = swift_tokens[:2]    # beginning
            authurl_parts = swift_tokens[2:-2]    # middle
            (container, file) = swift_tokens[-2:] # end

        except ValueError:
            raise BackendException(
                 "Expected four values to unpack in: swift:%s. "
                 "Should have received something like: %s."
                 % (parsed_uri.path, cls.EXAMPLE_URL))

        authurl = "https://%s" % '/'.join(authurl_parts)
        return user, api_key, authurl, container, file


BACKENDS = {
    "file": FilesystemBackend,
    "http": HTTPBackend,
    "https": HTTPBackend,
    "swift": SwiftBackend,
    "teststr": TestStrBackend
}

def get_from_backend(uri, **kwargs):
    """ Yields chunks of data from backend specified by uri """
    parsed_uri = urlparse.urlparse(uri)
    scheme = parsed_uri.scheme

    try:
        backend = BACKENDS[scheme]
    except KeyError:
        raise UnsupportedBackend("No backend found for '%s'" % scheme)

    return backend.get(parsed_uri, **kwargs)

