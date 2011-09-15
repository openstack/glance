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
import logging
import math
import tempfile
import urlparse

from glance.common import config
from glance.common import exception
import glance.store
import glance.store.base
import glance.store.location

try:
    from swift.common import client as swift_client
except ImportError:
    pass

DEFAULT_CONTAINER = 'glance'
DEFAULT_LARGE_OBJECT_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
DEFAULT_LARGE_OBJECT_CHUNK_SIZE = 200 * 1024 * 1024  # 200M

logger = logging.getLogger('glance.store.swift')


class StoreLocation(glance.store.location.StoreLocation):

    """
    Class describing a Swift URI. A Swift URI can look like any of
    the following:

        swift://user:pass@authurl.com/container/obj-id
        swift://account:user:pass@authurl.com/container/obj-id
        swift+http://user:pass@authurl.com/container/obj-id
        swift+https://user:pass@authurl.com/container/obj-id

    The swift+http:// URIs indicate there is an HTTP authentication URL.
    The default for Swift is an HTTPS authentication URL, so swift:// and
    swift+https:// are the same...
    """

    def process_specs(self):
        self.scheme = self.specs.get('scheme', 'swift+https')
        self.user = self.specs.get('user')
        self.key = self.specs.get('key')
        self.authurl = self.specs.get('authurl')
        self.container = self.specs.get('container')
        self.obj = self.specs.get('obj')

    def _get_credstring(self):
        if self.user:
            return '%s:%s@' % (self.user, self.key)
        return ''

    def get_uri(self):
        authurl = self.authurl
        if authurl.startswith('http://'):
            authurl = authurl[7:]
        elif authurl.startswith('https://'):
            authurl = authurl[8:]
        return "%s://%s%s/%s/%s" % (
            self.scheme,
            self._get_credstring(),
            authurl,
            self.container,
            self.obj)

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
            reason = _("URI Cannot contain more than one occurrence of a "
                      "scheme. If you have specified a "
                      "URI like swift://user:pass@http://authurl.com/v1/"
                      "container/obj, you need to change it to use the "
                      "swift+http:// scheme, like so: "
                      "swift+http://user:pass@authurl.com/v1/container/obj")
            raise exception.BadStoreUri(uri, reason)

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

            # User can be account:user, in which case cred_parts[0:2] will be
            # the account and user. Combine them into a single username of
            # account:user
            if len(cred_parts) == 1:
                reason = (_("Badly formed credentials '%(creds)s' in Swift "
                            "URI") % locals())
                raise exception.BadStoreUri(uri, reason)
            elif len(cred_parts) == 3:
                user = ':'.join(cred_parts[0:2])
            else:
                user = cred_parts[0]
            key = cred_parts[-1]
            self.user = user
            self.key = key
        else:
            self.user = None
        path_parts = path.split('/')
        try:
            self.obj = path_parts.pop()
            self.container = path_parts.pop()
            if not netloc.startswith('http'):
                # push hostname back into the remaining to build full authurl
                path_parts.insert(0, netloc)
                self.authurl = '/'.join(path_parts)
        except IndexError:
            reason = _("Badly formed Swift URI")
            raise exception.BadStoreUri(uri, reason)

    @property
    def swift_auth_url(self):
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

        full_url = ''.join([auth_scheme, self.authurl])
        return full_url


