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
Utility methods for working with WSGI servers
"""
from __future__ import print_function

import errno
import functools
import os
import signal
import sys
import time

from eventlet.green import socket
from eventlet.green import ssl
import eventlet.greenio
import eventlet.wsgi
import glance_store
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
from oslo_utils import strutils
from osprofiler import opts as profiler_opts
import routes.middleware
import six
import webob.dec
import webob.exc
from webob import multidict

from glance.common import config
from glance.common import exception
from glance.common import utils
from glance import i18n
from glance.i18n import _, _LE, _LI, _LW


bind_opts = [
    cfg.HostAddressOpt('bind_host',
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

    cfg.StrOpt('ca_file',
               sample_default='/etc/ssl/cafile',
               help=_("""
Absolute path to the CA file.

Provide a string value representing a valid absolute path to
the Certificate Authority file to use for client authentication.

A CA file typically contains necessary trusted certificates to
use for the client authentication. This is essential to ensure
that a secure connection is established to the server via the
internet.

Possible values:
    * Valid absolute path to the CA file

Related options:
    * None

""")),

    cfg.StrOpt('cert_file',
               sample_default='/etc/ssl/certs',
               help=_("""
Absolute path to the certificate file.

Provide a string value representing a valid absolute path to the
certificate file which is required to start the API service
securely.

A certificate file typically is a public key container and includes
the server's public key, server name, server information and the
signature which was a result of the verification process using the
CA certificate. This is required for a secure connection
establishment.

Possible values:
    * Valid absolute path to the certificate file

Related options:
    * None

""")),

    cfg.StrOpt('key_file',
               sample_default='/etc/ssl/key/key-file.pem',
               help=_("""
Absolute path to a private key file.

Provide a string value representing a valid absolute path to a
private key file which is required to establish the client-server
connection.

Possible values:
    * Absolute path to the private key file

Related options:
    * None

""")),
]

eventlet_opts = [
    cfg.IntOpt('workers',
               min=0,
               help=_("""
Number of Glance worker processes to start.

Provide a non-negative integer value to set the number of child
process workers to service requests. By default, the number of CPUs
available is set as the value for ``workers``.

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

wsgi_opts = [
    cfg.StrOpt('secure_proxy_ssl_header',
               deprecated_for_removal=True,
               deprecated_reason=_('Use the http_proxy_to_wsgi middleware '
                                   'instead.'),
               help=_('The HTTP header used to determine the scheme for the '
                      'original request, even if it was removed by an SSL '
                      'terminating proxy. Typical value is '
                      '"HTTP_X_FORWARDED_PROTO".')),
]


LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.register_opts(bind_opts)
CONF.register_opts(socket_opts)
CONF.register_opts(eventlet_opts)
CONF.register_opts(wsgi_opts)
profiler_opts.set_defaults(CONF)

ASYNC_EVENTLET_THREAD_POOL_LIST = []


def get_num_workers():
    """Return the configured number of workers."""
    if CONF.workers is None:
        # None implies the number of CPUs
        return processutils.get_worker_count()
    return CONF.workers


def get_bind_addr(default_port=None):
    """Return the host and port to bind to."""
    return (CONF.bind_host, CONF.bind_port or default_port)


def ssl_wrap_socket(sock):
    """
    Wrap an existing socket in SSL

    :param sock: non-SSL socket to wrap

    :returns: An SSL wrapped socket
    """
    utils.validate_key_cert(CONF.key_file, CONF.cert_file)

    ssl_kwargs = {
        'server_side': True,
        'certfile': CONF.cert_file,
        'keyfile': CONF.key_file,
        'cert_reqs': ssl.CERT_NONE,
    }

    if CONF.ca_file:
        ssl_kwargs['ca_certs'] = CONF.ca_file
        ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED

    return ssl.wrap_socket(sock, **ssl_kwargs)


