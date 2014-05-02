# Copyright 2010-2011 OpenStack Foundation
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

import sys

from oslo.config import cfg
import six

from glance.common import exception
from glance.common import utils
import glance.context
import glance.domain.proxy
from glance.openstack.common import importutils
import glance.openstack.common.log as logging
from glance import scrubber
from glance.store import location

LOG = logging.getLogger(__name__)

store_opts = [
    cfg.ListOpt('known_stores',
                default=[
                    'glance.store.filesystem.Store',
                    'glance.store.http.Store'
                ],
                help=_('List of which store classes and store class locations '
                       'are currently known to glance at startup.')),
    cfg.StrOpt('default_store', default='file',
               help=_("Default scheme to use to store image data. The "
                      "scheme must be registered by one of the stores "
                      "defined by the 'known_stores' config option.")),
    cfg.StrOpt('scrubber_datadir',
               default='/var/lib/glance/scrubber',
               help=_('Directory that the scrubber will use to track '
                      'information about what to delete. '
                      'Make sure this is set in glance-api.conf and '
                      'glance-scrubber.conf.')),
    cfg.BoolOpt('delayed_delete', default=False,
                help=_('Turn on/off delayed delete.')),
    cfg.BoolOpt('use_user_token', default=True,
                help=_('Whether to pass through the user token when '
                       'making requests to the registry.')),
    cfg.IntOpt('scrub_time', default=0,
               help=_('The amount of time in seconds to delay before '
                      'performing a delete.')),
]

REGISTERED_STORES = set()
CONF = cfg.CONF
CONF.register_opts(store_opts)

_ALL_STORES = [
    'glance.store.filesystem.Store',
    'glance.store.http.Store',
    'glance.store.rbd.Store',
    'glance.store.s3.Store',
    'glance.store.swift.Store',
    'glance.store.sheepdog.Store',
    'glance.store.cinder.Store',
    'glance.store.gridfs.Store',
    'glance.store.vmware_datastore.Store'
]


class BackendException(Exception):
    pass


class UnsupportedBackend(BackendException):
    pass


class Indexable(object):

    """
    Wrapper that allows an iterator or filelike be treated as an indexable
    data structure. This is required in the case where the return value from
    Store.get() is passed to Store.add() when adding a Copy-From image to a
    Store where the client library relies on eventlet GreenSockets, in which
    case the data to be written is indexed over.
    """

    def __init__(self, wrapped, size):
        """
        Initialize the object

        :param wrapped: the wrapped iterator or filelike.
        :param size: the size of data available
        """
        self.wrapped = wrapped
        self.size = int(size) if size else (wrapped.len
                                            if hasattr(wrapped, 'len') else 0)
        self.cursor = 0
        self.chunk = None

    def __iter__(self):
        """
        Delegate iteration to the wrapped instance.
        """
        for self.chunk in self.wrapped:
            yield self.chunk

    def __getitem__(self, i):
        """
        Index into the next chunk (or previous chunk in the case where
        the last data returned was not fully consumed).

        :param i: a slice-to-the-end
        """
        start = i.start if isinstance(i, slice) else i
        if start < self.cursor:
            return self.chunk[(start - self.cursor):]

        self.chunk = self.another()
        if self.chunk:
            self.cursor += len(self.chunk)

        return self.chunk

    def another(self):
        """Implemented by subclasses to return the next element"""
        raise NotImplementedError

    def getvalue(self):
        """
        Return entire string value... used in testing
        """
        return self.wrapped.getvalue()

    def __len__(self):
        """
        Length accessor.
        """
        return self.size


def _register_stores(store_classes):
    """
    Given a set of store names, add them to a globally available set
    of store names.
    """
    for store_cls in store_classes:
        REGISTERED_STORES.add(store_cls.__module__.split('.')[2])
    # NOTE (spredzy): The actual class name is filesystem but in order
    # to maintain backward compatibility we need to keep the 'file' store
    # as a known store
    if 'filesystem' in REGISTERED_STORES:
        REGISTERED_STORES.add('file')


