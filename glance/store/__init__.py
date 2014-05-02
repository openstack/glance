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

import collections
import copy
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

        :param wrappped: the wrapped iterator or filelike.
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
                LOG.warn(_("%s Skipping store driver.") % unicode(e))
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
                LOG.debug("Registering store %s with schemes %s",
                          store_cls, schemes)
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
        get_store_from_scheme(context, scheme)
    except exception.UnknownScheme:
        msg = _("Store for scheme %s not found") % scheme
        raise RuntimeError(msg)


def get_known_schemes():
    """Returns list of known schemes"""
    return location.SCHEME_TO_CLS_MAP.keys()


def get_known_stores():
    """Returns list of known stores"""
    return list(REGISTERED_STORES)


def get_store_from_scheme(context, scheme, loc=None):
    """
    Given a scheme, return the appropriate store object
    for handling that scheme.
    """
    if scheme not in location.SCHEME_TO_CLS_MAP:
        raise exception.UnknownScheme(scheme=scheme)
    scheme_info = location.SCHEME_TO_CLS_MAP[scheme]
    store = scheme_info['store_class'](context, loc)
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
        LOG.warn(six.text_type(e))
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
    elif not isinstance(val, unicode):
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
                      'error': six.text_type(e)})
            LOG.error(e_msg)
            raise BackendException(e_msg)
    return (location, size, checksum, metadata)


def add_to_backend(context, scheme, image_id, data, size):
    store = get_store_from_scheme(context, scheme)
    try:
        return store_add_to_backend(image_id, data, size, store)
    except NotImplementedError:
        raise exception.StoreAddNotSupported


def set_acls(context, location_uri, public=False, read_tenants=[],
             write_tenants=[]):
    loc = location.get_location_from_uri(location_uri)
    scheme = get_store_from_location(location_uri)
    store = get_store_from_scheme(context, scheme, loc)
    try:
        store.set_acls(loc, public=public, read_tenants=read_tenants,
                       write_tenants=write_tenants)
    except NotImplementedError:
        LOG.debug(_("Skipping store.set_acls... not implemented."))


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, store_api):
        self.context = context
        self.store_api = store_api
        proxy_kwargs = {'context': context, 'store_api': store_api}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

    def _set_acls(self, image):
        public = image.visibility == 'public'
        member_ids = []
        if image.locations and not public:
            member_repo = image.get_member_repo()
            member_ids = [m.member_id for m in member_repo.list()]
        for location in image.locations:
            self.store_api.set_acls(self.context, location['url'], public,
                                    read_tenants=member_ids)

    def add(self, image):
        result = super(ImageRepoProxy, self).add(image)
        self._set_acls(image)
        return result

    def save(self, image):
        result = super(ImageRepoProxy, self).save(image)
        self._set_acls(image)
        return result


def _check_location_uri(context, store_api, uri):
    """
    Check if an image location uri is valid.

    :param context: Glance request context
    :param store_api: store API module
    :param uri: location's uri string
    """
    is_ok = True
    try:
        size = store_api.get_size_from_backend(context, uri)
        # NOTE(zhiyan): Some stores return zero when it catch exception
        is_ok = size > 0
    except (exception.UnknownScheme, exception.NotFound):
        is_ok = False
    if not is_ok:
        raise exception.BadStoreUri(_('Invalid location: %s') % uri)


def _check_image_location(context, store_api, location):
    _check_location_uri(context, store_api, location['url'])
    store_api.check_location_metadata(location['metadata'])


def _set_image_size(context, image, locations):
    if not image.size:
        for location in locations:
            size_from_backend = glance.store.get_size_from_backend(
                context, location['url'])
            if size_from_backend:
                # NOTE(flwang): This assumes all locations have the same size
                image.size = size_from_backend
                break


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):
    def __init__(self, factory, context, store_api):
        self.context = context
        self.store_api = store_api
        proxy_kwargs = {'context': context, 'store_api': store_api}
        super(ImageFactoryProxy, self).__init__(factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=proxy_kwargs)

    def new_image(self, **kwargs):
        locations = kwargs.get('locations', [])
        for l in locations:
            _check_image_location(self.context, self.store_api, l)

            if locations.count(l) > 1:
                raise exception.DuplicateLocation(location=l['url'])

        return super(ImageFactoryProxy, self).new_image(**kwargs)


