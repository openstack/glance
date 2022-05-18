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

from collections import abc
import datetime
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import importutils

from glance.common import exception
from glance.common import timeutils
from glance.i18n import _, _LE, _LI, _LW

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('task_executor', 'glance.common.config', group='task')


_delayed_delete_imported = False


def _import_delayed_delete():
    # glance_store (indirectly) imports glance.domain therefore we can't put
    # the CONF.import_opt outside - we have to do it in a convoluted/indirect
    # way!
    global _delayed_delete_imported
    if not _delayed_delete_imported:
        CONF.import_opt('delayed_delete', 'glance_store')
        _delayed_delete_imported = True


class ImageFactory(object):
    _readonly_properties = ['created_at', 'updated_at', 'status', 'checksum',
                            'os_hash_algo', 'os_hash_value', 'size',
                            'virtual_size']
    _reserved_properties = ['owner', 'locations', 'deleted', 'deleted_at',
                            'direct_url', 'self', 'file', 'schema']

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

    def new_image(self, image_id=None, name=None, visibility='shared',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, tags=None, os_hidden=False,
                  **other_args):
        extra_properties = extra_properties or {}
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
                     os_hidden=os_hidden,
                     extra_properties=extra_properties, tags=tags or [])


class Image(object):

    valid_state_targets = {
        # Each key denotes a "current" state for the image. Corresponding
        # values list the valid states to which we can jump from that "current"
        # state.
        # NOTE(flwang): In v2, we are deprecating the 'killed' status, so it's
        # allowed to restore image from 'saving' to 'queued' so that upload
        # can be retried.
        'queued': ('saving', 'uploading', 'importing', 'active', 'deleted'),
        'saving': ('active', 'killed', 'deleted', 'queued'),
        'uploading': ('importing', 'queued', 'deleted'),
        'importing': ('active', 'deleted', 'queued'),
        'active': ('pending_delete', 'deleted', 'deactivated'),
        'killed': ('deleted',),
        'pending_delete': ('deleted', 'active'),
        'deleted': (),
        'deactivated': ('active', 'deleted'),
    }

    def __init__(self, image_id, status, created_at, updated_at, **kwargs):
        self.image_id = image_id
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.name = kwargs.pop('name', None)
        self.visibility = kwargs.pop('visibility', 'shared')
        self.os_hidden = kwargs.pop('os_hidden', False)
        self.min_disk = kwargs.pop('min_disk', 0)
        self.min_ram = kwargs.pop('min_ram', 0)
        self.protected = kwargs.pop('protected', False)
        self.locations = kwargs.pop('locations', [])
        self.checksum = kwargs.pop('checksum', None)
        self.os_hash_algo = kwargs.pop('os_hash_algo', None)
        self.os_hash_value = kwargs.pop('os_hash_value', None)
        self.owner = kwargs.pop('owner', None)
        self._disk_format = kwargs.pop('disk_format', None)
        self._container_format = kwargs.pop('container_format', None)
        self.size = kwargs.pop('size', None)
        self.virtual_size = kwargs.pop('virtual_size', None)
        extra_properties = kwargs.pop('extra_properties', {})
        self.extra_properties = ExtraProperties(extra_properties)
        self.tags = kwargs.pop('tags', [])
        self.member = kwargs.pop('member', None)
        if kwargs:
            message = _("__init__() got unexpected keyword argument '%s'")
            raise TypeError(message % list(kwargs.keys())[0])

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

            if self._status in ('queued', 'uploading') and status in (
                    'saving', 'active', 'importing'):
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
        if visibility not in ('community', 'public', 'private', 'shared'):
            raise ValueError(_('Visibility must be one of "community", '
                               '"public", "private", or "shared"'))
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
        if (hasattr(self, '_container_format') and
                self.status not in ('queued', 'importing')):
            msg = _("Attribute container_format can be only replaced "
                    "for a queued image.")
            raise exception.Forbidden(message=msg)
        self._container_format = value

    @property
    def disk_format(self):
        return self._disk_format

    @disk_format.setter
    def disk_format(self, value):
        if (hasattr(self, '_disk_format') and
                self.status not in ('queued', 'importing')):
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

    def deactivate(self):
        if self.status == 'active':
            self.status = 'deactivated'
        elif self.status == 'deactivated':
            # Noop if already deactivate
            pass
        else:
            LOG.debug("Not allowed to deactivate image in status '%s'",
                      self.status)
            msg = (_("Not allowed to deactivate image in status '%s'")
                   % self.status)
            raise exception.Forbidden(message=msg)

    def reactivate(self):
        if self.status == 'deactivated':
            self.status = 'active'
        elif self.status == 'active':
            # Noop if already active
            pass
        else:
            LOG.debug("Not allowed to reactivate image in status '%s'",
                      self.status)
            msg = (_("Not allowed to reactivate image in status '%s'")
                   % self.status)
            raise exception.Forbidden(message=msg)

    def get_data(self, *args, **kwargs):
        raise NotImplementedError()

    def set_data(self, data, size=None, backend=None, set_active=True):
        raise NotImplementedError()


