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
import glance.domain.proxy


def is_image_mutable(context, image):
    """Return True if the image is mutable in this context."""
    if context.is_admin:
        return True

    if image.owner is None or context.owner is None:
        return False

    return image.owner == context.owner


def proxy_image(context, image):
    if is_image_mutable(context, image):
        return ImageProxy(image, context)
    else:
        return ImmutableImageProxy(image, context)


def is_member_mutable(context, member):
    """Return True if the image is mutable in this context."""
    if context.is_admin:
        return True

    if context.owner is None:
        return False

    return member.member_id == context.owner


def proxy_member(context, member):
    if is_member_mutable(context, member):
        return member
    else:
        return ImmutableMemberProxy(member)


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context):
        self.context = context
        self.image_repo = image_repo
        proxy_kwargs = {'context': self.context}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

    def get(self, image_id):
        image = self.image_repo.get(image_id)
        return proxy_image(self.context, image)

    def list(self, *args, **kwargs):
        images = self.image_repo.list(*args, **kwargs)
        return [proxy_image(self.context, i) for i in images]


class ImageMemberRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, member_repo, image, context):
        self.member_repo = member_repo
        self.image = image
        self.context = context
        super(ImageMemberRepoProxy, self).__init__(member_repo)

    def get(self, member_id):
        if (self.context.is_admin or
            self.context.owner == self.image.owner or
            self.context.owner == member_id):
            member = self.member_repo.get(member_id)
            return proxy_member(self.context, member)
        else:
            message = _("You cannot get image member for %s")
            raise exception.Forbidden(message % member_id)

    def list(self, *args, **kwargs):
        members = self.member_repo.list(*args, **kwargs)
        if (self.context.is_admin or
            self.context.owner == self.image.owner):
            return [proxy_member(self.context, m) for m in members]
        for member in members:
            if member.member_id == self.context.owner:
                return [proxy_member(self.context, member)]
        message = _("You cannot get image member for %s")
        raise exception.Forbidden(message % self.image.image_id)

    def remove(self, image_member):
        if (self.image.owner == self.context.owner or
            self.context.is_admin):
            self.member_repo.remove(image_member)
        else:
            message = _("You cannot delete image member for %s")
            raise exception.Forbidden(message
                                      % self.image.image_id)

    def add(self, image_member):
        if (self.image.owner == self.context.owner or
            self.context.is_admin):
            return self.member_repo.add(image_member)
        else:
            message = _("You cannot add image member for %s")
            raise exception.Forbidden(message
                                      % self.image.image_id)

    def save(self, image_member):
        if (self.context.is_admin or
            self.context.owner == image_member.member_id):
            updated_member = self.member_repo.save(image_member)
            return proxy_member(self.context, updated_member)
        else:
            message = _("You cannot update image member %s")
            raise exception.Forbidden(message % image_member.member_id)


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):

    def __init__(self, image_factory, context):
        self.image_factory = image_factory
        self.context = context
        kwargs = {'context': self.context}
        super(ImageFactoryProxy, self).__init__(image_factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=kwargs)

    def new_image(self, **kwargs):
        owner = kwargs.pop('owner', self.context.owner)

        if not self.context.is_admin:
            if owner is None or owner != self.context.owner:
                message = _("You are not permitted to create images "
                            "owned by '%s'.")
                raise exception.Forbidden(message % owner)

        return super(ImageFactoryProxy, self).new_image(owner=owner, **kwargs)


class ImageMemberFactoryProxy(object):

    def __init__(self, image_member_factory, context):
        self.image_member_factory = image_member_factory
        self.context = context

    def new_image_member(self, image, member_id):
        owner = image.owner

        if not self.context.is_admin:
            if owner is None or owner != self.context.owner:
                message = _("You are not permitted to create image members "
                            "for the image.")
                raise exception.Forbidden(message)

        if image.visibility == 'public':
            message = _("Public images do not have members.")
            raise exception.Forbidden(message)

        return self.image_member_factory.new_image_member(image, member_id)


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


class ImmutableLocations(list):
    def forbidden(self, *args, **kwargs):
        message = _("You are not permitted to modify locations "
                    "for this image.")
        raise exception.Forbidden(message)

    append = forbidden
    extend = forbidden
    insert = forbidden
    pop = forbidden
    remove = forbidden
    reverse = forbidden
    sort = forbidden
    __delitem__ = forbidden
    __delslice__ = forbidden
    __iadd__ = forbidden
    __imul__ = forbidden
    __setitem__ = forbidden
    __setslice__ = forbidden


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
    def __init__(self, base, context):
        self.base = base
        self.context = context

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
    locations = _immutable_attr('base', 'locations', proxy=ImmutableLocations)
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

    def get_member_repo(self):
        member_repo = self.base.get_member_repo()
        return ImageMemberRepoProxy(member_repo, self, self.context)

    def get_data(self):
        return self.base.get_data()

    def set_data(self, *args, **kwargs):
        message = _("You are not permitted to upload data for this image.")
        raise exception.Forbidden(message)


class ImmutableMemberProxy(object):
    def __init__(self, base):
        self.base = base

    id = _immutable_attr('base', 'id')
    image_id = _immutable_attr('base', 'image_id')
    member_id = _immutable_attr('base', 'member_id')
    status = _immutable_attr('base', 'status')
    created_at = _immutable_attr('base', 'created_at')
    updated_at = _immutable_attr('base', 'updated_at')


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context):
        self.image = image
        self.context = context
        super(ImageProxy, self).__init__(image)

    def get_member_repo(self, **kwargs):
        if self.image.visibility == 'public':
            message = _("Public images do not have members.")
            raise exception.Forbidden(message)
        else:
            member_repo = self.image.get_member_repo(**kwargs)
            return ImageMemberRepoProxy(member_repo, self, self.context)
