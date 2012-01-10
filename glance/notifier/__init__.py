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


import datetime
import uuid
import socket

from glance.common import cfg
from glance.common import exception
from glance.common import utils


_STRATEGIES = {
    "logging": "glance.notifier.notify_log.LoggingStrategy",
    "rabbit": "glance.notifier.notify_kombu.RabbitStrategy",
    "noop": "glance.notifier.notify_noop.NoopStrategy",
    "default": "glance.notifier.notify_noop.NoopStrategy",
}


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    opts = [
        cfg.StrOpt('notifier_strategy', default='default')
    ]

    def __init__(self, conf, strategy=None):
        conf.register_opts(self.opts)
        strategy = conf.notifier_strategy
        try:
            self.strategy = utils.import_class(_STRATEGIES[strategy])(conf)
        except KeyError, ImportError:
            raise exception.InvalidNotifierStrategy(strategy=strategy)

    @staticmethod
    def generate_message(event_type, priority, payload):
        return {
            "message_id": str(uuid.uuid4()),
            "publisher_id": socket.gethostname(),
            "event_type": event_type,
            "priority": priority,
            "payload": payload,
            "timestamp": str(datetime.datetime.utcnow()),
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
