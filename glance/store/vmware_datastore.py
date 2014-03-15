# Copyright 2014 OpenStack, LLC
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

"""Storage backend for VMware Datastore"""

import hashlib
import httplib
import os

import netaddr
from oslo.config import cfg
from oslo.vmware import api
import six.moves.urllib.parse as urlparse

from glance.common import exception
from glance.openstack.common import excutils
import glance.openstack.common.log as logging
import glance.store
import glance.store.base
import glance.store.location


LOG = logging.getLogger(__name__)

MAX_REDIRECTS = 5
DEFAULT_STORE_IMAGE_DIR = '/openstack_glance'
DEFAULT_ESX_DATACENTER_PATH = 'ha-datacenter'
DS_URL_PREFIX = '/folder'
STORE_SCHEME = 'vsphere'

# check that datacenter/datastore combination is valid
_datastore_info_valid = False

vmware_opts = [
    cfg.StrOpt('vmware_server_host',
               help=_('ESX/ESXi or vCenter Server target system. '
                      'The server value can be an IP address or a DNS name.')),
    cfg.StrOpt('vmware_server_username',
               help=_('Username for authenticating with '
                      'VMware ESX/VC server.')),
    cfg.StrOpt('vmware_server_password',
               help=_('Password for authenticating with '
                      'VMware ESX/VC server.'),
               secret=True),
    cfg.StrOpt('vmware_datacenter_path',
               default=DEFAULT_ESX_DATACENTER_PATH,
               help=_('Inventory path to a datacenter. '
                      'If the vmware_server_host specified is an ESX/ESXi, '
                      'the vmware_datacenter_path is optional. If specified, '
                      'it should be "ha-datacenter".')),
    cfg.StrOpt('vmware_datastore_name',
               help=_('Datastore associated with the datacenter.')),
    cfg.IntOpt('vmware_api_retry_count',
               default=10,
               help=_('Number of times VMware ESX/VC server API must be '
                      'retried upon connection related issues.')),
    cfg.IntOpt('vmware_task_poll_interval',
               default=5,
               help=_('The interval used for polling remote tasks '
                      'invoked on VMware ESX/VC server.')),
    cfg.StrOpt('vmware_store_image_dir',
               default=DEFAULT_STORE_IMAGE_DIR,
               help=_('The name of the directory where the glance images '
                      'will be stored in the VMware datastore.')),
    cfg.BoolOpt('vmware_api_insecure',
                default=False,
                help=_('Allow to perform insecure SSL requests to ESX/VC.')),
]

CONF = cfg.CONF
CONF.register_opts(vmware_opts)


def is_valid_ipv6(address):
    try:
        return netaddr.valid_ipv6(address)
    except Exception:
        return False


def http_response_iterator(conn, response, size):
    """Return an iterator for a file-like object.

    :param conn: HTTP(S) Connection
    :param response: httplib.HTTPResponse object
    :param size: Chunk size to iterate with
    """
    try:
        chunk = response.read(size)
        while chunk:
            yield chunk
            chunk = response.read(size)
    finally:
        conn.close()


class _Reader(object):

    def __init__(self, data, checksum):
        self.data = data
        self.checksum = checksum
        self._size = 0

    def read(self, length):
        result = self.data.read(length)
        self._size += len(result)
        self.checksum.update(result)
        return result

    @property
    def size(self):
        return self._size


