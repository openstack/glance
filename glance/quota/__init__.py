# Copyright 2013, Red Hat, Inc.
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

import copy

import glance_store as store
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils

import glance.api.common
import glance.common.exception as exception
from glance.common import utils
import glance.domain
import glance.domain.proxy
from glance.i18n import _, _LI


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('image_member_quota', 'glance.common.config')
CONF.import_opt('image_property_quota', 'glance.common.config')
CONF.import_opt('image_tag_quota', 'glance.common.config')


def _enforce_image_tag_quota(tags):
    if CONF.image_tag_quota < 0:
        # If value is negative, allow unlimited number of tags
        return

    if not tags:
        return

    if len(tags) > CONF.image_tag_quota:
        raise exception.ImageTagLimitExceeded(attempted=len(tags),
                                              maximum=CONF.image_tag_quota)


def _calc_required_size(context, image, locations):
    required_size = None
    if image.size:
        required_size = image.size * len(locations)
    else:
        for location in locations:
            size_from_backend = None

            try:
                if CONF.enabled_backends:
                    size_from_backend = store.get_size_from_uri_and_backend(
                        location['url'], location['metadata'].get('store'),
                        context=context)
                else:
                    size_from_backend = store.get_size_from_backend(
                        location['url'], context=context)
            except (store.UnknownScheme, store.NotFound):
                pass
            except store.BadStoreUri:
                raise exception.BadStoreUri

            if size_from_backend:
                required_size = size_from_backend * len(locations)
                break
    return required_size


def _enforce_image_location_quota(image, locations, is_setter=False):
    if CONF.image_location_quota < 0:
        # If value is negative, allow unlimited number of locations
        return

    attempted = len(image.locations) + len(locations)
    attempted = attempted if not is_setter else len(locations)
    maximum = CONF.image_location_quota
    if attempted > maximum:
        raise exception.ImageLocationLimitExceeded(attempted=attempted,
                                                   maximum=maximum)


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, db_api, store_utils):
        self.image_repo = image_repo
        self.db_api = db_api
        proxy_kwargs = {'context': context, 'db_api': db_api,
                        'store_utils': store_utils}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

    def _enforce_image_property_quota(self, attempted):
        if CONF.image_property_quota < 0:
            # If value is negative, allow unlimited number of properties
            return

        maximum = CONF.image_property_quota
        if attempted > maximum:
            kwargs = {'attempted': attempted, 'maximum': maximum}
            exc = exception.ImagePropertyLimitExceeded(**kwargs)
            LOG.debug(encodeutils.exception_to_unicode(exc))
            raise exc

    def save(self, image, from_state=None):
        if image.added_new_properties():
            self._enforce_image_property_quota(len(image.extra_properties))
        return super(ImageRepoProxy, self).save(image, from_state=from_state)

    def add(self, image):
        self._enforce_image_property_quota(len(image.extra_properties))
        return super(ImageRepoProxy, self).add(image)


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):
    def __init__(self, factory, context, db_api, store_utils):
        proxy_kwargs = {'context': context, 'db_api': db_api,
                        'store_utils': store_utils}
        super(ImageFactoryProxy, self).__init__(factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=proxy_kwargs)

    def new_image(self, **kwargs):
        tags = kwargs.pop('tags', set([]))
        _enforce_image_tag_quota(tags)
        return super(ImageFactoryProxy, self).new_image(tags=tags, **kwargs)


class QuotaImageTagsProxy(object):

    def __init__(self, orig_set):
        if orig_set is None:
            orig_set = set([])
        self.tags = orig_set

    def add(self, item):
        self.tags.add(item)
        _enforce_image_tag_quota(self.tags)

    def __cast__(self, *args, **kwargs):
        return self.tags.__cast__(*args, **kwargs)

    def __contains__(self, *args, **kwargs):
        return self.tags.__contains__(*args, **kwargs)

    def __eq__(self, other):
        return self.tags == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __iter__(self, *args, **kwargs):
        return self.tags.__iter__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self.tags.__len__(*args, **kwargs)

    def __getattr__(self, name):
        # Protect against deepcopy, which calls getattr. __getattr__
        # is only called when an attribute is not "normal", so when
        # self.tags is called, this is not.
        if name == 'tags':
            try:
                return self.__getattribute__('tags')
            except AttributeError:
                return None
        return getattr(self.tags, name)


class ImageMemberFactoryProxy(glance.domain.proxy.ImageMembershipFactory):

    def __init__(self, member_factory, context, db_api, store_utils):
        self.db_api = db_api
        self.context = context
        proxy_kwargs = {'context': context, 'db_api': db_api,
                        'store_utils': store_utils}
        super(ImageMemberFactoryProxy, self).__init__(
            member_factory,
            proxy_class=ImageMemberProxy,
            proxy_kwargs=proxy_kwargs)

    def _enforce_image_member_quota(self, image):
        if CONF.image_member_quota < 0:
            # If value is negative, allow unlimited number of members
            return

        current_member_count = self.db_api.image_member_count(self.context,
                                                              image.image_id)
        attempted = current_member_count + 1
        maximum = CONF.image_member_quota
        if attempted > maximum:
            raise exception.ImageMemberLimitExceeded(attempted=attempted,
                                                     maximum=maximum)

    def new_image_member(self, image, member_id):
        self._enforce_image_member_quota(image)
        return super(ImageMemberFactoryProxy, self).new_image_member(image,
                                                                     member_id)


