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

import kombu.entity
import mox
try:
    import qpid
    import qpid.messaging
except ImportError:
    qpid = None
import stubout

from glance.common import exception
from glance import notifier
import glance.notifier.notify_kombu
from glance.openstack.common import importutils
import glance.openstack.common.log as logging
from glance.tests import utils


class TestNotifier(utils.BaseTestCase):

    def test_invalid_strategy(self):
        self.config(notifier_strategy="invalid_notifier")
        self.assertRaises(exception.InvalidNotifierStrategy,
                          notifier.Notifier)

    def test_custom_strategy(self):
        st = "glance.notifier.notify_noop.NoopStrategy"
        self.config(notifier_strategy=st)
        #NOTE(bcwaldon): the fact that Notifier is instantiated means we're ok
        notifier.Notifier()


class TestLoggingNotifier(utils.BaseTestCase):
    """Test the logging notifier is selected and works properly."""

    def setUp(self):
        super(TestLoggingNotifier, self).setUp()
        self.config(notifier_strategy="logging")
        self.called = False
        self.logger = logging.getLogger("glance.notifier.notify_log")
        self.notifier = notifier.Notifier()

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


class TestNoopNotifier(utils.BaseTestCase):
    """Test that the noop notifier works...and does nothing?"""

    def setUp(self):
        super(TestNoopNotifier, self).setUp()
        self.config(notifier_strategy="noop")
        self.notifier = notifier.Notifier()

    def test_warn(self):
        self.notifier.warn("test_event", "test_message")

    def test_info(self):
        self.notifier.info("test_event", "test_message")

    def test_error(self):
        self.notifier.error("test_event", "test_message")


