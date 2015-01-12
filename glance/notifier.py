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

import glance_store
from oslo.config import cfg
from oslo import messaging
from oslo_utils import excutils
from oslo_utils import timeutils
import webob

from glance.common import exception
from glance.common import utils
import glance.domain.proxy
from glance import i18n
import glance.openstack.common.log as logging

_ = i18n._

notifier_opts = [
    cfg.StrOpt('default_publisher_id', default="image.localhost",
               help='Default publisher_id for outgoing notifications.'),
]

CONF = cfg.CONF
CONF.register_opts(notifier_opts)

LOG = logging.getLogger(__name__)

_ALIASES = {
    'glance.openstack.common.rpc.impl_kombu': 'rabbit',
    'glance.openstack.common.rpc.impl_qpid': 'qpid',
    'glance.openstack.common.rpc.impl_zmq': 'zmq',
}


def get_transport():
    return messaging.get_transport(CONF, aliases=_ALIASES)


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    def __init__(self):
        publisher_id = CONF.default_publisher_id
        self._transport = get_transport()
        self._notifier = messaging.Notifier(self._transport,
                                            publisher_id=publisher_id)

    def warn(self, event_type, payload):
        self._notifier.warn({}, event_type, payload)

    def info(self, event_type, payload):
        self._notifier.info({}, event_type, payload)

    def error(self, event_type, payload):
        self._notifier.error({}, event_type, payload)


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
        'is_public': image.visibility == 'public',
        'properties': dict(image.extra_properties),
        'tags': list(image.tags),
        'deleted': False,
        'deleted_at': None,
    }


def format_task_notification(task):
    # NOTE(nikhil): input is not passed to the notifier payload as it may
    # contain sensitive info.
    return {'id': task.task_id,
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


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, notifier):
        self.image_repo = image_repo
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

    def save(self, image):
        super(ImageRepoProxy, self).save(image)
        self.notifier.info('image.update',
                           format_image_notification(image))

    def add(self, image):
        super(ImageRepoProxy, self).add(image)
        self.notifier.info('image.create',
                           format_image_notification(image))

    def remove(self, image):
        super(ImageRepoProxy, self).remove(image)
        payload = format_image_notification(image)
        payload['deleted'] = True
        payload['deleted_at'] = timeutils.isotime()
        self.notifier.info('image.delete', payload)


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):
    def __init__(self, factory, context, notifier):
        kwargs = {'context': context, 'notifier': notifier}
        super(ImageFactoryProxy, self).__init__(factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=kwargs)


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, notifier):
        self.image = image
        self.context = context
        self.notifier = notifier
        super(ImageProxy, self).__init__(image)

    def _format_image_send(self, bytes_sent):
        return {
            'bytes_sent': bytes_sent,
            'image_id': self.image.image_id,
            'owner_id': self.image.owner,
            'receiver_tenant_id': self.context.tenant,
            'receiver_user_id': self.context.user,
        }

    def _get_chunk_data_iterator(self, data, chunk_size=None):
        sent = 0
        for chunk in data:
            yield chunk
            sent += len(chunk)

        if sent != (chunk_size or self.image.size):
            notify = self.notifier.error
        else:
            notify = self.notifier.info

        try:
            notify('image.send',
                   self._format_image_send(sent))
        except Exception as err:
            msg = (_("An error occurred during image.send"
                     " notification: %(err)s") % {'err': err})
            LOG.error(msg)

    def get_data(self, offset=0, chunk_size=None):
        # Due to the need of evaluating subsequent proxies, this one
        # should return a generator, the call should be done before
        # generator creation
        data = self.image.get_data(offset=offset, chunk_size=chunk_size)
        return self._get_chunk_data_iterator(data, chunk_size=chunk_size)

    def set_data(self, data, size=None):
        payload = format_image_notification(self.image)
        self.notifier.info('image.prepare', payload)
        try:
            self.image.set_data(data, size)
        except glance_store.StorageFull as e:
            msg = (_("Image storage media is full: %s") %
                   utils.exception_to_str(e))
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg)
        except glance_store.StorageWriteDenied as e:
            msg = (_("Insufficient permissions on image storage media: %s")
                   % utils.exception_to_str(e))
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPServiceUnavailable(explanation=msg)
        except ValueError as e:
            msg = (_("Cannot save data for image %(image_id)s: %(error)s") %
                   {'image_id': self.image.image_id,
                    'error': utils.exception_to_str(e)})
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPBadRequest(
                explanation=utils.exception_to_str(e))
        except exception.Duplicate as e:
            msg = (_("Unable to upload duplicate image data for image"
                     "%(image_id)s: %(error)s") %
                   {'image_id': self.image.image_id,
                    'error': utils.exception_to_str(e)})
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPConflict(explanation=msg)
        except exception.Forbidden as e:
            msg = (_("Not allowed to upload image data for image %(image_id)s:"
                     " %(error)s") % {'image_id': self.image.image_id,
                                      'error': utils.exception_to_str(e)})
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPForbidden(explanation=msg)
        except exception.NotFound as e:
            msg = (_("Image %(image_id)s could not be found after upload."
                     " The image may have been deleted during the upload:"
                     " %(error)s") % {'image_id': self.image.image_id,
                                      'error': utils.exception_to_str(e)})
            self.notifier.error('image.upload', msg)
            raise webob.exc.HTTPNotFound(explanation=utils.exception_to_str(e))
        except webob.exc.HTTPError as e:
            with excutils.save_and_reraise_exception():
                msg = (_("Failed to upload image data for image %(image_id)s"
                         " due to HTTP error: %(error)s") %
                       {'image_id': self.image.image_id,
                        'error': utils.exception_to_str(e)})
                self.notifier.error('image.upload', msg)
        except Exception as e:
            with excutils.save_and_reraise_exception():
                msg = (_("Failed to upload image data for image %(image_id)s "
                         "due to internal error: %(error)s") %
                       {'image_id': self.image.image_id,
                        'error': utils.exception_to_str(e)})
                self.notifier.error('image.upload', msg)
        else:
            payload = format_image_notification(self.image)
            self.notifier.info('image.upload', payload)
            self.notifier.info('image.activate', payload)


