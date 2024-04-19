# Copyright 2010-2011 OpenStack Foundation
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

# HTTPSClientAuthConnection code comes courtesy of ActiveState website:
# http://code.activestate.com/recipes/
#   577548-https-httplib-client-connection-with-certificate-v/

import collections.abc
import copy
import functools
import http.client
import os
import re
import urllib.parse as urlparse

try:
    from eventlet.green import socket
    from eventlet.green import ssl
except ImportError:
    import socket
    import ssl

import osprofiler.web

from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import netutils

from glance.common import auth
from glance.common import exception
from glance.common import utils
from glance.i18n import _

LOG = logging.getLogger(__name__)

# common chunk size for get and put
CHUNKSIZE = 65536

VERSION_REGEX = re.compile(r"/?v[0-9\.]+")


def handle_unauthenticated(func):
    """
    Wrap a function to re-authenticate and retry.
    """
    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except exception.NotAuthenticated:
            self._authenticate(force_reauth=True)
            return func(self, *args, **kwargs)
    return wrapped


def handle_redirects(func):
    """
    Wrap the _do_request function to handle HTTP redirects.
    """
    MAX_REDIRECTS = 5

    @functools.wraps(func)
    def wrapped(self, method, url, body, headers):
        for i in range(MAX_REDIRECTS):
            try:
                return func(self, method, url, body, headers)
            except exception.RedirectException as redirect:
                if redirect.url is None:
                    raise exception.InvalidRedirect()
                url = redirect.url
        raise exception.MaxRedirectsExceeded(redirects=MAX_REDIRECTS)
    return wrapped


class HTTPSClientAuthConnection(http.client.HTTPSConnection):
    """
    Class to make a HTTPS connection, with support for
    full client-based SSL Authentication

    :see http://code.activestate.com/recipes/
            577548-https-httplib-client-connection-with-certificate-v/
    """

    def __init__(self, host, port, key_file, cert_file,
                 ca_file, timeout=None, insecure=False):
        http.client.HTTPSConnection.__init__(self, host, port,
                                             key_file=key_file,
                                             cert_file=cert_file)
        self.key_file = key_file
        self.cert_file = cert_file
        self.ca_file = ca_file
        self.timeout = timeout
        self.insecure = insecure

    def connect(self):
        """
        Connect to a host on a given (SSL) port.
        If ca_file is pointing somewhere, use it to check Server Certificate.

        Redefined/copied and extended from httplib.py:1105 (Python 2.6.x).
        This is needed to pass cert_reqs=ssl.CERT_REQUIRED as parameter to
        ssl.wrap_socket(), which forces SSL to check server certificate against
        our client certificate.
        """
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        # Check CA file unless 'insecure' is specified
        if self.insecure is True:
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file,
                                        cert_reqs=ssl.CERT_NONE)
        else:
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file,
                                        ca_certs=self.ca_file,
                                        cert_reqs=ssl.CERT_REQUIRED)