def _get_store_class(store_entry):
    store_cls = None
    try:
        LOG.debug("Attempting to import store %s", store_entry)
        store_cls = importutils.import_class(store_entry)
    except exception.NotFound:
        raise BackendException('Unable to load store. '
                               'Could not find a class named %s.'
                               % store_entry)
    return store_cls


def create_stores():
    """
    Registers all store modules and all schemes
    from the given config. Duplicates are not re-registered.
    """
    store_count = 0
    store_classes = set()
    for store_entry in set(CONF.known_stores + _ALL_STORES):
        store_entry = store_entry.strip()
        if not store_entry:
            continue
        store_cls = _get_store_class(store_entry)
        try:
            store_instance = store_cls()
        except exception.BadStoreConfiguration as e:
            if store_entry in CONF.known_stores:
                LOG.warn(_("%s Skipping store driver.") %
                         utils.exception_to_str(e))
            continue
        finally:
            # NOTE(flaper87): To be removed in Juno
            if store_entry not in CONF.known_stores:
                LOG.deprecated(_("%s not found in `known_store`. "
                                 "Stores need to be explicitly enabled in "
                                 "the configuration file.") % store_entry)

        schemes = store_instance.get_schemes()
        if not schemes:
            raise BackendException('Unable to register store %s. '
                                   'No schemes associated with it.'
                                   % store_cls)
        else:
            if store_cls not in store_classes:
                LOG.debug("Registering store %(cls)s with schemes "
                          "%(schemes)s", {'cls': store_cls,
                                          'schemes': schemes})
                store_classes.add(store_cls)
                scheme_map = {}
                for scheme in schemes:
                    loc_cls = store_instance.get_store_location_class()
                    scheme_map[scheme] = {
                        'store_class': store_cls,
                        'location_class': loc_cls,
                    }
                location.register_scheme_map(scheme_map)
                store_count += 1
            else:
                LOG.debug("Store %s already registered", store_cls)
    _register_stores(store_classes)
    return store_count


def verify_default_store():
    scheme = cfg.CONF.default_store
    context = glance.context.RequestContext()
    try:
        get_store_from_scheme(context, scheme, configure=False)
    except exception.UnknownScheme:
        msg = _("Store for scheme %s not found") % scheme
        raise RuntimeError(msg)


def get_known_schemes():
    """Returns list of known schemes"""
    return location.SCHEME_TO_CLS_MAP.keys()


def get_known_stores():
    """Returns list of known stores"""
    return list(REGISTERED_STORES)


def get_store_from_scheme(context, scheme, loc=None, configure=True):
    """
    Given a scheme, return the appropriate store object
    for handling that scheme.
    """
    if scheme not in location.SCHEME_TO_CLS_MAP:
        raise exception.UnknownScheme(scheme=scheme)
    scheme_info = location.SCHEME_TO_CLS_MAP[scheme]
    store = scheme_info['store_class'](context, loc, configure)
    return store


def get_store_from_uri(context, uri, loc=None):
    """
    Given a URI, return the store object that would handle
    operations on the URI.

    :param uri: URI to analyze
    """
    scheme = uri[0:uri.find('/') - 1]
    store = get_store_from_scheme(context, scheme, loc)
    return store


def get_from_backend(context, uri, **kwargs):
    """Yields chunks of data from backend specified by uri"""

    loc = location.get_location_from_uri(uri)
    store = get_store_from_uri(context, uri, loc)

    try:
        return store.get(loc)
    except NotImplementedError:
        raise exception.StoreGetNotSupported


def get_size_from_backend(context, uri):
    """Retrieves image size from backend specified by uri"""

    loc = location.get_location_from_uri(uri)
    store = get_store_from_uri(context, uri, loc)

    return store.get_size(loc)


def delete_from_backend(context, uri, **kwargs):
    """Removes chunks of data from backend specified by uri"""
    loc = location.get_location_from_uri(uri)
    store = get_store_from_uri(context, uri, loc)

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


