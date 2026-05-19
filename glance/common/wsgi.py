# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010 OpenStack Foundation
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

"""
Utility methods for working with WSGI applications
"""

import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
from oslo_utils import strutils
from oslo_utils import units
from osprofiler import opts as profiler_opts
import routes.middleware
import webob.dec
import webob.exc
from webob import multidict

from glance.common import exception
from glance import i18n
from glance.i18n import _, _LE

EVENTLET_DEPRECATION_REASON = """
Eventlet has been deprecated in the Gazpacho release. Glance is now expected to
be run using WSGI. The eventlet implementation will be removed in either the H
release or the I release.
"""


bind_opts = [
    cfg.HostAddressOpt('bind_host',
                       deprecated_reason=EVENTLET_DEPRECATION_REASON,
                       deprecated_since='Gazpacho',
                       default='0.0.0.0',
                       help=_("""
IP address to bind the glance servers to.

Provide an IP address to bind the glance server to. The default
value is ``0.0.0.0``.

Edit this option to enable the server to listen on one particular
IP address on the network card. This facilitates selection of a
particular network interface for the server.

Possible values:
    * A valid IPv4 address
    * A valid IPv6 address

Related options:
    * None

""")),

    cfg.PortOpt('bind_port',
                deprecated_reason=EVENTLET_DEPRECATION_REASON,
                deprecated_since='Gazpacho',
                help=_("""
Port number on which the server will listen.

Provide a valid port number to bind the server's socket to. This
port is then set to identify processes and forward network messages
that arrive at the server. The default bind_port value for the API
server is 9292 and for the registry server is 9191.

Possible values:
    * A valid port number (0 to 65535)

Related options:
    * None

""")),
]

socket_opts = [
    cfg.IntOpt('backlog',
               deprecated_reason=EVENTLET_DEPRECATION_REASON,
               deprecated_since='Gazpacho',
               default=4096,
               min=1,
               help=_("""
Set the number of incoming connection requests.

Provide a positive integer value to limit the number of requests in
the backlog queue. The default queue size is 4096.

An incoming connection to a TCP listener socket is queued before a
connection can be established with the server. Setting the backlog
for a TCP socket ensures a limited queue size for incoming traffic.

Possible values:
    * Positive integer

Related options:
    * None

""")),

    cfg.IntOpt('tcp_keepidle',
               deprecated_reason=EVENTLET_DEPRECATION_REASON,
               deprecated_since='Gazpacho',
               default=600,
               min=1,
               help=_("""
Set the wait time before a connection recheck.

Provide a positive integer value representing time in seconds which
is set as the idle wait time before a TCP keep alive packet can be
sent to the host. The default value is 600 seconds.

Setting ``tcp_keepidle`` helps verify at regular intervals that a
connection is intact and prevents frequent TCP connection
reestablishment.

Possible values:
    * Positive integer value representing time in seconds

Related options:
    * None

""")),
]