def get_socket(default_port):
    """
    Bind socket to bind ip:port in conf

    note: Mostly comes from Swift with a few small changes...

    :param default_port: port to bind to if none is specified in conf

    :returns: a socket object as returned from socket.listen or
               ssl.wrap_socket if conf specifies cert_file
    """
    bind_addr = get_bind_addr(default_port)

    # TODO(jaypipes): eventlet's greened socket module does not actually
    # support IPv6 in getaddrinfo(). We need to get around this in the
    # future or monitor upstream for a fix
    address_family = [
        addr[0] for addr in socket.getaddrinfo(bind_addr[0],
                                               bind_addr[1],
                                               socket.AF_UNSPEC,
                                               socket.SOCK_STREAM)
        if addr[0] in (socket.AF_INET, socket.AF_INET6)
    ][0]

    use_ssl = CONF.key_file or CONF.cert_file
    if use_ssl and (not CONF.key_file or not CONF.cert_file):
        raise RuntimeError(_("When running server in SSL mode, you must "
                             "specify both a cert_file and key_file "
                             "option value in your configuration file"))

    sock = utils.get_test_suite_socket()
    retry_until = time.time() + 30

    while not sock and time.time() < retry_until:
        try:
            sock = eventlet.listen(bind_addr,
                                   backlog=CONF.backlog,
                                   family=address_family)
        except socket.error as err:
            if err.args[0] != errno.EADDRINUSE:
                raise
            eventlet.sleep(0.1)
    if not sock:
        raise RuntimeError(_("Could not bind to %(host)s:%(port)s after"
                             " trying for 30 seconds") %
                           {'host': bind_addr[0],
                            'port': bind_addr[1]})

    return sock


def set_eventlet_hub():
    try:
        eventlet.hubs.use_hub('poll')
    except Exception:
        try:
            eventlet.hubs.use_hub('selects')
        except Exception:
            msg = _("eventlet 'poll' nor 'selects' hubs are available "
                    "on this platform")
            raise exception.WorkerCreationFailure(
                reason=msg)


def initialize_glance_store():
    """Initialize glance store."""
    glance_store.register_opts(CONF)
    glance_store.create_stores(CONF)
    glance_store.verify_default_store()


def get_asynchronous_eventlet_pool(size=1000):
    """Return eventlet pool to caller.

    Also store pools created in global list, to wait on
    it after getting signal for graceful shutdown.

    :param size: eventlet pool size
    :returns: eventlet pool
    """
    global ASYNC_EVENTLET_THREAD_POOL_LIST

    pool = eventlet.GreenPool(size=size)
    # Add pool to global ASYNC_EVENTLET_THREAD_POOL_LIST
    ASYNC_EVENTLET_THREAD_POOL_LIST.append(pool)

    return pool


