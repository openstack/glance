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


def get_backend_class(backend):
    """
    Returns the backend class as designated in the
    backend name

    :param backend: Name of backend to create
    """
    # NOTE(sirp): avoiding circular import
    from glance.store.http import HTTPBackend
    from glance.store.swift import SwiftBackend
    from glance.store.filesystem import FilesystemBackend

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


def get_store_from_location(location):
    """
    Given a location (assumed to be a URL), attempt to determine
    the store from the location.  We use here a simple guess that
    the scheme of the parsed URL is the store...

    :param location: Location to check for the store
    """
    loc_pieces = urlparse.urlparse(location)
    return loc_pieces.scheme