eventlet_opts = [
    cfg.IntOpt('workers',
               deprecated_reason=EVENTLET_DEPRECATION_REASON,
               deprecated_since='Gazpacho',
               min=0,
               help=_("""
Number of Glance worker processes to start.

Provide a non-negative integer value to set the number of child
process workers to service requests. By default, the number of CPUs
available is set as the value for ``workers`` limited to 8. For
example if the processor count is 6, 6 workers will be used, if the
processor count is 24 only 8 workers will be used. The limit will only
apply to the default value, if 24 workers is configured, 24 is used.

Each worker process is made to listen on the port set in the
configuration file and contains a greenthread pool of size 1000.

NOTE: Setting the number of workers to zero, triggers the creation
of a single API process with a greenthread pool of size 1000.

Possible values:
    * 0
    * Positive integer value (typically equal to the number of CPUs)

Related options:
    * None

""")),

    cfg.IntOpt('max_header_line',
               deprecated_reason=EVENTLET_DEPRECATION_REASON,
               deprecated_since='Gazpacho',
               default=16384,
               min=0,
               help=_("""
Maximum line size of message headers.

Provide an integer value representing a length to limit the size of
message headers. The default value is 16384.

NOTE: ``max_header_line`` may need to be increased when using large
tokens (typically those generated by the Keystone v3 API with big
service catalogs). However, it is to be kept in mind that larger
values for ``max_header_line`` would flood the logs.

Setting ``max_header_line`` to 0 sets no limit for the line size of
message headers.

Possible values:
    * 0
    * Positive integer

Related options:
    * None

""")),

    cfg.BoolOpt('http_keepalive',
                deprecated_reason=EVENTLET_DEPRECATION_REASON,
                deprecated_since='Gazpacho',
                default=True,
                help=_("""
Set keep alive option for HTTP over TCP.

Provide a boolean value to determine sending of keep alive packets.
If set to ``False``, the server returns the header
"Connection: close". If set to ``True``, the server returns a
"Connection: Keep-Alive" in its responses. This enables retention of
the same TCP connection for HTTP conversations instead of opening a
new one with each new request.

This option must be set to ``False`` if the client socket connection
needs to be closed explicitly after the response is received and
read successfully by the client.

Possible values:
    * True
    * False

Related options:
    * None

""")),

    cfg.IntOpt('client_socket_timeout',
               deprecated_reason=EVENTLET_DEPRECATION_REASON,
               deprecated_since='Gazpacho',
               default=900,
               min=0,
               help=_("""
Timeout for client connections' socket operations.

Provide a valid integer value representing time in seconds to set
the period of wait before an incoming connection can be closed. The
default value is 900 seconds.

The value zero implies wait forever.

Possible values:
    * Zero
    * Positive integer

Related options:
    * None

""")),
]

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.register_opts(bind_opts)
CONF.register_opts(socket_opts)
CONF.register_opts(eventlet_opts)
profiler_opts.set_defaults(CONF)


def _get_uwsgi():
    try:
        import uwsgi
    except ImportError:
        return None
    return uwsgi


class Middleware(object):
    """
    Base WSGI middleware wrapper. These classes require an application to be
    initialized that will be called next.  By default the middleware will
    simply call its wrapped app, or you can override __call__ to customize its
    behavior.
    """

    def __init__(self, application):
        self.application = application

    @classmethod
    def factory(cls, global_conf, **local_conf):
        def filter(app):
            return cls(app)
        return filter

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
        response.request = req
        try:
            return self.process_response(response)
        except webob.exc.HTTPException as e:
            return e


class Debug(Middleware):
    """
    Helper class that can be inserted into any WSGI application chain
    to get information about the request and response.
    """

    @webob.dec.wsgify
    def __call__(self, req):
        print(("*" * 40) + " REQUEST ENVIRON")
        for key, value in req.environ.items():
            print(key, "=", value)
        print('')
        resp = req.get_response(self.application)

        print(("*" * 40) + " RESPONSE HEADERS")
        for key, value in resp.headers.items():
            print(key, "=", value)
        print('')

        resp.app_iter = self.print_generator(resp.app_iter)

        return resp

    @staticmethod
    def print_generator(app_iter):
        """
        Iterator that prints the contents of a wrapper string iterator
        when iterated.
        """
        print(("*" * 40) + " BODY")
        for part in app_iter:
            sys.stdout.write(part)
            sys.stdout.flush()
            yield part
        print()


class APIMapper(routes.Mapper):
    """
    Handle route matching when url is '' because routes.Mapper returns
    an error in this case.
    """

    def routematch(self, url=None, environ=None):
        if url == "":
            result = self._match("", environ)
            return result[0], result[1]
        return routes.Mapper.routematch(self, url, environ)