class StoreLocations(collections.MutableSequence):
    """
    The proxy for store location property. It takes responsibility for:
    1. Location uri correctness checking when adding a new location.
    2. Remove the image data from the store when a location is removed
       from an image.
    """
    def __init__(self, image_proxy, value):
        self.image_proxy = image_proxy
        if isinstance(value, list):
            self.value = value
        else:
            self.value = list(value)

    def append(self, location):
        # NOTE(flaper87): Insert this
        # location at the very end of
        # the value list.
        self.insert(len(self.value), location)

    def extend(self, other):
        if isinstance(other, StoreLocations):
            locations = other.value
        else:
            locations = list(other)

        for location in locations:
            self.append(location)

    def insert(self, i, location):
        _check_image_location(self.image_proxy.context,
                              self.image_proxy.store_api, location)

        if location in self.value:
            raise exception.DuplicateLocation(location=location['url'])

        self.value.insert(i, location)
        _set_image_size(self.image_proxy.context,
                        self.image_proxy,
                        [location])

    def pop(self, i=-1):
        location = self.value.pop(i)
        try:
            delete_image_from_backend(self.image_proxy.context,
                                      self.image_proxy.store_api,
                                      self.image_proxy.image.image_id,
                                      location['url'])
        except Exception:
            self.value.insert(i, location)
            raise
        return location

    def count(self, location):
        return self.value.count(location)

    def index(self, location, *args):
        return self.value.index(location, *args)

    def remove(self, location):
        if self.count(location):
            self.pop(self.index(location))
        else:
            self.value.remove(location)

    def reverse(self):
        self.value.reverse()

    # Mutable sequence, so not hashable
    __hash__ = None

    def __getitem__(self, i):
        return self.value.__getitem__(i)

    def __setitem__(self, i, location):
        _check_image_location(self.image_proxy.context,
                              self.image_proxy.store_api, location)
        self.value.__setitem__(i, location)
        _set_image_size(self.image_proxy.context,
                        self.image_proxy,
                        [location])

    def __delitem__(self, i):
        location = None
        try:
            location = self.value.__getitem__(i)
        except Exception:
            return self.value.__delitem__(i)
        delete_image_from_backend(self.image_proxy.context,
                                  self.image_proxy.store_api,
                                  self.image_proxy.image.image_id,
                                  location['url'])
        self.value.__delitem__(i)

    def __delslice__(self, i, j):
        i = max(i, 0)
        j = max(j, 0)
        locations = []
        try:
            locations = self.value.__getslice__(i, j)
        except Exception:
            return self.value.__delslice__(i, j)
        for location in locations:
            delete_image_from_backend(self.image_proxy.context,
                                      self.image_proxy.store_api,
                                      self.image_proxy.image.image_id,
                                      location['url'])
            self.value.__delitem__(i)

    def __iadd__(self, other):
        self.extend(other)
        return self

    def __contains__(self, location):
        return location in self.value

    def __len__(self):
        return len(self.value)

    def __cast(self, other):
        if isinstance(other, StoreLocations):
            return other.value
        else:
            return other

    def __cmp__(self, other):
        return cmp(self.value, self.__cast(other))

    def __iter__(self):
        return iter(self.value)

    def __copy__(self):
        return type(self)(self.image_proxy, self.value)

    def __deepcopy__(self, memo):
        # NOTE(zhiyan): Only copy location entries, others can be reused.
        value = copy.deepcopy(self.value, memo)
        self.image_proxy.image.locations = value
        return type(self)(self.image_proxy, value)