class TaskRepoProxy(glance.domain.proxy.TaskRepo):

    def __init__(self, task_repo, context, notifier):
        self.task_repo = task_repo
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}
        super(TaskRepoProxy, self).__init__(task_repo,
                                            task_proxy_class=TaskProxy,
                                            task_proxy_kwargs=proxy_kwargs)

    def add(self, task):
        self.notifier.info('task.create',
                           format_task_notification(task))
        super(TaskRepoProxy, self).add(task)

    def remove(self, task):
        payload = format_task_notification(task)
        payload['deleted'] = True
        payload['deleted_at'] = timeutils.isotime()
        self.notifier.info('task.delete', payload)
        super(TaskRepoProxy, self).remove(task)


class TaskStubRepoProxy(glance.domain.proxy.TaskStubRepo):

    def __init__(self, task_stub_repo, context, notifier):
        self.task_stub_repo = task_stub_repo
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}
        super(TaskStubRepoProxy, self).__init__(
            task_stub_repo,
            task_stub_proxy_class=TaskStubProxy,
            task_stub_proxy_kwargs=proxy_kwargs)


class TaskFactoryProxy(glance.domain.proxy.TaskFactory):
    def __init__(self, task_factory, context, notifier):
        kwargs = {'context': context, 'notifier': notifier}
        super(TaskFactoryProxy, self).__init__(
            task_factory,
            task_proxy_class=TaskProxy,
            task_proxy_kwargs=kwargs)


class TaskProxy(glance.domain.proxy.Task):

    def __init__(self, task, context, notifier):
        self.task = task
        self.context = context
        self.notifier = notifier
        super(TaskProxy, self).__init__(task)

    def begin_processing(self):
        self.notifier.info(
            'task.processing',
            format_task_notification(self.task)
        )
        return super(TaskProxy, self).begin_processing()

    def succeed(self, result):
        self.notifier.info('task.success',
                           format_task_notification(self.task))
        return super(TaskProxy, self).succeed(result)

    def fail(self, message):
        self.notifier.info('task.failure',
                           format_task_notification(self.task))
        return super(TaskProxy, self).fail(message)

    def run(self, executor):
        self.notifier.info('task.run',
                           format_task_notification(self.task))
        return super(TaskProxy, self).run(executor)


class TaskStubProxy(glance.domain.proxy.TaskStub):

    def __init__(self, task, context, notifier):
        self.task = task
        self.context = context
        self.notifier = notifier
        super(TaskStubProxy, self).__init__(task)
