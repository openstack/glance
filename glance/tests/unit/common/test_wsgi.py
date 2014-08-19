# Copyright 2010-2011 OpenStack Foundation
# Copyright 2014 IBM Corp.
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
import socket

from babel import localedata
import eventlet.patcher
import fixtures
import gettext
import mock
import webob

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance.openstack.common import gettextutils
from glance.openstack.common import jsonutils
from glance.tests import utils as test_utils


class RequestTest(test_utils.BaseTestCase):

    def _set_expected_languages(self, all_locales=[], avail_locales=None):
        # Override localedata.locale_identifiers to return some locales.
        def returns_some_locales(*args, **kwargs):
            return all_locales

        self.stubs.Set(localedata, 'locale_identifiers', returns_some_locales)

        # Override gettext.find to return other than None for some languages.
        def fake_gettext_find(lang_id, *args, **kwargs):
            found_ret = '/glance/%s/LC_MESSAGES/glance.mo' % lang_id
            if avail_locales is None:
                # All locales are available.
                return found_ret
            languages = kwargs['languages']
            if languages[0] in avail_locales:
                return found_ret
            return None

        self.stubs.Set(gettext, 'find', fake_gettext_find)

    def test_content_type_missing(self):
        request = wsgi.Request.blank('/tests/123')
        self.assertRaises(exception.InvalidContentType,
                          request.get_content_type, ('application/xml',))

    def test_content_type_unsupported(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Type"] = "text/html"
        self.assertRaises(exception.InvalidContentType,
                          request.get_content_type, ('application/xml',))

    def test_content_type_with_charset(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Type"] = "application/json; charset=UTF-8"
        result = request.get_content_type(('application/json',))
        self.assertEqual(result, "application/json")

    def test_content_type_from_accept_xml(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_accept_json(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_accept_xml_json(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml, application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_accept_json_xml_quality(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = ("application/json; q=0.3, "
                                     "application/xml; q=0.9")
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_accept_default(self):
        request = wsgi.Request.blank('/tests/123.unsupported')
        request.headers["Accept"] = "application/unsupported1"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_language_accept_default(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept-Language"] = "zz-ZZ,zz;q=0.8"
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_language_accept_none(self):
        request = wsgi.Request.blank('/tests/123')
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_best_match_language_expected(self):
        # If Accept-Language is a supported language, best_match_language()
        # returns it.
        self._set_expected_languages(all_locales=['it'])

        req = wsgi.Request.blank('/', headers={'Accept-Language': 'it'})
        self.assertEqual('it', req.best_match_language())

    def test_request_match_language_unexpected(self):
        # If Accept-Language is a language we do not support,
        # best_match_language() returns None.
        self._set_expected_languages(all_locales=['it'])

        req = wsgi.Request.blank('/', headers={'Accept-Language': 'zh'})
        self.assertIsNone(req.best_match_language())

    @mock.patch.object(webob.acceptparse.AcceptLanguage, 'best_match')
    def test_best_match_language_unknown(self, mock_best_match):
        # Test that we are actually invoking language negotiation by webop
        request = wsgi.Request.blank('/')
        accepted = 'unknown-lang'
        request.headers = {'Accept-Language': accepted}

        mock_best_match.return_value = None

        self.assertIsNone(request.best_match_language())

        # If Accept-Language is missing or empty, match should be None
        request.headers = {'Accept-Language': ''}
        self.assertIsNone(request.best_match_language())
        request.headers.pop('Accept-Language')
        self.assertIsNone(request.best_match_language())


class ResourceTest(test_utils.BaseTestCase):

    def test_get_action_args(self):
        env = {
            'wsgiorg.routing_args': [
                None,
                {
                    'controller': None,
                    'format': None,
                    'action': 'update',
                    'id': 12,
                },
            ],
        }

        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)

        self.assertEqual(actual, expected)

    def test_get_action_args_invalid_index(self):
        env = {'wsgiorg.routing_args': []}
        expected = {}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(actual, expected)

    def test_get_action_args_del_controller_error(self):
        actions = {'format': None,
                   'action': 'update',
                   'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(actual, expected)

    def test_get_action_args_del_format_error(self):
        actions = {'action': 'update', 'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(actual, expected)

    def test_dispatch(self):
        class Controller(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(actual, expected)

    def test_dispatch_default(self):
        class Controller(object):
            def default(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(actual, expected)

    def test_dispatch_no_default(self):
        class Controller(object):
            def show(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        self.assertRaises(AttributeError, resource.dispatch, Controller(),
                          'index', 'on', pants='off')

    def test_call(self):
        class FakeController(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(FakeController(), None, None)

        def dispatch(self, obj, action, *args, **kwargs):
            if isinstance(obj, wsgi.JSONRequestDeserializer):
                return []
            if isinstance(obj, wsgi.JSONResponseSerializer):
                raise webob.exc.HTTPForbidden()

        self.stubs.Set(wsgi.Resource, 'dispatch', dispatch)

        request = wsgi.Request.blank('/')

        response = resource.__call__(request)

        self.assertIsInstance(response, webob.exc.HTTPForbidden)
        self.assertEqual(response.status_code, 403)

    @mock.patch.object(wsgi, 'translate_exception')
    def test_resource_call_error_handle_localized(self,
                                                  mock_translate_exception):
        class Controller(object):
            def delete(self, req, identity):
                raise webob.exc.HTTPBadRequest(explanation='Not Found')

        actions = {'action': 'delete', 'identity': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        request = wsgi.Request.blank('/tests/123', environ=env)
        message_es = 'No Encontrado'

        resource = wsgi.Resource(Controller(),
                                 wsgi.JSONRequestDeserializer(),
                                 None)
        translated_exc = webob.exc.HTTPBadRequest(message_es)
        mock_translate_exception.return_value = translated_exc

        e = self.assertRaises(webob.exc.HTTPBadRequest,
                              resource, request)
        self.assertEqual(message_es, str(e))

    @mock.patch.object(webob.acceptparse.AcceptLanguage, 'best_match')
    @mock.patch.object(gettextutils, 'translate')
    def test_translate_exception(self, mock_translate, mock_best_match):

        mock_translate.return_value = 'No Encontrado'
        mock_best_match.return_value = 'de'

        req = wsgi.Request.blank('/tests/123')
        req.headers["Accept-Language"] = "de"

        e = webob.exc.HTTPNotFound(explanation='Not Found')
        e = wsgi.translate_exception(req, e)
        self.assertEqual('No Encontrado', e.explanation)


class JSONResponseSerializerTest(test_utils.BaseTestCase):

    def test_to_json(self):
        fixture = {"key": "value"}
        expected = '{"key": "value"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(actual, expected)

    def test_to_json_with_date_format_value(self):
        fixture = {"date": datetime.datetime(1, 3, 8, 2)}
        expected = '{"date": "0001-03-08T02:00:00"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(actual, expected)

    def test_to_json_with_more_deep_format(self):
        fixture = {"is_public": True, "name": [{"name1": "test"}]}
        expected = {"is_public": True, "name": [{"name1": "test"}]}
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        actual = jsonutils.loads(actual)
        for k in expected:
            self.assertEqual(expected[k], actual[k])

    def test_to_json_with_set(self):
        fixture = set(["foo"])
        expected = '["foo"]'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(actual, expected)

    def test_default(self):
        fixture = {"key": "value"}
        response = webob.Response()
        wsgi.JSONResponseSerializer().default(response, fixture)
        self.assertEqual(response.status_int, 200)
        content_types = filter(lambda h: h[0] == 'Content-Type',
                               response.headerlist)
        self.assertEqual(len(content_types), 1)
        self.assertEqual(response.content_type, 'application/json')
        self.assertEqual(response.body, '{"key": "value"}')


class JSONRequestDeserializerTest(test_utils.BaseTestCase):

    def test_has_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        request.headers.pop('Content-Length')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_zero_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        request.headers['Content-Length'] = 0
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_has_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        self.assertTrue('Content-Length' in request.headers)
        self.assertTrue(wsgi.JSONRequestDeserializer().has_body(request))

    def test_no_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_from_json(self):
        fixture = '{"key": "value"}'
        expected = {"key": "value"}
        actual = wsgi.JSONRequestDeserializer().from_json(fixture)
        self.assertEqual(actual, expected)

    def test_from_json_malformed(self):
        fixture = 'kjasdklfjsklajf'
        self.assertRaises(webob.exc.HTTPBadRequest,
                          wsgi.JSONRequestDeserializer().from_json, fixture)

    def test_default_no_body(self):
        request = wsgi.Request.blank('/')
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {}
        self.assertEqual(actual, expected)

    def test_default_with_body(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = '{"key": "value"}'
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {"body": {"key": "value"}}
        self.assertEqual(actual, expected)

    def test_has_body_has_transfer_encoding(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'fake_body'
        request.headers['transfer-encoding'] = 0
        self.assertTrue('transfer-encoding' in request.headers)
        self.assertTrue(wsgi.JSONRequestDeserializer().has_body(request))

    def test_get_bind_addr_default_value(self):
        expected = ('0.0.0.0', '123456')
        actual = wsgi.get_bind_addr(default_port="123456")
        self.assertEqual(expected, actual)


class ServerTest(test_utils.BaseTestCase):
    def test_create_pool(self):
        """Ensure the wsgi thread pool is an eventlet.greenpool.GreenPool."""
        actual = wsgi.Server(threads=1).create_pool()
        self.assertIsInstance(actual, eventlet.greenpool.GreenPool)


class TestHelpers(test_utils.BaseTestCase):

    def test_headers_are_unicode(self):
        """
        Verifies that the headers returned by conversion code are unicode.

        Headers are passed via http in non-testing mode, which automatically
        converts them to unicode. Verifying that the method does the
        conversion proves that we aren't passing data that works in tests
        but will fail in production.
        """
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}
        headers = utils.image_meta_to_http_headers(fixture)
        for k, v in headers.iteritems():
            self.assertIsInstance(v, unicode)

    def test_data_passed_properly_through_headers(self):
        """
        Verifies that data is the same after being passed through headers
        """
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'deleted': False,
                   'name': None,
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}
        headers = utils.image_meta_to_http_headers(fixture)

        class FakeResponse():
            pass

        response = FakeResponse()
        response.headers = headers
        result = utils.get_image_meta_from_headers(response)
        for k, v in fixture.iteritems():
            if v is not None:
                self.assertEqual(v, result[k])
            else:
                self.assertFalse(k in result)


class GetSocketTestCase(test_utils.BaseTestCase):

    def setUp(self):
        super(GetSocketTestCase, self).setUp()
        self.useFixture(fixtures.MonkeyPatch(
            "glance.common.wsgi.get_bind_addr",
            lambda x: ('192.168.0.13', 1234)))
        addr_info_list = [(2, 1, 6, '', ('192.168.0.13', 80)),
                          (2, 2, 17, '', ('192.168.0.13', 80)),
                          (2, 3, 0, '', ('192.168.0.13', 80))]
        self.useFixture(fixtures.MonkeyPatch(
            "glance.common.wsgi.socket.getaddrinfo",
            lambda *x: addr_info_list))
        self.useFixture(fixtures.MonkeyPatch(
            "glance.common.wsgi.time.time",
            mock.Mock(side_effect=[0, 1, 5, 10, 20, 35])))
        self.useFixture(fixtures.MonkeyPatch(
            "glance.common.wsgi.utils.validate_key_cert",
            lambda *x: None))
        wsgi.CONF.cert_file = '/etc/ssl/cert'
        wsgi.CONF.key_file = '/etc/ssl/key'
        wsgi.CONF.ca_file = '/etc/ssl/ca_cert'
        wsgi.CONF.tcp_keepidle = 600

    def test_correct_get_socket(self):
        mock_socket = mock.Mock()
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.ssl.wrap_socket',
            mock_socket))
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            lambda *x, **y: None))
        wsgi.get_socket(1234)
        self.assertTrue(mock.call().setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1) in mock_socket.mock_calls)
        self.assertTrue(mock.call().setsockopt(
            socket.SOL_SOCKET,
            socket.SO_KEEPALIVE,
            1) in mock_socket.mock_calls)
        if hasattr(socket, 'TCP_KEEPIDLE'):
            self.assertTrue(mock.call().setsockopt(
                socket.IPPROTO_TCP,
                socket.TCP_KEEPIDLE,
                wsgi.CONF.tcp_keepidle) in mock_socket.mock_calls)

    def test_get_socket_without_all_ssl_reqs(self):
        wsgi.CONF.key_file = None
        self.assertRaises(RuntimeError, wsgi.get_socket, 1234)

    def test_get_socket_with_bind_problems(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=(
                [wsgi.socket.error(socket.errno.EADDRINUSE)] * 3 + [None]))))
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.ssl.wrap_socket',
            lambda *x, **y: None))

        self.assertRaises(RuntimeError, wsgi.get_socket, 1234)

    def test_get_socket_with_unexpected_socket_errno(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=wsgi.socket.error(socket.errno.ENOMEM))))
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.ssl.wrap_socket',
            lambda *x, **y: None))
        self.assertRaises(wsgi.socket.error, wsgi.get_socket, 1234)