class Server(object):
    """Server class to manage multiple WSGI sockets and applications.

    This class requires initialize_glance_store set to True if
    glance store needs to be initialized.
    """
    def __init__(self, threads=1000, initialize_glance_store=False):
        os.umask(0o27)  # ensure files are created with the correct privileges
        self._logger = logging.getLogger("eventlet.wsgi.server")
        self.threads = threads
        self.children = set()
        self.stale_children = set()
        self.running = True
        # NOTE(abhishek): Allows us to only re-initialize glance_store when
        # the API's configuration reloads.
        self.initialize_glance_store = initialize_glance_store
        self.pgid = os.getpid()
        try:
            # NOTE(flaper87): Make sure this process
            # runs in its own process group.
            os.setpgid(self.pgid, self.pgid)
        except OSError:
            # NOTE(flaper87): When running glance-control,
            # (glance's functional tests, for example)
            # setpgid fails with EPERM as glance-control
            # creates a fresh session, of which the newly
            # launched service becomes the leader (session
            # leaders may not change process groups)
            #
            # Running glance-(api|registry) is safe and
            # shouldn't raise any error here.
            self.pgid = 0

    def hup(self, *args):
        """
        Reloads configuration files with zero down time
        """
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        raise exception.SIGHUPInterrupt

    def kill_children(self, *args):
        """Kills the entire process group."""
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        self.running = False
        os.killpg(self.pgid, signal.SIGTERM)

    def start(self, application, default_port):
        """
        Run a WSGI server with the given application.

        :param application: The application to be run in the WSGI server
        :param default_port: Port to bind to if none is specified in conf
        """
        self.application = application
        self.default_port = default_port
        self.configure()
        self.start_wsgi()

    def start_wsgi(self):
        workers = get_num_workers()
        if workers == 0:
            # Useful for profiling, test, debug etc.
            self.pool = self.create_pool()
            self.pool.spawn_n(self._single_run, self.application, self.sock)
            return
        else:
            LOG.info(_LI("Starting %d workers"), workers)
            signal.signal(signal.SIGTERM, self.kill_children)
            signal.signal(signal.SIGINT, self.kill_children)
            signal.signal(signal.SIGHUP, self.hup)
            while len(self.children) < workers:
                self.run_child()

    def create_pool(self):
        return get_asynchronous_eventlet_pool(size=self.threads)

    def _remove_children(self, pid):
        if pid in self.children:
            self.children.remove(pid)
            LOG.info(_LI('Removed dead child %s'), pid)
        elif pid in self.stale_children:
            self.stale_children.remove(pid)
            LOG.info(_LI('Removed stale child %s'), pid)
        else:
            LOG.warn(_LW('Unrecognised child %s') % pid)

    def _verify_and_respawn_children(self, pid, status):
        if len(self.stale_children) == 0:
            LOG.debug('No stale children')
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) != 0:
            LOG.error(_LE('Not respawning child %d, cannot '
                          'recover from termination') % pid)
            if not self.children and not self.stale_children:
                LOG.info(
                    _LI('All workers have terminated. Exiting'))
                self.running = False
        else:
            if len(self.children) < get_num_workers():
                self.run_child()

    def wait_on_children(self):
        while self.running:
            try:
                pid, status = os.wait()
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    self._remove_children(pid)
                    self._verify_and_respawn_children(pid, status)
            except OSError as err:
                if err.errno not in (errno.EINTR, errno.ECHILD):
                    raise
            except KeyboardInterrupt:
                LOG.info(_LI('Caught keyboard interrupt. Exiting.'))
                break
            except exception.SIGHUPInterrupt:
                self.reload()
                continue
        eventlet.greenio.shutdown_safe(self.sock)
        self.sock.close()
        LOG.debug('Exited')

    def configure(self, old_conf=None, has_changed=None):
        """
        Apply configuration settings

        :param old_conf: Cached old configuration settings (if any)
        :param has changed: callable to determine if a parameter has changed
        """
        eventlet.wsgi.MAX_HEADER_LINE = CONF.max_header_line
        self.client_socket_timeout = CONF.client_socket_timeout or None
        self.configure_socket(old_conf, has_changed)
        if self.initialize_glance_store:
            initialize_glance_store()

    def reload(self):
        """
        Reload and re-apply configuration settings

        Existing child processes are sent a SIGHUP signal
        and will exit after completing existing requests.
        New child processes, which will have the updated
        configuration, are spawned. This allows preventing
        interruption to the service.
        """
        def _has_changed(old, new, param):
            old = old.get(param)
            new = getattr(new, param)
            return (new != old)

        old_conf = utils.stash_conf_values()
        has_changed = functools.partial(_has_changed, old_conf, CONF)
        CONF.reload_config_files()
        os.killpg(self.pgid, signal.SIGHUP)
        self.stale_children = self.children
        self.children = set()

        # Ensure any logging config changes are picked up
        logging.setup(CONF, 'glance')
        config.set_config_defaults()

        self.configure(old_conf, has_changed)
        self.start_wsgi()

    def wait(self):
        """Wait until all servers have completed running."""
        try:
            if self.children:
                self.wait_on_children()
            else:
                self.pool.waitall()
        except KeyboardInterrupt:
            pass

    def run_child(self):
        def child_hup(*args):
            """Shuts down child processes, existing requests are handled."""
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            eventlet.wsgi.is_accepting = False
            self.sock.close()

        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGHUP, child_hup)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            # ignore the interrupt signal to avoid a race whereby
            # a child worker receives the signal before the parent
            # and is respawned unnecessarily as a result
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            # The child has no need to stash the unwrapped
            # socket, and the reference prevents a clean
            # exit on sighup
            self._sock = None
            self.run_server()
            LOG.info(_LI('Child %d exiting normally'), os.getpid())
            # self.pool.waitall() is now called in wsgi's server so
            # it's safe to exit here
            sys.exit(0)
        else:
            LOG.info(_LI('Started child %s'), pid)
            self.children.add(pid)

    def run_server(self):
        """Run a WSGI server."""
        if cfg.CONF.pydev_worker_debug_host:
            utils.setup_remote_pydev_debug(cfg.CONF.pydev_worker_debug_host,
                                           cfg.CONF.pydev_worker_debug_port)

        eventlet.wsgi.HttpProtocol.default_request_version = "HTTP/1.0"
        self.pool = self.create_pool()
        try:
            eventlet.wsgi.server(self.sock,
                                 self.application,
                                 log=self._logger,
                                 custom_pool=self.pool,
                                 debug=False,
                                 keepalive=CONF.http_keepalive,
                                 socket_timeout=self.client_socket_timeout)
        except socket.error as err:
            if err[0] != errno.EINVAL:
                raise

        # waiting on async pools
        if ASYNC_EVENTLET_THREAD_POOL_LIST:
            for pool in ASYNC_EVENTLET_THREAD_POOL_LIST:
                pool.waitall()

    def _single_run(self, application, sock):
        """Start a WSGI server in a new green thread."""
        LOG.info(_LI("Starting single process server"))
        eventlet.wsgi.server(sock, application, custom_pool=self.pool,
                             log=self._logger,
                             debug=False,
                             keepalive=CONF.http_keepalive,
                             socket_timeout=self.client_socket_timeout)

    def configure_socket(self, old_conf=None, has_changed=None):
        """
        Ensure a socket exists and is appropriately configured.

        This function is called on start up, and can also be
        called in the event of a configuration reload.

        When called for the first time a new socket is created.
        If reloading and either bind_host or bind port have been
        changed the existing socket must be closed and a new
        socket opened (laws of physics).

        In all other cases (bind_host/bind_port have not changed)
        the existing socket is reused.

        :param old_conf: Cached old configuration settings (if any)
        :param has changed: callable to determine if a parameter has changed
        """
        # Do we need a fresh socket?
        new_sock = (old_conf is None or (
                    has_changed('bind_host') or
                    has_changed('bind_port')))
        # Will we be using https?
        use_ssl = not (not CONF.cert_file or not CONF.key_file)
        # Were we using https before?
        old_use_ssl = (old_conf is not None and not (
                       not old_conf.get('key_file') or
                       not old_conf.get('cert_file')))
        # Do we now need to perform an SSL wrap on the socket?
        wrap_sock = use_ssl is True and (old_use_ssl is False or new_sock)
        # Do we now need to perform an SSL unwrap on the socket?
        unwrap_sock = use_ssl is False and old_use_ssl is True

        if new_sock:
            self._sock = None
            if old_conf is not None:
                self.sock.close()
            _sock = get_socket(self.default_port)
            _sock.setsockopt(socket.SOL_SOCKET,
                             socket.SO_REUSEADDR, 1)
            # sockets can hang around forever without keepalive
            _sock.setsockopt(socket.SOL_SOCKET,
                             socket.SO_KEEPALIVE, 1)
            self._sock = _sock

        if wrap_sock:
            self.sock = ssl_wrap_socket(self._sock)

        if unwrap_sock:
            self.sock = self._sock

        if new_sock and not use_ssl:
            self.sock = self._sock

        # Pick up newly deployed certs
        if old_conf is not None and use_ssl is True and old_use_ssl is True:
            if has_changed('cert_file') or has_changed('key_file'):
                utils.validate_key_cert(CONF.key_file, CONF.cert_file)
            if has_changed('cert_file'):
                self.sock.certfile = CONF.cert_file
            if has_changed('key_file'):
                self.sock.keyfile = CONF.key_file

        if new_sock or (old_conf is not None and has_changed('tcp_keepidle')):
            # This option isn't available in the OS X version of eventlet
            if hasattr(socket, 'TCP_KEEPIDLE'):
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE,
                                     CONF.tcp_keepidle)

        if old_conf is not None and has_changed('backlog'):
            self.sock.listen(CONF.backlog)


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
        for (key, value) in six.iteritems(resp.headers):
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
        if url is "":
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