class StoreLocation(glance.store.location.StoreLocation):
    """Class describing an VMware URI.

    An VMware URI can look like any of the following:
    vsphere://server_host/folder/file_path?dcPath=dc_path&dsName=ds_name
    """

    def process_specs(self):
        self.scheme = self.specs.get('scheme', STORE_SCHEME)
        self.server_host = self.specs.get('server_host')
        self.path = os.path.join(DS_URL_PREFIX,
                                 self.specs.get('image_dir').strip('/'),
                                 self.specs.get('image_id'))
        dc_path = self.specs.get('datacenter_path')
        if dc_path is not None:
            param_list = {'dcPath': self.specs.get('datacenter_path'),
                          'dsName': self.specs.get('datastore_name')}
        else:
            param_list = {'dsName': self.specs.get('datastore_name')}
        self.query = urlparse.urlencode(param_list)

    def get_uri(self):
        if is_valid_ipv6(self.server_host):
            base_url = '%s://[%s]%s' % (self.scheme,
                                        self.server_host, self.path)
        else:
            base_url = '%s://%s%s' % (self.scheme,
                                      self.server_host, self.path)

        return '%s?%s' % (base_url, self.query)

    def _is_valid_path(self, path):
        return path.startswith(
            os.path.join(DS_URL_PREFIX,
                         CONF.vmware_store_image_dir.strip('/')))

    def parse_uri(self, uri):
        if not uri.startswith('%s://' % STORE_SCHEME):
            reason = (_("URI %(uri)s must start with %(scheme)s://") %
                      {'uri': uri, 'scheme': STORE_SCHEME})
            LOG.error(reason)
            raise exception.BadStoreUri(reason)
        (self.scheme, self.server_host,
         path, params, query, fragment) = urlparse.urlparse(uri)
        if not query:
            path = path.split('?')
            if self._is_valid_path(path[0]):
                self.path = path[0]
                self.query = path[1]
                return
        elif self._is_valid_path(path):
            self.path = path
            self.query = query
            return
        reason = (_('Badly formed VMware datastore URI %(uri)s.')
                  % {'uri': uri})
        LOG.debug(reason)
        raise exception.BadStoreUri(reason)


