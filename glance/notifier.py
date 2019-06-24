# Copyright 2011, OpenStack Foundation
# Copyright 2012, Red Hat, Inc.
# Copyright 2013 IBM Corp.
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

import abc

import glance_store
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging
from oslo_utils import encodeutils
from oslo_utils import excutils
import six
import webob

from glance.common import exception
from glance.common import timeutils
from glance.domain import proxy as domain_proxy
from glance.i18n import _, _LE


notifier_opts = [
    cfg.StrOpt('default_publisher_id',
               default="image.localhost",
               help=_("""
Default publisher_id for outgoing Glance notifications.

This is the value that the notification driver will use to identify
messages for events originating from the Glance service. Typically,
this is the hostname of the instance that generated the message.

Possible values:
    * Any reasonable instance identifier, for example: image.host1

Related options:
    * None

""")),
    cfg.ListOpt('disabled_notifications',
                default=[],
                help=_("""
List of notifications to be disabled.

Specify a list of notifications that should not be emitted.
A notification can be given either as a notification type to
disable a single event notification, or as a notification group
prefix to disable all event notifications within a group.

Possible values:
    A comma-separated list of individual notification types or
    notification groups to be disabled. Currently supported groups:

    * image
    * image.member
    * task
    * metadef_namespace
    * metadef_object
    * metadef_property
    * metadef_resource_type
    * metadef_tag

    For a complete listing and description of each event refer to:
    http://docs.openstack.org/developer/glance/notifications.html

    The values must be specified as: <group_name>.<event_name>
    For example: image.create,task.success,metadef_tag

Related options:
    * None

""")),
]

CONF = cfg.CONF
CONF.register_opts(notifier_opts)

LOG = logging.getLogger(__name__)


def set_defaults(control_exchange='glance'):
    oslo_messaging.set_transport_defaults(control_exchange)


def get_transport():
    return oslo_messaging.get_notification_transport(CONF)


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    def __init__(self):
        publisher_id = CONF.default_publisher_id
        self._transport = get_transport()
        self._notifier = oslo_messaging.Notifier(self._transport,
                                                 publisher_id=publisher_id)

    def warn(self, event_type, payload):
        self._notifier.warn({}, event_type, payload)

    def info(self, event_type, payload):
        self._notifier.info({}, event_type, payload)

    def error(self, event_type, payload):
        self._notifier.error({}, event_type, payload)


def _get_notification_group(notification):
    return notification.split('.', 1)[0]


def _is_notification_enabled(notification):
    disabled_notifications = CONF.disabled_notifications
    notification_group = _get_notification_group(notification)

    notifications = (notification, notification_group)
    for disabled_notification in disabled_notifications:
        if disabled_notification in notifications:
            return False

    return True


def _send_notification(notify, notification_type, payload):
    if _is_notification_enabled(notification_type):
        notify(notification_type, payload)


def format_image_notification(image):
    """
    Given a glance.domain.Image object, return a dictionary of relevant
    notification information. We purposely do not include 'location'
    as it may contain credentials.
    """
    return {
        'id': image.image_id,
        'name': image.name,
        'status': image.status,
        'created_at': timeutils.isotime(image.created_at),
        'updated_at': timeutils.isotime(image.updated_at),
        'min_disk': image.min_disk,
        'min_ram': image.min_ram,
        'protected': image.protected,
        'checksum': image.checksum,
        'owner': image.owner,
        'disk_format': image.disk_format,
        'container_format': image.container_format,
        'size': image.size,
        'virtual_size': image.virtual_size,
        'is_public': image.visibility == 'public',
        'visibility': image.visibility,
        'properties': dict(image.extra_properties),
        'tags': list(image.tags),
        'deleted': False,
        'deleted_at': None,
    }