class ExtraProperties(abc.MutableMapping, dict):

    def __getitem__(self, key):
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        return dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        return dict.__delitem__(self, key)

    def __eq__(self, other):
        if isinstance(other, ExtraProperties):
            return dict.__eq__(self, dict(other))
        elif isinstance(other, dict):
            return dict.__eq__(self, other)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __len__(self):
        return dict.__len__(self)

    def keys(self):
        return dict.keys(self)


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
    _supported_task_type = ('import', 'api_image_import')

    _supported_task_status = ('pending', 'processing', 'success', 'failure')

    def __init__(self, task_id, task_type, status, owner,
                 image_id, user_id, request_id,
                 expires_at, created_at, updated_at,
                 task_input, result, message):

        if task_type not in self._supported_task_type:
            raise exception.InvalidTaskType(type=task_type)

        if status not in self._supported_task_status:
            raise exception.InvalidTaskStatus(status=status)

        self.task_id = task_id
        self._status = status
        self.type = task_type
        self.owner = owner
        self.expires_at = expires_at
        # NOTE(nikhil): We use '_time_to_live' to determine how long a
        # task should live from the time it succeeds or fails.
        task_time_to_live = CONF.task.task_time_to_live
        self._time_to_live = datetime.timedelta(hours=task_time_to_live)
        self.created_at = created_at
        self.updated_at = updated_at
        self.task_input = task_input
        self.result = result
        self.message = message
        self.image_id = image_id
        self.request_id = request_id
        self.user_id = user_id

    @property
    def status(self):
        return self._status

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, message):
        if message:
            self._message = str(message)
        else:
            self._message = ''

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
            old_status = self.status
            self._status = new_status
            LOG.info(_LI("Task [%(task_id)s] status changing from "
                         "%(cur_status)s to %(new_status)s"),
                     {'task_id': self.task_id, 'cur_status': old_status,
                      'new_status': new_status})
        else:
            LOG.error(_LE("Task [%(task_id)s] status failed to change from "
                          "%(cur_status)s to %(new_status)s"),
                      {'task_id': self.task_id, 'cur_status': self.status,
                       'new_status': new_status})
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

    def run(self, executor):
        executor.begin_processing(self.task_id)


class TaskStub(object):

    def __init__(self, task_id, task_type, status, owner,
                 expires_at, created_at, updated_at,
                 image_id, user_id, request_id):
        self.task_id = task_id
        self._status = status
        self.type = task_type
        self.owner = owner
        self.expires_at = expires_at
        self.created_at = created_at
        self.updated_at = updated_at
        self.image_id = image_id
        self.request_id = request_id
        self.user_id = user_id

    @property
    def status(self):
        return self._status


class TaskFactory(object):

    def new_task(self, task_type, owner, image_id, user_id,
                 request_id, task_input=None, **kwargs):
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
            image_id,
            user_id,
            request_id,
            expires_at,
            created_at,
            updated_at,
            task_input,
            kwargs.get('result'),
            kwargs.get('message'),
        )


class TaskExecutorFactory(object):
    eventlet_deprecation_warned = False

    def __init__(self, task_repo, image_repo, image_factory, admin_repo=None):
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory
        self.admin_repo = admin_repo

    def new_task_executor(self, context):
        try:
            # NOTE(flaper87): Backwards compatibility layer.
            # It'll allow us to provide a deprecation path to
            # users that are currently consuming the `eventlet`
            # executor.
            task_executor = CONF.task.task_executor
            if task_executor == 'eventlet':
                # NOTE(jokke): Making sure we do not log the deprecation
                # warning 1000 times or anything crazy like that.
                if not TaskExecutorFactory.eventlet_deprecation_warned:
                    msg = _LW("The `eventlet` executor has been deprecated. "
                              "Use `taskflow` instead.")
                    LOG.warning(msg)
                    TaskExecutorFactory.eventlet_deprecation_warned = True
                task_executor = 'taskflow'

            executor_cls = ('glance.async_.%s_executor.'
                            'TaskExecutor' % task_executor)
            LOG.debug("Loading %s executor", task_executor)
            executor = importutils.import_class(executor_cls)
            return executor(context,
                            self.task_repo,
                            self.image_repo,
                            self.image_factory,
                            admin_repo=self.admin_repo)
        except ImportError:
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("Failed to load the %s executor provided "
                                  "in the config."), CONF.task.task_executor)


