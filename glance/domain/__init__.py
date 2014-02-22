# Copyright 2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
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
import datetime
import uuid

from oslo.config import cfg

from glance.common import exception
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


_delayed_delete_imported = False


def _import_delayed_delete():
    # glance.store (indirectly) imports glance.domain therefore we can't put
    # the CONF.import_opt outside - we have to do it in a convoluted/indirect
    # way!
    global _delayed_delete_imported
    if not _delayed_delete_imported:
        CONF.import_opt('delayed_delete', 'glance.store')
        _delayed_delete_imported = True


class ImageFactory(object):
    _readonly_properties = ['created_at', 'updated_at', 'status', 'checksum',
                            'size', 'virtual_size']
    _reserved_properties = ['owner', 'is_public', 'locations',
                            'deleted', 'deleted_at', 'direct_url', 'self',
                            'file', 'schema']

    def _check_readonly(self, kwargs):
        for key in self._readonly_properties:
            if key in kwargs:
                raise exception.ReadonlyProperty(property=key)

    def _check_unexpected(self, kwargs):
        if kwargs:
            msg = _('new_image() got unexpected keywords %s')
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
            image_id = str(uuid.uuid4())
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

    valid_state_targets = {
        # Each key denotes a "current" state for the image. Corresponding
        # values list the valid states to which we can jump from that "current"
        # state.
        # NOTE(flwang): In v2, we are deprecating the 'killed' status, so it's
        # allowed to restore image from 'saving' to 'queued' so that upload
        # can be retried.
        'queued': ('saving', 'active', 'deleted'),
        'saving': ('active', 'killed', 'deleted', 'queued'),
        'active': ('queued', 'pending_delete', 'deleted'),
        'killed': ('deleted'),
        'pending_delete': ('deleted'),
        'deleted': (),
    }

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
        self.locations = kwargs.pop('locations', [])
        self.checksum = kwargs.pop('checksum', None)
        self.owner = kwargs.pop('owner', None)
        self._disk_format = kwargs.pop('disk_format', None)
        self._container_format = kwargs.pop('container_format', None)
        self.size = kwargs.pop('size', None)
        self.virtual_size = kwargs.pop('virtual_size', None)
        extra_properties = kwargs.pop('extra_properties', None) or {}
        self.extra_properties = ExtraProperties(extra_properties)
        self.tags = kwargs.pop('tags', None) or []
        if kwargs:
            message = _("__init__() got unexpected keyword argument '%s'")
            raise TypeError(message % kwargs.keys()[0])

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        has_status = hasattr(self, '_status')
        if has_status:
            if status not in self.valid_state_targets[self._status]:
                kw = {'cur_status': self._status, 'new_status': status}
                e = exception.InvalidImageStatusTransition(**kw)
                LOG.debug(e)
                raise e

            if self._status == 'queued' and status in ('saving', 'active'):
                missing = [k for k in ['disk_format', 'container_format']
                           if not getattr(self, k)]
                if len(missing) > 0:
                    if len(missing) == 1:
                        msg = _('Property %s must be set prior to '
                                'saving data.')
                    else:
                        msg = _('Properties %s must be set prior to '
                                'saving data.')
                    raise ValueError(msg % ', '.join(missing))
        # NOTE(flwang): Image size should be cleared as long as the image
        # status is updated to 'queued'
        if status == 'queued':
            self.size = None
            self.virtual_size = None
        self._status = status

    @property
    def visibility(self):
        return self._visibility

    @visibility.setter
    def visibility(self, visibility):
        if visibility not in ('public', 'private'):
            raise ValueError(_('Visibility must be either "public" '
                               'or "private"'))
        self._visibility = visibility

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = set(value)

    @property
    def container_format(self):
        return self._container_format

    @container_format.setter
    def container_format(self, value):
        if hasattr(self, '_container_format') and self.status != 'queued':
            msg = _("Attribute container_format can be only replaced "
                    "for a queued image.")
            raise exception.Forbidden(message=msg)
        self._container_format = value

    @property
    def disk_format(self):
        return self._disk_format

    @disk_format.setter
    def disk_format(self, value):
        if hasattr(self, '_disk_format') and self.status != 'queued':
            msg = _("Attribute disk_format can be only replaced "
                    "for a queued image.")
            raise exception.Forbidden(message=msg)
        self._disk_format = value

    @property
    def min_disk(self):
        return self._min_disk

    @min_disk.setter
    def min_disk(self, value):
        if value and value < 0:
            extra_msg = _('Cannot be a negative value')
            raise exception.InvalidParameterValue(value=value,
                                                  param='min_disk',
                                                  extra_msg=extra_msg)
        self._min_disk = value

    @property
    def min_ram(self):
        return self._min_ram

    @min_ram.setter
    def min_ram(self, value):
        if value and value < 0:
            extra_msg = _('Cannot be a negative value')
            raise exception.InvalidParameterValue(value=value,
                                                  param='min_ram',
                                                  extra_msg=extra_msg)
        self._min_ram = value

    def delete(self):
        if self.protected:
            raise exception.ProtectedImageDelete(image_id=self.image_id)
        if CONF.delayed_delete and self.locations:
            self.status = 'pending_delete'
        else:
            self.status = 'deleted'

    def get_data(self):
        raise NotImplementedError()

    def set_data(self, data, size=None):
        raise NotImplementedError()


