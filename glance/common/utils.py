# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2014 SoftLayer Technologies, Inc.
# Copyright 2015 Mirantis, Inc
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
System-level utilities and helper functions.
"""

import errno

try:
    from eventlet import sleep
except ImportError:
    from time import sleep
from eventlet.green import socket

import functools
import os
import re
import urllib

import glance_store
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import netutils
from oslo_utils import strutils
from webob import exc

from glance.common import exception
from glance.common import location_strategy
from glance.common import timeutils
from glance.common import wsgi
from glance.i18n import _, _LE, _LW

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

# Whitelist of v1 API headers of form x-image-meta-xxx
IMAGE_META_HEADERS = ['x-image-meta-location', 'x-image-meta-size',
                      'x-image-meta-is_public', 'x-image-meta-disk_format',
                      'x-image-meta-container_format', 'x-image-meta-name',
                      'x-image-meta-status', 'x-image-meta-copy_from',
                      'x-image-meta-uri', 'x-image-meta-checksum',
                      'x-image-meta-created_at', 'x-image-meta-updated_at',
                      'x-image-meta-deleted_at', 'x-image-meta-min_ram',
                      'x-image-meta-min_disk', 'x-image-meta-owner',
                      'x-image-meta-store', 'x-image-meta-id',
                      'x-image-meta-protected', 'x-image-meta-deleted',
                      'x-image-meta-virtual_size']

GLANCE_TEST_SOCKET_FD_STR = 'GLANCE_TEST_SOCKET_FD'


def chunkreadable(iter, chunk_size=65536):
    """
    Wrap a readable iterator with a reader yielding chunks of
    a preferred size, otherwise leave iterator unchanged.

    :param iter: an iter which may also be readable
    :param chunk_size: maximum size of chunk
    """
    return chunkiter(iter, chunk_size) if hasattr(iter, 'read') else iter


def chunkiter(fp, chunk_size=65536):
    """
    Return an iterator to a file-like obj which yields fixed size chunks

    :param fp: a file-like object
    :param chunk_size: maximum size of chunk
    """
    while True:
        chunk = fp.read(chunk_size)
        if chunk:
            yield chunk
        else:
            break


def cooperative_iter(iter):
    """
    Return an iterator which schedules after each
    iteration. This can prevent eventlet thread starvation.

    :param iter: an iterator to wrap
    """
    try:
        for chunk in iter:
            sleep(0)
            yield chunk
    except Exception as err:
        with excutils.save_and_reraise_exception():
            msg = _LE("Error: cooperative_iter exception %s") % err
            LOG.error(msg)


def cooperative_read(fd):
    """
    Wrap a file descriptor's read with a partial function which schedules
    after each read. This can prevent eventlet thread starvation.

    :param fd: a file descriptor to wrap
    """
    def readfn(*args):
        result = fd.read(*args)
        sleep(0)
        return result
    return readfn


MAX_COOP_READER_BUFFER_SIZE = 134217728  # 128M seems like a sane buffer limit

CONF.import_group('import_filtering_opts',
                  'glance.async_.flows._internal_plugins')


def validate_import_uri(uri):
    """Validate requested uri for Image Import web-download.

    :param uri: target uri to be validated
    """
    if not uri:
        return False

    parsed_uri = urllib.parse.urlparse(uri)
    scheme = parsed_uri.scheme
    host = parsed_uri.hostname
    port = parsed_uri.port
    wl_schemes = CONF.import_filtering_opts.allowed_schemes
    bl_schemes = CONF.import_filtering_opts.disallowed_schemes
    wl_hosts = CONF.import_filtering_opts.allowed_hosts
    bl_hosts = CONF.import_filtering_opts.disallowed_hosts
    wl_ports = CONF.import_filtering_opts.allowed_ports
    bl_ports = CONF.import_filtering_opts.disallowed_ports

    # NOTE(jokke): Checking if both allowed and disallowed are defined and
    # logging it to inform only allowed will be obeyed.
    if wl_schemes and bl_schemes:
        bl_schemes = []
        LOG.debug("Both allowed and disallowed schemes has been configured. "
                  "Will only process allowed list.")
    if wl_hosts and bl_hosts:
        bl_hosts = []
        LOG.debug("Both allowed and disallowed hosts has been configured. "
                  "Will only process allowed list.")
    if wl_ports and bl_ports:
        bl_ports = []
        LOG.debug("Both allowed and disallowed ports has been configured. "
                  "Will only process allowed list.")

    if not scheme or ((wl_schemes and scheme not in wl_schemes) or
                      parsed_uri.scheme in bl_schemes):
        return False
    if not host or ((wl_hosts and host not in wl_hosts) or
                    host in bl_hosts):
        return False
    if port and ((wl_ports and port not in wl_ports) or
                 port in bl_ports):
        return False

    return True


class CooperativeReader(object):
    """
    An eventlet thread friendly class for reading in image data.

    When accessing data either through the iterator or the read method
    we perform a sleep to allow a co-operative yield. When there is more than
    one image being uploaded/downloaded this prevents eventlet thread
    starvation, ie allows all threads to be scheduled periodically rather than
    having the same thread be continuously active.
    """
    def __init__(self, fd):
        """
        :param fd: Underlying image file object
        """
        self.fd = fd
        self.iterator = None
        # NOTE(markwash): if the underlying supports read(), overwrite the
        # default iterator-based implementation with cooperative_read which
        # is more straightforward
        if hasattr(fd, 'read'):
            self.read = cooperative_read(fd)
        else:
            self.iterator = None
            self.buffer = b''
            self.position = 0

    def read(self, length=None):
        """Return the requested amount of bytes, fetching the next chunk of
        the underlying iterator when needed.

        This is replaced with cooperative_read in __init__ if the underlying
        fd already supports read().
        """
        if length is None:
            if len(self.buffer) - self.position > 0:
                # if no length specified but some data exists in buffer,
                # return that data and clear the buffer
                result = self.buffer[self.position:]
                self.buffer = b''
                self.position = 0
                return bytes(result)
            else:
                # otherwise read the next chunk from the underlying iterator
                # and return it as a whole. Reset the buffer, as subsequent
                # calls may specify the length
                try:
                    if self.iterator is None:
                        self.iterator = self.__iter__()
                    return next(self.iterator)
                except StopIteration:
                    return b''
                finally:
                    self.buffer = b''
                    self.position = 0
        else:
            result = bytearray()
            while len(result) < length:
                if self.position < len(self.buffer):
                    to_read = length - len(result)
                    chunk = self.buffer[self.position:self.position + to_read]
                    result.extend(chunk)

                    # This check is here to prevent potential OOM issues if
                    # this code is called with unreasonably high values of read
                    # size. Currently it is only called from the HTTP clients
                    # of Glance backend stores, which use httplib for data
                    # streaming, which has readsize hardcoded to 8K, so this
                    # check should never fire. Regardless it still worths to
                    # make the check, as the code may be reused somewhere else.
                    if len(result) >= MAX_COOP_READER_BUFFER_SIZE:
                        raise exception.LimitExceeded()
                    self.position += len(chunk)
                else:
                    try:
                        if self.iterator is None:
                            self.iterator = self.__iter__()
                        self.buffer = next(self.iterator)
                        self.position = 0
                    except StopIteration:
                        self.buffer = b''
                        self.position = 0
                        return bytes(result)
            return bytes(result)

    def __iter__(self):
        return cooperative_iter(self.fd.__iter__())


class LimitingReader(object):
    """
    Reader designed to fail when reading image data past the configured
    allowable amount.
    """
    def __init__(self, data, limit,
                 exception_class=exception.ImageSizeLimitExceeded):
        """
        :param data: Underlying image data object
        :param limit: maximum number of bytes the reader should allow
        :param exception_class: Type of exception to be raised
        """
        self.data = data
        self.limit = limit
        self.bytes_read = 0
        self.exception_class = exception_class

    def __iter__(self):
        for chunk in self.data:
            self.bytes_read += len(chunk)
            if self.bytes_read > self.limit:
                raise self.exception_class()
            else:
                yield chunk

    def read(self, i):
        result = self.data.read(i)
        self.bytes_read += len(result)
        if self.bytes_read > self.limit:
            raise self.exception_class()
        return result


def image_meta_to_http_headers(image_meta):
    """
    Returns a set of image metadata into a dict
    of HTTP headers that can be fed to either a Webob
    Request object or an httplib.HTTP(S)Connection object

    :param image_meta: Mapping of image metadata
    """
    headers = {}
    for k, v in image_meta.items():
        if v is not None:
            if k == 'properties':
                for pk, pv in v.items():
                    if pv is not None:
                        headers["x-image-meta-property-%s"
                                % pk.lower()] = str(pv)
            else:
                headers["x-image-meta-%s" % k.lower()] = str(v)
    return headers


def get_image_meta_from_headers(response):
    """
    Processes HTTP headers from a supplied response that
    match the x-image-meta and x-image-meta-property and
    returns a mapping of image metadata and properties

    :param response: Response to process
    """
    result = {}
    properties = {}

    if hasattr(response, 'getheaders'):  # httplib.HTTPResponse
        headers = response.getheaders()
    else:  # webob.Response
        headers = response.headers.items()

    for key, value in headers:
        key = str(key.lower())
        if key.startswith('x-image-meta-property-'):
            field_name = key[len('x-image-meta-property-'):].replace('-', '_')
            properties[field_name] = value or None
        elif key.startswith('x-image-meta-'):
            field_name = key[len('x-image-meta-'):].replace('-', '_')
            if 'x-image-meta-' + field_name not in IMAGE_META_HEADERS:
                msg = _("Bad header: %(header_name)s") % {'header_name': key}
                raise exc.HTTPBadRequest(msg, content_type="text/plain")
            result[field_name] = value or None
    result['properties'] = properties

    for key, nullable in [('size', False), ('min_disk', False),
                          ('min_ram', False), ('virtual_size', True)]:
        if key in result:
            try:
                result[key] = int(result[key])
            except ValueError:
                if nullable and result[key] == str(None):
                    result[key] = None
                else:
                    extra = (_("Cannot convert image %(key)s '%(value)s' "
                               "to an integer.")
                             % {'key': key, 'value': result[key]})
                    raise exception.InvalidParameterValue(value=result[key],
                                                          param=key,
                                                          extra_msg=extra)
            if result[key] is not None and result[key] < 0:
                extra = _('Cannot be a negative value.')
                raise exception.InvalidParameterValue(value=result[key],
                                                      param=key,
                                                      extra_msg=extra)

    for key in ('is_public', 'deleted', 'protected'):
        if key in result:
            result[key] = strutils.bool_from_string(result[key])
    return result


def create_mashup_dict(image_meta):
    """
    Returns a dictionary-like mashup of the image core properties
    and the image custom properties from given image metadata.

    :param image_meta: metadata of image with core and custom properties
    """

    d = {}
    for key, value in image_meta.items():
        if isinstance(value, dict):
            for subkey, subvalue in create_mashup_dict(value).items():
                if subkey not in image_meta:
                    d[subkey] = subvalue
        else:
            d[key] = value

    return d


def safe_mkdirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def mutating(func):
    """Decorator to enforce read-only logic"""
    @functools.wraps(func)
    def wrapped(self, req, *args, **kwargs):
        if req.context.read_only:
            msg = "Read-only access"
            LOG.debug(msg)
            raise exc.HTTPForbidden(msg, request=req,
                                    content_type="text/plain")
        return func(self, req, *args, **kwargs)
    return wrapped


def setup_remote_pydev_debug(host, port):
    error_msg = _LE('Error setting up the debug environment. Verify that the'
                    ' option pydev_worker_debug_host is pointing to a valid '
                    'hostname or IP on which a pydev server is listening on'
                    ' the port indicated by pydev_worker_debug_port.')

    try:
        try:
            from pydev import pydevd
        except ImportError:
            import pydevd

        pydevd.settrace(host,
                        port=port,
                        stdoutToServer=True,
                        stderrToServer=True)
        return True
    except Exception:
        with excutils.save_and_reraise_exception():
            LOG.exception(error_msg)


def get_test_suite_socket():
    global GLANCE_TEST_SOCKET_FD_STR
    if GLANCE_TEST_SOCKET_FD_STR in os.environ:
        fd = int(os.environ[GLANCE_TEST_SOCKET_FD_STR])
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        sock.listen(CONF.backlog)
        del os.environ[GLANCE_TEST_SOCKET_FD_STR]
        os.close(fd)
        return sock
    return None


def is_valid_hostname(hostname):
    """Verify whether a hostname (not an FQDN) is valid."""
    return re.match('^[a-zA-Z0-9-]+$', hostname) is not None


def is_valid_fqdn(fqdn):
    """Verify whether a host is a valid FQDN."""
    return re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', fqdn) is not None


def parse_valid_host_port(host_port):
    """
    Given a "host:port" string, attempts to parse it as intelligently as
    possible to determine if it is valid. This includes IPv6 [host]:port form,
    IPv4 ip:port form, and hostname:port or fqdn:port form.

    Invalid inputs will raise a ValueError, while valid inputs will return
    a (host, port) tuple where the port will always be of type int.
    """

    try:
        try:
            host, port = netutils.parse_host_port(host_port)
        except Exception:
            raise ValueError(_('Host and port "%s" is not valid.') % host_port)

        if not netutils.is_valid_port(port):
            raise ValueError(_('Port "%s" is not valid.') % port)

        # First check for valid IPv6 and IPv4 addresses, then a generic
        # hostname. Failing those, if the host includes a period, then this
        # should pass a very generic FQDN check. The FQDN check for letters at
        # the tail end will weed out any hilariously absurd IPv4 addresses.

        if not (netutils.is_valid_ipv6(host) or netutils.is_valid_ipv4(host) or
                is_valid_hostname(host) or is_valid_fqdn(host)):
            raise ValueError(_('Host "%s" is not valid.') % host)

    except Exception as ex:
        raise ValueError(_('%s '
                           'Please specify a host:port pair, where host is an '
                           'IPv4 address, IPv6 address, hostname, or FQDN. If '
                           'using an IPv6 address, enclose it in brackets '
                           'separately from the port (i.e., '
                           '"[fe80::a:b:c]:9876").') % ex)

    return (host, int(port))


try:
    REGEX_4BYTE_UNICODE = re.compile('[\U00010000-\U0010ffff]')
except re.error:
    # UCS-2 build case
    REGEX_4BYTE_UNICODE = re.compile('[\uD800-\uDBFF][\uDC00-\uDFFF]')


def no_4byte_params(f):
    """
    Checks that no 4 byte unicode characters are allowed
    in dicts' keys/values and string's parameters
    """
    def wrapper(*args, **kwargs):

        def _is_match(some_str):
            return (
                isinstance(some_str, str) and
                REGEX_4BYTE_UNICODE.findall(some_str) != []
            )

        def _check_dict(data_dict):
            # a dict of dicts has to be checked recursively
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    _check_dict(value)
                else:
                    if _is_match(key):
                        msg = _("Property names can't contain 4 byte unicode.")
                        raise exception.Invalid(msg)
                    if _is_match(value):
                        msg = (_("%s can't contain 4 byte unicode characters.")
                               % key.title())
                        raise exception.Invalid(msg)

        for data_dict in [arg for arg in args if isinstance(arg, dict)]:
            _check_dict(data_dict)
        # now check args for str values
        for arg in args:
            if _is_match(arg):
                msg = _("Param values can't contain 4 byte unicode.")
                raise exception.Invalid(msg)
        # check kwargs as well, as params are passed as kwargs via
        # registry calls
        _check_dict(kwargs)
        return f(*args, **kwargs)
    return wrapper


def stash_conf_values():
    """
    Make a copy of some of the current global CONF's settings.
    Allows determining if any of these values have changed
    when the config is reloaded.
    """
    conf = {
        'bind_host': CONF.bind_host,
        'bind_port': CONF.bind_port,
        'backlog': CONF.backlog,
    }

    return conf


def split_filter_op(expression):
    """Split operator from threshold in an expression.
    Designed for use on a comparative-filtering query field.
    When no operator is found, default to an equality comparison.

    :param expression: the expression to parse

    :returns: a tuple (operator, threshold) parsed from expression
    """
    left, sep, right = expression.partition(':')
    if sep:
        # If the expression is a date of the format ISO 8601 like
        # CCYY-MM-DDThh:mm:ss+hh:mm and has no operator, it should
        # not be partitioned, and a default operator of eq should be
        # assumed.
        try:
            timeutils.parse_isotime(expression)
            op = 'eq'
            threshold = expression
        except ValueError:
            op = left
            threshold = right
    else:
        op = 'eq'  # default operator
        threshold = left

    # NOTE stevelle decoding escaped values may be needed later
    return op, threshold


def validate_quotes(value):
    """Validate filter values

    Validation opening/closing quotes in the expression.
    """
    open_quotes = True
    for i in range(len(value)):
        if value[i] == '"':
            if i and value[i - 1] == '\\':
                continue
            if open_quotes:
                if i and value[i - 1] != ',':
                    msg = _("Invalid filter value %s. There is no comma "
                            "before opening quotation mark.") % value
                    raise exception.InvalidParameterValue(message=msg)
            else:
                if i + 1 != len(value) and value[i + 1] != ",":
                    msg = _("Invalid filter value %s. There is no comma "
                            "after closing quotation mark.") % value
                    raise exception.InvalidParameterValue(message=msg)
            open_quotes = not open_quotes
    if not open_quotes:
        msg = _("Invalid filter value %s. The quote is not closed.") % value
        raise exception.InvalidParameterValue(message=msg)


def split_filter_value_for_quotes(value):
    """Split filter values

    Split values by commas and quotes for 'in' operator, according api-wg.
    """
    validate_quotes(value)
    tmp = re.compile(r'''
        "(                 # if found a double-quote
           [^\"\\]*        # take characters either non-quotes or backslashes
           (?:\\.          # take backslashes and character after it
            [^\"\\]*)*     # take characters either non-quotes or backslashes
         )                 # before double-quote
        ",?                # a double-quote with comma maybe
        | ([^,]+),?        # if not found double-quote take any non-comma
                           # characters with comma maybe
        | ,                # if we have only comma take empty string
        ''', re.VERBOSE)
    return [val[0] or val[1] for val in re.findall(tmp, value)]


def evaluate_filter_op(value, operator, threshold):
    """Evaluate a comparison operator.
    Designed for use on a comparative-filtering query field.

    :param value: evaluated against the operator, as left side of expression
    :param operator: any supported filter operation
    :param threshold: to compare value against, as right side of expression

    :raises InvalidFilterOperatorValue: if an unknown operator is provided

    :returns: boolean result of applied comparison

    """
    if operator == 'gt':
        return value > threshold
    elif operator == 'gte':
        return value >= threshold
    elif operator == 'lt':
        return value < threshold
    elif operator == 'lte':
        return value <= threshold
    elif operator == 'neq':
        return value != threshold
    elif operator == 'eq':
        return value == threshold

    msg = _("Unable to filter on a unknown operator.")
    raise exception.InvalidFilterOperatorValue(msg)


def _get_available_stores():
    available_stores = CONF.enabled_backends
    stores = []
    # Remove reserved stores from the available stores list
    for store in available_stores:
        # NOTE (abhishekk): http store is readonly and should be
        # excluded from the list.
        if available_stores[store] == 'http':
            continue
        if store not in wsgi.RESERVED_STORES:
            stores.append(store)

    return stores


def get_stores_from_request(req, body):
    """Processes a supplied request and extract stores from it

    :param req: request to process
    :param body: request body

    :raises glance_store.UnknownScheme:  if a store is not valid
    :return: a list of stores
    """
    if body.get('all_stores', False):
        if 'stores' in body or 'x-image-meta-store' in req.headers:
            msg = _("All_stores parameter can't be used with "
                    "x-image-meta-store header or stores parameter")
            raise exc.HTTPBadRequest(explanation=msg)
        stores = _get_available_stores()
    else:
        try:
            stores = body['stores']
        except KeyError:
            stores = [req.headers.get('x-image-meta-store',
                                      CONF.glance_store.default_backend)]
        else:
            if 'x-image-meta-store' in req.headers:
                msg = _("Stores parameter and x-image-meta-store header can't "
                        "be both specified")
                raise exc.HTTPBadRequest(explanation=msg)
    # Validate each store
    for store in stores:
        glance_store.get_store_from_store_identifier(store)
    return stores


def sort_image_locations(locations):
    if not CONF.enabled_backends:
        return location_strategy.get_ordered_locations(locations)

    def get_store_weight(location):
        store_id = location['metadata'].get('store')
        if not store_id:
            return 0
        try:
            store = glance_store.get_store_from_store_identifier(store_id)
        except glance_store.exceptions.UnknownScheme:
            msg = (_LW("Unable to find store '%s', returning "
                       "default weight '0'") % store_id)
            LOG.warning(msg)
            return 0
        return store.weight if store is not None else 0

    sorted_locations = sorted(locations, key=get_store_weight, reverse=True)
    LOG.debug(('Sorted locations: %s'), sorted_locations)
    return sorted_locations
