# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import datetime
import logging
import socket
import uuid

import kombu.connection

from glance.common import config
from glance.common import exception


class NoopStrategy(object):
    """A notifier that does nothing when called."""

    def __init__(self, options):
        pass

    def warn(self, msg):
        pass

    def info(self, msg):
        pass

    def error(self, msg):
        pass


class LoggingStrategy(object):
    """A notifier that calls logging when called."""

    def __init__(self, options):
        self.logger = logging.getLogger('glance.notifier.logging_notifier')

    def warn(self, msg):
        self.logger.warn(msg)

    def info(self, msg):
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)


class RabbitStrategy(object):
    """A notifier that puts a message on a queue when called."""

    def __init__(self, options):
        """Initialize the rabbit notification strategy."""
        self._options = options
        host = self._get_option('rabbit_host', 'str', 'localhost')
        port = self._get_option('rabbit_port', 'int', 5672)
        use_ssl = self._get_option('rabbit_use_ssl', 'bool', False)
        userid = self._get_option('rabbit_userid', 'str', 'guest')
        password = self._get_option('rabbit_password', 'str', 'guest')
        virtual_host = self._get_option('rabbit_virtual_host', 'str', '/')

        self.connection = kombu.connection.BrokerConnection(
            hostname=host,
            userid=userid,
            password=password,
            virtual_host=virtual_host,
            ssl=use_ssl)

        self.topic = self._get_option('rabbit_notification_topic',
                                      'str',
                                      'glance_notifications')

    def _get_option(self, name, datatype, default):
        """Retrieve a configuration option."""
        return config.get_option(self._options,
                                 name,
                                 type=datatype,
                                 default=default)

    def _send_message(self, message, priority):
        topic = "%s.%s" % (self.topic, priority)
        queue = self.connection.SimpleQueue(topic)
        queue.put(message, serializer="json")
        queue.close()

    def warn(self, msg):
        self._send_message(msg, "WARN")

    def info(self, msg):
        self._send_message(msg, "INFO")

    def error(self, msg):
        self._send_message(msg, "ERROR")


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    STRATEGIES = {
        "logging": LoggingStrategy,
        "rabbit": RabbitStrategy,
        "noop": NoopStrategy,
        "default": NoopStrategy,
    }

    def __init__(self, options, strategy=None):
        strategy = config.get_option(options, "notifier_strategy",
                                     type="str", default="default")
        try:
            self.strategy = self.STRATEGIES[strategy](options)
        except KeyError:
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
