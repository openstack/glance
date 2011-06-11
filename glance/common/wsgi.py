# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010 OpenStack LLC.
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

"""
Utility methods for working with WSGI servers
"""

import json
import logging
import sys
import datetime
import eventlet
import eventlet.wsgi
eventlet.patcher.monkey_patch(all=False, socket=True)
import routes
import routes.middleware
import webob.dec
import webob.exc

from glance.common import exception


class WritableLogger(object):
    """A thin wrapper that responds to `write` and logs."""

    def __init__(self, logger, level=logging.DEBUG):
        self.logger = logger
        self.level = level

    def write(self, msg):
        self.logger.log(self.level, msg.strip("\n"))


def run_server(application, port):
    """Run a WSGI server with the given application."""
    sock = eventlet.listen(('0.0.0.0', port))
    eventlet.wsgi.server(sock, application)


class Server(object):
    """Server class to manage multiple WSGI sockets and applications."""

    def __init__(self, threads=1000):
        self.pool = eventlet.GreenPool(threads)

    def start(self, application, port, host='0.0.0.0', backlog=128):
        """Run a WSGI server with the given application."""
        socket = eventlet.listen((host, port), backlog=backlog)
        self.pool.spawn_n(self._run, application, socket)

    def wait(self):
        """Wait until all servers have completed running."""
        try:
            self.pool.waitall()
        except KeyboardInterrupt:
            pass

    def _run(self, application, socket):
        """Start a WSGI server in a new green thread."""
        logger = logging.getLogger('eventlet.wsgi.server')
        eventlet.wsgi.server(socket, application, custom_pool=self.pool,
                             log=WritableLogger(logger))


class Middleware(object):
    """
    Base WSGI middleware wrapper. These classes require an application to be
    initialized that will be called next.  By default the middleware will
    simply call its wrapped app, or you can override __call__ to customize its
    behavior.
    """

    def __init__(self, application):
        self.application = application

    def process_request(self, req):
        """
        Called on each request.

        If this returns None, the next application down the stack will be
        executed. If it returns a response then that response will be returned
        and execution will stop here.

        """
        return None

    def process_response(self, response):
        """Do whatever you'd like to the response."""
        return response

    @webob.dec.wsgify
    def __call__(self, req):
        response = self.process_request(req)
        if response:
            return response
        response = req.get_response(self.application)
        return self.process_response(response)


class Debug(Middleware):
    """
    Helper class that can be inserted into any WSGI application chain
    to get information about the request and response.
    """

    @webob.dec.wsgify
    def __call__(self, req):
        print ("*" * 40) + " REQUEST ENVIRON"
        for key, value in req.environ.items():
            print key, "=", value
        print
        resp = req.get_response(self.application)

        print ("*" * 40) + " RESPONSE HEADERS"
        for (key, value) in resp.headers.iteritems():
            print key, "=", value
        print

        resp.app_iter = self.print_generator(resp.app_iter)

        return resp

    @staticmethod
    def print_generator(app_iter):
        """
        Iterator that prints the contents of a wrapper string iterator
        when iterated.
        """
        print ("*" * 40) + " BODY"
        for part in app_iter:
            sys.stdout.write(part)
            sys.stdout.flush()
            yield part
        print


class Router(object):
    """
    WSGI middleware that maps incoming requests to WSGI apps.
    """

    def __init__(self, mapper):
        """
        Create a router for the given routes.Mapper.

        Each route in `mapper` must specify a 'controller', which is a
        WSGI app to call.  You'll probably want to specify an 'action' as
        well and have your controller be a wsgi.Controller, who will route
        the request to the action method.

        Examples:
          mapper = routes.Mapper()
          sc = ServerController()

          # Explicit mapping of one route to a controller+action
          mapper.connect(None, "/svrlist", controller=sc, action="list")

          # Actions are all implicitly defined
          mapper.resource("server", "servers", controller=sc)

          # Pointing to an arbitrary WSGI app.  You can specify the
          # {path_info:.*} parameter so the target app can be handed just that
          # section of the URL.
          mapper.connect(None, "/v1.0/{path_info:.*}", controller=BlogApp())
        """
        self.map = mapper
        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          self.map)

    @webob.dec.wsgify
    def __call__(self, req):
        """
        Route the incoming request to a controller based on self.map.
        If no match, return a 404.
        """
        return self._router

    @staticmethod
    @webob.dec.wsgify
    def _dispatch(req):
        """
        Called by self._router after matching the incoming request to a route
        and putting the information into req.environ.  Either returns 404
        or the routed WSGI app's response.
        """
        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            return webob.exc.HTTPNotFound()
        app = match['controller']
        return app


