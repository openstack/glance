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
    cfg.StrOpt('swift_store_endpoint_type', default='publicURL'),
    cfg.StrOpt('swift_store_service_type', default='object-store'),
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
            reason = _("URI cannot contain more than one occurrence "
                       "of a scheme. If you have specified a URI like "
                       "swift://user:pass@http://authurl.com/v1/container/obj"
                       ", you need to change it to use the "
                       "swift+http:// scheme, like so: "
                       "swift+http://user:pass@authurl.com/v1/container/obj")
            LOG.debug(_("Invalid store uri %(uri)s: %(reason)s") % locals())
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
                reason = (_("Badly formed credentials '%(creds)s' in Swift "
                            "URI") % locals())
                LOG.debug(reason)
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
            reason = _("Badly formed Swift URI: %s") % uri
            LOG.debug(reason)
            raise exception.BadStoreUri()

    @property
    def swift_url(self):
        """
        Creates a fully-qualified auth url that the Swift client library can
        use. The scheme for the auth_url is determined using the scheme
        included in the `location` field.

        HTTPS is assumed, unless 'swift+http' is specified.
        """
        if self.auth_or_store_url.startswith('http'):
            return self.auth_or_store_url
        else:
            if self.scheme in ('swift+https', 'swift'):
                auth_scheme = 'https://'
            else:
                auth_scheme = 'http://'

            return ''.join([auth_scheme, self.auth_or_store_url])


def Store(context=None, loc=None):
    if (CONF.swift_store_multi_tenant and
            (loc is None or loc.store_location.user is None)):
        return MultiTenantStore(context, loc)
    return SingleTenantStore(context, loc)


