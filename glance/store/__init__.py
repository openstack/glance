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

import logging
import optparse
import os
import urlparse

from glance import registry
from glance.common import config, exception
from glance.store import location


logger = logging.getLogger('glance.store')


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
    import glance.store.http
    import glance.store.s3
    import glance.store.swift
    import glance.store.filesystem

    BACKENDS = {
        "filesystem": glance.store.filesystem.FilesystemBackend,
        "http": glance.store.http.HTTPBackend,
        "swift": glance.store.swift.SwiftBackend,
        "s3": glance.store.s3.S3Backend}

    try:
        return BACKENDS[backend]
    except KeyError:
        # Total hack... this will go away with refactor-stores
        try:
            return BACKENDS[location.SCHEME_TO_STORE_MAP[backend]]
        except KeyError:
            raise UnsupportedBackend("No backend found for '%s'" % backend)


def get_from_backend(uri, **kwargs):
    """Yields chunks of data from backend specified by uri"""

    loc = location.get_location_from_uri(uri)
    backend_class = get_backend_class(loc.store_name)

    return backend_class.get(loc, **kwargs)


def delete_from_backend(uri, **kwargs):
    """Removes chunks of data from backend specified by uri"""

    loc = location.get_location_from_uri(uri)
    backend_class = get_backend_class(loc.store_name)

    if hasattr(backend_class, 'delete'):
        return backend_class.delete(loc, **kwargs)


def get_store_from_location(uri):
    """
    Given a location (assumed to be a URL), attempt to determine
    the store from the location.  We use here a simple guess that
    the scheme of the parsed URL is the store...

    :param uri: Location to check for the store
    """
    loc = location.get_location_from_uri(uri)
    return loc.store_name


def schedule_delete_from_backend(uri, options, context, id, **kwargs):
    """
    Given a uri and a time, schedule the deletion of an image.
    """
    use_delay = config.get_option(options, 'delayed_delete', type='bool',
                                  default=False)
    if not use_delay:
        registry.update_image_metadata(options, context, id,
                                       {'status': 'deleted'})
        try:
            return delete_from_backend(uri, **kwargs)
        except (UnsupportedBackend, exception.NotFound):
            msg = "Failed to delete image from store (%s). "
            logger.error(msg % uri)

    registry.update_image_metadata(options, context, id,
                                   {'status': 'pending_delete'})
