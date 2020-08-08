# Copyright 2014 OpenStack Foundation
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

from collections import abc
import copy
import functools

from cryptography import exceptions as crypto_exception
from cursive import exception as cursive_exception
from cursive import signature_utils
import glance_store as store
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils

from glance.common import exception
from glance.common import format_inspector
from glance.common import utils
import glance.domain.proxy
from glance.i18n import _, _LE, _LI, _LW


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, store_api, store_utils):
        self.context = context
        self.store_api = store_api
        proxy_kwargs = {'context': context, 'store_api': store_api,
                        'store_utils': store_utils}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

        self.db_api = glance.db.get_api()

    def _set_acls(self, image):
        public = image.visibility == 'public'
        member_ids = []
        if image.locations and not public:
            member_repo = _get_member_repo_for_store(image,
                                                     self.context,
                                                     self.db_api,
                                                     self.store_api)
            member_ids = [m.member_id for m in member_repo.list()]
        for location in image.locations:
            if CONF.enabled_backends:
                self.store_api.set_acls_for_multi_store(
                    location['url'], location['metadata'].get('store'),
                    public=public, read_tenants=member_ids,
                    context=self.context
                )
            else:
                self.store_api.set_acls(location['url'], public=public,
                                        read_tenants=member_ids,
                                        context=self.context)

    def add(self, image):
        result = super(ImageRepoProxy, self).add(image)
        self._set_acls(image)
        return result

    def save(self, image, from_state=None):
        result = super(ImageRepoProxy, self).save(image, from_state=from_state)
        self._set_acls(image)
        return result


def _get_member_repo_for_store(image, context, db_api, store_api):
    image_member_repo = glance.db.ImageMemberRepo(context, db_api, image)
    store_image_repo = glance.location.ImageMemberRepoProxy(
        image_member_repo, image, context, store_api)

    return store_image_repo


def _check_location_uri(context, store_api, store_utils, uri,
                        backend=None):
    """Check if an image location is valid.

    :param context: Glance request context
    :param store_api: store API module
    :param store_utils: store utils module
    :param uri: location's uri string
    :param backend: A backend name for the store
    """

    try:
        # NOTE(zhiyan): Some stores return zero when it catch exception
        if CONF.enabled_backends:
            size_from_backend = store_api.get_size_from_uri_and_backend(
                uri, backend, context=context)
        else:
            size_from_backend = store_api.get_size_from_backend(
                uri, context=context)

        is_ok = (store_utils.validate_external_location(uri) and
                 size_from_backend > 0)
    except (store.UnknownScheme, store.NotFound, store.BadStoreUri):
        is_ok = False
    if not is_ok:
        reason = _('Invalid location')
        raise exception.BadStoreUri(message=reason)


def _check_image_location(context, store_api, store_utils, location):
    backend = None
    if CONF.enabled_backends:
        backend = location['metadata'].get('store')

    _check_location_uri(context, store_api, store_utils, location['url'],
                        backend=backend)
    store_api.check_location_metadata(location['metadata'])


def _set_image_size(context, image, locations):
    if not image.size:
        for location in locations:
            if CONF.enabled_backends:
                size_from_backend = store.get_size_from_uri_and_backend(
                    location['url'], location['metadata'].get('store'),
                    context=context)
            else:
                size_from_backend = store.get_size_from_backend(
                    location['url'], context=context)

            if size_from_backend:
                # NOTE(flwang): This assumes all locations have the same size
                image.size = size_from_backend
                break