class QuotaImageLocationsProxy(object):

    def __init__(self, image, context, db_api):
        self.image = image
        self.context = context
        self.db_api = db_api
        self.locations = image.locations

    def __cast__(self, *args, **kwargs):
        return self.locations.__cast__(*args, **kwargs)

    def __contains__(self, *args, **kwargs):
        return self.locations.__contains__(*args, **kwargs)

    def __delitem__(self, *args, **kwargs):
        return self.locations.__delitem__(*args, **kwargs)

    def __delslice__(self, *args, **kwargs):
        return self.locations.__delslice__(*args, **kwargs)

    def __eq__(self, other):
        return self.locations == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __getitem__(self, *args, **kwargs):
        return self.locations.__getitem__(*args, **kwargs)

    def __iadd__(self, other):
        if not hasattr(other, '__iter__'):
            raise TypeError()
        self._check_user_storage_quota(other)
        return self.locations.__iadd__(other)

    def __iter__(self, *args, **kwargs):
        return self.locations.__iter__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self.locations.__len__(*args, **kwargs)

    def __setitem__(self, key, value):
        return self.locations.__setitem__(key, value)

    def count(self, *args, **kwargs):
        return self.locations.count(*args, **kwargs)

    def index(self, *args, **kwargs):
        return self.locations.index(*args, **kwargs)

    def pop(self, *args, **kwargs):
        return self.locations.pop(*args, **kwargs)

    def remove(self, *args, **kwargs):
        return self.locations.remove(*args, **kwargs)

    def reverse(self, *args, **kwargs):
        return self.locations.reverse(*args, **kwargs)

    def _check_user_storage_quota(self, locations):
        required_size = _calc_required_size(self.context,
                                            self.image,
                                            locations)
        glance.api.common.check_quota(self.context,
                                      required_size,
                                      self.db_api)
        _enforce_image_location_quota(self.image, locations)

    def __copy__(self):
        return type(self)(self.image, self.context, self.db_api)

    def __deepcopy__(self, memo):
        # NOTE(zhiyan): Only copy location entries, others can be reused.
        self.image.locations = copy.deepcopy(self.locations, memo)
        return type(self)(self.image, self.context, self.db_api)

    def append(self, object):
        self._check_user_storage_quota([object])
        return self.locations.append(object)

    def insert(self, index, object):
        self._check_user_storage_quota([object])
        return self.locations.insert(index, object)

    def extend(self, iter):
        self._check_user_storage_quota(iter)
        return self.locations.extend(iter)


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, db_api, store_utils):
        self.image = image
        self.context = context
        self.db_api = db_api
        self.store_utils = store_utils
        super(ImageProxy, self).__init__(image)
        self.orig_props = set(image.extra_properties.keys())

    def set_data(self, data, size=None, backend=None, set_active=True):
        remaining = glance.api.common.check_quota(
            self.context, size, self.db_api, image_id=self.image.image_id)
        if remaining is not None:
            # NOTE(jbresnah) we are trying to enforce a quota, put a limit
            # reader on the data
            data = utils.LimitingReader(
                data, remaining, exception_class=exception.StorageQuotaFull)

        self.image.set_data(data, size=size, backend=backend,
                            set_active=set_active)

        # NOTE(jbresnah) If two uploads happen at the same time and neither
        # properly sets the size attribute[1] then there is a race condition
        # that will allow for the quota to be broken[2].  Thus we must recheck
        # the quota after the upload and thus after we know the size.
        #
        # Also, when an upload doesn't set the size properly then the call to
        # check_quota above returns None and so utils.LimitingReader is not
        # used above. Hence the store (e.g.  filesystem store) may have to
        # download the entire file before knowing the actual file size.  Here
        # also we need to check for the quota again after the image has been
        # downloaded to the store.
        #
        # [1] For e.g. when using chunked transfers the 'Content-Length'
        #     header is not set.
        # [2] For e.g.:
        #       - Upload 1 does not exceed quota but upload 2 exceeds quota.
        #         Both uploads are to different locations
        #       - Upload 2 completes before upload 1 and writes image.size.
        #       - Immediately, upload 1 completes and (over)writes image.size
        #         with the smaller size.
        #       - Now, to glance, image has not exceeded quota but, in
        #         reality, the quota has been exceeded.

        try:
            glance.api.common.check_quota(
                self.context, self.image.size, self.db_api,
                image_id=self.image.image_id)
        except exception.StorageQuotaFull:
            with excutils.save_and_reraise_exception():
                LOG.info(_LI('Cleaning up %s after exceeding the quota.'),
                         self.image.image_id)
                self.store_utils.safe_delete_from_backend(
                    self.context, self.image.image_id, self.image.locations[0])

    @property
    def tags(self):
        return QuotaImageTagsProxy(self.image.tags)

    @tags.setter
    def tags(self, value):
        _enforce_image_tag_quota(value)
        self.image.tags = value

    @property
    def locations(self):
        return QuotaImageLocationsProxy(self.image,
                                        self.context,
                                        self.db_api)

    @locations.setter
    def locations(self, value):
        _enforce_image_location_quota(self.image, value, is_setter=True)

        if not isinstance(value, (list, QuotaImageLocationsProxy)):
            raise exception.Invalid(_('Invalid locations: %s') % value)

        required_size = _calc_required_size(self.context,
                                            self.image,
                                            value)

        glance.api.common.check_quota(
            self.context, required_size, self.db_api,
            image_id=self.image.image_id)
        self.image.locations = value

    def added_new_properties(self):
        current_props = set(self.image.extra_properties.keys())
        return bool(current_props.difference(self.orig_props))


class ImageMemberProxy(glance.domain.proxy.ImageMember):

    def __init__(self, image_member, context, db_api, store_utils):
        self.image_member = image_member
        self.context = context
        self.db_api = db_api
        self.store_utils = store_utils
        super(ImageMemberProxy, self).__init__(image_member)