class TestRabbitNotifier(utils.BaseTestCase):
    """Test AMQP/Rabbit notifier works."""

    def setUp(self):
        super(TestRabbitNotifier, self).setUp()

        def _fake_connect(rabbit_self):
            rabbit_self.connection_errors = ()
            rabbit_self.connection = 'fake_connection'
            return None

        self.notify_kombu = importutils.import_module("glance.notifier."
                                                      "notify_kombu")
        self.notify_kombu.RabbitStrategy._send_message = self._send_message
        self.notify_kombu.RabbitStrategy._connect = _fake_connect
        self.called = False
        self.config(notifier_strategy="rabbit",
                    rabbit_retry_backoff=0,
                    rabbit_notification_topic="fake_topic")
        self.notifier = notifier.Notifier()

    def _send_message(self, message, routing_key):
        self.called = {
            "message": message,
            "routing_key": routing_key,
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
        self.assertRaises(MyException, notifier.Notifier)

    def test_timeout_on_connect_reconnects(self):
        info = {'num_called': 0}

        def _connect(rabbit_self):
            rabbit_self.connection_errors = ()
            info['num_called'] += 1
            if info['num_called'] == 1:
                raise Exception('foo timeout foo')
            rabbit_self.connection = 'fake_connection'

        self.notify_kombu.RabbitStrategy._connect = _connect
        notifier_ = notifier.Notifier()
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
        notifier_ = notifier.Notifier()
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
        notifier_ = notifier.Notifier()
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
        notifier_ = notifier.Notifier()
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
        notifier_ = notifier.Notifier()
        notifier_.error('test_event', 'test_message')

        if self.called is False:
            self.fail("Did not call _send_message properly.")

        self.assertEquals("test_message", self.called["message"]["payload"])
        self.assertEquals("ERROR", self.called["message"]["priority"])
        self.assertEquals(info['send_called'], 2)
        self.assertEquals(info['conn_called'], 2)


class TestQpidNotifier(utils.BaseTestCase):
    """Test Qpid notifier."""

    def setUp(self):
        super(TestQpidNotifier, self).setUp()

        if not qpid:
            return

        self.mocker = mox.Mox()

        self.mock_connection = None
        self.mock_session = None
        self.mock_sender = None
        self.mock_receiver = None

        self.orig_connection = qpid.messaging.Connection
        self.orig_session = qpid.messaging.Session
        self.orig_sender = qpid.messaging.Sender
        self.orig_receiver = qpid.messaging.Receiver
        qpid.messaging.Connection = lambda *_x, **_y: self.mock_connection
        qpid.messaging.Session = lambda *_x, **_y: self.mock_session
        qpid.messaging.Sender = lambda *_x, **_y: self.mock_sender
        qpid.messaging.Receiver = lambda *_x, **_y: self.mock_receiver

        self.notify_qpid = importutils.import_module("glance.notifier."
                                                     "notify_qpid")

    def tearDown(self):
        super(TestQpidNotifier, self).tearDown()

        if not qpid:
            return

        qpid.messaging.Connection = self.orig_connection
        qpid.messaging.Session = self.orig_session
        qpid.messaging.Sender = self.orig_sender
        qpid.messaging.Receiver = self.orig_receiver

        self.mocker.ResetAll()

    def _test_notify(self, priority):
        test_msg = {'a': 'b'}

        self.mock_connection = self.mocker.CreateMock(self.orig_connection)
        self.mock_session = self.mocker.CreateMock(self.orig_session)
        self.mock_sender = self.mocker.CreateMock(self.orig_sender)

        self.mock_connection.username = ""
        self.mock_connection.open()
        self.mock_connection.session().AndReturn(self.mock_session)
        for p in ["info", "warn", "error"]:
            expected_address = ('glance/glance_notifications.%s ; {"node": '
                '{"x-declare": {"auto-delete": true, "durable": false}, '
                '"type": "topic"}, "create": "always"}' % p)
            self.mock_session.sender(expected_address).AndReturn(
                    self.mock_sender)
        self.mock_sender.send(mox.IgnoreArg())

        self.mocker.ReplayAll()

        self.config(notifier_strategy="qpid")
        notifier = self.notify_qpid.QpidStrategy()
        if priority == 'info':
            notifier.info(test_msg)
        elif priority == 'warn':
            notifier.warn(test_msg)
        elif priority == 'error':
            notifier.error(test_msg)

        self.mocker.VerifyAll()

    @utils.skip_if(qpid is None, "qpid not installed")
    def test_info(self):
        self._test_notify('info')

    @utils.skip_if(qpid is None, "qpid not installed")
    def test_warn(self):
        self._test_notify('warn')

    @utils.skip_if(qpid is None, "qpid not installed")
    def test_error(self):
        self._test_notify('error')


class TestRabbitContentType(utils.BaseTestCase):
    """Test AMQP/Rabbit notifier works."""

    def setUp(self):
        super(TestRabbitContentType, self).setUp()
        self.stubs = stubout.StubOutForTesting()

        def _fake_connect(rabbit_self):
            rabbit_self.connection_errors = ()
            rabbit_self.connection = 'fake_connection'
            rabbit_self.exchange = self._fake_exchange()
            return None

        def dummy(*args, **kwargs):
            pass

        self.stubs.Set(kombu.entity.Exchange, 'publish', dummy)
        self.stubs.Set(glance.notifier.notify_kombu.RabbitStrategy, '_connect',
                       _fake_connect)
        self.called = False
        self.config(notifier_strategy="rabbit",
                    rabbit_retry_backoff=0,
                    rabbit_notification_topic="fake_topic")
        self.notifier = notifier.Notifier()

    def _fake_exchange(self):
        class Dummy(object):
            class Message(object):
                def __init__(message_self, message, content_type):
                    self.called = {
                        'message': message,
                        'content_type': content_type
                    }

            @classmethod
            def publish(*args, **kwargs):
                pass
        return Dummy

    def test_content_type_passed(self):
        self.notifier.warn("test_event", "test_message")
        self.assertEquals(self.called['content_type'], 'application/json')
