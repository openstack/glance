# Copyright 2012 OpenStack, LLC
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
from glance.openstack.common import timeutils
from glance.openstack.common import uuidutils


class ImageFactory(object):
    _readonly_properties = ['created_at', 'updated_at', 'status', 'checksum',
                            'size']
    _reserved_properties = ['owner', 'is_public', 'location',
                            'deleted', 'deleted_at', 'direct_url', 'self',
                            'file', 'schema']

    def _check_readonly(self, kwargs):
        for key in self._readonly_properties:
            if key in kwargs:
                raise exception.ReadonlyProperty(property=key)

    def _check_unexpected(self, kwargs):
        if len(kwargs) > 0:
            msg = 'new_image() got unexpected keywords %s'
            raise TypeError(msg % kwargs.keys())

    def _check_reserved(self, properties):
        if properties is not None:
            for key in self._reserved_properties:
                if key in properties:
                    raise exception.ReservedProperty(property=key)

    def new_image(self, image_id=None, name=None, visibility='private',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, tags=None, **other_args):
        self._check_readonly(other_args)
        self._check_unexpected(other_args)
        self._check_reserved(extra_properties)

        if image_id is None:
            image_id = uuidutils.generate_uuid()
        created_at = timeutils.utcnow()
        updated_at = created_at
        status = 'queued'

        return Image(image_id=image_id, name=name, status=status,
                     created_at=created_at, updated_at=updated_at,
                     visibility=visibility, min_disk=min_disk,
                     min_ram=min_ram, protected=protected,
                     owner=owner, disk_format=disk_format,
                     container_format=container_format,
                     extra_properties=extra_properties, tags=tags)


class Image(object):

    def __init__(self, image_id, status, created_at, updated_at, **kwargs):
        self.image_id = image_id
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.name = kwargs.pop('name', None)
        self.visibility = kwargs.pop('visibility', 'private')
        self.min_disk = kwargs.pop('min_disk', 0)
        self.min_ram = kwargs.pop('min_ram', 0)
        self.protected = kwargs.pop('protected', False)
        self.location = kwargs.pop('location', None)
        self.checksum = kwargs.pop('checksum', None)
        self.owner = kwargs.pop('owner', None)
        self.disk_format = kwargs.pop('disk_format', None)
        self.container_format = kwargs.pop('container_format', None)
        self.size = kwargs.pop('size', None)
        self.extra_properties = kwargs.pop('extra_properties', None) or {}
        self.tags = kwargs.pop('tags', None) or []
        if len(kwargs) > 0:
            message = "__init__() got unexpected keyword argument '%s'"
            raise TypeError(message % kwargs.keys()[0])

    @property
    def visibility(self):
        return self._visibility

    @visibility.setter
    def visibility(self, visibility):
        if visibility not in ('public', 'private'):
            raise ValueError('Visibility must be either "public" or "private"')
        self._visibility = visibility

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = set(value)

    def delete(self):
        if self.protected:
            raise exception.ProtectedImageDelete(image_id=self.image_id)
        self.status = 'deleted'


def _proxy(target, attr):

    def get_attr(self):
        return getattr(getattr(self, target), attr)

    def set_attr(self, value):
        return setattr(getattr(self, target), attr, value)

    def del_attr(self):
        return delattr(getattr(self, target), attr)

    return property(get_attr, set_attr, del_attr)


class ImageRepoProxy(object):
    def __init__(self, base):
        self.base = base

    def get(self, image_id):
        return self.base.get(image_id)

    def list(self, *args, **kwargs):
        return self.base.list(*args, **kwargs)

    def add(self, image):
        return self.base.add(image)

    def save(self, image):
        return self.base.save(image)

    def remove(self, image):
        return self.base.remove(image)


class ImageProxy(object):
    def __init__(self, base):
        self.base = base

    name = _proxy('base', 'name')
    image_id = _proxy('base', 'image_id')
    name = _proxy('base', 'name')
    status = _proxy('base', 'status')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')
    visibility = _proxy('base', 'visibility')
    min_disk = _proxy('base', 'min_disk')
    min_ram = _proxy('base', 'min_ram')
    protected = _proxy('base', 'protected')
    location = _proxy('base', 'location')
    checksum = _proxy('base', 'checksum')
    owner = _proxy('base', 'owner')
    disk_format = _proxy('base', 'disk_format')
    container_format = _proxy('base', 'container_format')
    size = _proxy('base', 'size')
    extra_properties = _proxy('base', 'extra_properties')
    tags = _proxy('base', 'tags')

    def delete(self):
        self.base.delete()

    def get_member_repo(self):
        return self.base.get_member_repo()


class ImageMembership(object):

    def __init__(self, image_id, member_id, created_at, updated_at,
                 id=None, status=None):
        self.id = id
        self.image_id = image_id
        self.member_id = member_id
        self.created_at = created_at
        self.updated_at = updated_at
        self.status = status

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        if status not in ('pending', 'accepted', 'rejected'):
            msg = _('Status must be "pending", "accepted" or "rejected".')
            raise ValueError(msg)
        self._status = status


class ImageMemberFactory(object):

    def new_image_member(self, image, member_id):
        created_at = timeutils.utcnow()
        updated_at = created_at

        return ImageMembership(image_id=image.image_id, member_id=member_id,
                               created_at=created_at, updated_at=updated_at,
                               status='pending')


class ImageMembershipRepoProxy(object):

    def __init__(self, base):
        self.base = base

    def get(self, image_id):
        return self.base.get(image_id)

    def list(self, *args, **kwargs):
        return self.base.list(*args, **kwargs)

    def add(self, image_member):
        return self.base.add(image_member)

    def save(self, image_member):
        return self.base.save(image_member)

    def remove(self, image_member):
        return self.base.remove(image_member)