def _locations_proxy(target, attr):
    """
    Make a location property proxy on the image object.

    :param target: the image object on which to add the proxy
    :param attr: the property proxy we want to hook
    """
    def get_attr(self):
        value = getattr(getattr(self, target), attr)
        return StoreLocations(self, value)

    def set_attr(self, value):
        if not isinstance(value, (list, StoreLocations)):
            raise exception.BadStoreUri(_('Invalid locations: %s') % value)
        ori_value = getattr(getattr(self, target), attr)
        if ori_value != value:
            # NOTE(zhiyan): Enforced locations list was previously empty list.
            if len(ori_value) > 0:
                raise exception.Invalid(_('Original locations is not empty: '
                                          '%s') % ori_value)
            # NOTE(zhiyan): Check locations are all valid.
            for location in value:
                _check_image_location(self.context, self.store_api,
                                      location)

                if value.count(location) > 1:
                    raise exception.DuplicateLocation(location=location['url'])
            _set_image_size(self.context, getattr(self, target), value)
            return setattr(getattr(self, target), attr, list(value))

    def del_attr(self):
        value = getattr(getattr(self, target), attr)
        while len(value):
            delete_image_from_backend(self.context, self.store_api,
                                      self.image.image_id, value[0]['url'])
            del value[0]
            setattr(getattr(self, target), attr, value)
        return delattr(getattr(self, target), attr)

    return property(get_attr, set_attr, del_attr)


class ImageProxy(glance.domain.proxy.Image):

    locations = _locations_proxy('image', 'locations')

    def __init__(self, image, context, store_api):
        self.image = image
        self.context = context
        self.store_api = store_api
        proxy_kwargs = {
            'context': context,
            'image': self,
            'store_api': store_api,
        }
        super(ImageProxy, self).__init__(
            image, member_repo_proxy_class=ImageMemberRepoProxy,
            member_repo_proxy_kwargs=proxy_kwargs)

    def delete(self):
        self.image.delete()
        if self.image.locations:
            for location in self.image.locations:
                self.store_api.delete_image_from_backend(self.context,
                                                         self.store_api,
                                                         self.image.image_id,
                                                         location['url'])

    def set_data(self, data, size=None):
        if size is None:
            size = 0  # NOTE(markwash): zero -> unknown size
        location, size, checksum, loc_meta = self.store_api.add_to_backend(
            self.context, CONF.default_store,
            self.image.image_id,
            utils.LimitingReader(utils.CooperativeReader(data),
                                 CONF.image_size_cap),
            size)
        self.image.locations = [{'url': location, 'metadata': loc_meta}]
        self.image.size = size
        self.image.checksum = checksum
        self.image.status = 'active'

    def get_data(self):
        if not self.image.locations:
            raise exception.NotFound(_("No image data could be found"))
        err = None
        for loc in self.image.locations:
            try:
                data, size = self.store_api.get_from_backend(self.context,
                                                             loc['url'])

                return data
            except Exception as e:
                LOG.warn(_('Get image %(id)s data failed: '
                           '%(err)s.') % {'id': self.image.image_id,
                                          'err': six.text_type(e)})
                err = e
        # tried all locations
        LOG.error(_('Glance tried all locations to get data for image %s '
                    'but all have failed.') % self.image.image_id)
        raise err


class ImageMemberRepoProxy(glance.domain.proxy.Repo):
    def __init__(self, repo, image, context, store_api):
        self.repo = repo
        self.image = image
        self.context = context
        self.store_api = store_api
        super(ImageMemberRepoProxy, self).__init__(repo)

    def _set_acls(self):
        public = self.image.visibility == 'public'
        if self.image.locations and not public:
            member_ids = [m.member_id for m in self.repo.list()]
            for location in self.image.locations:
                self.store_api.set_acls(self.context, location['url'], public,
                                        read_tenants=member_ids)

    def add(self, member):
        super(ImageMemberRepoProxy, self).add(member)
        self._set_acls()

    def remove(self, member):
        super(ImageMemberRepoProxy, self).remove(member)
        self._set_acls()
