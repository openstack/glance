# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011, OpenStack LLC.
# Copyright 2012, Red Hat, Inc.
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


import socket
import uuid

from glance.common import exception
import glance.domain
from glance.openstack.common import cfg
from glance.openstack.common import importutils
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils

notifier_opts = [
    cfg.StrOpt('notifier_strategy', default='default')
]

CONF = cfg.CONF
CONF.register_opts(notifier_opts)

LOG = logging.getLogger(__name__)

_STRATEGY_ALIASES = {
    "logging": "glance.notifier.notify_log.LoggingStrategy",
    "rabbit": "glance.notifier.notify_kombu.RabbitStrategy",
    "qpid": "glance.notifier.notify_qpid.QpidStrategy",
    "noop": "glance.notifier.notify_noop.NoopStrategy",
    "default": "glance.notifier.notify_noop.NoopStrategy",
}


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    def __init__(self, strategy=None):
        _strategy = CONF.notifier_strategy
        try:
            strategy = _STRATEGY_ALIASES[_strategy]
            msg = _('Converted strategy alias %s to %s')
            LOG.debug(msg % (_strategy, strategy))
        except KeyError:
            strategy = _strategy
            LOG.debug(_('No strategy alias found for %s') % strategy)

        try:
            strategy_class = importutils.import_class(strategy)
        except ImportError:
            raise exception.InvalidNotifierStrategy(strategy=strategy)
        else:
            self.strategy = strategy_class()

    @staticmethod
    def generate_message(event_type, priority, payload):
        return {
            "message_id": str(uuid.uuid4()),
            "publisher_id": socket.gethostname(),
            "event_type": event_type,
            "priority": priority,
            "payload": payload,
            "timestamp": str(timeutils.utcnow()),
        }

    def warn(self, event_type, payload):
        msg = self.generate_message(event_type, "WARN", payload)
        self.strategy.warn(msg)

    def info(self, event_type, payload):
        msg = self.generate_message(event_type, "INFO", payload)
        self.strategy.info(msg)

    def error(self, event_type, payload):
        msg = self.generate_message(event_type, "ERROR", payload)
        self.strategy.error(msg)


def format_image_notification(image):
    """
    Given a glance.domain.Image object, return a dictionary of relevant
    notification information.
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
        'location': image.location,
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


class ImageRepoProxy(glance.domain.ImageRepoProxy):

    def __init__(self, image_repo, notifier):
        self.image_repo = image_repo
        self.notifier = notifier
        super(ImageRepoProxy, self).__init__(image_repo)

    def save(self, image):
        self.image_repo.save(image)
        self.notifier.info('image.update', format_image_notification(image))

    def add(self, image):
        self.image_repo.add(image)
        self.notifier.info('image.create', format_image_notification(image))

    def remove(self, image):
        self.image_repo.remove(image)
        payload = format_image_notification(image)
        payload['deleted'] = True
        payload['deleted_at'] = timeutils.isotime()
        self.notifier.info('image.delete', payload)
