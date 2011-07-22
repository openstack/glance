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
from glance.common import notifier


class TestInvalidNotifier(unittest.TestCase):
    """Test that notifications are generated appropriately"""

    def test_cannot_create(self):
        options = {"notifier_strategy": "invalid_notifier"}
        self.assertRaises(exception.InvalidNotifierStrategy,
                          notifier.Notifier,
                          options)


class TestLoggingNotifier(unittest.TestCase):
    """Test the logging notifier is selected and works properly."""

    def setUp(self):
        options = {"notifier_strategy": "logging"}
        self.called = False
        self.logger = logging.getLogger("glance.notifier.logging_notifier")
        self.notifier = notifier.Notifier(options)

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
        options = {"notifier_strategy": "noop"}
        self.notifier = notifier.Notifier(options)

    def test_warn(self):
        self.notifier.warn("test_event", "test_message")

    def test_info(self):
        self.notifier.info("test_event", "test_message")

    def test_error(self):
        self.notifier.error("test_event", "test_message")


class TestRabbitNotifier(unittest.TestCase):
    """Test AMQP/Rabbit notifier works."""

    def setUp(self):
        notifier.RabbitStrategy._send_message = self._send_message
        self.called = False
        options = {"notifier_strategy": "rabbit"}
        self.notifier = notifier.Notifier(options)

    def _send_message(self, message, priority):
        self.called = {
            "message": message,
            "priority": priority,
        }

    def test_warn(self):
        self.notifier.warn("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("WARN", self.called["message"]["priority"])

    def test_info(self):
        self.notifier.info("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("INFO", self.called["message"]["priority"])

    def test_error(self):
        self.notifier.error("test_event", "test_message")

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
