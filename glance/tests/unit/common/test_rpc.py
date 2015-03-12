# -*- coding: utf-8 -*-

# Copyright 2013 Red Hat, Inc.
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

from oslo_config import cfg
from oslo_serialization import jsonutils
import routes
import webob

from glance.common import exception
from glance.common import rpc
from glance.common import wsgi
from glance.tests.unit import base
from glance.tests import utils as test_utils

CONF = cfg.CONF


class FakeResource(object):
    """
    Fake resource defining some methods that
    will be called later by the api.
    """

    def get_images(self, context, keyword=None):
        return keyword

    def count_images(self, context, images):
        return len(images)

    def get_all_images(self, context):
        return False

    def raise_value_error(self, context):
        raise ValueError("Yep, Just like that!")

    def raise_weird_error(self, context):
        class WeirdError(Exception):
            pass
        raise WeirdError("Weirdness")


def create_api():
    deserializer = rpc.RPCJSONDeserializer()
    serializer = rpc.RPCJSONSerializer()
    controller = rpc.Controller()
    controller.register(FakeResource())
    res = wsgi.Resource(controller, deserializer, serializer)

    mapper = routes.Mapper()
    mapper.connect("/rpc", controller=res,
                   conditions=dict(method=["POST"]),
                   action="__call__")
    return test_utils.FakeAuthMiddleware(wsgi.Router(mapper), is_admin=True)


class TestRPCController(base.IsolatedUnitTest):

    def setUp(self):
        super(TestRPCController, self).setUp()
        self.res = FakeResource()
        self.controller = rpc.Controller()
        self.controller.register(self.res)

    def test_register(self):
        res = FakeResource()
        controller = rpc.Controller()
        controller.register(res)
        self.assertIn("get_images", controller._registered)
        self.assertIn("get_all_images", controller._registered)

    def test_reigster_filtered(self):
        res = FakeResource()
        controller = rpc.Controller()
        controller.register(res, filtered=["get_all_images"])
        self.assertIn("get_all_images", controller._registered)

    def test_reigster_excluded(self):
        res = FakeResource()
        controller = rpc.Controller()
        controller.register(res, excluded=["get_all_images"])
        self.assertIn("get_images", controller._registered)

    def test_reigster_refiner(self):
        res = FakeResource()
        controller = rpc.Controller()

        # Not callable
        self.assertRaises(AssertionError,
                          controller.register,
                          res, refiner="get_all_images")

        # Filter returns False
        controller.register(res, refiner=lambda x: False)
        self.assertNotIn("get_images", controller._registered)
        self.assertNotIn("get_images", controller._registered)

        # Filter returns True
        controller.register(res, refiner=lambda x: True)
        self.assertIn("get_images", controller._registered)
        self.assertIn("get_images", controller._registered)

    def test_request(self):
        api = create_api()
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        req.body = jsonutils.dumps([
            {
                "command": "get_images",
                "kwargs": {"keyword": 1}
            }
        ])
        res = req.get_response(api)
        returned = jsonutils.loads(res.body)
        self.assertIsInstance(returned, list)
        self.assertEqual(1, returned[0])

    def test_request_exc(self):
        api = create_api()
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        req.body = jsonutils.dumps([
            {
                "command": "get_all_images",
                "kwargs": {"keyword": 1}
            }
        ])

        # Sending non-accepted keyword
        # to get_all_images method
        res = req.get_response(api)
        returned = jsonutils.loads(res.body)
        self.assertIn("_error", returned[0])

    def test_rpc_errors(self):
        api = create_api()
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        req.content_type = 'application/json'

        # Body is not a list, it should fail
        req.body = jsonutils.dumps({})
        res = req.get_response(api)
        self.assertEqual(400, res.status_int)

        # cmd is not dict, it should fail.
        req.body = jsonutils.dumps([None])
        res = req.get_response(api)
        self.assertEqual(400, res.status_int)

        # No command key, it should fail.
        req.body = jsonutils.dumps([{}])
        res = req.get_response(api)
        self.assertEqual(400, res.status_int)

        # kwargs not dict, it should fail.
        req.body = jsonutils.dumps([{"command": "test", "kwargs": 200}])
        res = req.get_response(api)
        self.assertEqual(400, res.status_int)

        # Command does not exist, it should fail.
        req.body = jsonutils.dumps([{"command": "test"}])
        res = req.get_response(api)
        self.assertEqual(404, res.status_int)

    def test_rpc_exception_propagation(self):
        api = create_api()
        req = webob.Request.blank('/rpc')
        req.method = 'POST'
        req.content_type = 'application/json'

        req.body = jsonutils.dumps([{"command": "raise_value_error"}])
        res = req.get_response(api)
        self.assertEqual(200, res.status_int)

        returned = jsonutils.loads(res.body)[0]
        self.assertEqual('exceptions.ValueError', returned['_error']['cls'])

        req.body = jsonutils.dumps([{"command": "raise_weird_error"}])
        res = req.get_response(api)
        self.assertEqual(200, res.status_int)

        returned = jsonutils.loads(res.body)[0]
        self.assertEqual('glance.common.exception.RPCError',
                         returned['_error']['cls'])


