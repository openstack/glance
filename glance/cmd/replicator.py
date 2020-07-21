#!/usr/bin/env python

# Copyright 2012 Michael Still and Canonical Inc
# Copyright 2014 SoftLayer Technologies, Inc.
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

import os
import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
from oslo_utils import uuidutils
import six
from six.moves import http_client as http
import six.moves.urllib.parse as urlparse
from webob import exc

from glance.common import config
from glance.common import exception
from glance.common import utils
from glance.i18n import _, _LE, _LI, _LW

LOG = logging.getLogger(__name__)


# NOTE: positional arguments <args> will be parsed before <command> until
# this bug is corrected https://bugs.launchpad.net/oslo.config/+bug/1392428
cli_opts = [
    cfg.IntOpt('chunksize',
               short='c',
               default=65536,
               help="Amount of data to transfer per HTTP write."),
    cfg.StrOpt('dontreplicate',
               short='D',
               default=('created_at date deleted_at location updated_at'),
               help="List of fields to not replicate."),
    cfg.BoolOpt('metaonly',
                short='m',
                default=False,
                help="Only replicate metadata, not images."),
    cfg.StrOpt('token',
               short='t',
               default='',
               help=("Pass in your authentication token if you have "
                     "one. If you use this option the same token is "
                     "used for both the source and the target.")),
    cfg.StrOpt('command',
               positional=True,
               required=False,
               help="Command to be given to replicator"),
    cfg.MultiStrOpt('args',
                    positional=True,
                    required=False,
                    help="Arguments for the command"),
]

CONF = cfg.CONF
CONF.register_cli_opts(cli_opts)

CONF.register_opt(
    cfg.StrOpt('sourcetoken',
               default='',
               help=("Pass in your authentication token if you have "
                     "one. This is the token used for the source.")))
CONF.register_opt(
    cfg.StrOpt('targettoken',
               default='',
               help=("Pass in your authentication token if you have "
                     "one. This is the token used for the target.")))

logging.register_options(CONF)
CONF.set_default(name='use_stderr', default=True)

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)


COMMANDS = """Commands:

    help <command>  Output help for one of the commands below

    compare         What is missing from the target glance?
    dump            Dump the contents of a glance instance to local disk.
    livecopy        Load the contents of one glance instance into another.
    load            Load the contents of a local directory into glance.
    size            Determine the size of a glance instance if dumped to disk.
"""


IMAGE_ALREADY_PRESENT_MESSAGE = _('The image %s is already present on '
                                  'the target, but our check for it did '
                                  'not find it. This indicates that we '
                                  'do not have permissions to see all '
                                  'the images on the target server.')


