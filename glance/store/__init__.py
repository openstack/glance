# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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
import sys
import time
import urlparse

from glance import registry
from glance.common import cfg
from glance.common import exception
from glance.common import utils
from glance.store import location

logger = logging.getLogger('glance.store')

# Set of known store modules
REGISTERED_STORE_MODULES = []

# Set of store objects, constructed in create_stores()
STORES = {}


class ImageAddResult(object):

    """
    Class that represents the succesful result of adding
    an image to a backend store.
    """

    def __init__(self, location, bytes_written, checksum=None):
        """
        Initialize the object

        :param location: `glance.store.StoreLocation` object representing
                         the location of the image in the backend store
        :param bytes_written: Number of bytes written to store
        :param checksum: Optional checksum of the image data
        """
        self.location = location
        self.bytes_written = bytes_written
        self.checksum = checksum


class BackendException(Exception):
    pass


class UnsupportedBackend(BackendException):
    pass


def register_store(store_module, schemes):
    """
    Registers a store module and a set of schemes
    for which a particular URI request should be routed.

    :param store_module: String representing the store module
    :param schemes: List of strings representing schemes for
                    which this store should be used in routing
    """
    try:
        utils.import_class(store_module + '.Store')
    except exception.NotFound:
        raise BackendException('Unable to register store. Could not find '
                               'a class named Store in module %s.'
                               % store_module)
    REGISTERED_STORE_MODULES.append(store_module)
    scheme_map = {}
    for scheme in schemes:
        scheme_map[scheme] = store_module
    location.register_scheme_map(scheme_map)


def create_stores(conf):
    """
    Construct the store objects with supplied configuration options
    """
    for store_module in REGISTERED_STORE_MODULES:
        try:
            store_class = utils.import_class(store_module + '.Store')
        except exception.NotFound:
            raise BackendException('Unable to create store. Could not find '
                                   'a class named Store in module %s.'
                                   % store_module)
        STORES[store_module] = store_class(conf)


def get_store_from_scheme(scheme):
    """
    Given a scheme, return the appropriate store object
    for handling that scheme
    """
    if scheme not in location.SCHEME_TO_STORE_MAP:
        raise exception.UnknownScheme(scheme=scheme)
    return STORES[location.SCHEME_TO_STORE_MAP[scheme]]


def get_store_from_uri(uri):
    """
    Given a URI, return the store object that would handle
    operations on the URI.

    :param uri: URI to analyze
    """
    scheme = uri[0:uri.find('/') - 1]
    return get_store_from_scheme(scheme)


def get_from_backend(uri, **kwargs):
    """Yields chunks of data from backend specified by uri"""

    store = get_store_from_uri(uri)
    loc = location.get_location_from_uri(uri)

    return store.get(loc)


def get_size_from_backend(uri):
    """Retrieves image size from backend specified by uri"""

    store = get_store_from_uri(uri)
    loc = location.get_location_from_uri(uri)

    return store.get_size(loc)


def delete_from_backend(uri, **kwargs):
    """Removes chunks of data from backend specified by uri"""
    store = get_store_from_uri(uri)
    loc = location.get_location_from_uri(uri)

    try:
        return store.delete(loc)
    except NotImplementedError:
        raise exception.StoreDeleteNotSupported


def get_store_from_location(uri):
    """
    Given a location (assumed to be a URL), attempt to determine
    the store from the location.  We use here a simple guess that
    the scheme of the parsed URL is the store...

    :param uri: Location to check for the store
    """
    loc = location.get_location_from_uri(uri)
    return loc.store_name


scrubber_datadir_opt = cfg.StrOpt('scrubber_datadir',
                                  default='/var/lib/glance/scrubber')


def get_scrubber_datadir(conf):
    conf.register_opt(scrubber_datadir_opt)
    return conf.scrubber_datadir


delete_opts = [
    cfg.BoolOpt('delayed_delete', default=False),
    cfg.IntOpt('scrub_time', default=0)
    ]


def schedule_delete_from_backend(uri, conf, context, image_id, **kwargs):
    """
    Given a uri and a time, schedule the deletion of an image.
    """
    conf.register_opts(delete_opts)
    if not conf.delayed_delete:
        registry.update_image_metadata(context, image_id,
                                       {'status': 'deleted'})
        try:
            return delete_from_backend(uri, **kwargs)
        except (UnsupportedBackend,
                exception.StoreDeleteNotSupported,
                exception.NotFound):
            exc_type = sys.exc_info()[0].__name__
            msg = _("Failed to delete image at %s from store (%s)") % \
                  (uri, exc_type)
            logger.error(msg)
        finally:
            # avoid falling through to the delayed deletion logic
            return

    datadir = get_scrubber_datadir(conf)
    delete_time = time.time() + conf.scrub_time
    file_path = os.path.join(datadir, str(image_id))
    utils.safe_mkdirs(datadir)

    if os.path.exists(file_path):
        msg = _("Image id %(image_id)s already queued for delete") % {
                'image_id': image_id}
        raise exception.Duplicate(msg)

    with open(file_path, 'w') as f:
        f.write('\n'.join([uri, str(int(delete_time))]))
    os.chmod(file_path, 0600)
    os.utime(file_path, (delete_time, delete_time))

    registry.update_image_metadata(context, image_id,
                                   {'status': 'pending_delete'})
