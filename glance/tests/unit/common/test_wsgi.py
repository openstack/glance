# -*- coding: utf-8 -*-
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
import gettext
import os
import socket
from unittest import mock

from babel import localedata
import eventlet.patcher
import fixtures
from oslo_concurrency import processutils
from oslo_serialization import jsonutils
import routes
import six
from six.moves import http_client as http
import webob

from glance.api.v2 import router as router_v2
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance import i18n
from glance.image_cache import prefetcher
from glance.tests import utils as test_utils


class RequestTest(test_utils.BaseTestCase):

    def _set_expected_languages(self, all_locales=None, avail_locales=None):
        if all_locales is None:
            all_locales = []

        # Override localedata.locale_identifiers to return some locales.
        def returns_some_locales(*args, **kwargs):
            return all_locales

        self.mock_object(localedata, 'locale_identifiers',
                         returns_some_locales)

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

        self.mock_object(gettext, 'find', fake_gettext_find)

    def test_content_range(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Range"] = 'bytes 10-99/*'
        range_ = request.get_range_from_request(120)
        self.assertEqual(10, range_.start)
        self.assertEqual(100, range_.stop)  # non-inclusive
        self.assertIsNone(range_.length)

    def test_content_range_invalid(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Range"] = 'bytes=0-99'
        self.assertRaises(webob.exc.HTTPRequestRangeNotSatisfiable,
                          request.get_range_from_request, 120)

    def test_range(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Range"] = 'bytes=10-99'
        range_ = request.get_range_from_request(120)
        self.assertEqual(10, range_.start)
        self.assertEqual(100, range_.end)  # non-inclusive

    def test_range_invalid(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Range"] = 'bytes=150-'
        self.assertRaises(webob.exc.HTTPRequestRangeNotSatisfiable,
                          request.get_range_from_request, 120)

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
        self.assertEqual("application/json", result)

    def test_params(self):
        if six.PY2:
            expected = webob.multidict.NestedMultiDict({
                'limit': '20', 'name':
                    '\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82',
                'sort_key': 'name', 'sort_dir': 'asc'})
        else:
            expected = webob.multidict.NestedMultiDict({
                'limit': '20', 'name': 'Привет', 'sort_key': 'name',
                'sort_dir': 'asc'})

        request = wsgi.Request.blank("/?limit=20&name=%D0%9F%D1%80%D0%B8"
                                     "%D0%B2%D0%B5%D1%82&sort_key=name"
                                     "&sort_dir=asc")
        actual = request.params
        self.assertEqual(expected, actual)

    def test_content_type_from_accept_xml(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml"
        result = request.best_match_content_type()
        self.assertEqual("application/json", result)

    def test_content_type_from_accept_json(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/json"
        result = request.best_match_content_type()
        self.assertEqual("application/json", result)

    def test_content_type_from_accept_xml_json(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml, application/json"
        result = request.best_match_content_type()
        self.assertEqual("application/json", result)

    def test_content_type_from_accept_json_xml_quality(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = ("application/json; q=0.3, "
                                     "application/xml; q=0.9")
        result = request.best_match_content_type()
        self.assertEqual("application/json", result)

    def test_content_type_accept_default(self):
        request = wsgi.Request.blank('/tests/123.unsupported')
        request.headers["Accept"] = "application/unsupported1"
        result = request.best_match_content_type()
        self.assertEqual("application/json", result)

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

        req = wsgi.Request.blank('/', headers={'Accept-Language': 'unknown'})
        self.assertIsNone(req.best_match_language())

    @mock.patch.object(webob.acceptparse.AcceptLanguageValidHeader, 'lookup')
    def test_best_match_language_unknown(self, mock_lookup):
        # Test that we are actually invoking language negotiation by WebOb
        request = wsgi.Request.blank('/')
        accepted = 'unknown-lang'
        request.headers = {'Accept-Language': accepted}

        # Bug #1765748: see comment in code in the function under test
        # to understand why this is the correct return value for the
        # webob 1.8.x mock
        mock_lookup.return_value = 'fake_LANG'

        self.assertIsNone(request.best_match_language())
        mock_lookup.assert_called_once()

        # If Accept-Language is missing or empty, match should be None
        request.headers = {'Accept-Language': ''}
        self.assertIsNone(request.best_match_language())
        request.headers.pop('Accept-Language')
        self.assertIsNone(request.best_match_language())

    def test_http_error_response_codes(self):
        sample_id, member_id, tag_val, task_id = 'abc', '123', '1', '2'

        """Makes sure v2 unallowed methods return 405"""
        unallowed_methods = [
            ('/schemas/image', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/schemas/images', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/schemas/member', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/schemas/members', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/schemas/task', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/schemas/tasks', ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/images', ['PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/images/%s' % sample_id, ['POST', 'PUT', 'HEAD']),
            ('/images/%s/file' % sample_id,
                ['POST', 'DELETE', 'PATCH', 'HEAD']),
            ('/images/%s/tags/%s' % (sample_id, tag_val),
                ['GET', 'POST', 'PATCH', 'HEAD']),
            ('/images/%s/members' % sample_id,
                ['PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/images/%s/members/%s' % (sample_id, member_id),
                ['POST', 'PATCH', 'HEAD']),
            ('/tasks', ['PUT', 'DELETE', 'PATCH', 'HEAD']),
            ('/tasks/%s' % task_id, ['POST', 'PUT', 'PATCH', 'HEAD']),
        ]
        api = test_utils.FakeAuthMiddleware(router_v2.API(routes.Mapper()))
        for uri, methods in unallowed_methods:
            for method in methods:
                req = webob.Request.blank(uri)
                req.method = method
                res = req.get_response(api)
                self.assertEqual(http.METHOD_NOT_ALLOWED, res.status_int)

        # Makes sure not implemented methods return 405
        req = webob.Request.blank('/schemas/image')
        req.method = 'NonexistentMethod'
        res = req.get_response(api)
        self.assertEqual(http.METHOD_NOT_ALLOWED, res.status_int)


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

        self.assertEqual(expected, actual)

    def test_get_action_args_invalid_index(self):
        env = {'wsgiorg.routing_args': []}
        expected = {}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_get_action_args_del_controller_error(self):
        actions = {'format': None,
                   'action': 'update',
                   'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_get_action_args_del_format_error(self):
        actions = {'action': 'update', 'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_dispatch(self):
        class Controller(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(expected, actual)

    def test_dispatch_default(self):
        class Controller(object):
            def default(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(expected, actual)

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

        self.mock_object(wsgi.Resource, 'dispatch', dispatch)

        request = wsgi.Request.blank('/')

        response = resource.__call__(request)

        self.assertIsInstance(response, webob.exc.HTTPForbidden)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    def test_call_raises_exception(self):
        class FakeController(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(FakeController(), None, None)

        def dispatch(self, obj, action, *args, **kwargs):
            raise Exception("test exception")

        self.mock_object(wsgi.Resource, 'dispatch', dispatch)

        request = wsgi.Request.blank('/')

        response = resource.__call__(request)

        self.assertIsInstance(response, webob.exc.HTTPInternalServerError)
        self.assertEqual(http.INTERNAL_SERVER_ERROR, response.status_code)

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

    @mock.patch.object(webob.acceptparse.AcceptLanguageValidHeader, 'lookup')
    @mock.patch.object(i18n, 'translate')
    def test_translate_exception(self, mock_translate, mock_lookup):
        mock_translate.return_value = 'No Encontrado'
        mock_lookup.return_value = 'de'

        req = wsgi.Request.blank('/tests/123')
        req.headers["Accept-Language"] = "de"

        e = webob.exc.HTTPNotFound(explanation='Not Found')
        e = wsgi.translate_exception(req, e)
        self.assertEqual('No Encontrado', e.explanation)

    def test_response_headers_encoded(self):
        # prepare environment
        for_openstack_comrades = (
            u'\u0417\u0430 \u043e\u043f\u0435\u043d\u0441\u0442\u0435\u043a, '
            u'\u0442\u043e\u0432\u0430\u0440\u0438\u0449\u0438')

        class FakeController(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        class FakeSerializer(object):
            def index(self, response, result):
                response.headers['unicode_test'] = for_openstack_comrades

        # make request
        resource = wsgi.Resource(FakeController(), None, FakeSerializer())
        actions = {'action': 'index'}
        env = {'wsgiorg.routing_args': [None, actions]}
        request = wsgi.Request.blank('/tests/123', environ=env)
        response = resource.__call__(request)

        # ensure it has been encoded correctly
        value = (response.headers['unicode_test'].decode('utf-8')
                 if six.PY2 else response.headers['unicode_test'])
        self.assertEqual(for_openstack_comrades, value)


class JSONResponseSerializerTest(test_utils.BaseTestCase):

    def test_to_json(self):
        fixture = {"key": "value"}
        expected = b'{"key": "value"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_to_json_with_date_format_value(self):
        fixture = {"date": datetime.datetime(1901, 3, 8, 2)}
        expected = b'{"date": "1901-03-08T02:00:00.000000"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_to_json_with_more_deep_format(self):
        fixture = {"is_public": True, "name": [{"name1": "test"}]}
        expected = {"is_public": True, "name": [{"name1": "test"}]}
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        actual = jsonutils.loads(actual)
        for k in expected:
            self.assertEqual(expected[k], actual[k])

    def test_to_json_with_set(self):
        fixture = set(["foo"])
        expected = b'["foo"]'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_default(self):
        fixture = {"key": "value"}
        response = webob.Response()
        wsgi.JSONResponseSerializer().default(response, fixture)
        self.assertEqual(http.OK, response.status_int)
        content_types = [h for h in response.headerlist
                         if h[0] == 'Content-Type']
        self.assertEqual(1, len(content_types))
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(b'{"key": "value"}', response.body)


class JSONRequestDeserializerTest(test_utils.BaseTestCase):

    def test_has_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        request.headers.pop('Content-Length')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_zero_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        request.headers['Content-Length'] = 0
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_has_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        self.assertIn('Content-Length', request.headers)
        self.assertTrue(wsgi.JSONRequestDeserializer().has_body(request))

    def test_no_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_from_json(self):
        fixture = '{"key": "value"}'
        expected = {"key": "value"}
        actual = wsgi.JSONRequestDeserializer().from_json(fixture)
        self.assertEqual(expected, actual)

    def test_from_json_malformed(self):
        fixture = 'kjasdklfjsklajf'
        self.assertRaises(webob.exc.HTTPBadRequest,
                          wsgi.JSONRequestDeserializer().from_json, fixture)

    def test_default_no_body(self):
        request = wsgi.Request.blank('/')
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {}
        self.assertEqual(expected, actual)

    def test_default_with_body(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'{"key": "value"}'
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {"body": {"key": "value"}}
        self.assertEqual(expected, actual)

    def test_has_body_has_transfer_encoding(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked'))

    def test_has_body_multiple_transfer_encoding(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked, gzip'))

    def test_has_body_invalid_transfer_encoding(self):
        self.assertFalse(self._check_transfer_encoding(
                         transfer_encoding='invalid', content_length=0))

    def test_has_body_invalid_transfer_encoding_no_content_len_and_body(self):
        self.assertFalse(self._check_transfer_encoding(
                         transfer_encoding='invalid', include_body=False))

    def test_has_body_invalid_transfer_encoding_no_content_len_but_body(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='invalid', include_body=True))

    def test_has_body_invalid_transfer_encoding_with_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='invalid', content_length=5))

    def test_has_body_valid_transfer_encoding_with_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked', content_length=1))

    def test_has_body_valid_transfer_encoding_without_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked'))

    def _check_transfer_encoding(self, transfer_encoding=None,
                                 content_length=None, include_body=True):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        if include_body:
            request.body = b'fake_body'
        request.headers['transfer-encoding'] = transfer_encoding
        if content_length is not None:
            request.headers['content-length'] = content_length

        return wsgi.JSONRequestDeserializer().has_body(request)

    def test_get_bind_addr_default_value(self):
        expected = ('0.0.0.0', '123456')
        actual = wsgi.get_bind_addr(default_port="123456")
        self.assertEqual(expected, actual)


class ServerTest(test_utils.BaseTestCase):
    @mock.patch.object(prefetcher, 'Prefetcher')
    def test_create_pool(self, mock_prefetcher):
        """Ensure the wsgi thread pool is an eventlet.greenpool.GreenPool."""
        actual = wsgi.Server(threads=1).create_pool()
        self.assertIsInstance(actual, eventlet.greenpool.GreenPool)

    @mock.patch.object(prefetcher, 'Prefetcher')
    @mock.patch.object(wsgi.Server, 'configure_socket')
    def test_reserved_stores_not_allowed(self, mock_configure_socket,
                                         mock_prefetcher):
        """Ensure the reserved stores are not allowed"""
        enabled_backends = {'os_glance_file_store': 'file'}
        self.config(enabled_backends=enabled_backends)
        server = wsgi.Server(threads=1, initialize_glance_store=True)
        self.assertRaises(RuntimeError, server.configure)

    @mock.patch.object(prefetcher, 'Prefetcher')
    @mock.patch.object(wsgi.Server, 'configure_socket')
    def test_http_keepalive(self, mock_configure_socket, mock_prefetcher):
        self.config(http_keepalive=False)
        self.config(workers=0)

        server = wsgi.Server(threads=1)
        server.sock = 'fake_socket'
        # mocking eventlet.wsgi server method to check it is called with
        # configured 'http_keepalive' value.
        with mock.patch.object(eventlet.wsgi,
                               'server') as mock_server:
            fake_application = "fake-application"
            server.start(fake_application, 0)
            server.wait()
            mock_server.assert_called_once_with('fake_socket',
                                                fake_application,
                                                log=server._logger,
                                                debug=False,
                                                custom_pool=server.pool,
                                                keepalive=False,
                                                socket_timeout=900)

    @mock.patch.object(prefetcher, 'Prefetcher')
    def test_number_of_workers_posix(self, mock_prefetcher):
        """Ensure the number of workers matches num cpus limited to 8."""
        if os.name == 'nt':
            raise self.skipException("Unsupported platform.")

        def pid():
            i = 1
            while True:
                i = i + 1
                yield i

        with mock.patch.object(os, 'fork') as mock_fork:
            with mock.patch('oslo_concurrency.processutils.get_worker_count',
                            return_value=4):
                mock_fork.side_effect = pid
                server = wsgi.Server()
                server.configure = mock.Mock()
                fake_application = "fake-application"
                server.start(fake_application, None)
                self.assertEqual(4, len(server.children))
            with mock.patch('oslo_concurrency.processutils.get_worker_count',
                            return_value=24):
                mock_fork.side_effect = pid
                server = wsgi.Server()
                server.configure = mock.Mock()
                fake_application = "fake-application"
                server.start(fake_application, None)
                self.assertEqual(8, len(server.children))
            mock_fork.side_effect = pid
            server = wsgi.Server()
            server.configure = mock.Mock()
            fake_application = "fake-application"
            server.start(fake_application, None)
            cpus = processutils.get_worker_count()
            expected_workers = cpus if cpus < 8 else 8
            self.assertEqual(expected_workers,
                             len(server.children))


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
        for k, v in six.iteritems(headers):
            self.assertIsInstance(v, six.text_type)

    def test_data_passed_properly_through_headers(self):
        """
        Verifies that data is the same after being passed through headers
        """
        fixture = {'is_public': True,
                   'deleted': False,
                   'name': None,
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}
        headers = utils.image_meta_to_http_headers(fixture)

        class FakeResponse(object):
            pass

        response = FakeResponse()
        response.headers = headers
        result = utils.get_image_meta_from_headers(response)
        for k, v in six.iteritems(fixture):
            if v is not None:
                self.assertEqual(v, result[k])
            else:
                self.assertNotIn(k, result)


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
        wsgi.CONF.tcp_keepidle = 600

    @mock.patch.object(prefetcher, 'Prefetcher')
    def test_correct_configure_socket(self, mock_prefetcher):
        mock_socket = mock.Mock()
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            lambda *x, **y: mock_socket))
        server = wsgi.Server()
        server.default_port = 1234
        server.configure_socket()
        self.assertIn(mock.call.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1), mock_socket.mock_calls)
        self.assertIn(mock.call.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_KEEPALIVE,
            1), mock_socket.mock_calls)
        if hasattr(socket, 'TCP_KEEPIDLE'):
            self.assertIn(mock.call.setsockopt(
                socket.IPPROTO_TCP,
                socket.TCP_KEEPIDLE,
                wsgi.CONF.tcp_keepidle), mock_socket.mock_calls)

    def test_get_socket_with_bind_problems(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=(
                [wsgi.socket.error(socket.errno.EADDRINUSE)] * 3 + [None]))))

        self.assertRaises(RuntimeError, wsgi.get_socket, 1234)

    def test_get_socket_with_unexpected_socket_errno(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glance.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=wsgi.socket.error(socket.errno.ENOMEM))))
        self.assertRaises(wsgi.socket.error, wsgi.get_socket, 1234)


def _cleanup_uwsgi():
    wsgi.uwsgi = None


class Test_UwsgiChunkedFile(test_utils.BaseTestCase):

    def test_read_no_data(self):
        reader = wsgi._UWSGIChunkFile()
        wsgi.uwsgi = mock.MagicMock()
        self.addCleanup(_cleanup_uwsgi)

        def fake_read():
            return None

        wsgi.uwsgi.chunked_read = fake_read
        out = reader.read()
        self.assertEqual(out, b'')

    def test_read_data_no_length(self):
        reader = wsgi._UWSGIChunkFile()
        wsgi.uwsgi = mock.MagicMock()
        self.addCleanup(_cleanup_uwsgi)

        values = iter([b'a', b'b', b'c', None])

        def fake_read():
            return next(values)

        wsgi.uwsgi.chunked_read = fake_read
        out = reader.read()
        self.assertEqual(out, b'abc')

    def test_read_zero_length(self):
        reader = wsgi._UWSGIChunkFile()
        self.assertEqual(b'', reader.read(length=0))

    def test_read_data_length(self):
        reader = wsgi._UWSGIChunkFile()
        wsgi.uwsgi = mock.MagicMock()
        self.addCleanup(_cleanup_uwsgi)

        values = iter([b'a', b'b', b'c', None])

        def fake_read():
            return next(values)

        wsgi.uwsgi.chunked_read = fake_read
        out = reader.read(length=2)
        self.assertEqual(out, b'ab')

    def test_read_data_negative_length(self):
        reader = wsgi._UWSGIChunkFile()
        wsgi.uwsgi = mock.MagicMock()
        self.addCleanup(_cleanup_uwsgi)

        values = iter([b'a', b'b', b'c', None])

        def fake_read():
            return next(values)

        wsgi.uwsgi.chunked_read = fake_read
        out = reader.read(length=-2)
        self.assertEqual(out, b'abc')