class RejectMethodController(object):
    def reject(self, req, allowed_methods, *args, **kwargs):
        LOG.debug("The method %s is not allowed for this resource",
                  req.environ['REQUEST_METHOD'])
        raise webob.exc.HTTPMethodNotAllowed(
            headers=[('Allow', allowed_methods)])


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
        mapper.redirect("", "/")
        self.map = mapper
        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          self.map)

    @classmethod
    def factory(cls, global_conf, **local_conf):
        return cls(APIMapper())

    @webob.dec.wsgify
    def __call__(self, req):
        """
        Route the incoming request to a controller based on self.map.
        If no match, return either a 404(Not Found) or 501(Not Implemented).
        """
        return self._router

    @staticmethod
    @webob.dec.wsgify
    def _dispatch(req):
        """
        Called by self._router after matching the incoming request to a route
        and putting the information into req.environ.  Either returns 404,
        501, or the routed WSGI app's response.
        """
        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            implemented_http_methods = ['GET', 'HEAD', 'POST', 'PUT',
                                        'DELETE', 'PATCH']
            if req.environ['REQUEST_METHOD'] not in implemented_http_methods:
                return webob.exc.HTTPNotImplemented()
            else:
                return webob.exc.HTTPNotFound()
        app = match['controller']
        return app


class _UWSGIChunkFile(object):
    """
    A file-like object for reading uWSGI chunked requests, with internal
    buffering/caching of excess data for subsequent reads.
    """

    def __init__(self):
        # Buffer to cache data read in excess of the requested length
        self._buffer = b""

    def read(self, length=None):
        """
        Reads up to 'length' bytes from the chunked request stream.
        Caches any excess data internally.
        """
        if length == 0:
            return b""

        # If length is negative, treat it as reading until the end of the file.
        if length and length < 0:
            length = None

        # If no length is provided, choose some sane minimum default
        length = length if length is not None else 1 * units.Mi

        uwsgi_mod = _get_uwsgi()
        while len(self._buffer) < length:
            data = uwsgi_mod.chunked_read()
            if not data:
                break
            # append the buffer
            self._buffer += data

        chunk = self._buffer[:length]
        self._buffer = self._buffer[length:]
        return chunk


