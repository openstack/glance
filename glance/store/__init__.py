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

import optparse
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
    from glance.store.s3 import S3Backend
    from glance.store.swift import SwiftBackend
    from glance.store.filesystem import FilesystemBackend

    BACKENDS = {
        "file": FilesystemBackend,
        "http": HTTPBackend,
        "https": HTTPBackend,
        "swift": SwiftBackend,
        "s3": S3Backend}

    try:
        return BACKENDS[backend]
    except KeyError:
        raise UnsupportedBackend("No backend found for '%s'" % backend)


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

    if hasattr(backend_class, 'delete'):
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


def parse_uri_tokens(parsed_uri, example_url):
    """
    Given a URI and an example_url, attempt to parse the uri to assemble an
    authurl. This method returns the user, key, authurl, referenced container,
    and the object we're looking for in that container.

    Parsing the uri is three phases:
        1) urlparse to split the tokens
        2) use RE to split on @ and /
        3) reassemble authurl

    """
    path = parsed_uri.path.lstrip('//')
    netloc = parsed_uri.netloc

    try:
        try:
            creds, netloc = netloc.split('@')
        except ValueError:
            # Python 2.6.1 compat
            # see lp659445 and Python issue7904
            creds, path = path.split('@')
        user, key = creds.split(':')
        path_parts = path.split('/')
        obj = path_parts.pop()
        container = path_parts.pop()
    except (ValueError, IndexError):
        raise BackendException(
             "Expected four values to unpack in: %s:%s. "
             "Should have received something like: %s."
             % (parsed_uri.scheme, parsed_uri.path, example_url))

    authurl = "https://%s" % '/'.join(path_parts)

    return user, key, authurl, container, obj


def add_options(parser):
    """
    Adds any configuration options that each store might
    have.

    :param parser: An optparse.OptionParser object
    :retval None
    """
    # TODO(jaypipes): Remove these imports...
    from glance.store.http import HTTPBackend
    from glance.store.s3 import S3Backend
    from glance.store.swift import SwiftBackend
    from glance.store.filesystem import FilesystemBackend

    help_text = "The following configuration options are specific to the "\
                "Glance image store."

    DEFAULT_STORE_CHOICES = ['file', 'swift', 's3']
    group = optparse.OptionGroup(parser, "Image Store Options", help_text)
    group.add_option('--default-store', metavar="STORE",
                     default="file",
                     choices=DEFAULT_STORE_CHOICES,
                     help="The backend store that Glance will use to store "
                     "virtual machine images to. Choices: ('%s') "
                     "Default: %%default" % "','".join(DEFAULT_STORE_CHOICES))

    backend_classes = [FilesystemBackend,
                       HTTPBackend,
                       SwiftBackend,
                       S3Backend]
    for backend_class in backend_classes:
        if hasattr(backend_class, 'add_options'):
            backend_class.add_options(group)

    parser.add_option_group(group)