class Controller(object):
    """
    WSGI app that reads routing information supplied by RoutesMiddleware
    and calls the requested action method upon itself.  All action methods
    must, in addition to their normal parameters, accept a 'req' argument
    which is the incoming webob.Request.  They raise a webob.exc exception,
    or return a dict which will be serialized by requested content type.
    """

    @webob.dec.wsgify
    def __call__(self, req):
        """
        Call the method specified in req.environ by RoutesMiddleware.
        """
        arg_dict = req.environ['wsgiorg.routing_args'][1]
        action = arg_dict['action']
        method = getattr(self, action)
        del arg_dict['controller']
        del arg_dict['action']
        arg_dict['req'] = req
        result = method(**arg_dict)
        if type(result) is dict:
            return self._serialize(result, req)
        else:
            return result

    def _serialize(self, data, request):
        """
        Serialize the given dict to the response type requested in request.
        Uses self._serialization_metadata if it exists, which is a dict mapping
        MIME types to information needed to serialize to that type.
        """
        _metadata = getattr(type(self), "_serialization_metadata", {})
        serializer = Serializer(request.environ, _metadata)
        return serializer.to_content_type(data)


class Serializer(object):
    """
    Serializes a dictionary to a Content Type specified by a WSGI environment.
    """

    def __init__(self, environ, metadata=None):
        """
        Create a serializer based on the given WSGI environment.
        'metadata' is an optional dict mapping MIME types to information
        needed to serialize a dictionary to that type.
        """
        self.environ = environ
        self.metadata = metadata or {}
        self._methods = {
            'application/json': self._to_json,
            'application/xml': self._to_xml}

    def to_content_type(self, data):
        """
        Serialize a dictionary into a string.  The format of the string
        will be decided based on the Content Type requested in self.environ:
        by Accept: header, or by URL suffix.
        """
        # FIXME(sirp): for now, supporting json only
        #mimetype = 'application/xml'
        mimetype = 'application/json'
        # TODO(gundlach): determine mimetype from request
        return self._methods.get(mimetype, repr)(data)

    def _to_json(self, data):
        def sanitizer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            return obj

        return json.dumps(data, default=sanitizer)

    def _to_xml(self, data):
        metadata = self.metadata.get('application/xml', {})
        # We expect data to contain a single key which is the XML root.
        root_key = data.keys()[0]
        from xml.dom import minidom
        doc = minidom.Document()
        node = self._to_xml_node(doc, metadata, root_key, data[root_key])
        return node.toprettyxml(indent='    ')

    def _to_xml_node(self, doc, metadata, nodename, data):
        """Recursive method to convert data members to XML nodes."""
        result = doc.createElement(nodename)
        if type(data) is list:
            singular = metadata.get('plurals', {}).get(nodename, None)
            if singular is None:
                if nodename.endswith('s'):
                    singular = nodename[:-1]
                else:
                    singular = 'item'
            for item in data:
                node = self._to_xml_node(doc, metadata, singular, item)
                result.appendChild(node)
        elif type(data) is dict:
            attrs = metadata.get('attributes', {}).get(nodename, {})
            for k, v in data.items():
                if k in attrs:
                    result.setAttribute(k, str(v))
                else:
                    node = self._to_xml_node(doc, metadata, k, v)
                    result.appendChild(node)
        else:  # atom
            node = doc.createTextNode(str(data))
            result.appendChild(node)
        return result


class Request(webob.Request):
    """Add some Openstack API-specific logic to the base webob.Request."""

    def best_match_content_type(self):
        """Determine the requested response content-type.

        Based on the query extension then the Accept header.

        """
        supported = ('application/json',)

        #parts = self.path.rsplit('.', 1)
        #if len(parts) > 1:
        #    ctype = 'application/{0}'.format(parts[1])
        #    if ctype in supported:
        #        return ctype

        bm = self.accept.best_match(supported)

        # default to application/json if we don't find a preference
        return bm or 'application/json'

    def get_content_type(self):
        """Determine content type of the request body.

        Does not do any body introspection, only checks header

        """
        if not "Content-Type" in self.headers:
            raise exception.InvalidContentType(content_type=None)

        allowed_types = ("application/json")
        content_type = self.content_type

        if content_type not in allowed_types:
            raise exception.InvalidContentType(content_type=content_type)
        else:
            return content_type


class BodyDeserializer(object):
    """Custom request body deserialization based on controller action name."""

    def deserialize(self, datastring, action='default'):
        """Find local deserialization method and parse request body."""
        action_method = getattr(self, action, self.default)
        return action_method(datastring)

    def default(self, datastring):
        """Default deserialization code should live here"""
        raise NotImplementedError()