class ImageService(object):
    def __init__(self, conn, auth_token):
        """Initialize the ImageService.

        conn: a http_client.HTTPConnection to the glance server
        auth_token: authentication token to pass in the x-auth-token header
        """
        self.auth_token = auth_token
        self.conn = conn

    def _http_request(self, method, url, headers, body,
                      ignore_result_body=False):
        """Perform an HTTP request against the server.

        method: the HTTP method to use
        url: the URL to request (not including server portion)
        headers: headers for the request
        body: body to send with the request
        ignore_result_body: the body of the result will be ignored

        Returns: a http_client response object
        """
        if self.auth_token:
            headers.setdefault('x-auth-token', self.auth_token)

        LOG.debug('Request: %(method)s http://%(server)s:%(port)s'
                  '%(url)s with headers %(headers)s',
                  {'method': method,
                   'server': self.conn.host,
                   'port': self.conn.port,
                   'url': url,
                   'headers': repr(headers)})
        self.conn.request(method, url, body, headers)

        response = self.conn.getresponse()
        headers = self._header_list_to_dict(response.getheaders())
        code = response.status
        code_description = http.responses[code]
        LOG.debug('Response: %(code)s %(status)s %(headers)s',
                  {'code': code,
                   'status': code_description,
                   'headers': repr(headers)})

        if code == http.BAD_REQUEST:
            raise exc.HTTPBadRequest(
                explanation=response.read())

        if code == http.INTERNAL_SERVER_ERROR:
            raise exc.HTTPInternalServerError(
                explanation=response.read())

        if code == http.UNAUTHORIZED:
            raise exc.HTTPUnauthorized(
                explanation=response.read())

        if code == http.FORBIDDEN:
            raise exc.HTTPForbidden(
                explanation=response.read())

        if code == http.CONFLICT:
            raise exc.HTTPConflict(
                explanation=response.read())

        if ignore_result_body:
            # NOTE: because we are pipelining requests through a single HTTP
            # connection, http_client requires that we read the response body
            # before we can make another request. If the caller knows they
            # don't care about the body, they can ask us to do that for them.
            response.read()
        return response

    def get_images(self):
        """Return a detailed list of images.

        Yields a series of images as dicts containing metadata.
        """
        params = {'is_public': None}

        while True:
            url = '/v1/images/detail'
            query = urlparse.urlencode(params)
            if query:
                url += '?%s' % query

            response = self._http_request('GET', url, {}, '')
            result = jsonutils.loads(response.read())

            if not result or 'images' not in result or not result['images']:
                return
            for image in result.get('images', []):
                params['marker'] = image['id']
                yield image

    def get_image(self, image_uuid):
        """Fetch image data from glance.

        image_uuid: the id of an image

        Returns: a http_client Response object where the body is the image.
        """
        url = '/v1/images/%s' % image_uuid
        return self._http_request('GET', url, {}, '')

    @staticmethod
    def _header_list_to_dict(headers):
        """Expand a list of headers into a dictionary.

        headers: a list of [(key, value), (key, value), (key, value)]

        Returns: a dictionary representation of the list
        """
        d = {}
        for (header, value) in headers:
            if header.startswith('x-image-meta-property-'):
                prop = header.replace('x-image-meta-property-', '')
                d.setdefault('properties', {})
                d['properties'][prop] = value
            else:
                d[header.replace('x-image-meta-', '')] = value
        return d

    def get_image_meta(self, image_uuid):
        """Return the metadata for a single image.

        image_uuid: the id of an image

        Returns: image metadata as a dictionary
        """
        url = '/v1/images/%s' % image_uuid
        response = self._http_request('HEAD', url, {}, '',
                                      ignore_result_body=True)
        return self._header_list_to_dict(response.getheaders())

    @staticmethod
    def _dict_to_headers(d):
        """Convert a dictionary into one suitable for a HTTP request.

        d: a dictionary

        Returns: the same dictionary, with x-image-meta added to every key
        """
        h = {}
        for key in d:
            if key == 'properties':
                for subkey in d[key]:
                    if d[key][subkey] is None:
                        h['x-image-meta-property-%s' % subkey] = ''
                    else:
                        h['x-image-meta-property-%s' % subkey] = d[key][subkey]

            else:
                h['x-image-meta-%s' % key] = d[key]
        return h

    def add_image(self, image_meta, image_data):
        """Upload an image.

        image_meta: image metadata as a dictionary
        image_data: image data as a object with a read() method

        Returns: a tuple of (http response headers, http response body)
        """

        url = '/v1/images'
        headers = self._dict_to_headers(image_meta)
        headers['Content-Type'] = 'application/octet-stream'
        headers['Content-Length'] = int(image_meta['size'])

        response = self._http_request('POST', url, headers, image_data)
        headers = self._header_list_to_dict(response.getheaders())

        LOG.debug('Image post done')
        body = response.read()
        return headers, body

    def add_image_meta(self, image_meta):
        """Update image metadata.

        image_meta: image metadata as a dictionary

        Returns: a tuple of (http response headers, http response body)
        """

        url = '/v1/images/%s' % image_meta['id']
        headers = self._dict_to_headers(image_meta)
        headers['Content-Type'] = 'application/octet-stream'

        response = self._http_request('PUT', url, headers, '')
        headers = self._header_list_to_dict(response.getheaders())

        LOG.debug('Image post done')
        body = response.read()
        return headers, body


def get_image_service():
    """Get a copy of the image service.

    This is done like this to make it easier to mock out ImageService.
    """
    return ImageService


