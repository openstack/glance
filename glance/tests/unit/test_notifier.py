# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

import logging
import unittest

from glance.common import exception
from glance.common import utils as common_utils
from glance import notifier
from glance.tests import utils


class TestInvalidNotifier(unittest.TestCase):
    """Test that notifications are generated appropriately"""

    def test_cannot_create(self):
        conf = utils.TestConfigOpts({"notifier_strategy": "invalid_notifier"})
        self.assertRaises(exception.InvalidNotifierStrategy,
                          notifier.Notifier,
                          conf)


class TestLoggingNotifier(unittest.TestCase):
    """Test the logging notifier is selected and works properly."""

    def setUp(self):
        conf = utils.TestConfigOpts({"notifier_strategy": "logging"})
        self.called = False
        self.logger = logging.getLogger("glance.notifier.logging_notifier")
        self.notifier = notifier.Notifier(conf)

    def _called(self, msg):
        self.called = msg

    def test_warn(self):
        self.logger.warn = self._called
        self.notifier.warn("test_event", "test_message")
        if self.called is False:
            self.fail("Did not call logging library correctly.")

    def test_info(self):
        self.logger.info = self._called
        self.notifier.info("test_event", "test_message")
        if self.called is False:
            self.fail("Did not call logging library correctly.")

    def test_erorr(self):
        self.logger.error = self._called
        self.notifier.error("test_event", "test_message")
        if self.called is False:
            self.fail("Did not call logging library correctly.")


class TestNoopNotifier(unittest.TestCase):
    """Test that the noop notifier works...and does nothing?"""

    def setUp(self):
        conf = utils.TestConfigOpts({"notifier_strategy": "noop"})
        self.notifier = notifier.Notifier(conf)

    def test_warn(self):
        self.notifier.warn("test_event", "test_message")

    def test_info(self):
        self.notifier.info("test_event", "test_message")

    def test_error(self):
        self.notifier.error("test_event", "test_message")


class TestRabbitNotifier(unittest.TestCase):
    """Test AMQP/Rabbit notifier works."""

    def setUp(self):
        def _fake_connect(rabbit_self):
            rabbit_self.connection_errors = ()
            rabbit_self.connection = 'fake_connection'
            return None

        self.notify_kombu = common_utils.import_object(
                                        "glance.notifier.notify_kombu")
        self.notify_kombu.RabbitStrategy._send_message = self._send_message
        self.notify_kombu.RabbitStrategy._connect = _fake_connect
        self.called = False
        self.conf = utils.TestConfigOpts({"notifier_strategy": "rabbit",
                                          "rabbit_retry_backoff": 0,
                                          "rabbit_notification_topic":
                                                "fake_topic"})
        self.notifier = notifier.Notifier(self.conf)

    def _send_message(self, message, routing_key):
        self.called = {
            "message": message,
            "routing_key": routing_key
        }

    def test_warn(self):
        self.notifier.warn("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("WARN", self.called["message"]["priority"])
        self.assertEquals("fake_topic.warn", self.called["routing_key"])

    def test_info(self):
        self.notifier.info("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("INFO", self.called["message"]["priority"])
        self.assertEquals("fake_topic.info", self.called["routing_key"])

    def test_error(self):
        self.notifier.error("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals("fake_topic.error", self.called["routing_key"])

    def test_unknown_error_on_connect_raises(self):
        class MyException(Exception):
            pass

        def _connect(self):
            self.connection_errors = ()
            raise MyException('meow')

        self.notify_kombu.RabbitStrategy._connect = _connect
        self.assertRaises(MyException, notifier.Notifier, self.conf)

    def test_timeout_on_connect_reconnects(self):
        info = {'num_called': 0}

        def _connect(rabbit_self):
            rabbit_self.connection_errors = ()
            info['num_called'] += 1
            if info['num_called'] == 1:
                raise Exception('foo timeout foo')
            rabbit_self.connection = 'fake_connection'

        self.notify_kombu.RabbitStrategy._connect = _connect
        notifier_ = notifier.Notifier(self.conf)
        notifier_.error('test_event', 'test_message')

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals(info['num_called'], 2)

    def test_connection_error_on_connect_reconnects(self):
        info = {'num_called': 0}

        class MyException(Exception):
            pass

        def _connect(rabbit_self):
            rabbit_self.connection_errors = (MyException, )
            info['num_called'] += 1
            if info['num_called'] == 1:
                raise MyException('meow')
            rabbit_self.connection = 'fake_connection'

        self.notify_kombu.RabbitStrategy._connect = _connect
        notifier_ = notifier.Notifier(self.conf)
        notifier_.error('test_event', 'test_message')

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals(info['num_called'], 2)

    def test_unknown_error_on_send_message_raises(self):
        class MyException(Exception):
            pass

        def _send_message(rabbit_self, msg, routing_key):
            raise MyException('meow')

        self.notify_kombu.RabbitStrategy._send_message = _send_message
        notifier_ = notifier.Notifier(self.conf)
        self.assertRaises(MyException, notifier_.error, 'a', 'b')

    def test_timeout_on_send_message_reconnects(self):
        info = {'send_called': 0, 'conn_called': 0}

        def _connect(rabbit_self):
            info['conn_called'] += 1
            rabbit_self.connection_errors = ()
            rabbit_self.connection = 'fake_connection'

        def _send_message(rabbit_self, msg, routing_key):
            info['send_called'] += 1
            if info['send_called'] == 1:
                raise Exception('foo timeout foo')
            self._send_message(msg, routing_key)

        self.notify_kombu.RabbitStrategy._connect = _connect
        self.notify_kombu.RabbitStrategy._send_message = _send_message
        notifier_ = notifier.Notifier(self.conf)
        notifier_.error('test_event', 'test_message')

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals(info['send_called'], 2)
        self.assertEquals(info['conn_called'], 2)

    def test_connection_error_on_send_message_reconnects(self):
        info = {'send_called': 0, 'conn_called': 0}

        class MyException(Exception):
            pass

        def _connect(rabbit_self):
            info['conn_called'] += 1
            rabbit_self.connection_errors = (MyException, )
            rabbit_self.connection = 'fake_connection'

        def _send_message(rabbit_self, msg, routing_key):
            info['send_called'] += 1
            if info['send_called'] == 1:
                raise MyException('meow')
            self._send_message(msg, routing_key)

        self.notify_kombu.RabbitStrategy._connect = _connect
        self.notify_kombu.RabbitStrategy._send_message = _send_message
        notifier_ = notifier.Notifier(self.conf)
        notifier_.error('test_event', 'test_message')

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals(info['send_called'], 2)
        self.assertEquals(info['conn_called'], 2)