def _count_duplicated_locations(locations, new):
    """
    To calculate the count of duplicated locations for new one.

    :param locations: The exiting image location set
    :param new: The new image location
    :returns: The count of duplicated locations
    """

    ret = 0
    for loc in locations:
        if loc['url'] == new['url'] and loc['metadata'] == new['metadata']:
            ret += 1
    return ret


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):
    def __init__(self, factory, context, store_api, store_utils):
        self.context = context
        self.store_api = store_api
        self.store_utils = store_utils
        proxy_kwargs = {'context': context, 'store_api': store_api,
                        'store_utils': store_utils}
        super(ImageFactoryProxy, self).__init__(factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=proxy_kwargs)

    def new_image(self, **kwargs):
        locations = kwargs.get('locations', [])
        for loc in locations:
            _check_image_location(self.context,
                                  self.store_api,
                                  self.store_utils,
                                  loc)
            loc['status'] = 'active'
            if _count_duplicated_locations(locations, loc) > 1:
                raise exception.DuplicateLocation(location=loc['url'])
        return super(ImageFactoryProxy, self).new_image(**kwargs)


@functools.total_ordering
class StoreLocations(abc.MutableSequence):
    """
    The proxy for store location property. It takes responsibility for::

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
                              self.image_proxy.store_api,
                              self.image_proxy.store_utils,
                              location)
        location['status'] = 'active'
        if _count_duplicated_locations(self.value, location) > 0:
            raise exception.DuplicateLocation(location=location['url'])

        self.value.insert(i, location)
        _set_image_size(self.image_proxy.context,
                        self.image_proxy,
                        [location])

    def pop(self, i=-1):
        location = self.value.pop(i)
        try:
            self.image_proxy.store_utils.delete_image_location_from_backend(
                self.image_proxy.context,
                self.image_proxy.image.image_id,
                location)
        except store.exceptions.NotFound:
            # NOTE(rosmaita): This can happen if the data was deleted by an
            # operator from the backend, or a race condition from multiple
            # delete-from-store requests. The old way to deal with this was
            # that the user could just delete the image when the data is gone,
            # but with multi-store, that is no longer a good option. So we
            # intentionally leave the location popped (in other words, the
            # pop() succeeds) but we also reraise the NotFound so that the
            # calling code knows what happened.
            with excutils.save_and_reraise_exception():
                pass
        except Exception:
            with excutils.save_and_reraise_exception():
                self.value.insert(i, location)
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
                              self.image_proxy.store_api,
                              self.image_proxy.store_utils,
                              location)
        location['status'] = 'active'
        self.value.__setitem__(i, location)
        _set_image_size(self.image_proxy.context,
                        self.image_proxy,
                        [location])

    def __delitem__(self, i):
        if isinstance(i, slice):
            if i.step not in (None, 1):
                raise NotImplementedError("slice with step")
            self.__delslice__(i.start, i.stop)
            return
        location = None
        try:
            location = self.value[i]
        except Exception:
            del self.value[i]
            return
        self.image_proxy.store_utils.delete_image_location_from_backend(
            self.image_proxy.context,
            self.image_proxy.image.image_id,
            location)
        del self.value[i]

    def __delslice__(self, i, j):
        i = 0 if i is None else max(i, 0)
        j = len(self) if j is None else max(j, 0)
        locations = []
        try:
            locations = self.value[i:j]
        except Exception:
            del self.value[i:j]
            return
        for location in locations:
            self.image_proxy.store_utils.delete_image_location_from_backend(
                self.image_proxy.context,
                self.image_proxy.image.image_id,
                location)
            del self.value[i]

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

    def __eq__(self, other):
        return self.value == self.__cast(other)

    def __lt__(self, other):
        return self.value < self.__cast(other)

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
            reason = _('Invalid locations')
            raise exception.BadStoreUri(message=reason)
        ori_value = getattr(getattr(self, target), attr)
        if ori_value != value:
            # NOTE(flwang): If all the URL of passed-in locations are same as
            # current image locations, that means user would like to only
            # update the metadata, not the URL.
            ordered_value = sorted([loc['url'] for loc in value])
            ordered_ori = sorted([loc['url'] for loc in ori_value])
            if len(ori_value) > 0 and ordered_value != ordered_ori:
                raise exception.Invalid(_('Original locations is not empty: '
                                          '%s') % ori_value)
            # NOTE(zhiyan): Check locations are all valid
            # NOTE(flwang): If all the URL of passed-in locations are same as
            # current image locations, then it's not necessary to verify those
            # locations again. Otherwise, if there is any restricted scheme in
            # existing locations. _check_image_location will fail.
            if ordered_value != ordered_ori:
                for loc in value:
                    _check_image_location(self.context,
                                          self.store_api,
                                          self.store_utils,
                                          loc)
                    loc['status'] = 'active'
                    if _count_duplicated_locations(value, loc) > 1:
                        raise exception.DuplicateLocation(location=loc['url'])
                _set_image_size(self.context, getattr(self, target), value)
            else:
                for loc in value:
                    loc['status'] = 'active'
            return setattr(getattr(self, target), attr, list(value))

    def del_attr(self):
        value = getattr(getattr(self, target), attr)
        while len(value):
            self.store_utils.delete_image_location_from_backend(
                self.context,
                self.image.image_id,
                value[0])
            del value[0]
            setattr(getattr(self, target), attr, value)
        return delattr(getattr(self, target), attr)

    return property(get_attr, set_attr, del_attr)


class ImageProxy(glance.domain.proxy.Image):

    locations = _locations_proxy('image', 'locations')

    def __init__(self, image, context, store_api, store_utils):
        self.image = image
        self.context = context
        self.store_api = store_api
        self.store_utils = store_utils
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
                self.store_utils.delete_image_location_from_backend(
                    self.context,
                    self.image.image_id,
                    location)

    def _upload_to_store(self, data, verifier, store=None, size=None):
        """
        Upload data to store

        :param data: data to upload to store
        :param verifier: for signature verification
        :param store: store to upload data to
        :param size: data size
        :return:
        """
        hashing_algo = self.image.os_hash_algo or CONF['hashing_algorithm']
        if CONF.enabled_backends:
            (location, size, checksum,
             multihash, loc_meta) = self.store_api.add_with_multihash(
                CONF,
                self.image.image_id,
                utils.LimitingReader(utils.CooperativeReader(data),
                                     CONF.image_size_cap),
                size,
                store,
                hashing_algo,
                context=self.context,
                verifier=verifier)
        else:
            (location,
             size,
             checksum,
             multihash,
             loc_meta) = self.store_api.add_to_backend_with_multihash(
                CONF,
                self.image.image_id,
                utils.LimitingReader(utils.CooperativeReader(data),
                                     CONF.image_size_cap),
                size,
                hashing_algo,
                context=self.context,
                verifier=verifier)
        self._verify_signature(verifier, location, loc_meta)
        for attr, data in {"size": size, "os_hash_value": multihash,
                           "checksum": checksum}.items():
            self._verify_uploaded_data(data, attr)
        self.image.locations.append({'url': location, 'metadata': loc_meta,
                                     'status': 'active'})
        self.image.checksum = checksum
        self.image.os_hash_value = multihash
        self.image.size = size
        self.image.os_hash_algo = hashing_algo

    def _verify_signature(self, verifier, location, loc_meta):
        """
        Verify signature of uploaded data.

        :param verifier: for signature verification
        """
        # NOTE(bpoulos): if verification fails, exception will be raised
        if verifier is not None:
            try:
                verifier.verify()
                msg = _LI("Successfully verified signature for image %s")
                LOG.info(msg, self.image.image_id)
            except crypto_exception.InvalidSignature:
                if CONF.enabled_backends:
                    self.store_api.delete(location,
                                          loc_meta.get('store'),
                                          context=self.context)
                else:
                    self.store_api.delete_from_backend(location,
                                                       context=self.context)
                raise cursive_exception.SignatureVerificationError(
                    _('Signature verification failed')
                )

    def _verify_uploaded_data(self, value, attribute_name):
        """
        Verify value of attribute_name uploaded data

        :param value: value to compare
        :param attribute_name: attribute name of the image to compare with
        """
        image_value = getattr(self.image, attribute_name)
        if image_value is not None and value != image_value:
            msg = _("%s of uploaded data is different from current "
                    "value set on the image.")
            LOG.error(msg, attribute_name)
            raise exception.UploadException(msg % attribute_name)

    def set_data(self, data, size=None, backend=None, set_active=True):
        if size is None:
            size = 0  # NOTE(markwash): zero -> unknown size

        # Create the verifier for signature verification (if correct properties
        # are present)
        extra_props = self.image.extra_properties
        verifier = None
        if signature_utils.should_create_verifier(extra_props):
            # NOTE(bpoulos): if creating verifier fails, exception will be
            # raised
            img_signature = extra_props[signature_utils.SIGNATURE]
            hash_method = extra_props[signature_utils.HASH_METHOD]
            key_type = extra_props[signature_utils.KEY_TYPE]
            cert_uuid = extra_props[signature_utils.CERT_UUID]
            verifier = signature_utils.get_verifier(
                context=self.context,
                img_signature_certificate_uuid=cert_uuid,
                img_signature_hash_method=hash_method,
                img_signature=img_signature,
                img_signature_key_type=key_type
            )

        if not self.image.virtual_size:
            inspector = format_inspector.get_inspector(self.image.disk_format)
        else:
            # No need to do this again
            inspector = None

        if inspector and self.image.container_format == 'bare':
            fmt = inspector()
            data = format_inspector.InfoWrapper(data, fmt)
            LOG.debug('Enabling in-flight format inspection for %s', fmt)
        else:
            fmt = None

        self._upload_to_store(data, verifier, backend, size)

        if fmt and fmt.format_match and fmt.virtual_size:
            self.image.virtual_size = fmt.virtual_size
            LOG.info('Image format matched and virtual size computed: %i',
                     self.image.virtual_size)
        elif fmt:
            LOG.warning('Image format %s did not match; '
                        'unable to calculate virtual size',
                        self.image.disk_format)

        if set_active and self.image.status != 'active':
            self.image.status = 'active'

    def get_data(self, offset=0, chunk_size=None):
        if not self.image.locations:
            # NOTE(mclaren): This is the only set of arguments
            # which work with this exception currently, see:
            # https://bugs.launchpad.net/glance-store/+bug/1501443
            # When the above glance_store bug is fixed we can
            # add a msg as usual.
            raise store.NotFound(image=None)
        err = None
        for loc in self.image.locations:
            try:
                backend = loc['metadata'].get('store')
                if CONF.enabled_backends:
                    data, size = self.store_api.get(
                        loc['url'], backend, offset=offset,
                        chunk_size=chunk_size, context=self.context
                    )
                else:
                    data, size = self.store_api.get_from_backend(
                        loc['url'],
                        offset=offset,
                        chunk_size=chunk_size,
                        context=self.context)

                return data
            except Exception as e:
                LOG.warn(_LW('Get image %(id)s data failed: '
                             '%(err)s.'),
                         {'id': self.image.image_id,
                          'err': encodeutils.exception_to_unicode(e)})
                err = e
        # tried all locations
        LOG.error(_LE('Glance tried all active locations to get data for '
                      'image %s but all have failed.'), self.image.image_id)
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
                if CONF.enabled_backends:
                    self.store_api.set_acls_for_multi_store(
                        location['url'], location['metadata'].get('store'),
                        public=public, read_tenants=member_ids,
                        context=self.context
                    )
                else:
                    self.store_api.set_acls(location['url'], public=public,
                                            read_tenants=member_ids,
                                            context=self.context)

    def add(self, member):
        super(ImageMemberRepoProxy, self).add(member)
        self._set_acls()

    def remove(self, member):
        super(ImageMemberRepoProxy, self).remove(member)
        self._set_acls()