class Request(webob.Request):
    """Add some OpenStack API-specific logic to the base webob.Request."""

    def __init__(self, environ, *args, **kwargs):
        super(Request, self).__init__(environ, *args, **kwargs)

    @property
    def body_file(self):
        if _get_uwsgi():
            if self.headers.get('transfer-encoding', '').lower() == 'chunked':
                return _UWSGIChunkFile()
        return super(Request, self).body_file

    @body_file.setter
    def body_file(self, value):
        # NOTE(cdent): If you have a property setter in a superclass, it will
        # not be inherited.
        webob.Request.body_file.fset(self, value)

    def best_match_content_type(self):
        """Determine the requested response content-type."""
        supported = ('application/json',)
        best_matches = self.accept.acceptable_offers(supported)
        if not best_matches:
            return 'application/json'
        return best_matches[0][0]

    def get_content_type(self, allowed_content_types):
        """Determine content type of the request body."""
        if "Content-Type" not in self.headers:
            raise exception.InvalidContentType(content_type=None)

        content_type = self.content_type

        if content_type not in allowed_content_types:
            raise exception.InvalidContentType(content_type=content_type)
        else:
            return content_type

    def best_match_language(self):
        """Determines best available locale from the Accept-Language header.

        :returns: the best language match or None if the 'Accept-Language'
                  header was not available in the request.
        """
        if not self.accept_language:
            return None
        langs = i18n.get_available_languages('glance')
        # NOTE(rosmaita): give the webob lookup() function a sentinel value
        # for default so we can preserve the behavior of this function as
        # indicated by the current unit tests.  See Launchpad bug #1765748.
        best_match = self.accept_language.lookup(langs, default='fake_LANG')
        if best_match == 'fake_LANG':
            best_match = None
        return best_match

    def get_range_from_request(self, image_size):
        """Return the `Range` in a request."""

        range_str = self.headers.get('Range')
        if range_str is not None:

            # NOTE(dharinic): We do not support multi range requests.
            if ',' in range_str:
                msg = ("Requests with multiple ranges are not supported in "
                       "Glance. You may make multiple single-range requests "
                       "instead.")
                raise webob.exc.HTTPBadRequest(explanation=msg)

            range_ = webob.byterange.Range.parse(range_str)
            if range_ is None:
                msg = ("Invalid Range header.")
                raise webob.exc.HTTPRequestRangeNotSatisfiable(msg)
            # NOTE(dharinic): Ensure that a range like bytes=4- for an image
            # size of 3 is invalidated as per rfc7233.
            if range_.start >= image_size:
                msg = ("Invalid start position in Range header. "
                       "Start position MUST be in the inclusive range [0, %s]."
                       % (image_size - 1))
                raise webob.exc.HTTPRequestRangeNotSatisfiable(msg)
            return range_

        # NOTE(dharinic): For backward compatibility reasons, we maintain
        # support for 'Content-Range' in requests even though it's not
        # correct to use it in requests..
        c_range_str = self.headers.get('Content-Range')
        if c_range_str is not None:
            content_range = webob.byterange.ContentRange.parse(c_range_str)
            # NOTE(dharinic): Ensure that a content range like 1-4/* for an
            # image size of 3 is invalidated.
            if content_range is None:
                msg = ("Invalid Content-Range header.")
                raise webob.exc.HTTPRequestRangeNotSatisfiable(msg)
            if (content_range.length is None and
                    content_range.stop > image_size):
                msg = ("Invalid stop position in Content-Range header. "
                       "The stop position MUST be in the inclusive range "
                       "[0, %s]." % (image_size - 1))
                raise webob.exc.HTTPRequestRangeNotSatisfiable(msg)
            if content_range.start >= image_size:
                msg = ("Invalid start position in Content-Range header. "
                       "Start position MUST be in the inclusive range [0, %s]."
                       % (image_size - 1))
                raise webob.exc.HTTPRequestRangeNotSatisfiable(msg)
            return content_range


class JSONRequestDeserializer(object):
    valid_transfer_encoding = frozenset(['chunked', 'compress', 'deflate',
                                         'gzip', 'identity'])
    httpverb_may_have_body = frozenset({'POST', 'PUT', 'PATCH'})

    @classmethod
    def is_valid_encoding(cls, request):
        request_encoding = request.headers.get('transfer-encoding', '').lower()
        return request_encoding in cls.valid_transfer_encoding

    @classmethod
    def is_valid_method(cls, request):
        return request.method.upper() in cls.httpverb_may_have_body

    def has_body(self, request):
        """
        Returns whether a Webob.Request object will possess an entity body.

        :param request:  Webob.Request object
        """

        if self.is_valid_encoding(request) and self.is_valid_method(request):
            request.is_body_readable = True
            return True

        if request.content_length is not None and request.content_length > 0:
            return True

        return False

    @staticmethod
    def _sanitizer(obj):
        """Sanitizer method that will be passed to jsonutils.loads."""
        return obj

    def from_json(self, datastring):
        try:
            jsondata = jsonutils.loads(datastring, object_hook=self._sanitizer)
            if not isinstance(jsondata, (dict, list)):
                msg = _('Unexpected body type. Expected list/dict.')
                raise webob.exc.HTTPBadRequest(explanation=msg)
            return jsondata
        except ValueError:
            msg = _('Malformed JSON in request body.')
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def default(self, request):
        if self.has_body(request):
            return {'body': self.from_json(request.body)}
        else:
            return {}