def format_image_member_notification(image_member):
    """Given a glance.domain.ImageMember object, return a dictionary of relevant
    notification information.
    """
    return {
        'image_id': image_member.image_id,
        'member_id': image_member.member_id,
        'status': image_member.status,
        'created_at': timeutils.isotime(image_member.created_at),
        'updated_at': timeutils.isotime(image_member.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_task_notification(task):
    # NOTE(nikhil): input is not passed to the notifier payload as it may
    # contain sensitive info.
    return {
        'id': task.task_id,
        'type': task.type,
        'status': task.status,
        'result': None,
        'owner': task.owner,
        'message': None,
        'expires_at': timeutils.isotime(task.expires_at),
        'created_at': timeutils.isotime(task.created_at),
        'updated_at': timeutils.isotime(task.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_namespace_notification(metadef_namespace):
    return {
        'namespace': metadef_namespace.namespace,
        'namespace_old': metadef_namespace.namespace,
        'display_name': metadef_namespace.display_name,
        'protected': metadef_namespace.protected,
        'visibility': metadef_namespace.visibility,
        'owner': metadef_namespace.owner,
        'description': metadef_namespace.description,
        'created_at': timeutils.isotime(metadef_namespace.created_at),
        'updated_at': timeutils.isotime(metadef_namespace.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_object_notification(metadef_object):
    object_properties = metadef_object.properties or {}
    properties = []
    for name, prop in six.iteritems(object_properties):
        object_property = _format_metadef_object_property(name, prop)
        properties.append(object_property)

    return {
        'namespace': metadef_object.namespace,
        'name': metadef_object.name,
        'name_old': metadef_object.name,
        'properties': properties,
        'required': metadef_object.required,
        'description': metadef_object.description,
        'created_at': timeutils.isotime(metadef_object.created_at),
        'updated_at': timeutils.isotime(metadef_object.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def _format_metadef_object_property(name, metadef_property):
    return {
        'name': name,
        'type': metadef_property.type or None,
        'title': metadef_property.title or None,
        'description': metadef_property.description or None,
        'default': metadef_property.default or None,
        'minimum': metadef_property.minimum or None,
        'maximum': metadef_property.maximum or None,
        'enum': metadef_property.enum or None,
        'pattern': metadef_property.pattern or None,
        'minLength': metadef_property.minLength or None,
        'maxLength': metadef_property.maxLength or None,
        'confidential': metadef_property.confidential or None,
        'items': metadef_property.items or None,
        'uniqueItems': metadef_property.uniqueItems or None,
        'minItems': metadef_property.minItems or None,
        'maxItems': metadef_property.maxItems or None,
        'additionalItems': metadef_property.additionalItems or None,
    }


def format_metadef_property_notification(metadef_property):
    schema = metadef_property.schema

    return {
        'namespace': metadef_property.namespace,
        'name': metadef_property.name,
        'name_old': metadef_property.name,
        'type': schema.get('type'),
        'title': schema.get('title'),
        'description': schema.get('description'),
        'default': schema.get('default'),
        'minimum': schema.get('minimum'),
        'maximum': schema.get('maximum'),
        'enum': schema.get('enum'),
        'pattern': schema.get('pattern'),
        'minLength': schema.get('minLength'),
        'maxLength': schema.get('maxLength'),
        'confidential': schema.get('confidential'),
        'items': schema.get('items'),
        'uniqueItems': schema.get('uniqueItems'),
        'minItems': schema.get('minItems'),
        'maxItems': schema.get('maxItems'),
        'additionalItems': schema.get('additionalItems'),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_resource_type_notification(metadef_resource_type):
    return {
        'namespace': metadef_resource_type.namespace,
        'name': metadef_resource_type.name,
        'name_old': metadef_resource_type.name,
        'prefix': metadef_resource_type.prefix,
        'properties_target': metadef_resource_type.properties_target,
        'created_at': timeutils.isotime(metadef_resource_type.created_at),
        'updated_at': timeutils.isotime(metadef_resource_type.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_tag_notification(metadef_tag):
    return {
        'namespace': metadef_tag.namespace,
        'name': metadef_tag.name,
        'name_old': metadef_tag.name,
        'created_at': timeutils.isotime(metadef_tag.created_at),
        'updated_at': timeutils.isotime(metadef_tag.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


class NotificationBase(object):
    def get_payload(self, obj):
        return {}

    def send_notification(self, notification_id, obj, extra_payload=None,
                          backend=None):
        payload = self.get_payload(obj)
        if extra_payload is not None:
            payload.update(extra_payload)

        # update backend information in the notification
        if backend:
            payload["backend"] = backend

        _send_notification(self.notifier.info, notification_id, payload)


@six.add_metaclass(abc.ABCMeta)
class NotificationProxy(NotificationBase):
    def __init__(self, repo, context, notifier):
        self.repo = repo
        self.context = context
        self.notifier = notifier

        super_class = self.get_super_class()
        super_class.__init__(self, repo)

    @abc.abstractmethod
    def get_super_class(self):
        pass


@six.add_metaclass(abc.ABCMeta)
class NotificationRepoProxy(NotificationBase):
    def __init__(self, repo, context, notifier):
        self.repo = repo
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}

        proxy_class = self.get_proxy_class()
        super_class = self.get_super_class()
        super_class.__init__(self, repo, proxy_class, proxy_kwargs)

    @abc.abstractmethod
    def get_super_class(self):
        pass

    @abc.abstractmethod
    def get_proxy_class(self):
        pass


@six.add_metaclass(abc.ABCMeta)
class NotificationFactoryProxy(object):
    def __init__(self, factory, context, notifier):
        kwargs = {'context': context, 'notifier': notifier}

        proxy_class = self.get_proxy_class()
        super_class = self.get_super_class()
        super_class.__init__(self, factory, proxy_class, kwargs)

    @abc.abstractmethod
    def get_super_class(self):
        pass

    @abc.abstractmethod
    def get_proxy_class(self):
        pass


class ImageProxy(NotificationProxy, domain_proxy.Image):
    def get_super_class(self):
        return domain_proxy.Image

    def get_payload(self, obj):
        return format_image_notification(obj)

    def _format_image_send(self, bytes_sent):
        return {
            'bytes_sent': bytes_sent,
            'image_id': self.repo.image_id,
            'owner_id': self.repo.owner,
            'receiver_tenant_id': self.context.project_id,
            'receiver_user_id': self.context.user_id,
        }

    def _format_import_properties(self):
        importing = self.repo.extra_properties.get(
            'os_glance_importing_to_stores')
        importing = importing.split(',') if importing else []
        failed = self.repo.extra_properties.get('os_glance_failed_import')
        failed = failed.split(',') if failed else []
        return {
            'os_glance_importing_to_stores': importing,
            'os_glance_failed_import': failed
        }

    def _get_chunk_data_iterator(self, data, chunk_size=None):
        sent = 0
        for chunk in data:
            yield chunk
            sent += len(chunk)

        if sent != (chunk_size or self.repo.size):
            notify = self.notifier.error
        else:
            notify = self.notifier.info

        try:
            _send_notification(notify, 'image.send',
                               self._format_image_send(sent))
        except Exception as err:
            msg = (_LE("An error occurred during image.send"
                       " notification: %(err)s") % {'err': err})
            LOG.error(msg)

    def get_data(self, offset=0, chunk_size=None):
        # Due to the need of evaluating subsequent proxies, this one
        # should return a generator, the call should be done before
        # generator creation
        data = self.repo.get_data(offset=offset, chunk_size=chunk_size)
        return self._get_chunk_data_iterator(data, chunk_size=chunk_size)

    def set_data(self, data, size=None, backend=None, set_active=True):
        self.send_notification('image.prepare', self.repo, backend=backend,
                               extra_payload=self._format_import_properties())

        notify_error = self.notifier.error
        status = self.repo.status
        try:
            self.repo.set_data(data, size, backend=backend,
                               set_active=set_active)
        except glance_store.StorageFull as e:
            msg = (_("Image storage media is full: %s") %
                   encodeutils.exception_to_unicode(e))
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg)
        except glance_store.StorageWriteDenied as e:
            msg = (_("Insufficient permissions on image storage media: %s")
                   % encodeutils.exception_to_unicode(e))
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPServiceUnavailable(explanation=msg)
        except ValueError as e:
            msg = (_("Cannot save data for image %(image_id)s: %(error)s") %
                   {'image_id': self.repo.image_id,
                    'error': encodeutils.exception_to_unicode(e)})
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPBadRequest(
                explanation=encodeutils.exception_to_unicode(e))
        except exception.Duplicate as e:
            msg = (_("Unable to upload duplicate image data for image "
                     "%(image_id)s: %(error)s") %
                   {'image_id': self.repo.image_id,
                    'error': encodeutils.exception_to_unicode(e)})
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPConflict(explanation=msg)
        except exception.Forbidden as e:
            msg = (_("Not allowed to upload image data for image %(image_id)s:"
                     " %(error)s")
                   % {'image_id': self.repo.image_id,
                      'error': encodeutils.exception_to_unicode(e)})
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPForbidden(explanation=msg)
        except exception.NotFound as e:
            exc_str = encodeutils.exception_to_unicode(e)
            msg = (_("Image %(image_id)s could not be found after upload."
                     " The image may have been deleted during the upload:"
                     " %(error)s") % {'image_id': self.repo.image_id,
                                      'error': exc_str})
            _send_notification(notify_error, 'image.upload', msg)
            raise webob.exc.HTTPNotFound(explanation=exc_str)
        except webob.exc.HTTPError as e:
            with excutils.save_and_reraise_exception():
                msg = (_("Failed to upload image data for image %(image_id)s"
                         " due to HTTP error: %(error)s") %
                       {'image_id': self.repo.image_id,
                        'error': encodeutils.exception_to_unicode(e)})
                _send_notification(notify_error, 'image.upload', msg)
        except Exception as e:
            with excutils.save_and_reraise_exception():
                msg = (_("Failed to upload image data for image %(image_id)s "
                         "due to internal error: %(error)s") %
                       {'image_id': self.repo.image_id,
                        'error': encodeutils.exception_to_unicode(e)})
                _send_notification(notify_error, 'image.upload', msg)
        else:
            extra_payload = self._format_import_properties()
            self.send_notification('image.upload', self.repo,
                                   extra_payload=extra_payload)
            if set_active and status != 'active':
                self.send_notification('image.activate', self.repo)


class ImageMemberProxy(NotificationProxy, domain_proxy.ImageMember):
    def get_super_class(self):
        return domain_proxy.ImageMember


class ImageFactoryProxy(NotificationFactoryProxy, domain_proxy.ImageFactory):
    def get_super_class(self):
        return domain_proxy.ImageFactory

    def get_proxy_class(self):
        return ImageProxy


class ImageRepoProxy(NotificationRepoProxy, domain_proxy.Repo):
    def get_super_class(self):
        return domain_proxy.Repo

    def get_proxy_class(self):
        return ImageProxy

    def get_payload(self, obj):
        return format_image_notification(obj)

    def save(self, image, from_state=None):
        super(ImageRepoProxy, self).save(image, from_state=from_state)
        self.send_notification('image.update', image)

    def add(self, image):
        super(ImageRepoProxy, self).add(image)
        self.send_notification('image.create', image)

    def remove(self, image):
        super(ImageRepoProxy, self).remove(image)
        self.send_notification('image.delete', image, extra_payload={
            'deleted': True, 'deleted_at': timeutils.isotime()
        })


class ImageMemberRepoProxy(NotificationBase, domain_proxy.MemberRepo):

    def __init__(self, repo, image, context, notifier):
        self.repo = repo
        self.image = image
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}

        proxy_class = self.get_proxy_class()
        super_class = self.get_super_class()
        super_class.__init__(self, image, repo, proxy_class, proxy_kwargs)

    def get_super_class(self):
        return domain_proxy.MemberRepo

    def get_proxy_class(self):
        return ImageMemberProxy

    def get_payload(self, obj):
        return format_image_member_notification(obj)

    def save(self, member, from_state=None):
        super(ImageMemberRepoProxy, self).save(member, from_state=from_state)
        self.send_notification('image.member.update', member)

    def add(self, member):
        super(ImageMemberRepoProxy, self).add(member)
        self.send_notification('image.member.create', member)

    def remove(self, member):
        super(ImageMemberRepoProxy, self).remove(member)
        self.send_notification('image.member.delete', member, extra_payload={
            'deleted': True, 'deleted_at': timeutils.isotime()
        })


class TaskProxy(NotificationProxy, domain_proxy.Task):
    def get_super_class(self):
        return domain_proxy.Task

    def get_payload(self, obj):
        return format_task_notification(obj)

    def begin_processing(self):
        super(TaskProxy, self).begin_processing()
        self.send_notification('task.processing', self.repo)

    def succeed(self, result):
        super(TaskProxy, self).succeed(result)
        self.send_notification('task.success', self.repo)

    def fail(self, message):
        super(TaskProxy, self).fail(message)
        self.send_notification('task.failure', self.repo)

    def run(self, executor):
        super(TaskProxy, self).run(executor)
        self.send_notification('task.run', self.repo)


class TaskFactoryProxy(NotificationFactoryProxy, domain_proxy.TaskFactory):
    def get_super_class(self):
        return domain_proxy.TaskFactory

    def get_proxy_class(self):
        return TaskProxy


class TaskRepoProxy(NotificationRepoProxy, domain_proxy.TaskRepo):
    def get_super_class(self):
        return domain_proxy.TaskRepo

    def get_proxy_class(self):
        return TaskProxy

    def get_payload(self, obj):
        return format_task_notification(obj)

    def add(self, task):
        result = super(TaskRepoProxy, self).add(task)
        self.send_notification('task.create', task)
        return result

    def remove(self, task):
        result = super(TaskRepoProxy, self).remove(task)
        self.send_notification('task.delete', task, extra_payload={
            'deleted': True, 'deleted_at': timeutils.isotime()
        })
        return result


class TaskStubProxy(NotificationProxy, domain_proxy.TaskStub):
    def get_super_class(self):
        return domain_proxy.TaskStub


class TaskStubRepoProxy(NotificationRepoProxy, domain_proxy.TaskStubRepo):
    def get_super_class(self):
        return domain_proxy.TaskStubRepo

    def get_proxy_class(self):
        return TaskStubProxy


class MetadefNamespaceProxy(NotificationProxy, domain_proxy.MetadefNamespace):
    def get_super_class(self):
        return domain_proxy.MetadefNamespace


class MetadefNamespaceFactoryProxy(NotificationFactoryProxy,
                                   domain_proxy.MetadefNamespaceFactory):
    def get_super_class(self):
        return domain_proxy.MetadefNamespaceFactory

    def get_proxy_class(self):
        return MetadefNamespaceProxy


class MetadefNamespaceRepoProxy(NotificationRepoProxy,
                                domain_proxy.MetadefNamespaceRepo):
    def get_super_class(self):
        return domain_proxy.MetadefNamespaceRepo

    def get_proxy_class(self):
        return MetadefNamespaceProxy

    def get_payload(self, obj):
        return format_metadef_namespace_notification(obj)

    def save(self, metadef_namespace):
        name = getattr(metadef_namespace, '_old_namespace',
                       metadef_namespace.namespace)
        result = super(MetadefNamespaceRepoProxy, self).save(metadef_namespace)
        self.send_notification(
            'metadef_namespace.update', metadef_namespace,
            extra_payload={
                'namespace_old': name,
            })
        return result

    def add(self, metadef_namespace):
        result = super(MetadefNamespaceRepoProxy, self).add(metadef_namespace)
        self.send_notification('metadef_namespace.create', metadef_namespace)
        return result

    def remove(self, metadef_namespace):
        result = super(MetadefNamespaceRepoProxy, self).remove(
            metadef_namespace)
        self.send_notification(
            'metadef_namespace.delete', metadef_namespace,
            extra_payload={'deleted': True, 'deleted_at': timeutils.isotime()}
        )
        return result

    def remove_objects(self, metadef_namespace):
        result = super(MetadefNamespaceRepoProxy, self).remove_objects(
            metadef_namespace)
        self.send_notification('metadef_namespace.delete_objects',
                               metadef_namespace)
        return result

    def remove_properties(self, metadef_namespace):
        result = super(MetadefNamespaceRepoProxy, self).remove_properties(
            metadef_namespace)
        self.send_notification('metadef_namespace.delete_properties',
                               metadef_namespace)
        return result

    def remove_tags(self, metadef_namespace):
        result = super(MetadefNamespaceRepoProxy, self).remove_tags(
            metadef_namespace)
        self.send_notification('metadef_namespace.delete_tags',
                               metadef_namespace)
        return result


class MetadefObjectProxy(NotificationProxy, domain_proxy.MetadefObject):
    def get_super_class(self):
        return domain_proxy.MetadefObject


class MetadefObjectFactoryProxy(NotificationFactoryProxy,
                                domain_proxy.MetadefObjectFactory):
    def get_super_class(self):
        return domain_proxy.MetadefObjectFactory

    def get_proxy_class(self):
        return MetadefObjectProxy


class MetadefObjectRepoProxy(NotificationRepoProxy,
                             domain_proxy.MetadefObjectRepo):
    def get_super_class(self):
        return domain_proxy.MetadefObjectRepo

    def get_proxy_class(self):
        return MetadefObjectProxy

    def get_payload(self, obj):
        return format_metadef_object_notification(obj)

    def save(self, metadef_object):
        name = getattr(metadef_object, '_old_name', metadef_object.name)
        result = super(MetadefObjectRepoProxy, self).save(metadef_object)
        self.send_notification(
            'metadef_object.update', metadef_object,
            extra_payload={
                'namespace': metadef_object.namespace.namespace,
                'name_old': name,
            })
        return result

    def add(self, metadef_object):
        result = super(MetadefObjectRepoProxy, self).add(metadef_object)
        self.send_notification('metadef_object.create', metadef_object)
        return result

    def remove(self, metadef_object):
        result = super(MetadefObjectRepoProxy, self).remove(metadef_object)
        self.send_notification(
            'metadef_object.delete', metadef_object,
            extra_payload={
                'deleted': True,
                'deleted_at': timeutils.isotime(),
                'namespace': metadef_object.namespace.namespace
            }
        )
        return result


class MetadefPropertyProxy(NotificationProxy, domain_proxy.MetadefProperty):
    def get_super_class(self):
        return domain_proxy.MetadefProperty


class MetadefPropertyFactoryProxy(NotificationFactoryProxy,
                                  domain_proxy.MetadefPropertyFactory):
    def get_super_class(self):
        return domain_proxy.MetadefPropertyFactory

    def get_proxy_class(self):
        return MetadefPropertyProxy


class MetadefPropertyRepoProxy(NotificationRepoProxy,
                               domain_proxy.MetadefPropertyRepo):
    def get_super_class(self):
        return domain_proxy.MetadefPropertyRepo

    def get_proxy_class(self):
        return MetadefPropertyProxy

    def get_payload(self, obj):
        return format_metadef_property_notification(obj)

    def save(self, metadef_property):
        name = getattr(metadef_property, '_old_name', metadef_property.name)
        result = super(MetadefPropertyRepoProxy, self).save(metadef_property)
        self.send_notification(
            'metadef_property.update', metadef_property,
            extra_payload={
                'namespace': metadef_property.namespace.namespace,
                'name_old': name,
            })
        return result

    def add(self, metadef_property):
        result = super(MetadefPropertyRepoProxy, self).add(metadef_property)
        self.send_notification('metadef_property.create', metadef_property)
        return result

    def remove(self, metadef_property):
        result = super(MetadefPropertyRepoProxy, self).remove(metadef_property)
        self.send_notification(
            'metadef_property.delete', metadef_property,
            extra_payload={
                'deleted': True,
                'deleted_at': timeutils.isotime(),
                'namespace': metadef_property.namespace.namespace
            }
        )
        return result


class MetadefResourceTypeProxy(NotificationProxy,
                               domain_proxy.MetadefResourceType):
    def get_super_class(self):
        return domain_proxy.MetadefResourceType


class MetadefResourceTypeFactoryProxy(NotificationFactoryProxy,
                                      domain_proxy.MetadefResourceTypeFactory):
    def get_super_class(self):
        return domain_proxy.MetadefResourceTypeFactory

    def get_proxy_class(self):
        return MetadefResourceTypeProxy


class MetadefResourceTypeRepoProxy(NotificationRepoProxy,
                                   domain_proxy.MetadefResourceTypeRepo):
    def get_super_class(self):
        return domain_proxy.MetadefResourceTypeRepo

    def get_proxy_class(self):
        return MetadefResourceTypeProxy

    def get_payload(self, obj):
        return format_metadef_resource_type_notification(obj)

    def add(self, md_resource_type):
        result = super(MetadefResourceTypeRepoProxy, self).add(
            md_resource_type)
        self.send_notification('metadef_resource_type.create',
                               md_resource_type)
        return result

    def remove(self, md_resource_type):
        result = super(MetadefResourceTypeRepoProxy, self).remove(
            md_resource_type)
        self.send_notification(
            'metadef_resource_type.delete', md_resource_type,
            extra_payload={
                'deleted': True,
                'deleted_at': timeutils.isotime(),
                'namespace': md_resource_type.namespace.namespace
            }
        )
        return result


class MetadefTagProxy(NotificationProxy, domain_proxy.MetadefTag):
    def get_super_class(self):
        return domain_proxy.MetadefTag


class MetadefTagFactoryProxy(NotificationFactoryProxy,
                             domain_proxy.MetadefTagFactory):
    def get_super_class(self):
        return domain_proxy.MetadefTagFactory

    def get_proxy_class(self):
        return MetadefTagProxy


class MetadefTagRepoProxy(NotificationRepoProxy, domain_proxy.MetadefTagRepo):
    def get_super_class(self):
        return domain_proxy.MetadefTagRepo

    def get_proxy_class(self):
        return MetadefTagProxy

    def get_payload(self, obj):
        return format_metadef_tag_notification(obj)

    def save(self, metadef_tag):
        name = getattr(metadef_tag, '_old_name', metadef_tag.name)
        result = super(MetadefTagRepoProxy, self).save(metadef_tag)
        self.send_notification(
            'metadef_tag.update', metadef_tag,
            extra_payload={
                'namespace': metadef_tag.namespace.namespace,
                'name_old': name,
            })
        return result

    def add(self, metadef_tag):
        result = super(MetadefTagRepoProxy, self).add(metadef_tag)
        self.send_notification('metadef_tag.create', metadef_tag)
        return result

    def add_tags(self, metadef_tags):
        result = super(MetadefTagRepoProxy, self).add_tags(metadef_tags)
        for metadef_tag in metadef_tags:
            self.send_notification('metadef_tag.create', metadef_tag)

        return result

    def remove(self, metadef_tag):
        result = super(MetadefTagRepoProxy, self).remove(metadef_tag)
        self.send_notification(
            'metadef_tag.delete', metadef_tag,
            extra_payload={
                'deleted': True,
                'deleted_at': timeutils.isotime(),
                'namespace': metadef_tag.namespace.namespace
            }
        )
        return result
