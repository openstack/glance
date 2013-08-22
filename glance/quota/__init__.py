# vim: tabstop=4 shiftwidth=4 softtabstop=4

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


import glance.api.common
import glance.common.exception as exception
from glance.common import utils
import glance.domain
import glance.domain.proxy
import glance.openstack.common.log as logging


LOG = logging.getLogger(__name__)


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, db_api):
        self.image_repo = image_repo
        self.db_api = db_api
        proxy_kwargs = {'db_api': db_api, 'context': context}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):
    def __init__(self, factory, context, db_api):
        proxy_kwargs = {'db_api': db_api, 'context': context}
        super(ImageFactoryProxy, self).__init__(factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=proxy_kwargs)


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

    def __getitem__(self, *args, **kwargs):
        return self.locations.__getitem__(*args, **kwargs)

    def __iadd__(self, other):
        if not hasattr(other, '__iter__'):
            raise TypeError()
        self._check_quota(len(list(other)))
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

    def __getitem__(self, *args, **kwargs):
        return self.locations.__getitem__(*args, **kwargs)

    def _check_quota(self, count):
        glance.api.common.check_quota(
            self.context, self.image.size * count, self.db_api)

    def append(self, object):
        self._check_quota(1)
        return self.locations.append(object)

    def insert(self, index, object):
        self._check_quota(1)
        return self.locations.insert(index, object)

    def extend(self, iter):
        self._check_quota(len(list(iter)))
        return self.locations.extend(iter)


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, db_api):
        self.image = image
        self.context = context
        self.db_api = db_api
        super(ImageProxy, self).__init__(image)

    def set_data(self, data, size=None):
        remaining = glance.api.common.check_quota(
            self.context, size, self.db_api, image_id=self.image.image_id)
        if remaining is not None:
            # NOTE(jbresnah) we are trying to enforce a quota, put a limit
            # reader on the data
            data = utils.LimitingReader(data, remaining)
        try:
            self.image.set_data(data, size=size)
        except exception.ImageSizeLimitExceeded as ex:
            raise exception.StorageQuotaFull(image_size=size,
                                             remaining=remaining)

        # NOTE(jbresnah) If two uploads happen at the same time and neither
        # properly sets the size attribute than there is a race condition
        # that will allow for the quota to be broken.  Thus we must recheck
        # the quota after the upload and thus after we know the size
        try:
            glance.api.common.check_quota(
                self.context, self.image.size, self.db_api,
                image_id=self.image.image_id)
        except exception.StorageQuotaFull:
            LOG.info(_('Cleaning up %s after exceeding the quota.')
                     % self.image.image_id)
            location = self.image.locations[0]['url']
            glance.store.safe_delete_from_backend(
                location, self.context, self.image.image_id)
            raise

    @property
    def locations(self):
        return QuotaImageLocationsProxy(self.image,
                                        self.context,
                                        self.db_api)

    @locations.setter
    def locations(self, value):
        if not isinstance(value, (list, QuotaImageLocationsProxy)):
            raise exception.Invalid(_('Invalid locations: %s') % value)
        glance.api.common.check_quota(
            self.context, self.image.size * len(value), self.db_api,
            image_id=self.image.image_id)
        self.image.locations = value