def _human_readable_size(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


def replication_size(options, args):
    """%(prog)s size <server:port>

    Determine the size of a glance instance if dumped to disk.

    server:port: the location of the glance instance.
    """

    # Make sure server info is provided
    if args is None or len(args) < 1:
        raise TypeError(_("Too few arguments."))

    server, port = utils.parse_valid_host_port(args.pop())

    total_size = 0
    count = 0

    imageservice = get_image_service()
    client = imageservice(http.HTTPConnection(server, port),
                          options.targettoken)
    for image in client.get_images():
        LOG.debug('Considering image: %(image)s', {'image': image})
        if image['status'] == 'active':
            total_size += int(image['size'])
            count += 1

    print(_('Total size is %(size)d bytes (%(human_size)s) across '
            '%(img_count)d images') %
          {'size': total_size,
           'human_size': _human_readable_size(total_size),
           'img_count': count})


def replication_dump(options, args):
    """%(prog)s dump <server:port> <path>

    Dump the contents of a glance instance to local disk.

    server:port: the location of the glance instance.
    path:        a directory on disk to contain the data.
    """

    # Make sure server and path are provided
    if len(args) < 2:
        raise TypeError(_("Too few arguments."))

    path = args.pop()
    server, port = utils.parse_valid_host_port(args.pop())

    imageservice = get_image_service()
    client = imageservice(http.HTTPConnection(server, port),
                          options.sourcetoken)
    for image in client.get_images():
        LOG.debug('Considering: %(image_id)s (%(image_name)s) '
                  '(%(image_size)d bytes)',
                  {'image_id': image['id'],
                   'image_name': image.get('name', '--unnamed--'),
                   'image_size': image['size']})

        data_path = os.path.join(path, image['id'])
        data_filename = data_path + '.img'
        if not os.path.exists(data_path):
            LOG.info(_LI('Storing: %(image_id)s (%(image_name)s)'
                         ' (%(image_size)d bytes) in %(data_filename)s'),
                     {'image_id': image['id'],
                      'image_name': image.get('name', '--unnamed--'),
                      'image_size': image['size'],
                      'data_filename': data_filename})

            # Dump glance information
            if six.PY3:
                f = open(data_path, 'w', encoding='utf-8')
            else:
                f = open(data_path, 'w')
            with f:
                f.write(jsonutils.dumps(image))

            if image['status'] == 'active' and not options.metaonly:
                # Now fetch the image. The metadata returned in headers here
                # is the same as that which we got from the detailed images
                # request earlier, so we can ignore it here. Note that we also
                # only dump active images.
                LOG.debug('Image %s is active', image['id'])
                image_response = client.get_image(image['id'])
                with open(data_filename, 'wb') as f:
                    while True:
                        chunk = image_response.read(options.chunksize)
                        if not chunk:
                            break
                        f.write(chunk)


def _dict_diff(a, b):
    """A one way dictionary diff.

    a: a dictionary
    b: a dictionary

    Returns: True if the dictionaries are different
    """
    # Only things the source has which the target lacks matter
    if set(a.keys()) - set(b.keys()):
        LOG.debug('metadata diff -- source has extra keys: %(keys)s',
                  {'keys': ' '.join(set(a.keys()) - set(b.keys()))})
        return True

    for key in a:
        if str(a[key]) != str(b[key]):
            LOG.debug('metadata diff -- value differs for key '
                      '%(key)s: source "%(source_value)s" vs '
                      'target "%(target_value)s"',
                      {'key': key,
                       'source_value': a[key],
                       'target_value': b[key]})
            return True

    return False


def replication_load(options, args):
    """%(prog)s load <server:port> <path>

    Load the contents of a local directory into glance.

    server:port: the location of the glance instance.
    path:        a directory on disk containing the data.
    """

    # Make sure server and path are provided
    if len(args) < 2:
        raise TypeError(_("Too few arguments."))

    path = args.pop()
    server, port = utils.parse_valid_host_port(args.pop())

    imageservice = get_image_service()
    client = imageservice(http.HTTPConnection(server, port),
                          options.targettoken)

    updated = []

    for ent in os.listdir(path):
        if uuidutils.is_uuid_like(ent):
            image_uuid = ent
            LOG.info(_LI('Considering: %s'), image_uuid)

            meta_file_name = os.path.join(path, image_uuid)
            with open(meta_file_name) as meta_file:
                meta = jsonutils.loads(meta_file.read())

            # Remove keys which don't make sense for replication
            for key in options.dontreplicate.split(' '):
                if key in meta:
                    LOG.debug('Stripping %(header)s from saved '
                              'metadata', {'header': key})
                    del meta[key]

            if _image_present(client, image_uuid):
                # NOTE(mikal): Perhaps we just need to update the metadata?
                # Note that we don't attempt to change an image file once it
                # has been uploaded.
                LOG.debug('Image %s already present', image_uuid)
                headers = client.get_image_meta(image_uuid)
                for key in options.dontreplicate.split(' '):
                    if key in headers:
                        LOG.debug('Stripping %(header)s from target '
                                  'metadata', {'header': key})
                        del headers[key]

                if _dict_diff(meta, headers):
                    LOG.info(_LI('Image %s metadata has changed'), image_uuid)
                    headers, body = client.add_image_meta(meta)
                    _check_upload_response_headers(headers, body)
                    updated.append(meta['id'])

            else:
                if not os.path.exists(os.path.join(path, image_uuid + '.img')):
                    LOG.debug('%s dump is missing image data, skipping',
                              image_uuid)
                    continue

                # Upload the image itself
                with open(os.path.join(path, image_uuid + '.img')) as img_file:
                    try:
                        headers, body = client.add_image(meta, img_file)
                        _check_upload_response_headers(headers, body)
                        updated.append(meta['id'])
                    except exc.HTTPConflict:
                        LOG.error(_LE(IMAGE_ALREADY_PRESENT_MESSAGE)
                                  % image_uuid)  # noqa

    return updated


def replication_livecopy(options, args):
    """%(prog)s livecopy <fromserver:port> <toserver:port>

    Load the contents of one glance instance into another.

    fromserver:port: the location of the source glance instance.
    toserver:port:   the location of the target glance instance.
    """

    # Make sure from-server and to-server are provided
    if len(args) < 2:
        raise TypeError(_("Too few arguments."))

    imageservice = get_image_service()

    target_server, target_port = utils.parse_valid_host_port(args.pop())
    target_conn = http.HTTPConnection(target_server, target_port)
    target_client = imageservice(target_conn, options.targettoken)

    source_server, source_port = utils.parse_valid_host_port(args.pop())
    source_conn = http.HTTPConnection(source_server, source_port)
    source_client = imageservice(source_conn, options.sourcetoken)

    updated = []

    for image in source_client.get_images():
        LOG.debug('Considering %(id)s', {'id': image['id']})
        for key in options.dontreplicate.split(' '):
            if key in image:
                LOG.debug('Stripping %(header)s from source metadata',
                          {'header': key})
                del image[key]

        if _image_present(target_client, image['id']):
            # NOTE(mikal): Perhaps we just need to update the metadata?
            # Note that we don't attempt to change an image file once it
            # has been uploaded.
            headers = target_client.get_image_meta(image['id'])
            if headers['status'] == 'active':
                for key in options.dontreplicate.split(' '):
                    if key in image:
                        LOG.debug('Stripping %(header)s from source '
                                  'metadata', {'header': key})
                        del image[key]
                    if key in headers:
                        LOG.debug('Stripping %(header)s from target '
                                  'metadata', {'header': key})
                        del headers[key]

                if _dict_diff(image, headers):
                    LOG.info(_LI('Image %(image_id)s (%(image_name)s) '
                                 'metadata has changed'),
                             {'image_id': image['id'],
                              'image_name': image.get('name', '--unnamed--')})
                    headers, body = target_client.add_image_meta(image)
                    _check_upload_response_headers(headers, body)
                    updated.append(image['id'])

        elif image['status'] == 'active':
            LOG.info(_LI('Image %(image_id)s (%(image_name)s) '
                         '(%(image_size)d bytes) '
                         'is being synced'),
                     {'image_id': image['id'],
                      'image_name': image.get('name', '--unnamed--'),
                      'image_size': image['size']})
            if not options.metaonly:
                image_response = source_client.get_image(image['id'])
                try:
                    headers, body = target_client.add_image(image,
                                                            image_response)
                    _check_upload_response_headers(headers, body)
                    updated.append(image['id'])
                except exc.HTTPConflict:
                    LOG.error(_LE(IMAGE_ALREADY_PRESENT_MESSAGE) % image['id'])  # noqa

    return updated


def replication_compare(options, args):
    """%(prog)s compare <fromserver:port> <toserver:port>

    Compare the contents of fromserver with those of toserver.

    fromserver:port: the location of the source glance instance.
    toserver:port:   the location of the target glance instance.
    """

    # Make sure from-server and to-server are provided
    if len(args) < 2:
        raise TypeError(_("Too few arguments."))

    imageservice = get_image_service()

    target_server, target_port = utils.parse_valid_host_port(args.pop())
    target_conn = http.HTTPConnection(target_server, target_port)
    target_client = imageservice(target_conn, options.targettoken)

    source_server, source_port = utils.parse_valid_host_port(args.pop())
    source_conn = http.HTTPConnection(source_server, source_port)
    source_client = imageservice(source_conn, options.sourcetoken)

    differences = {}

    for image in source_client.get_images():
        if _image_present(target_client, image['id']):
            headers = target_client.get_image_meta(image['id'])
            for key in options.dontreplicate.split(' '):
                if key in image:
                    LOG.debug('Stripping %(header)s from source metadata',
                              {'header': key})
                    del image[key]
                if key in headers:
                    LOG.debug('Stripping %(header)s from target metadata',
                              {'header': key})
                    del headers[key]

            for key in image:
                if image[key] != headers.get(key):
                    LOG.warn(_LW('%(image_id)s: field %(key)s differs '
                                 '(source is %(source_value)s, destination '
                                 'is %(target_value)s)')
                             % {'image_id': image['id'],
                                'key': key,
                                'source_value': image[key],
                                'target_value': headers.get(key,
                                                            'undefined')})
                    differences[image['id']] = 'diff'
                else:
                    LOG.debug('%(image_id)s is identical',
                              {'image_id': image['id']})

        elif image['status'] == 'active':
            LOG.warn(_LW('Image %(image_id)s ("%(image_name)s") '
                     'entirely missing from the destination')
                     % {'image_id': image['id'],
                        'image_name': image.get('name', '--unnamed')})
            differences[image['id']] = 'missing'

    return differences


def _check_upload_response_headers(headers, body):
    """Check that the headers of an upload are reasonable.

    headers: the headers from the upload
    body: the body from the upload
    """

    if 'status' not in headers:
        try:
            d = jsonutils.loads(body)
            if 'image' in d and 'status' in d['image']:
                return

        except Exception:
            raise exception.UploadException(body)


def _image_present(client, image_uuid):
    """Check if an image is present in glance.

    client: the ImageService
    image_uuid: the image uuid to check

    Returns: True if the image is present
    """
    headers = client.get_image_meta(image_uuid)
    return 'status' in headers


def print_help(options, args):
    """Print help specific to a command.

    options: the parsed command line options
    args: the command line
    """
    if not args:
        print(COMMANDS)
    else:
        command_name = args.pop()
        command = lookup_command(command_name)
        print(command.__doc__ % {'prog': os.path.basename(sys.argv[0])})


def lookup_command(command_name):
    """Lookup a command.

    command_name: the command name

    Returns: a method which implements that command
    """
    BASE_COMMANDS = {'help': print_help}

    REPLICATION_COMMANDS = {'compare': replication_compare,
                            'dump': replication_dump,
                            'livecopy': replication_livecopy,
                            'load': replication_load,
                            'size': replication_size}

    commands = {}
    for command_set in (BASE_COMMANDS, REPLICATION_COMMANDS):
        commands.update(command_set)

    try:
        command = commands[command_name]
    except KeyError:
        if command_name:
            sys.exit(_("Unknown command: %s") % command_name)
        else:
            command = commands['help']
    return command


def main():
    """The main function."""

    try:
        config.parse_args()
    except RuntimeError as e:
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))
    except SystemExit:
        sys.exit("Please specify one command")

    # Setup logging
    logging.setup(CONF, 'glance')

    if CONF.token:
        CONF.sourcetoken = CONF.token
        CONF.targettoken = CONF.token

    command = lookup_command(CONF.command)

    try:
        command(CONF, CONF.args)
    except TypeError as e:
        LOG.error(_LE(command.__doc__) % {'prog': command.__name__})  # noqa
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))
    except ValueError as e:
        LOG.error(_LE(command.__doc__) % {'prog': command.__name__})  # noqa
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))


if __name__ == '__main__':
    main()