class JSONBodyDeserializer(BodyDeserializer):

    def default(self, datastring):
        return json.loads(datastring)


class RequestDeserializer(object):
    """Break up a Request object into more useful pieces."""

    def __init__(self, body_deserializers=None):
        """
        :param deserializers: dictionary of content-type-specific deserializers

        """
        self._body_deserializers = {
            'application/json': JSONBodyDeserializer(),
        }

        self._body_deserializers.update(body_deserializers or {})

    def deserialize(self, request):
        """Extract necessary pieces of the request.

        :param request: Request object
        :returns tuple of expected controller action name, dictionary of
                 keyword arguments to pass to the controller, the expected
                 content type of the response

        """
        action_args = self.get_action_args(request.environ)
        action = action_args.pop('action', None)

        if request.method.lower() in ('post', 'put'):
            if len(request.body) == 0:
                action_args['body'] = None
            else:
                content_type = request.get_content_type()
                body_deserializer = self.get_body_deserializer(content_type)

                try:
                    body = body_deserializer.deserialize(request.body, action)
                    action_args['body'] = body
                except exception.InvalidContentType:
                    action_args['body'] = None

        accept = self.get_expected_content_type(request)

        return (action, action_args, accept)

    def get_body_deserializer(self, content_type):
        try:
            return self._body_deserializers[content_type]
        except (KeyError, TypeError):
            raise exception.InvalidContentType(content_type=content_type)

    def get_expected_content_type(self, request):
        return request.best_match_content_type()

    def get_action_args(self, request_environment):
        """Parse dictionary created by routes library."""
        try:
            args = request_environment['wsgiorg.routing_args'][1].copy()
        except Exception:
            return {}

        try:
            del args['controller']
        except KeyError:
            pass

        try:
            del args['format']
        except KeyError:
            pass

        return args


class BodySerializer(object):
    """Custom response body serialization based on controller action name."""

    def serialize(self, data, action='default'):
        """Find local serialization method and encode response body."""
        action_method = getattr(self, action, self.default)
        return action_method(data)

    def default(self, data):
        """Default serialization code should live here"""
        raise NotImplementedError()


class JSONBodySerializer(BodySerializer):

    def default(self, data):
        def sanitizer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            return obj

        return json.dumps(data, default=sanitizer)


class ResponseSerializer(object):
    """Encode the necessary pieces into a response object"""

    def __init__(self, body_serializers=None):
        """
        :param serializers: dictionary of content-type-specific serializers

        """
        self._body_serializers = {
            'application/json': JSONBodySerializer(),
        }
        self._body_serializers.update(body_serializers or {})

    def serialize(self, response_data, content_type):
        """Serialize a dict into a string and wrap in a wsgi.Request object.

        :param response_data: dict produced by the Controller
        :param content_type: expected mimetype of serialized response body

        """
        response = webob.Response()
        response.headers['Content-Type'] = content_type

        body_serializer = self.get_body_serializer(content_type)
        response.body = body_serializer.serialize(response_data)

        return response

    def get_body_serializer(self, content_type):
        try:
            return self._body_serializers[content_type]
        except (KeyError, TypeError):
            raise exception.InvalidContentType(content_type=content_type)


class Resource():
    """WSGI app that handles (de)serialization and controller dispatch.

    WSGI app that reads routing information supplied by RoutesMiddleware
    and calls the requested action method upon its controller.  All
    controller action methods must accept a 'req' argument, which is the
    incoming wsgi.Request. If the operation is a PUT or POST, the controller
    method must also accept a 'body' argument (the deserialized request body).
    They may raise a webob.exc exception or return a dict, which will be
    serialized by requested content type.

    """
    def __init__(self, controller, serializers=None, deserializers=None):
        """
        :param controller: object that implement methods created by routes lib
        :param serializers: dict of content-type specific text serializers
        :param deserializers: dict of content-type specific text deserializers

        """
        self.controller = controller
        self.serializer = ResponseSerializer(serializers)
        self.deserializer = RequestDeserializer(deserializers)

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, request):
        """WSGI method that controls (de)serialization and method dispatch."""

        try:
            action, action_args, accept = self.deserializer.deserialize(
                                                                      request)
        except exception.InvalidContentType:
            return webob.exc.HTTPBadRequest("Unsupported Content-Type")

        action_result = self.dispatch(request, action, action_args)

        #TODO(bcwaldon): find a more elegant way to pass through non-dict types
        if type(action_result) is dict:
            response = self.serializer.serialize(action_result, accept)
        else:
            response = action_result

        return response

    def dispatch(self, request, action, action_args):
        """Find action-spefic method on controller and call it."""

        controller_method = getattr(self.controller, action)
        return controller_method(req=request, **action_args)