class ExtraProperties(collections.MutableMapping, dict):

    def __getitem__(self, key):
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        return dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        return dict.__delitem__(self, key)

    def __eq__(self, other):
        if isinstance(other, ExtraProperties):
            return dict(self).__eq__(dict(other))
        elif isinstance(other, dict):
            return dict(self).__eq__(other)
        else:
            return False

    def __len__(self):
        return dict(self).__len__()

    def keys(self):
        return dict(self).keys()


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


class Task(object):
    _supported_task_type = ('import',)

    _supported_task_status = ('pending', 'processing', 'success', 'failure')

    def __init__(self, task_id, task_type, status, owner,
                 expires_at, created_at, updated_at, task_time_to_live=48):

        if task_type not in self._supported_task_type:
            raise exception.InvalidTaskType(task_type)

        if status not in self._supported_task_status:
            raise exception.InvalidTaskStatus(status)

        self.task_id = task_id
        self._status = status
        self.type = task_type
        self.owner = owner
        self.expires_at = expires_at
        # NOTE(nikhil): We use '_time_to_live' to determine how long a
        # task should live from the time it succeeds or fails.
        self._time_to_live = datetime.timedelta(hours=task_time_to_live)
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def status(self):
        return self._status

    def run(self, executor):
        pass

    def _validate_task_status_transition(self, cur_status, new_status):
            valid_transitions = {
                'pending': ['processing', 'failure'],
                'processing': ['success', 'failure'],
                'success': [],
                'failure': [],
            }

            if new_status in valid_transitions[cur_status]:
                return True
            else:
                return False

    def _set_task_status(self, new_status):
        if self._validate_task_status_transition(self.status, new_status):
            self._status = new_status
            log_msg = (_("Task status changed from %(cur_status)s to "
                         "%(new_status)s") % {'cur_status': self.status,
                                              'new_status': new_status})
            LOG.info(log_msg)
        else:
            log_msg = (_("Task status failed to change from %(cur_status)s "
                         "to %(new_status)s") % {'cur_status': self.status,
                                                 'new_status': new_status})
            LOG.error(log_msg)
            raise exception.InvalidTaskStatusTransition(
                cur_status=self.status,
                new_status=new_status
            )

    def begin_processing(self):
        new_status = 'processing'
        self._set_task_status(new_status)

    def succeed(self, result):
        new_status = 'success'
        self.result = result
        self._set_task_status(new_status)
        self.expires_at = timeutils.utcnow() + self._time_to_live

    def fail(self, message):
        new_status = 'failure'
        self.message = message
        self._set_task_status(new_status)
        self.expires_at = timeutils.utcnow() + self._time_to_live


class TaskDetails(object):

    def __init__(self, task_id, task_input, message, result):
        if task_id is None:
            raise exception.TaskException(_('task_id is required to create '
                                            'a new TaskDetails object'))
        self.task_id = task_id
        self.input = task_input
        self.message = message
        self.result = result


class TaskFactory(object):

    def new_task(self, task_type, owner, task_time_to_live=48):
        task_id = str(uuid.uuid4())
        status = 'pending'
        # Note(nikhil): expires_at would be set on the task, only when it
        # succeeds or fails.
        expires_at = None
        created_at = timeutils.utcnow()
        updated_at = created_at
        return Task(
            task_id,
            task_type,
            status,
            owner,
            expires_at,
            created_at,
            updated_at,
            task_time_to_live
        )

    def new_task_details(self, task_id, task_input, message=None, result=None):
        return TaskDetails(task_id, task_input, message, result)
