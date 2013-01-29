# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

"""Storage backend for SWIFT"""

from __future__ import absolute_import

import hashlib
import httplib
import math
import urllib
import urlparse

from glance.common import auth
from glance.common import exception
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
import glance.store
import glance.store.base
import glance.store.location

try:
    import swiftclient
except ImportError:
    pass

LOG = logging.getLogger(__name__)

DEFAULT_CONTAINER = 'glance'
DEFAULT_LARGE_OBJECT_SIZE = 5 * 1024  # 5GB
DEFAULT_LARGE_OBJECT_CHUNK_SIZE = 200  # 200M
ONE_MB = 1000 * 1024

swift_opts = [
    cfg.BoolOpt('swift_enable_snet', default=False),
    cfg.StrOpt('swift_store_auth_address'),
    cfg.StrOpt('swift_store_user', secret=True),
    cfg.StrOpt('swift_store_key', secret=True),
    cfg.StrOpt('swift_store_auth_version', default='2'),
    cfg.StrOpt('swift_store_region'),
    cfg.StrOpt('swift_store_container',
               default=DEFAULT_CONTAINER),
    cfg.IntOpt('swift_store_large_object_size',
               default=DEFAULT_LARGE_OBJECT_SIZE),
    cfg.IntOpt('swift_store_large_object_chunk_size',
               default=DEFAULT_LARGE_OBJECT_CHUNK_SIZE),
    cfg.BoolOpt('swift_store_create_container_on_put', default=False),
    cfg.BoolOpt('swift_store_multi_tenant', default=False),
    cfg.ListOpt('swift_store_admin_tenants', default=[]),
    ]

CONF = cfg.CONF
CONF.register_opts(swift_opts)


class StoreLocation(glance.store.location.StoreLocation):

    """
    Class describing a Swift URI. A Swift URI can look like any of
    the following:

        swift://user:pass@authurl.com/container/obj-id
        swift://account:user:pass@authurl.com/container/obj-id
        swift+http://user:pass@authurl.com/container/obj-id
        swift+https://user:pass@authurl.com/container/obj-id

    When using multi-tenant a URI might look like this (a storage URL):

        swift+https://example.com/container/obj-id

    The swift+http:// URIs indicate there is an HTTP authentication URL.
    The default for Swift is an HTTPS authentication URL, so swift:// and
    swift+https:// are the same...
    """

    def process_specs(self):
        self.scheme = self.specs.get('scheme', 'swift+https')
        self.user = self.specs.get('user')
        self.key = self.specs.get('key')
        self.auth_or_store_url = self.specs.get('auth_or_store_url')
        self.container = self.specs.get('container')
        self.obj = self.specs.get('obj')

    def _get_credstring(self):
        if self.user and self.key:
            return '%s:%s@' % (urllib.quote(self.user), urllib.quote(self.key))
        return ''

    def get_uri(self):
        auth_or_store_url = self.auth_or_store_url
        if auth_or_store_url.startswith('http://'):
            auth_or_store_url = auth_or_store_url[len('http://'):]
        elif auth_or_store_url.startswith('https://'):
            auth_or_store_url = auth_or_store_url[len('https://'):]

        credstring = self._get_credstring()
        auth_or_store_url = auth_or_store_url.strip('/')
        container = self.container.strip('/')
        obj = self.obj.strip('/')

        return '%s://%s%s/%s/%s' % (self.scheme, credstring, auth_or_store_url,
                                    container, obj)

    def parse_uri(self, uri):
        """
        Parse URLs. This method fixes an issue where credentials specified
        in the URL are interpreted differently in Python 2.6.1+ than prior
        versions of Python. It also deals with the peculiarity that new-style
        Swift URIs have where a username can contain a ':', like so:

            swift://account:user:pass@authurl.com/container/obj
        """
        # Make sure that URIs that contain multiple schemes, such as:
        # swift://user:pass@http://authurl.com/v1/container/obj
        # are immediately rejected.
        if uri.count('://') != 1:
            reason = _(
                    "URI cannot contain more than one occurrence of a scheme."
                    "If you have specified a URI like "
                    "swift://user:pass@http://authurl.com/v1/container/obj"
                    ", you need to change it to use the swift+http:// scheme, "
                    "like so: "
                    "swift+http://user:pass@authurl.com/v1/container/obj"
                    )
            LOG.error(_("Invalid store URI: %(reason)s") % locals())
            raise exception.BadStoreUri(message=reason)

        pieces = urlparse.urlparse(uri)
        assert pieces.scheme in ('swift', 'swift+http', 'swift+https')
        self.scheme = pieces.scheme
        netloc = pieces.netloc
        path = pieces.path.lstrip('/')
        if netloc != '':
            # > Python 2.6.1
            if '@' in netloc:
                creds, netloc = netloc.split('@')
            else:
                creds = None
        else:
            # Python 2.6.1 compat
            # see lp659445 and Python issue7904
            if '@' in path:
                creds, path = path.split('@')
            else:
                creds = None
            netloc = path[0:path.find('/')].strip('/')
            path = path[path.find('/'):].strip('/')
        if creds:
            cred_parts = creds.split(':')
            if len(cred_parts) != 2:
                reason = (_("Badly formed credentials in Swift URI."))
                LOG.error(reason)
                raise exception.BadStoreUri()
            user, key = cred_parts
            self.user = urllib.unquote(user)
            self.key = urllib.unquote(key)
        else:
            self.user = None
            self.key = None
        path_parts = path.split('/')
        try:
            self.obj = path_parts.pop()
            self.container = path_parts.pop()
            if not netloc.startswith('http'):
                # push hostname back into the remaining to build full authurl
                path_parts.insert(0, netloc)
                self.auth_or_store_url = '/'.join(path_parts)
        except IndexError:
            reason = _("Badly formed Swift URI.")
            LOG.error(reason)
            raise exception.BadStoreUri()

    @property
    def swift_url(self):
        """
        Creates a fully-qualified auth url that the Swift client library can
        use. The scheme for the auth_url is determined using the scheme
        included in the `location` field.

        HTTPS is assumed, unless 'swift+http' is specified.
        """
        if self.scheme in ('swift+https', 'swift'):
            auth_scheme = 'https://'
        else:
            auth_scheme = 'http://'

        full_url = ''.join([auth_scheme, self.auth_or_store_url])
        return full_url