class BaseStore(glance.store.base.Store):
    CHUNKSIZE = 65536

    def get_schemes(self):
        return ('swift+https', 'swift', 'swift+http')

    def configure(self):
        _obj_size = self._option_get('swift_store_large_object_size')
        self.large_object_size = _obj_size * ONE_MB
        _chunk_size = self._option_get('swift_store_large_object_chunk_size')
        self.large_object_chunk_size = _chunk_size * ONE_MB
        self.admin_tenants = CONF.swift_store_admin_tenants
        self.region = CONF.swift_store_region
        self.service_type = CONF.swift_store_service_type
        self.endpoint_type = CONF.swift_store_endpoint_type
        self.snet = CONF.swift_enable_snet

    def get(self, location, connection=None):
        location = location.store_location
        if not connection:
            connection = self.get_connection(location)

        try:
            resp_headers, resp_body = connection.get_object(
                    container=location.container, obj=location.obj,
                    resp_chunk_size=self.CHUNKSIZE)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_uri()
                raise exception.NotFound(_("Swift could not find image at "
                                           "uri %(uri)s") % locals())
            else:
                raise

        class ResponseIndexable(glance.store.Indexable):
            def another(self):
                try:
                    return self.wrapped.next()
                except StopIteration:
                    return ''

        length = int(resp_headers.get('content-length', 0))
        return (ResponseIndexable(resp_body, length), length)

    def get_size(self, location, connection=None):
        location = location.store_location
        if not connection:
            connection = self.get_connection(location)
        try:
            resp_headers = connection.head_object(
                    container=location.container, obj=location.obj)
            return int(resp_headers.get('content-length', 0))
        except Exception:
            return 0

    def _option_get(self, param):
        result = getattr(CONF, param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % locals())
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="swift",
                                                  reason=reason)
        return result

    def add(self, image_id, image_file, image_size, connection=None):
        location = self.create_location(image_id)
        if not connection:
            connection = self.get_connection(location)

        self._create_container_if_missing(location.container, connection)

        LOG.debug(_("Adding image object '%(obj_name)s' "
                    "to Swift") % dict(obj_name=location.obj))
        try:
            if image_size > 0 and image_size < self.large_object_size:
                # Image size is known, and is less than large_object_size.
                # Send to Swift with regular PUT.
                obj_etag = connection.put_object(location.container,
                                                 location.obj, image_file,
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

                    chunk_name = "%s-%05d" % (location.obj, chunk_id)
                    reader = ChunkReader(image_file, checksum, chunk_size)
                    chunk_etag = connection.put_object(
                        location.container, chunk_name, reader,
                        content_length=content_length)
                    bytes_read = reader.bytes_read
                    msg = _("Wrote chunk %(chunk_name)s (%(chunk_id)d/"
                            "%(total_chunks)s) of length %(bytes_read)d "
                            "to Swift returning MD5 of content: "
                            "%(chunk_etag)s")
                    LOG.debug(msg % locals())

                    if bytes_read == 0:
                        # Delete the last chunk, because it's of zero size.
                        # This will happen if size == 0.
                        LOG.debug(_("Deleting final zero-length chunk"))
                        connection.delete_object(location.container,
                                                 chunk_name)
                        break

                    chunk_id += 1
                    combined_chunks_size += bytes_read

                # In the case we have been given an unknown image size,
                # set the size to the total size of the combined chunks.
                if image_size == 0:
                    image_size = combined_chunks_size

                # Now we write the object manifest and return the
                # manifest's etag...
                manifest = "%s/%s" % (location.container, location.obj)
                headers = {'ETag': hashlib.md5("").hexdigest(),
                           'X-Object-Manifest': manifest}

                # The ETag returned for the manifest is actually the
                # MD5 hash of the concatenated checksums of the strings
                # of each chunk...so we ignore this result in favour of
                # the MD5 of the entire image file contents, so that
                # users can verify the image file contents accordingly
                connection.put_object(location.container, location.obj,
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
                                            "location %s") %
                                          location.get_uri())
            msg = (_("Failed to add object to Swift.\n"
                     "Got error from Swift: %(e)s") % locals())
            LOG.error(msg)
            raise glance.store.BackendException(msg)

    def delete(self, location, connection=None):
        location = location.store_location
        if not connection:
            connection = self.get_connection(location)

        try:
            # We request the manifest for the object. If one exists,
            # that means the object was uploaded in chunks/segments,
            # and we need to delete all the chunks as well as the
            # manifest.
            manifest = None
            try:
                headers = connection.head_object(
                        location.container, location.obj)
                manifest = headers.get('x-object-manifest')
            except swiftclient.ClientException, e:
                if e.http_status != httplib.NOT_FOUND:
                    raise
            if manifest:
                # Delete all the chunks before the object manifest itself
                obj_container, obj_prefix = manifest.split('/', 1)
                segments = connection.get_container(
                        obj_container, prefix=obj_prefix)[1]
                for segment in segments:
                    # TODO(jaypipes): This would be an easy area to parallelize
                    # since we're simply sending off parallelizable requests
                    # to Swift to delete stuff. It's not like we're going to
                    # be hogging up network or file I/O here...
                    connection.delete_object(
                            obj_container, segment['name'])

            else:
                connection.delete_object(location.container, location.obj)

        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_uri()
                raise exception.NotFound(_("Swift could not find image at "
                                           "uri %(uri)s") % locals())
            else:
                raise

    def _create_container_if_missing(self, container, connection):
        """
        Creates a missing container in Swift if the
        ``swift_store_create_container_on_put`` option is set.

        :param container: Name of container to create
        :param connection: Connection to swift service
        """
        try:
            connection.head_container(container)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                if CONF.swift_store_create_container_on_put:
                    try:
                        connection.put_container(container)
                    except swiftclient.ClientException, e:
                        msg = _("Failed to add container to Swift.\n"
                                "Got error from Swift: %(e)s") % locals()
                        raise glance.store.BackendException(msg)
                else:
                    msg = (_("The container %(container)s does not exist in "
                             "Swift. Please set the "
                             "swift_store_create_container_on_put option"
                             "to add container to Swift automatically.") %
                           locals())
                    raise glance.store.BackendException(msg)
            else:
                raise

    def get_connection(self):
        raise NotImplemented()

    def create_location(self):
        raise NotImplemented()