class TestRPCClient(base.IsolatedUnitTest):

    def setUp(self):
        super(TestRPCClient, self).setUp()
        self.api = create_api()
        self.client = rpc.RPCClient(host="http://127.0.0.1:9191")
        self.client._do_request = self.fake_request

    def fake_request(self, method, url, body, headers):
        req = webob.Request.blank(url.path)
        req.body = body
        req.method = method

        webob_res = req.get_response(self.api)
        return test_utils.FakeHTTPResponse(status=webob_res.status_int,
                                           headers=webob_res.headers,
                                           data=webob_res.body)

    def test_method_proxy(self):
        proxy = self.client.some_method
        self.assertIn("method_proxy", str(proxy))

    def test_bulk_request(self):
        commands = [{"command": "get_images", 'kwargs': {'keyword': True}},
                    {"command": "get_all_images"}]

        res = self.client.bulk_request(commands)
        self.assertEqual(2, len(res))
        self.assertTrue(res[0])
        self.assertFalse(res[1])

    def test_exception_raise(self):
        try:
            self.client.raise_value_error()
            self.fail("Exception not raised")
        except ValueError as exc:
            self.assertEqual("Yep, Just like that!", str(exc))

    def test_rpc_exception(self):
        try:
            self.client.raise_weird_error()
            self.fail("Exception not raised")
        except exception.RPCError:
            pass

    def test_non_str_or_dict_response(self):
        rst = self.client.count_images(images=[1, 2, 3, 4])
        self.assertEqual(4, rst)
        self.assertIsInstance(rst, int)


class TestRPCJSONSerializer(test_utils.BaseTestCase):

    def test_to_json(self):
        fixture = {"key": "value"}
        expected = '{"key": "value"}'
        actual = rpc.RPCJSONSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_to_json_with_date_format_value(self):
        fixture = {"date": datetime.datetime(1900, 3, 8, 2)}
        expected = {"date": {"_value": "1900-03-08T02:00:00",
                             "_type": "datetime"}}
        actual = rpc.RPCJSONSerializer().to_json(fixture)
        actual = jsonutils.loads(actual)
        for k in expected['date']:
            self.assertEqual(expected['date'][k], actual['date'][k])

    def test_to_json_with_more_deep_format(self):
        fixture = {"is_public": True, "name": [{"name1": "test"}]}
        expected = {"is_public": True, "name": [{"name1": "test"}]}
        actual = rpc.RPCJSONSerializer().to_json(fixture)
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        actual = jsonutils.loads(actual)
        for k in expected:
            self.assertEqual(expected[k], actual[k])

    def test_default(self):
        fixture = {"key": "value"}
        response = webob.Response()
        rpc.RPCJSONSerializer().default(response, fixture)
        self.assertEqual(200, response.status_int)
        content_types = filter(lambda h: h[0] == 'Content-Type',
                               response.headerlist)
        self.assertEqual(1, len(content_types))
        self.assertEqual('application/json', response.content_type)
        self.assertEqual('{"key": "value"}', response.body)


class TestRPCJSONDeserializer(test_utils.BaseTestCase):

    def test_has_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        request.headers.pop('Content-Length')
        self.assertFalse(rpc.RPCJSONDeserializer().has_body(request))

    def test_has_body_zero_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        request.headers['Content-Length'] = 0
        self.assertFalse(rpc.RPCJSONDeserializer().has_body(request))

    def test_has_body_has_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'asdf'
        self.assertIn('Content-Length', request.headers)
        self.assertTrue(rpc.RPCJSONDeserializer().has_body(request))

    def test_no_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        self.assertFalse(rpc.RPCJSONDeserializer().has_body(request))

    def test_from_json(self):
        fixture = '{"key": "value"}'
        expected = {"key": "value"}
        actual = rpc.RPCJSONDeserializer().from_json(fixture)
        self.assertEqual(expected, actual)

    def test_from_json_malformed(self):
        fixture = 'kjasdklfjsklajf'
        self.assertRaises(webob.exc.HTTPBadRequest,
                          rpc.RPCJSONDeserializer().from_json, fixture)

    def test_default_no_body(self):
        request = wsgi.Request.blank('/')
        actual = rpc.RPCJSONDeserializer().default(request)
        expected = {}
        self.assertEqual(expected, actual)

    def test_default_with_body(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = '{"key": "value"}'
        actual = rpc.RPCJSONDeserializer().default(request)
        expected = {"body": {"key": "value"}}
        self.assertEqual(expected, actual)

    def test_has_body_has_transfer_encoding(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = 'fake_body'
        request.headers['transfer-encoding'] = ''
        self.assertIn('transfer-encoding', request.headers)
        self.assertTrue(rpc.RPCJSONDeserializer().has_body(request))

    def test_to_json_with_date_format_value(self):
        fixture = ('{"date": {"_value": "1900-03-08T02:00:00.000000",'
                   '"_type": "datetime"}}')
        expected = {"date": datetime.datetime(1900, 3, 8, 2)}
        actual = rpc.RPCJSONDeserializer().from_json(fixture)
        self.assertEqual(expected, actual)