class Request(webob.Request):
    """Add some OpenStack API-specific logic to the base webob.Request."""

    def __init__(self, environ, *args, **kwargs):
        if CONF.secure_proxy_ssl_header:
            scheme = environ.get(CONF.secure_proxy_ssl_header)
            if scheme:
                environ['wsgi.url_scheme'] = scheme
        super(Request, self).__init__(environ, *args, **kwargs)

    @property
    def params(self):
        """Override params property of webob.request.BaseRequest.

        Added an 'encoded_params' attribute in case of PY2 to avoid
        encoding values in next subsequent calls to the params property.
        """
        if six.PY2:
            encoded_params = getattr(self, 'encoded_params', None)
            if encoded_params is None:
                params = super(Request, self).params
                params_dict = multidict.MultiDict()
                for key, value in params.items():
                    params_dict.add(key, encodeutils.safe_encode(value))

                setattr(self, 'encoded_params',
                        multidict.NestedMultiDict(params_dict))
            return self.encoded_params
        return super(Request, self).params

    def best_match_content_type(self):
        """Determine the requested response content-type."""
        supported = ('application/json',)
        bm = self.accept.best_match(supported)
        return bm or 'application/json'

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
        return self.accept_language.best_match(langs)

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
            exc_info = sys.exc_info()
            e = translate_exception(request, e)
            six.reraise(type(e), e, exc_info[2])
        except UnicodeDecodeError:
            msg = _("Error decoding your request. Either the URL or the "
                    "request body contained characters that could not be "
                    "decoded by Glance")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except Exception as e:
            LOG.exception(_LE("Caught error: %s"),
                          encodeutils.exception_to_unicode(e))
            response = webob.exc.HTTPInternalServerError()
            return response

        try:
            response = webob.Response(request=request)
            self.dispatch(self.serializer, action, response, action_result)
            # encode all headers in response to utf-8 to prevent unicode errors
            for name, value in list(response.headers.items()):
                if six.PY2 and isinstance(value, six.text_type):
                    response.headers[name] = encodeutils.safe_encode(value)
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
