# Copyright 2012 OpenStack Foundation
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

from glance.common import exception
import glance.domain


def is_image_mutable(context, image):
    """Return True if the image is mutable in this context."""
    if context.is_admin:
        return True

    if image.owner is None or context.owner is None:
        return False

    return image.owner == context.owner


def proxy_image(context, image):
    if is_image_mutable(context, image):
        return image
    else:
        return ImmutableImageProxy(image)


class ImageRepoProxy(glance.domain.ImageRepoProxy):

    def __init__(self, image_repo, context):
        self.context = context
        self.image_repo = image_repo
        super(ImageRepoProxy, self).__init__(image_repo)

    def get(self, *args, **kwargs):
        image = self.image_repo.get(*args, **kwargs)
        return proxy_image(self.context, image)

    def list(self, *args, **kwargs):
        images = self.image_repo.list(*args, **kwargs)
        return [proxy_image(self.context, i) for i in images]


class ImageFactoryProxy(object):

    def __init__(self, image_factory, context):
        self.image_factory = image_factory
        self.context = context

    def new_image(self, **kwargs):
        owner = kwargs.pop('owner', self.context.owner)

        if not self.context.is_admin:
            if owner is None or owner != self.context.owner:
                message = _("You are not permitted to create images "
                            "owned by '%s'.")
                raise exception.Forbidden(message % owner)

        return self.image_factory.new_image(owner=owner, **kwargs)


def _immutable_attr(target, attr, proxy=None):

    def get_attr(self):
        value = getattr(getattr(self, target), attr)
        if proxy is not None:
            value = proxy(value)
        return value

    def forbidden(self, *args, **kwargs):
        message = _("You are not permitted to modify '%s' on this image.")
        raise exception.Forbidden(message % attr)

    return property(get_attr, forbidden, forbidden)


class ImmutableProperties(dict):
    def forbidden_key(self, key, *args, **kwargs):
        message = _("You are not permitted to modify '%s' on this image.")
        raise exception.Forbidden(message % key)

    def forbidden(self, *args, **kwargs):
        message = _("You are not permitted to modify this image.")
        raise exception.Forbidden(message)

    __delitem__ = forbidden_key
    __setitem__ = forbidden_key
    pop = forbidden
    popitem = forbidden
    setdefault = forbidden
    update = forbidden


class ImmutableTags(set):
    def forbidden(self, *args, **kwargs):
        message = _("You are not permitted to modify tags on this image.")
        raise exception.Forbidden(message)

    add = forbidden
    clear = forbidden
    difference_update = forbidden
    intersection_update = forbidden
    pop = forbidden
    remove = forbidden
    symmetric_difference_update = forbidden
    update = forbidden


class ImmutableImageProxy(object):
    def __init__(self, base):
        self.base = base

    name = _immutable_attr('base', 'name')
    image_id = _immutable_attr('base', 'image_id')
    name = _immutable_attr('base', 'name')
    status = _immutable_attr('base', 'status')
    created_at = _immutable_attr('base', 'created_at')
    updated_at = _immutable_attr('base', 'updated_at')
    visibility = _immutable_attr('base', 'visibility')
    min_disk = _immutable_attr('base', 'min_disk')
    min_ram = _immutable_attr('base', 'min_ram')
    protected = _immutable_attr('base', 'protected')
    location = _immutable_attr('base', 'location')
    checksum = _immutable_attr('base', 'checksum')
    owner = _immutable_attr('base', 'owner')
    disk_format = _immutable_attr('base', 'disk_format')
    container_format = _immutable_attr('base', 'container_format')
    size = _immutable_attr('base', 'size')
    extra_properties = _immutable_attr('base', 'extra_properties',
                                       proxy=ImmutableProperties)
    tags = _immutable_attr('base', 'tags', proxy=ImmutableTags)

    def delete(self):
        message = _("You are not permitted to delete this image.")
        raise exception.Forbidden(message)