class BaseClient(object):

    """A base client class"""

    DEFAULT_PORT = 80
    DEFAULT_DOC_ROOT = None
    # Standard CA file locations for Debian/Ubuntu, RedHat/Fedora,
    # Suse, FreeBSD/OpenBSD
    DEFAULT_CA_FILE_PATH = ('/etc/ssl/certs/ca-certificates.crt:'
                            '/etc/pki/tls/certs/ca-bundle.crt:'
                            '/etc/ssl/ca-bundle.pem:'
                            '/etc/ssl/cert.pem')

    OK_RESPONSE_CODES = (
        http.client.OK,
        http.client.CREATED,
        http.client.ACCEPTED,
        http.client.NO_CONTENT,
    )

    REDIRECT_RESPONSE_CODES = (
        http.client.MOVED_PERMANENTLY,
        http.client.FOUND,
        http.client.SEE_OTHER,
        http.client.USE_PROXY,
        http.client.TEMPORARY_REDIRECT,
    )

    def __init__(self, host, port=None, timeout=None, use_ssl=False,
                 auth_token=None, creds=None, doc_root=None, key_file=None,
                 cert_file=None, ca_file=None, insecure=False,
                 configure_via_auth=True):
        """
        Creates a new client to some service.

        :param host: The host where service resides
        :param port: The port where service resides
        :param timeout: Connection timeout.
        :param use_ssl: Should we use HTTPS?
        :param auth_token: The auth token to pass to the server
        :param creds: The credentials to pass to the auth plugin
        :param doc_root: Prefix for all URLs we request from host
        :param key_file: Optional PEM-formatted file that contains the private
                         key.
                         If use_ssl is True, and this param is None (the
                         default), then an environ variable
                         GLANCE_CLIENT_KEY_FILE is looked for. If no such
                         environ variable is found, ClientConnectionError
                         will be raised.
        :param cert_file: Optional PEM-formatted certificate chain file.
                          If use_ssl is True, and this param is None (the
                          default), then an environ variable
                          GLANCE_CLIENT_CERT_FILE is looked for. If no such
                          environ variable is found, ClientConnectionError
                          will be raised.
        :param ca_file: Optional CA cert file to use in SSL connections
                        If use_ssl is True, and this param is None (the
                        default), then an environ variable
                        GLANCE_CLIENT_CA_FILE is looked for.
        :param insecure: Optional. If set then the server's certificate
                         will not be verified.
        :param configure_via_auth: Optional. Defaults to True. If set, the
                         URL returned from the service catalog for the image
                         endpoint will **override** the URL supplied to in
                         the host parameter.
        """
        self.host = host
        self.port = port or self.DEFAULT_PORT
        self.timeout = timeout
        # A value of '0' implies never timeout
        if timeout == 0:
            self.timeout = None
        self.use_ssl = use_ssl
        self.auth_token = auth_token
        self.creds = creds or {}
        self.connection = None
        self.configure_via_auth = configure_via_auth
        # doc_root can be a nullstring, which is valid, and why we
        # cannot simply do doc_root or self.DEFAULT_DOC_ROOT below.
        self.doc_root = (doc_root if doc_root is not None
                         else self.DEFAULT_DOC_ROOT)

        self.key_file = key_file
        self.cert_file = cert_file
        self.ca_file = ca_file
        self.insecure = insecure
        self.auth_plugin = self.make_auth_plugin(self.creds, self.insecure)
        self.connect_kwargs = self.get_connect_kwargs()

    def get_connect_kwargs(self):
        # Both secure and insecure connections have a timeout option
        connect_kwargs = {'timeout': self.timeout}

        if self.use_ssl:
            if self.key_file is None:
                self.key_file = os.environ.get('GLANCE_CLIENT_KEY_FILE')
            if self.cert_file is None:
                self.cert_file = os.environ.get('GLANCE_CLIENT_CERT_FILE')
            if self.ca_file is None:
                self.ca_file = os.environ.get('GLANCE_CLIENT_CA_FILE')

            # Check that key_file/cert_file are either both set or both unset
            if self.cert_file is not None and self.key_file is None:
                msg = _("You have selected to use SSL in connecting, "
                        "and you have supplied a cert, "
                        "however you have failed to supply either a "
                        "key_file parameter or set the "
                        "GLANCE_CLIENT_KEY_FILE environ variable")
                raise exception.ClientConnectionError(msg)

            if self.key_file is not None and self.cert_file is None:
                msg = _("You have selected to use SSL in connecting, "
                        "and you have supplied a key, "
                        "however you have failed to supply either a "
                        "cert_file parameter or set the "
                        "GLANCE_CLIENT_CERT_FILE environ variable")
                raise exception.ClientConnectionError(msg)

            if (self.key_file is not None and
                    not os.path.exists(self.key_file)):
                msg = _("The key file you specified %s does not "
                        "exist") % self.key_file
                raise exception.ClientConnectionError(msg)
            connect_kwargs['key_file'] = self.key_file

            if (self.cert_file is not None and
                    not os.path.exists(self.cert_file)):
                msg = _("The cert file you specified %s does not "
                        "exist") % self.cert_file
                raise exception.ClientConnectionError(msg)
            connect_kwargs['cert_file'] = self.cert_file

            if (self.ca_file is not None and
                    not os.path.exists(self.ca_file)):
                msg = _("The CA file you specified %s does not "
                        "exist") % self.ca_file
                raise exception.ClientConnectionError(msg)

            if self.ca_file is None:
                for ca in self.DEFAULT_CA_FILE_PATH.split(":"):
                    if os.path.exists(ca):
                        self.ca_file = ca
                        break

            connect_kwargs['ca_file'] = self.ca_file
            connect_kwargs['insecure'] = self.insecure

        return connect_kwargs

    def configure_from_url(self, url):
        """
        Setups the connection based on the given url.

        The form is::

            <http|https>://<host>:port/doc_root
        """
        LOG.debug("Configuring from URL: %s", url)
        parsed = urlparse.urlparse(url)
        self.use_ssl = parsed.scheme == 'https'
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.doc_root = parsed.path.rstrip('/')

        # We need to ensure a version identifier is appended to the doc_root
        if not VERSION_REGEX.match(self.doc_root):
            if self.DEFAULT_DOC_ROOT:
                doc_root = self.DEFAULT_DOC_ROOT.lstrip('/')
                self.doc_root += '/' + doc_root
                LOG.debug("Appending doc_root %(doc_root)s to URL %(url)s",
                          {'doc_root': doc_root, 'url': url})

        # ensure connection kwargs are re-evaluated after the service catalog
        # publicURL is parsed for potential SSL usage
        self.connect_kwargs = self.get_connect_kwargs()

    def make_auth_plugin(self, creds, insecure):
        """
        Returns an instantiated authentication plugin.
        """
        strategy = creds.get('strategy', 'noauth')
        plugin = auth.get_plugin_from_strategy(strategy, creds, insecure,
                                               self.configure_via_auth)
        return plugin

    def get_connection_type(self):
        """
        Returns the proper connection type
        """
        if self.use_ssl:
            return HTTPSClientAuthConnection
        else:
            return http.client.HTTPConnection

    def _authenticate(self, force_reauth=False):
        """
        Use the authentication plugin to authenticate and set the auth token.

        :param force_reauth: For re-authentication to bypass cache.
        """
        auth_plugin = self.auth_plugin

        if not auth_plugin.is_authenticated or force_reauth:
            auth_plugin.authenticate()

        self.auth_token = auth_plugin.auth_token

        management_url = auth_plugin.management_url
        if management_url and self.configure_via_auth:
            self.configure_from_url(management_url)

    @handle_unauthenticated
    def do_request(self, method, action, body=None, headers=None,
                   params=None):
        """
        Make a request, returning an HTTP response object.

        :param method: HTTP verb (GET, POST, PUT, etc.)
        :param action: Requested path to append to self.doc_root
        :param body: Data to send in the body of the request
        :param headers: Headers to send with the request
        :param params: Key/value pairs to use in query string
        :returns: HTTP response object
        """
        if not self.auth_token:
            self._authenticate()

        url = self._construct_url(action, params)
        # NOTE(ameade): We need to copy these kwargs since they can be altered
        # in _do_request but we need the originals if handle_unauthenticated
        # calls this function again.
        return self._do_request(method=method, url=url,
                                body=copy.deepcopy(body),
                                headers=copy.deepcopy(headers))

    def _construct_url(self, action, params=None):
        """
        Create a URL object we can use to pass to _do_request().
        """
        action = urlparse.quote(action)
        path = '/'.join([self.doc_root or '', action.lstrip('/')])
        scheme = "https" if self.use_ssl else "http"
        if netutils.is_valid_ipv6(self.host):
            netloc = "[%s]:%d" % (self.host, self.port)
        else:
            netloc = "%s:%d" % (self.host, self.port)

        if isinstance(params, dict):
            for (key, value) in list(params.items()):
                if value is None:
                    del params[key]
                    continue
                if not isinstance(value, str):
                    value = str(value)
                params[key] = encodeutils.safe_encode(value)
            query = urlparse.urlencode(params)
        else:
            query = None

        url = urlparse.ParseResult(scheme, netloc, path, '', query, '')
        log_msg = _("Constructed URL: %s")
        LOG.debug(log_msg, url.geturl())
        return url

    @handle_redirects
    def _do_request(self, method, url, body, headers):
        """
        Connects to the server and issues a request.  Handles converting
        any returned HTTP error status codes to OpenStack/Glance exceptions
        and closing the server connection. Returns the result data, or
        raises an appropriate exception.

        :param method: HTTP method ("GET", "POST", "PUT", etc...)
        :param url: urlparse.ParsedResult object with URL information
        :param body: data to send (as string, filelike or iterable),
                     or None (default)
        :param headers: mapping of key/value pairs to add as headers

        :note

        If the body param has a read attribute, and method is either
        POST or PUT, this method will automatically conduct a chunked-transfer
        encoding and use the body as a file object or iterable, transferring
        chunks of data using the connection's send() method. This allows large
        objects to be transferred efficiently without buffering the entire
        body in memory.
        """
        if url.query:
            path = url.path + "?" + url.query
        else:
            path = url.path

        try:
            connection_type = self.get_connection_type()
            headers = headers or {}
            headers.update(osprofiler.web.get_trace_id_headers())

            if 'x-auth-token' not in headers and self.auth_token:
                headers['x-auth-token'] = self.auth_token

            c = connection_type(url.hostname, url.port, **self.connect_kwargs)

            def _pushing(method):
                return method.lower() in ('post', 'put')

            def _simple(body):
                return body is None or isinstance(body, bytes)

            def _filelike(body):
                return hasattr(body, 'read')

            def _chunkbody(connection, iter):
                connection.putheader('Transfer-Encoding', 'chunked')
                connection.endheaders()
                for chunk in iter:
                    connection.send('%x\r\n%s\r\n' % (len(chunk), chunk))
                connection.send('0\r\n\r\n')

            # Do a simple request or a chunked request, depending
            # on whether the body param is file-like or iterable and
            # the method is PUT or POST
            #
            if not _pushing(method) or _simple(body):
                # Simple request...
                c.request(method, path, body, headers)
            elif _filelike(body) or self._iterable(body):
                c.putrequest(method, path)

                # According to HTTP/1.1, Content-Length and Transfer-Encoding
                # conflict.
                for header, value in headers.items():
                    if header.lower() != 'content-length':
                        c.putheader(header, str(value))

                iter = utils.chunkreadable(body)

                _chunkbody(c, iter)
            else:
                raise TypeError('Unsupported image type: %s' % body.__class__)

            res = c.getresponse()

            def _retry(res):
                return res.getheader('Retry-After')

            def read_body(res):
                body = res.read().decode('utf-8')
                return body

            status_code = self.get_status_code(res)
            if status_code in self.OK_RESPONSE_CODES:
                return res
            elif status_code in self.REDIRECT_RESPONSE_CODES:
                raise exception.RedirectException(res.getheader('Location'))
            elif status_code == http.client.UNAUTHORIZED:
                raise exception.NotAuthenticated(read_body(res))
            elif status_code == http.client.FORBIDDEN:
                raise exception.Forbidden(read_body(res))
            elif status_code == http.client.NOT_FOUND:
                raise exception.NotFound(read_body(res))
            elif status_code == http.client.CONFLICT:
                raise exception.Duplicate(read_body(res))
            elif status_code == http.client.BAD_REQUEST:
                raise exception.Invalid(read_body(res))
            elif status_code == http.client.MULTIPLE_CHOICES:
                raise exception.MultipleChoices(body=read_body(res))
            elif status_code == http.client.REQUEST_ENTITY_TOO_LARGE:
                raise exception.LimitExceeded(retry=_retry(res),
                                              body=read_body(res))
            elif status_code == http.client.INTERNAL_SERVER_ERROR:
                raise exception.ServerError()
            elif status_code == http.client.SERVICE_UNAVAILABLE:
                raise exception.ServiceUnavailable(retry=_retry(res))
            else:
                raise exception.UnexpectedStatus(status=status_code,
                                                 body=read_body(res))

        except (socket.error, IOError) as e:
            raise exception.ClientConnectionError(e)

    def _iterable(self, body):
        return isinstance(body, collections.abc.Iterable)

    def get_status_code(self, response):
        """
        Returns the integer status code from the response, which
        can be either a Webob.Response (used in testing) or httplib.Response
        """
        if hasattr(response, 'status_int'):
            return response.status_int
        else:
            return response.status

    def _extract_params(self, actual_params, allowed_params):
        """
        Extract a subset of keys from a dictionary. The filters key
        will also be extracted, and each of its values will be returned
        as an individual param.

        :param actual_params: dict of keys to filter
        :param allowed_params: list of keys that 'actual_params' will be
                               reduced to
        :returns: subset of 'params' dict
        """
        try:
            # expect 'filters' param to be a dict here
            result = dict(actual_params.get('filters'))
        except TypeError:
            result = {}

        for allowed_param in allowed_params:
            if allowed_param in actual_params:
                result[allowed_param] = actual_params[allowed_param]

        return result