class SingleTenantStore(BaseStore):
    EXAMPLE_URL = "swift://<USER>:<KEY>@<AUTH_ADDRESS>/<CONTAINER>/<FILE>"

    def configure(self):
        super(SingleTenantStore, self).configure()
        self.auth_version = self._option_get('swift_store_auth_version')

    def configure_add(self):
        self.auth_address = self._option_get('swift_store_auth_address')
        if self.auth_address.startswith('http://'):
            self.scheme = 'swift+http'
        else:
            self.scheme = 'swift+https'
        self.container = CONF.swift_store_container
        self.user = self._option_get('swift_store_user')
        self.key = self._option_get('swift_store_key')

    def create_location(self, image_id):
        specs = {'scheme': self.scheme,
                 'container': self.container,
                 'obj': str(image_id),
                 'auth_or_store_url': self.auth_address,
                 'user': self.user,
                 'key': self.key}
        return StoreLocation(specs)

    def get_connection(self, location):
        if not location.user:
            reason = (_("Location is missing user:password information."))
            LOG.debug(reason)
            raise exception.BadStoreUri(message=reason)

        auth_url = location.swift_url
        if not auth_url.endswith('/'):
            auth_url += '/'

        if self.auth_version == '2':
            try:
                tenant_name, user = location.user.split(':')
            except ValueError:
                reason = (_("Badly formed tenant:user '%(user)s' in "
                            "Swift URI") % {'user': location.user})
                LOG.debug(reason)
                raise exception.BadStoreUri()
        else:
            tenant_name = None
            user = location.user

        os_options = {}
        if self.region:
            os_options['region_name'] = self.region
        os_options['endpoint_type'] = self.endpoint_type
        os_options['service_type'] = self.service_type

        return swiftclient.Connection(
                auth_url, user, location.key,
                tenant_name=tenant_name, snet=self.snet,
                auth_version=self.auth_version, os_options=os_options)


class MultiTenantStore(BaseStore):
    EXAMPLE_URL = "swift://<SWIFT_URL>/<CONTAINER>/<FILE>"

    def configure_add(self):
        self.container = CONF.swift_store_container
        if self.context is None:
            reason = _("Multi-tenant Swift storage requires a context.")
            raise exception.BadStoreConfiguration(store_name="swift",
                                                  reason=reason)
        if self.context.service_catalog is None:
            reason = _("Multi-tenant Swift storage requires "
                       "a service catalog.")
            raise exception.BadStoreConfiguration(store_name="swift",
                                                  reason=reason)
        self.storage_url = auth.get_endpoint(
                self.context.service_catalog, service_type=self.service_type,
                endpoint_region=self.region, endpoint_type=self.endpoint_type)
        if self.storage_url.startswith('http://'):
            self.scheme = 'swift+http'
        else:
            self.scheme = 'swift+https'

    def delete(self, location, connection=None):
        if not connection:
            connection = self.get_connection(location.store_location)
        super(MultiTenantStore, self).delete(location, connection)
        connection.delete_container(location.store_location.container)

    def set_acls(self, location, public=False, read_tenants=None,
                 write_tenants=None, connection=None):
        location = location.store_location
        if not connection:
            connection = self.get_connection(location)

        if read_tenants is None:
            read_tenants = []
        if write_tenants is None:
            write_tenants = []

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
            connection.post_container(location.container, headers=headers)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_uri()
                raise exception.NotFound(_("Swift could not find image at "
                                           "uri %(uri)s") % locals())
            else:
                raise

    def create_location(self, image_id):
        specs = {'scheme': self.scheme,
                 'container': self.container + '_' + str(image_id),
                 'obj': str(image_id),
                 'auth_or_store_url': self.storage_url}
        return StoreLocation(specs)

    def get_connection(self, location):
        return swiftclient.Connection(
                None, self.context.user, None,
                preauthurl=location.swift_url,
                preauthtoken=self.context.auth_tok,
                tenant_name=self.context.tenant,
                auth_version='2', snet=self.snet)


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