def safe_delete_from_backend(context, uri, image_id, **kwargs):
    """Given a uri, delete an image from the store."""
    try:
        return delete_from_backend(context, uri, **kwargs)
    except exception.NotFound:
        msg = _('Failed to delete image %s in store from URI')
        LOG.warn(msg % image_id)
    except exception.StoreDeleteNotSupported as e:
        LOG.warn(utils.exception_to_str(e))
    except UnsupportedBackend:
        exc_type = sys.exc_info()[0].__name__
        msg = (_('Failed to delete image %(image_id)s from store '
                 '(%(error)s)') % {'image_id': image_id,
                                   'error': exc_type})
        LOG.error(msg)


def schedule_delayed_delete_from_backend(context, uri, image_id, **kwargs):
    """Given a uri, schedule the deletion of an image location."""
    (file_queue, _db_queue) = scrubber.get_scrub_queues()
    # NOTE(zhiyan): Defautly ask glance-api store using file based queue.
    # In future we can change it using DB based queued instead,
    # such as using image location's status to saving pending delete flag
    # when that property be added.
    if CONF.use_user_token is False:
        context = None
    file_queue.add_location(image_id, uri, user_context=context)


def delete_image_from_backend(context, store_api, image_id, uri):
    if CONF.delayed_delete:
        store_api.schedule_delayed_delete_from_backend(context, uri, image_id)
    else:
        store_api.safe_delete_from_backend(context, uri, image_id)


def check_location_metadata(val, key=''):
    if isinstance(val, dict):
        for key in val:
            check_location_metadata(val[key], key=key)
    elif isinstance(val, list):
        ndx = 0
        for v in val:
            check_location_metadata(v, key='%s[%d]' % (key, ndx))
            ndx = ndx + 1
    elif not isinstance(val, six.text_type):
        raise BackendException(_("The image metadata key %(key)s has an "
                                 "invalid type of %(val)s.  Only dict, list, "
                                 "and unicode are supported.") %
                               {'key': key,
                                'val': type(val)})


def store_add_to_backend(image_id, data, size, store):
    """
    A wrapper around a call to each stores add() method.  This gives glance
    a common place to check the output

    :param image_id:  The image add to which data is added
    :param data: The data to be stored
    :param size: The length of the data in bytes
    :param store: The store to which the data is being added
    :return: The url location of the file,
             the size amount of data,
             the checksum of the data
             the storage systems metadata dictionary for the location
    """
    (location, size, checksum, metadata) = store.add(image_id, data, size)
    if metadata is not None:
        if not isinstance(metadata, dict):
            msg = (_("The storage driver %(store)s returned invalid metadata "
                     "%(metadata)s. This must be a dictionary type") %
                   {'store': six.text_type(store),
                    'metadata': six.text_type(metadata)})
            LOG.error(msg)
            raise BackendException(msg)
        try:
            check_location_metadata(metadata)
        except BackendException as e:
            e_msg = (_("A bad metadata structure was returned from the "
                       "%(store)s storage driver: %(metadata)s.  %(error)s.") %
                     {'store': six.text_type(store),
                      'metadata': six.text_type(metadata),
                      'error': utils.exception_to_str(e)})
            LOG.error(e_msg)
            raise BackendException(e_msg)
    return (location, size, checksum, metadata)


def add_to_backend(context, scheme, image_id, data, size):
    store = get_store_from_scheme(context, scheme)
    try:
        return store_add_to_backend(image_id, data, size, store)
    except NotImplementedError:
        raise exception.StoreAddNotSupported


def set_acls(context, location_uri, public=False, read_tenants=None,
             write_tenants=None):
    if read_tenants is None:
        read_tenants = []
    if write_tenants is None:
        write_tenants = []

    loc = location.get_location_from_uri(location_uri)
    scheme = get_store_from_location(location_uri)
    store = get_store_from_scheme(context, scheme, loc)
    try:
        store.set_acls(loc, public=public, read_tenants=read_tenants,
                       write_tenants=write_tenants)
    except NotImplementedError:
        LOG.debug("Skipping store.set_acls... not implemented.")