class Store(glance.store.base.Store):
    """An implementation of the VMware datastore adapter."""

    def get_schemes(self):
        return (STORE_SCHEME,)

    def configure(self):
        self.scheme = STORE_SCHEME
        self.server_host = self._option_get('vmware_server_host')
        self.server_username = self._option_get('vmware_server_username')
        self.server_password = self._option_get('vmware_server_password')
        self.api_retry_count = CONF.vmware_api_retry_count
        self.task_poll_interval = CONF.vmware_task_poll_interval
        self.api_insecure = CONF.vmware_api_insecure
        self._session = api.VMwareAPISession(self.server_host,
                                             self.server_username,
                                             self.server_password,
                                             self.api_retry_count,
                                             self.task_poll_interval)
        self._service_content = self._session.vim.service_content

    def configure_add(self):
        self.datacenter_path = CONF.vmware_datacenter_path
        self.datastore_name = self._option_get('vmware_datastore_name')
        global _datastore_info_valid
        if not _datastore_info_valid:
            search_index_moref = self._service_content.searchIndex

            inventory_path = ('%s/datastore/%s'
                              % (self.datacenter_path, self.datastore_name))
            ds_moref = self._session.invoke_api(self._session.vim,
                                                'FindByInventoryPath',
                                                search_index_moref,
                                                inventoryPath=inventory_path)
            if ds_moref is None:
                reason = (_("Could not find datastore %(ds_name)s "
                            "in datacenter %(dc_path)s")
                          % {'ds_name': self.datastore_name,
                             'dc_path': self.datacenter_path})
                raise exception.BadStoreConfiguration(
                    store_name='vmware_datastore', reason=reason)
            else:
                _datastore_info_valid = True
        self.store_image_dir = CONF.vmware_store_image_dir

    def _option_get(self, param):
        result = getattr(CONF, param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % {'param': param})
            raise exception.BadStoreConfiguration(
                store_name='vmware_datastore', reason=reason)
        return result

    def _build_vim_cookie_header(self, vim_cookies):
        """Build ESX host session cookie header."""
        if len(list(vim_cookies)) > 0:
            cookie = list(vim_cookies)[0]
            return cookie.name + '=' + cookie.value

    def add(self, image_id, image_file, image_size):
        """Stores an image file with supplied identifier to the backend
        storage system and returns a tuple containing information
        about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes
        :retval tuple of URL in backing store, bytes written, checksum
                and a dictionary with storage system specific information
        :raises `glance.common.exception.Duplicate` if the image already
                existed
                `glance.common.exception.UnexpectedStatus` if the upload
                request returned an unexpected status. The expected responses
                are 201 Created and 200 OK.
        """
        checksum = hashlib.md5()
        image_file = _Reader(image_file, checksum)
        loc = StoreLocation({'scheme': self.scheme,
                             'server_host': self.server_host,
                             'image_dir': self.store_image_dir,
                             'datacenter_path': self.datacenter_path,
                             'datastore_name': self.datastore_name,
                             'image_id': image_id})
        cookie = self._build_vim_cookie_header(
            self._session.vim.client.options.transport.cookiejar)
        headers = {'Cookie': cookie, 'Content-Length': image_size}
        try:
            conn = self._get_http_conn('PUT', loc, headers,
                                       content=image_file)
            res = conn.getresponse()
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception(_('Failed to upload content of image '
                                '%(image)s') % {'image': image_id})

        if res.status == httplib.CONFLICT:
            raise exception.Duplicate(_("Image file %(image_id)s already "
                                        "exists!") % {'image_id': image_id})

        if res.status not in (httplib.CREATED, httplib.OK):
            msg = (_('Failed to upload content of image %(image)s') %
                   {'image': image_id})
            LOG.error(msg)
            raise exception.UnexpectedStatus(status=res.status,
                                             body=res.read())

        return (loc.get_uri(), image_file.size, checksum.hexdigest(), {})

    def get(self, location):
        """Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location: `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        """
        cookie = self._build_vim_cookie_header(
            self._session.vim.client.options.transport.cookiejar)
        conn, resp, content_length = self._query(location,
                                                 'GET',
                                                 headers={'Cookie': cookie})
        iterator = http_response_iterator(conn, resp, self.CHUNKSIZE)

        class ResponseIndexable(glance.store.Indexable):

            def another(self):
                try:
                    return self.wrapped.next()
                except StopIteration:
                    return ''

        return (ResponseIndexable(iterator, content_length), content_length)

    def get_size(self, location):
        """Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the size

        :param location: `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        """
        cookie = self._build_vim_cookie_header(
            self._session.vim.client.options.transport.cookiejar)

        return self._query(location, 'HEAD', headers={'Cookie': cookie})[2]

    def delete(self, location):
        """Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        :raises NotFound if image does not exist
        """
        file_path = '[%s] %s' % (
            self.datastore_name,
            location.store_location.path[len(DS_URL_PREFIX):])
        search_index_moref = self._service_content.searchIndex
        dc_moref = self._session.invoke_api(self._session.vim,
                                            'FindByInventoryPath',
                                            search_index_moref,
                                            inventoryPath=self.datacenter_path)
        delete_task = self._session.invoke_api(
            self._session.vim,
            'DeleteDatastoreFile_Task',
            self._service_content.fileManager,
            name=file_path,
            datacenter=dc_moref)
        try:
            self._session.wait_for_task(delete_task)
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception(_('Failed to delete image %(image)s content.') %
                              {'image': location.image_id})

    def _query(self, location, method, headers, depth=0):
        if depth > MAX_REDIRECTS:
            msg = (_("The HTTP URL exceeded %(max_redirects)s maximum "
                     "redirects.") % {'max_redirects': MAX_REDIRECTS})
            LOG.debug(msg)
            raise exception.MaxRedirectsExceeded(redirects=MAX_REDIRECTS)
        loc = location.store_location
        try:
            conn = self._get_http_conn(method, loc, headers)
            resp = conn.getresponse()
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception(_('Failed to access image %(image)s content.') %
                              {'image': location.image_id})
        if resp.status >= 400:
            if resp.status == httplib.NOT_FOUND:
                msg = _('VMware datastore could not find image at URI.')
                LOG.debug(msg)
                raise exception.NotFound(msg)
            msg = (_('HTTP request returned a %(status)s status code.')
                   % {'status': resp.status})
            LOG.debug(msg)
            raise exception.BadStoreUri(msg)
        location_header = resp.getheader('location')
        if location_header:
            if resp.status not in (301, 302):
                msg = (_("The HTTP URL %(path)s attempted to redirect "
                         "with an invalid %(status)s status code.")
                       % {'path': loc.path, 'status': resp.status})
                LOG.debug(msg)
                raise exception.BadStoreUri(msg)
            location_class = glance.store.location.Location
            new_loc = location_class(location.store_name,
                                     location.store_location.__class__,
                                     uri=location_header,
                                     image_id=location.image_id,
                                     store_specs=location.store_specs)
            return self._query(new_loc, method, depth + 1)
        content_length = int(resp.getheader('content-length', 0))

        return (conn, resp, content_length)

    def _get_http_conn(self, method, loc, headers, content=None):
        conn_class = self._get_http_conn_class()
        conn = conn_class(loc.server_host)
        url = urlparse.quote('%s?%s' % (loc.path, loc.query))
        conn.request(method, url, content, headers)

        return conn

    def _get_http_conn_class(self):
        if self.api_insecure:
            return httplib.HTTPConnection
        return httplib.HTTPSConnection