class Store(glance.store.base.Store):
    """An implementation of the swift backend adapter."""

    EXAMPLE_URL = "swift://<USER>:<KEY>@<AUTH_ADDRESS>/<CONTAINER>/<FILE>"

    CHUNKSIZE = 65536

    def get_schemes(self):
        return ('swift+https', 'swift', 'swift+http')

    def configure(self):
        self.snet = CONF.swift_enable_snet
        self.multi_tenant = CONF.swift_store_multi_tenant
        self.admin_tenants = CONF.swift_store_admin_tenants
        self.region = CONF.swift_store_region
        self.auth_version = self._option_get('swift_store_auth_version')
        self.storage_url = None
        self.token = None

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.auth_address = self._option_get('swift_store_auth_address')
        self.user = self._option_get('swift_store_user')
        self.key = self._option_get('swift_store_key')
        self.container = CONF.swift_store_container

        if self.multi_tenant:
            if self.context is None:
                reason = _("Multi-tenant Swift storage requires a context.")
                raise exception.BadStoreConfiguration(store_name="swift",
                                                      reason=reason)
            self.token = self.context.auth_tok
            self.key = None  # multi-tenant uses tokens, not (passwords)
            if self.context.tenant and self.context.user:
                self.user = self.context.tenant + ':' + self.context.user
            if self.context.service_catalog:
                service_catalog = self.context.service_catalog
                self.storage_url = self._get_swift_endpoint(service_catalog)

        try:
            # The config file has swift_store_large_object_*size in MB, but
            # internally we store it in bytes, since the image_size parameter
            # passed to add() is also in bytes.
            _obj_size = CONF.swift_store_large_object_size
            self.large_object_size = _obj_size * ONE_MB
            _obj_chunk_size = CONF.swift_store_large_object_chunk_size
            self.large_object_chunk_size = _obj_chunk_size * ONE_MB
        except cfg.ConfigFileValueError, e:
            reason = _("Error in configuration conf: %s") % e
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="swift",
                                                  reason=reason)

        self.scheme = 'swift+https'
        if self.auth_address.startswith('http://'):
            self.scheme = 'swift+http'
            self.full_auth_address = self.auth_address
        elif self.auth_address.startswith('https://'):
            self.full_auth_address = self.auth_address
        else:  # Defaults https
            self.full_auth_address = 'https://' + self.auth_address

    def _get_swift_endpoint(self, service_catalog):
        return auth.get_endpoint(service_catalog, service_type='object-store')

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        loc = location.store_location
        swift_conn = self._swift_connection_for_location(loc)

        try:
            (resp_headers, resp_body) = swift_conn.get_object(
                container=loc.container, obj=loc.obj,
                resp_chunk_size=self.CHUNKSIZE)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                msg = _("Swift could not find image at URI.")
                raise exception.NotFound(msg)
            else:
                raise

        class ResponseIndexable(glance.store.Indexable):
            def another(self):
                try:
                    return self.wrapped.next()
                except StopIteration:
                    return ''

        length = resp_headers.get('content-length')
        return (ResponseIndexable(resp_body, length), length)

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the image_size (or 0
        if unavailable)

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        """
        loc = location.store_location
        swift_conn = self._swift_connection_for_location(loc)

        try:
            resp_headers = swift_conn.head_object(container=loc.container,
                                                  obj=loc.obj)
            return resp_headers.get('content-length', 0)
        except Exception:
            return 0

    def _swift_connection_for_location(self, loc):
        if loc.user:
            return self._make_swift_connection(
                loc.swift_url, loc.user, loc.key, region=self.region)
        else:
            if self.multi_tenant:
                return self._make_swift_connection(
                    None, self.user, None,
                    storage_url=loc.swift_url, token=self.token)
            else:
                reason = (_("Location is missing user:password information."))
                LOG.error(reason)
                raise exception.BadStoreUri(message=reason)

    def _make_swift_connection(self, auth_url, user, key, region=None,
                               storage_url=None, token=None):
        """
        Creates a connection using the Swift client library.

        :param auth_url The authentication for v1 style Swift auth or
                        v2 style Keystone auth.
        :param user A string containing the tenant:user information.
        :param key  A string containing the key/password for the connection.
        :param region   A string containing the swift endpoint region
        :param storage_url A string containing the storage URL.
        :param token A string containing the token
        """
        snet = self.snet
        auth_version = self.auth_version
        full_auth_url = (auth_url if not auth_url or auth_url.endswith('/')
                         else auth_url + '/')
        LOG.debug(_("Creating Swift connection with "
                    "(auth_address=%(full_auth_url)s, user=%(user)s, "
                    "snet=%(snet)s, auth_version=%(auth_version)s)") %
                  locals())
        tenant_name = None
        if self.auth_version == '2':
            tenant_user = user.split(':')
            if len(tenant_user) != 2:
                reason = (_("Badly formed tenant:user '%(tenant_user)s' in "
                            "Swift URI") % locals())
                LOG.error(reason)
                raise exception.BadStoreUri()
            (tenant_name, user) = tenant_user

        if self.multi_tenant:
            #NOTE: multi-tenant supports v2 auth only
            return swiftclient.Connection(
                None, user, None, preauthurl=storage_url, preauthtoken=token,
                snet=snet, tenant_name=tenant_name, auth_version='2')
        else:
            os_options = {}
            if region:
                os_options['region_name'] = region
            return swiftclient.Connection(
                full_auth_url, user, key, snet=snet, os_options=os_options,
                tenant_name=tenant_name, auth_version=auth_version)

    def _option_get(self, param):
        result = getattr(CONF, param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % locals())
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="swift",
                                                  reason=reason)
        return result

    def add(self, image_id, image_file, image_size):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns an `glance.store.ImageAddResult` object
        containing information about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes

        :retval `glance.store.ImageAddResult` object
        :raises `glance.common.exception.Duplicate` if the image already
                existed

        Swift writes the image data using the scheme:
            ``swift://<USER>:<KEY>@<AUTH_ADDRESS>/<CONTAINER>/<ID>`
        where:
            <USER> = ``swift_store_user``
            <KEY> = ``swift_store_key``
            <AUTH_ADDRESS> = ``swift_store_auth_address``
            <CONTAINER> = ``swift_store_container``
            <ID> = The id of the image being added

        :note Swift auth URLs by default use HTTPS. To specify an HTTP
              auth URL, you can specify http://someurl.com for the
              swift_store_auth_address config option

        :note Swift cannot natively/transparently handle objects >5GB
              in size. So, if the image is greater than 5GB, we write
              chunks of image data to Swift and then write an manifest
              to Swift that contains information about the chunks.
              This same chunking process is used by default for images
              of an unknown size, as pushing them directly to swift would
              fail if the image turns out to be greater than 5GB.
        """
        swift_conn = self._make_swift_connection(
            self.full_auth_address, self.user, self.key,
            storage_url=self.storage_url, token=self.token)

        obj_name = str(image_id)
        if self.multi_tenant:
            # NOTE: When using multi-tenant we create containers for each
            # image so we can set permissions on each image in swift
            container = self.container + '_' + obj_name
            auth_or_store_url = self.storage_url
        else:
            container = self.container
            auth_or_store_url = self.auth_address

        create_container_if_missing(container, swift_conn)

        location = StoreLocation({'scheme': self.scheme,
                                  'container': container,
                                  'obj': obj_name,
                                  'auth_or_store_url': auth_or_store_url,
                                  'user': self.user,
                                  'key': self.key})

        LOG.debug(_("Adding image object '%(obj_name)s' "
                    "to Swift") % locals())
        try:
            if image_size > 0 and image_size < self.large_object_size:
                # Image size is known, and is less than large_object_size.
                # Send to Swift with regular PUT.
                obj_etag = swift_conn.put_object(container, obj_name,
                                                 image_file,
                                                 content_length=image_size)
            else:
                # Write the image into Swift in chunks.
                chunk_id = 1
                if image_size > 0:
                    total_chunks = str(int(
                        math.ceil(float(image_size) /
                                  float(self.large_object_chunk_size))))
                else:
                    # image_size == 0 is when we don't know the size
                    # of the image. This can occur with older clients
                    # that don't inspect the payload size.
                    LOG.debug(_("Cannot determine image size. Adding as a "
                                "segmented object to Swift."))
                    total_chunks = '?'

                checksum = hashlib.md5()
                combined_chunks_size = 0
                while True:
                    chunk_size = self.large_object_chunk_size
                    if image_size == 0:
                        content_length = None
                    else:
                        left = image_size - combined_chunks_size
                        if left == 0:
                            break
                        if chunk_size > left:
                            chunk_size = left
                        content_length = chunk_size

                    chunk_name = "%s-%05d" % (obj_name, chunk_id)
                    reader = ChunkReader(image_file, checksum, chunk_size)
                    chunk_etag = swift_conn.put_object(
                        container, chunk_name, reader,
                        content_length=content_length)
                    bytes_read = reader.bytes_read
                    msg = _("Wrote chunk %(chunk_name)s (%(chunk_id)d/"
                            "%(total_chunks)s) of length %(bytes_read)d "
                            "to Swift returning MD5 of content: "
                            "%(chunk_etag)s")
                    LOG.debug(msg % locals())

                    if bytes_read == 0:
                        # Delete the last chunk, because it's of zero size.
                        # This will happen if image_size == 0.
                        LOG.debug(_("Deleting final zero-length chunk"))
                        swift_conn.delete_object(container, chunk_name)
                        break

                    chunk_id += 1
                    combined_chunks_size += bytes_read

                # In the case we have been given an unknown image size,
                # set the image_size to the total size of the combined chunks.
                if image_size == 0:
                    image_size = combined_chunks_size

                # Now we write the object manifest and return the
                # manifest's etag...
                manifest = "%s/%s" % (container, obj_name)
                headers = {'ETag': hashlib.md5("").hexdigest(),
                           'X-Object-Manifest': manifest}

                # The ETag returned for the manifest is actually the
                # MD5 hash of the concatenated checksums of the strings
                # of each chunk...so we ignore this result in favour of
                # the MD5 of the entire image file contents, so that
                # users can verify the image file contents accordingly
                swift_conn.put_object(container, obj_name,
                                      None, headers=headers)
                obj_etag = checksum.hexdigest()

            # NOTE: We return the user and key here! Have to because
            # location is used by the API server to return the actual
            # image data. We *really* should consider NOT returning
            # the location attribute from GET /images/<ID> and
            # GET /images/details

            return (location.get_uri(), image_size, obj_etag)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.CONFLICT:
                raise exception.Duplicate(_("Swift already has an image at "
                                          "this location."))
            msg = (_("Failed to add object to Swift.\n"
                     "Got error from Swift: %(e)s") % locals())
            LOG.error(msg)
            raise glance.store.BackendException(msg)

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """
        loc = location.store_location
        swift_conn = self._swift_connection_for_location(loc)

        try:
            # We request the manifest for the object. If one exists,
            # that means the object was uploaded in chunks/segments,
            # and we need to delete all the chunks as well as the
            # manifest.
            manifest = None
            try:
                headers = swift_conn.head_object(loc.container, loc.obj)
                manifest = headers.get('x-object-manifest')
            except swiftclient.ClientException, e:
                if e.http_status != httplib.NOT_FOUND:
                    raise
            if manifest:
                # Delete all the chunks before the object manifest itself
                obj_container, obj_prefix = manifest.split('/', 1)
                for segment in swift_conn.get_container(obj_container,
                                                        prefix=obj_prefix)[1]:
                    # TODO(jaypipes): This would be an easy area to parallelize
                    # since we're simply sending off parallelizable requests
                    # to Swift to delete stuff. It's not like we're going to
                    # be hogging up network or file I/O here...
                    swift_conn.delete_object(obj_container, segment['name'])

            else:
                swift_conn.delete_object(loc.container, loc.obj)

            if self.multi_tenant:
                #NOTE: In multi-tenant mode containers are specific to
                # each object (Glance image)
                swift_conn.delete_container(loc.container)

        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                msg = _("Swift could not find image at URI.")
                raise exception.NotFound(msg)
            else:
                raise

    def set_acls(self, location, public=False, read_tenants=[],
                     write_tenants=[]):
        """
        Sets the read and write access control list for an image in the
        backend store.

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        :public A boolean indicating whether the image should be public.
        :read_tenants A list of tenant strings which should be granted
                      read access for an image.
        :write_tenants A list of tenant strings which should be granted
                      write access for an image.
        """
        if self.multi_tenant:
            loc = location.store_location
            swift_conn = self._swift_connection_for_location(loc)
            headers = {}
            if public:
                headers['X-Container-Read'] = ".r:*"
            elif read_tenants:
                headers['X-Container-Read'] = ','.join(read_tenants)
            else:
                headers['X-Container-Read'] = ''

            write_tenants.extend(self.admin_tenants)
            if write_tenants:
                headers['X-Container-Write'] = ','.join(write_tenants)
            else:
                headers['X-Container-Write'] = ''

            try:
                swift_conn.post_container(loc.container, headers=headers)
            except swiftclient.ClientException, e:
                if e.http_status == httplib.NOT_FOUND:
                    uri = location.get_store_uri()
                    msg = _("Swift could not find image at URI.")
                    raise exception.NotFound(msg)
                else:
                    raise


class ChunkReader(object):
    def __init__(self, fd, checksum, total):
        self.fd = fd
        self.checksum = checksum
        self.total = total
        self.bytes_read = 0

    def read(self, i):
        left = self.total - self.bytes_read
        if i > left:
            i = left
        result = self.fd.read(i)
        self.bytes_read += len(result)
        self.checksum.update(result)
        return result


def create_container_if_missing(container, swift_conn):
    """
    Creates a missing container in Swift if the
    ``swift_store_create_container_on_put`` option is set.

    :param container: Name of container to create
    :param swift_conn: Connection to Swift
    """
    try:
        swift_conn.head_container(container)
    except swiftclient.ClientException, e:
        if e.http_status == httplib.NOT_FOUND:
            if CONF.swift_store_create_container_on_put:
                try:
                    swift_conn.put_container(container)
                except swiftclient.ClientException, e:
                    msg = _("Failed to add container to Swift.\n"
                           "Got error from Swift: %(e)s") % locals()
                    raise glance.store.BackendException(msg)
            else:
                msg = (_("The container %(container)s does not exist in "
                       "Swift. Please set the "
                       "swift_store_create_container_on_put option"
                       "to add container to Swift automatically.")
                       % locals())
                raise glance.store.BackendException(msg)
        else:
            raise
