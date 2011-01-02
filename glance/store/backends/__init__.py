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

import os
import urlparse

from glance.common import exception


# TODO(sirp): should this be moved out to common/utils.py ?
def _file_iter(f, size):
    """
    Return an iterator for a file-like object
    """
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


class FilesystemBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, expected_size, opener=lambda p: open(p, "rb")):
        """ Filesystem-based backend

        file:///path/to/file.tar.gz.0
        """
        #FIXME: must prevent attacks using ".." and "." paths
        with opener(parsed_uri.path) as f:
            return _file_iter(f, cls.CHUNKSIZE)

    @classmethod
    def delete(cls, parsed_uri):
        """
        Removes a file from the filesystem backend.

        :param parsed_uri: Parsed pieces of URI in form of::
            file:///path/to/filename.ext

        :raises NotFound if file does not exist
        :raises NotAuthorized if cannot delete because of permissions
        """
        fn = parsed_uri.path
        if os.path.exists(fn):
            try:
                os.unlink(fn)
            except OSError:
                raise exception.NotAuthorized("You cannot delete file %s" % fn)
        else:
            raise exception.NotFound("File %s does not exist" % fn)


def get_backend_class(backend):
    """
    Returns the backend class as designated in the
    backend name

    :param backend: Name of backend to create
    """
    # NOTE(sirp): avoiding circular import
    from glance.store.backends.http import HTTPBackend
    from glance.store.backends.swift import SwiftBackend

    BACKENDS = {
        "file": FilesystemBackend,
        "http": HTTPBackend,
        "https": HTTPBackend,
        "swift": SwiftBackend
    }

    try:
        return BACKENDS[backend]
    except KeyError:
        raise UnsupportedBackend("No backend found for '%s'" % scheme)


def get_from_backend(uri, **kwargs):
    """Yields chunks of data from backend specified by uri"""

    parsed_uri = urlparse.urlparse(uri)
    scheme = parsed_uri.scheme

    backend_class = get_backend_class(scheme)

    return backend_class.get(parsed_uri, **kwargs)


def delete_from_backend(uri, **kwargs):
    """Removes chunks of data from backend specified by uri"""

    parsed_uri = urlparse.urlparse(uri)
    scheme = parsed_uri.scheme

    backend_class = get_backend_class(scheme)

    return backend_class.delete(parsed_uri, **kwargs)