class MetadefNamespace(object):

    def __init__(self, namespace_id, namespace, display_name, description,
                 owner, visibility, protected, created_at, updated_at):
        self.namespace_id = namespace_id
        self.namespace = namespace
        self.display_name = display_name
        self.description = description
        self.owner = owner
        self.visibility = visibility or "private"
        self.protected = protected or False
        self.created_at = created_at
        self.updated_at = updated_at

    def delete(self):
        if self.protected:
            raise exception.ProtectedMetadefNamespaceDelete(
                namespace=self.namespace)


class MetadefNamespaceFactory(object):

    def new_namespace(self, namespace, owner, **kwargs):
        namespace_id = str(uuid.uuid4())
        created_at = timeutils.utcnow()
        updated_at = created_at
        return MetadefNamespace(
            namespace_id,
            namespace,
            kwargs.get('display_name'),
            kwargs.get('description'),
            owner,
            kwargs.get('visibility'),
            kwargs.get('protected'),
            created_at,
            updated_at
        )


class MetadefObject(object):

    def __init__(self, namespace, object_id, name, created_at, updated_at,
                 required, description, properties):
        self.namespace = namespace
        self.object_id = object_id
        self.name = name
        self.created_at = created_at
        self.updated_at = updated_at
        self.required = required
        self.description = description
        self.properties = properties

    def delete(self):
        if self.namespace.protected:
            raise exception.ProtectedMetadefObjectDelete(object_name=self.name)


class MetadefObjectFactory(object):

    def new_object(self, namespace, name, **kwargs):
        object_id = str(uuid.uuid4())
        created_at = timeutils.utcnow()
        updated_at = created_at
        return MetadefObject(
            namespace,
            object_id,
            name,
            created_at,
            updated_at,
            kwargs.get('required'),
            kwargs.get('description'),
            kwargs.get('properties')
        )


class MetadefResourceType(object):

    def __init__(self, namespace, name, prefix, properties_target,
                 created_at, updated_at):
        self.namespace = namespace
        self.name = name
        self.prefix = prefix
        self.properties_target = properties_target
        self.created_at = created_at
        self.updated_at = updated_at

    def delete(self):
        if self.namespace.protected:
            raise exception.ProtectedMetadefResourceTypeAssociationDelete(
                resource_type=self.name)


class MetadefResourceTypeFactory(object):

    def new_resource_type(self, namespace, name, **kwargs):
        created_at = timeutils.utcnow()
        updated_at = created_at
        return MetadefResourceType(
            namespace,
            name,
            kwargs.get('prefix'),
            kwargs.get('properties_target'),
            created_at,
            updated_at
        )


class MetadefProperty(object):

    def __init__(self, namespace, property_id, name, schema):
        self.namespace = namespace
        self.property_id = property_id
        self.name = name
        self.schema = schema

    def delete(self):
        if self.namespace.protected:
            raise exception.ProtectedMetadefNamespacePropDelete(
                property_name=self.name)


class MetadefPropertyFactory(object):

    def new_namespace_property(self, namespace, name, schema, **kwargs):
        property_id = str(uuid.uuid4())
        return MetadefProperty(
            namespace,
            property_id,
            name,
            schema
        )


class MetadefTag(object):

    def __init__(self, namespace, tag_id, name, created_at, updated_at):
        self.namespace = namespace
        self.tag_id = tag_id
        self.name = name
        self.created_at = created_at
        self.updated_at = updated_at

    def delete(self):
        if self.namespace.protected:
            raise exception.ProtectedMetadefTagDelete(tag_name=self.name)


class MetadefTagFactory(object):

    def new_tag(self, namespace, name, **kwargs):
        tag_id = str(uuid.uuid4())
        created_at = timeutils.utcnow()
        updated_at = created_at
        return MetadefTag(
            namespace,
            tag_id,
            name,
            created_at,
            updated_at
        )
