# Copyright 2011 OpenStack Foundation
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

"""Functional test cases testing glance client redirect-following."""
import eventlet.patcher
from six.moves import http_client as http
import webob.dec
import webob.exc

from glance.common import client
from glance.common import exception
from glance.common import wsgi
from glance.tests import functional
from glance.tests import utils


eventlet.patcher.monkey_patch(socket=True)


def RedirectTestApp(name):
    class App(object):
        """
        Test WSGI application which can respond with multiple kinds of HTTP
        redirects and is used to verify Glance client redirects.
        """
        def __init__(self):
            """
            Initialize app with a name and port.
            """
            self.name = name

        @webob.dec.wsgify
        def __call__(self, request):
            """
            Handles all requests to the application.
            """
            base = "http://%s" % request.host
            path = request.path_qs

            if path == "/":
                return "root"

            elif path == "/302":
                url = "%s/success" % base
                raise webob.exc.HTTPFound(location=url)

            elif path == "/302?with_qs=yes":
                url = "%s/success?with_qs=yes" % base
                raise webob.exc.HTTPFound(location=url)

            elif path == "/infinite_302":
                raise webob.exc.HTTPFound(location=request.url)

            elif path.startswith("/redirect-to"):
                url = "http://127.0.0.1:%s/success" % path.split("-")[-1]
                raise webob.exc.HTTPFound(location=url)

            elif path == "/success":
                return "success_from_host_%s" % self.name

            elif path == "/success?with_qs=yes":
                return "success_with_qs"

            return "fail"

    return App


class TestClientRedirects(functional.FunctionalTest):

    def setUp(self):
        super(TestClientRedirects, self).setUp()
        self.port_one = utils.get_unused_port()
        self.port_two = utils.get_unused_port()
        server_one = wsgi.Server()
        server_two = wsgi.Server()
        self.config(bind_host='127.0.0.1')
        self.config(workers=0)
        server_one.start(RedirectTestApp("one")(), self.port_one)
        server_two.start(RedirectTestApp("two")(), self.port_two)
        self.client = client.BaseClient("127.0.0.1", self.port_one)

    def test_get_without_redirect(self):
        """
        Test GET with no redirect
        """
        response = self.client.do_request("GET", "/")
        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"root", response.read())

    def test_get_with_one_redirect(self):
        """
        Test GET with one 302 FOUND redirect
        """
        response = self.client.do_request("GET", "/302")
        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"success_from_host_one", response.read())

    def test_get_with_one_redirect_query_string(self):
        """
        Test GET with one 302 FOUND redirect w/ a query string
        """
        response = self.client.do_request("GET", "/302",
                                          params={'with_qs': 'yes'})
        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"success_with_qs", response.read())

    def test_get_with_max_redirects(self):
        """
        Test we don't redirect forever.
        """
        self.assertRaises(exception.MaxRedirectsExceeded,
                          self.client.do_request,
                          "GET",
                          "/infinite_302")

    def test_post_redirect(self):
        """
        Test POST with 302 redirect
        """
        response = self.client.do_request("POST", "/302")
        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"success_from_host_one", response.read())

    def test_redirect_to_new_host(self):
        """
        Test redirect to one host and then another.
        """
        url = "/redirect-to-%d" % self.port_two
        response = self.client.do_request("POST", url)

        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"success_from_host_two", response.read())

        response = self.client.do_request("POST", "/success")
        self.assertEqual(http.OK, response.status)
        self.assertEqual(b"success_from_host_one", response.read())