class Store(glance.store.base.Store):
    """An implementation of the swift backend adapter."""

    EXAMPLE_URL = "swift://<USER>:<KEY>@<AUTH_ADDRESS>/<CONTAINER>/<FILE>"

    CHUNKSIZE = 65536

    def configure(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.auth_address = self._option_get('swift_store_auth_address')
        self.user = self._option_get('swift_store_user')
        self.key = self._option_get('swift_store_key')
        self.container = self.options.get('swift_store_container',
                                          DEFAULT_CONTAINER)
        try:
            if self.options.get('swift_store_large_object_size'):
                self.large_object_size = int(
                    self.options.get('swift_store_large_object_size')
                    ) * (1024 * 1024)  # Size specified in MB in conf files
            else:
                self.large_object_size = DEFAULT_LARGE_OBJECT_SIZE

            if self.options.get('swift_store_large_object_chunk_size'):
                self.large_object_chunk_size = int(
                    self.options.get('swift_store_large_object_chunk_size')
                    ) * (1024 * 1024)  # Size specified in MB in conf files
            else:
                self.large_object_chunk_size = DEFAULT_LARGE_OBJECT_CHUNK_SIZE
        except Exception, e:
            reason = _("Error in configuration options: %s") % e
            logger.error(reason)
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

        self.snet = config.get_option(
            self.options, 'swift_enable_snet', type='bool', default=False)

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
        swift_conn = self._make_swift_connection(
            auth_url=loc.swift_auth_url, user=loc.user, key=loc.key)

        try:
            (resp_headers, resp_body) = swift_conn.get_object(
                container=loc.container, obj=loc.obj,
                resp_chunk_size=self.CHUNKSIZE)
        except swift_client.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                raise exception.NotFound(_("Swift could not find image at "
                                         "uri %(uri)s") % locals())
            else:
                raise

        #if expected_size:
        #    obj_size = int(resp_headers['content-length'])
        #    if  obj_size != expected_size:
        #        raise glance.store.BackendException(
        #            "Expected %s byte file, Swift has %s bytes" %
        #            (expected_size, obj_size))

        return (resp_body, None)

    def _make_swift_connection(self, auth_url, user, key):
        """
        Creates a connection using the Swift client library.
        """
        snet = self.snet
        logger.debug(_("Creating Swift connection with "
                     "(auth_address=%(auth_url)s, user=%(user)s, "
                     "key=%(key)s, snet=%(snet)s)") % locals())
        return swift_client.Connection(
            authurl=auth_url, user=user, key=key, snet=snet)

    def _option_get(self, param):
        result = self.options.get(param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % locals())
            logger.error(reason)
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
        """
        swift_conn = self._make_swift_connection(
            auth_url=self.full_auth_address, user=self.user, key=self.key)

        create_container_if_missing(self.container, swift_conn, self.options)

        obj_name = str(image_id)
        location = StoreLocation({'scheme': self.scheme,
                                  'container': self.container,
                                  'obj': obj_name,
                                  'authurl': self.auth_address,
                                  'user': self.user,
                                  'key': self.key})

        logger.debug(_("Adding image object '%(obj_name)s' "
                       "to Swift") % locals())
        try:
            if image_size < self.large_object_size:
                # image_size == 0 is when we don't know the size
                # of the image. This can occur with older clients
                # that don't inspect the payload size, and we simply
                # try to put the object into Swift and hope for the
                # best...
                obj_etag = swift_conn.put_object(self.container, obj_name,
                                                 image_file)
            else:
                # Write the image into Swift in chunks. We cannot
                # stream chunks of the webob.Request.body_file, unfortunately,
                # so we must write chunks of the body_file into a temporary
                # disk buffer, and then pass this disk buffer to Swift.
                bytes_left = image_size
                chunk_id = 1
                total_chunks = int(math.ceil(
                    float(image_size) / float(self.large_object_chunk_size)))
                checksum = hashlib.md5()
                while bytes_left > 0:
                    with tempfile.NamedTemporaryFile() as disk_buffer:
                        chunk_size = min(self.large_object_chunk_size,
                                         bytes_left)
                        logger.debug(_("Writing %(chunk_size)d bytes for "
                                       "chunk %(chunk_id)d/"
                                       "%(total_chunks)d to disk buffer "
                                       "for image %(image_id)s")
                                     % locals())
                        chunk = image_file.read(chunk_size)
                        checksum.update(chunk)
                        disk_buffer.write(chunk)
                        disk_buffer.flush()
                        logger.debug(_("Writing chunk %(chunk_id)d/"
                                       "%(total_chunks)d to Swift "
                                       "for image %(image_id)s")
                                     % locals())
                        chunk_etag = swift_conn.put_object(
                            self.container,
                            "%s-%05d" % (obj_name, chunk_id),
                            open(disk_buffer.name, 'rb'))
                        logger.debug(_("Wrote chunk %(chunk_id)d/"
                                       "%(total_chunks)d to Swift "
                                       "returning MD5 of content: "
                                       "%(chunk_etag)s")
                                     % locals())
                    bytes_left -= self.large_object_chunk_size
                    chunk_id += 1

                # Now we write the object manifest and return the
                # manifest's etag...
                manifest = "%s/%s" % (self.container, obj_name)
                headers = {'ETag': hashlib.md5("").hexdigest(),
                           'X-Object-Manifest': manifest}

                # The ETag returned for the manifest is actually the
                # MD5 hash of the concatenated checksums of the strings
                # of each chunk...so we ignore this result in favour of
                # the MD5 of the entire image file contents, so that
                # users can verify the image file contents accordingly
                _ignored = swift_conn.put_object(self.container, obj_name,
                                                 None, headers=headers)
                obj_etag = checksum.hexdigest()

            # NOTE: We return the user and key here! Have to because
            # location is used by the API server to return the actual
            # image data. We *really* should consider NOT returning
            # the location attribute from GET /images/<ID> and
            # GET /images/details

            return (location.get_uri(), image_size, obj_etag)
        except swift_client.ClientException, e:
            if e.http_status == httplib.CONFLICT:
                raise exception.Duplicate(_("Swift already has an image at "
                                          "location %s") % location.get_uri())
            msg = (_("Failed to add object to Swift.\n"
                   "Got error from Swift: %(e)s") % locals())
            logger.error(msg)
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
        swift_conn = self._make_swift_connection(
            auth_url=loc.swift_auth_url, user=loc.user, key=loc.key)

        try:
            # We request the manifest for the object. If one exists,
            # that means the object was uploaded in chunks/segments,
            # and we need to delete all the chunks as well as the
            # manifest.
            manifest = None
            try:
                headers = swift_conn.head_object(loc.container, loc.obj)
                manifest = headers.get('x-object-manifest')
            except swift_client.ClientException, e:
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

            swift_conn.delete_object(loc.container, loc.obj)
        except swift_client.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                raise exception.NotFound(_("Swift could not find image at "
                                         "uri %(uri)s") % locals())
            else:
                raise


def create_container_if_missing(container, swift_conn, options):
    """
    Creates a missing container in Swift if the
    ``swift_store_create_container_on_put`` option is set.

    :param container: Name of container to create
    :param swift_conn: Connection to Swift
    :param options: Option mapping
    """
    try:
        swift_conn.head_container(container)
    except swift_client.ClientException, e:
        if e.http_status == httplib.NOT_FOUND:
            add_container = config.get_option(options,
                                'swift_store_create_container_on_put',
                                type='bool', default=False)
            if add_container:
                try:
                    swift_conn.put_container(container)
                except ClientException, e:
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


glance.store.register_store(__name__, ['swift', 'swift+http', 'swift+https'])