class JSONResponseSerializer(object):

    def _sanitizer(self, obj):
        """Sanitizer method that will be passed to jsonutils.dumps."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, multidict.MultiDict):
            return obj.mixed()
        return jsonutils.to_primitive(obj)

    def to_json(self, data):
        return jsonutils.dump_as_bytes(data, default=self._sanitizer)

    def default(self, response, result):
        response.content_type = 'application/json'
        body = self.to_json(result)
        body = encodeutils.to_utf8(body)
        response.body = body


def translate_exception(req, e):
    """Translates all translatable elements of the given exception."""

    # The RequestClass attribute in the webob.dec.wsgify decorator
    # does not guarantee that the request object will be a particular
    # type; this check is therefore necessary.
    if not hasattr(req, "best_match_language"):
        return e

    locale = req.best_match_language()

    if isinstance(e, webob.exc.HTTPError):
        e.explanation = i18n.translate(e.explanation, locale)
        e.detail = i18n.translate(e.detail, locale)
        if getattr(e, 'body_template', None):
            e.body_template = i18n.translate(e.body_template, locale)
    return e


class Resource(object):
    """
    WSGI app that handles (de)serialization and controller dispatch.

    Reads routing information supplied by RoutesMiddleware and calls
    the requested action method upon its deserializer, controller,
    and serializer. Those three objects may implement any of the basic
    controller action methods (create, update, show, index, delete)
    along with any that may be specified in the api router. A 'default'
    method may also be implemented to be used in place of any
    non-implemented actions. Deserializer methods must accept a request
    argument and return a dictionary. Controller methods must accept a
    request argument. Additionally, they must also accept keyword
    arguments that represent the keys returned by the Deserializer. They
    may raise a webob.exc exception or return a dict, which will be
    serialized by requested content type.
    """

    def __init__(self, controller, deserializer=None, serializer=None):
        """
        :param controller: object that implement methods created by routes lib
        :param deserializer: object that supports webob request deserialization
                             through controller-like actions
        :param serializer: object that supports webob response serialization
                           through controller-like actions
        """
        self.controller = controller
        self.serializer = serializer or JSONResponseSerializer()
        self.deserializer = deserializer or JSONRequestDeserializer()

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, request):
        """WSGI method that controls (de)serialization and method dispatch."""
        action_args = self.get_action_args(request.environ)
        action = action_args.pop('action', None)
        body_reject = strutils.bool_from_string(
            action_args.pop('body_reject', None))

        try:
            if body_reject and self.deserializer.has_body(request):
                msg = _('A body is not expected with this request.')
                raise webob.exc.HTTPBadRequest(explanation=msg)
            deserialized_request = self.dispatch(self.deserializer,
                                                 action, request)
            action_args.update(deserialized_request)
            action_result = self.dispatch(self.controller, action,
                                          request, **action_args)
        except webob.exc.WSGIHTTPException as e:
            e = translate_exception(request, e)
            raise e.with_traceback(sys.exc_info()[2])
        except UnicodeDecodeError:
            msg = _("Error decoding your request. Either the URL or the "
                    "request body contained characters that could not be "
                    "decoded by Glance")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.InvalidPropertyProtectionConfiguration as e:
            LOG.exception(_LE("Caught error: %s"), e)
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except Exception as e:
            LOG.exception(_LE("Caught error: %s"), e)
            response = webob.exc.HTTPInternalServerError()
            return response

        # We cannot serialize an Exception, so return the action_result
        if isinstance(action_result, Exception):
            return action_result

        try:
            response = webob.Response(request=request)
            self.dispatch(self.serializer, action, response, action_result)
            return response
        except webob.exc.WSGIHTTPException as e:
            return translate_exception(request, e)
        except webob.exc.HTTPException as e:
            return e
        # return unserializable result (typically a webob exc)
        except Exception:
            return action_result

    def dispatch(self, obj, action, *args, **kwargs):
        """Find action-specific method on self and call it."""
        try:
            method = getattr(obj, action)
        except AttributeError:
            method = getattr(obj, 'default')

        return method(*args, **kwargs)

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
