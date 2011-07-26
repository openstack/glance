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

import httplib
import logging
import urlparse

from glance.common import config
from glance.common import exception
import glance.store
import glance.store.location

DEFAULT_SWIFT_CONTAINER = 'glance'

logger = logging.getLogger('glance.store.swift')

glance.store.location.add_scheme_map({'swift': 'swift',
                                      'swift+http': 'swift',
                                      'swift+https': 'swift'})


class StoreLocation(glance.store.location.StoreLocation):

    """
    Class describing a Swift URI. A Swift URI can look like any of
    the following:

        swift://user:pass@authurl.com/container/obj-id
        swift+http://user:pass@authurl.com/container/obj-id
        swift+https://user:pass@authurl.com/container/obj-id

    The swift+https:// URIs indicate there is an HTTPS authentication URL
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
        return "%s://%s%s/%s/%s" % (
            self.scheme,
            self._get_credstring(),
            self.authurl,
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
                reason = "Badly formed credentials '%s' in Swift URI" % creds
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
            self.authurl = netloc
            if len(path_parts) > 0:
                self.authurl = netloc + '/' + '/'.join(path_parts).strip('/')
        except IndexError:
            reason = "Badly formed Swift URI"
            raise exception.BadStoreUri(uri, reason)


class SwiftBackend(glance.store.Backend):
    """An implementation of the swift backend adapter."""

    EXAMPLE_URL = "swift://<USER>:<KEY>@<AUTH_ADDRESS>/<CONTAINER>/<FILE>"

    CHUNKSIZE = 65536

    @classmethod
    def get(cls, location, expected_size=None, options=None):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator from Swift
        provided by Swift client's get_object() method.

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        from swift.common import client as swift_client

        # TODO(sirp): snet=False for now, however, if the instance of
        # swift we're talking to is within our same region, we should set
        # snet=True
        loc = location.store_location
        swift_conn = swift_client.Connection(
            authurl=loc.authurl, user=loc.user, key=loc.key, snet=False)

        try:
            (resp_headers, resp_body) = swift_conn.get_object(
                container=loc.container, obj=loc.obj,
                resp_chunk_size=cls.CHUNKSIZE)
        except swift_client.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                raise exception.NotFound("Swift could not find image at "
                                         "uri %(uri)s" % locals())

        if expected_size:
            obj_size = int(resp_headers['content-length'])
            if  obj_size != expected_size:
                raise glance.store.BackendException(
                    "Expected %s byte file, Swift has %s bytes" %
                    (expected_size, obj_size))

        return resp_body

    @classmethod
    def _option_get(cls, options, param):
        result = options.get(param)
        if not result:
            msg = ("Could not find %s in configuration options." % param)
            logger.error(msg)
            raise glance.store.BackendException(msg)
        return result

    @classmethod
    def add(cls, id, data, options):
        """
        Stores image data to Swift and returns a location that the image was
        written to.

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

        :param id: The opaque image identifier
        :param data: The image data to write, as a file-like object
        :param options: Conf mapping

        :retval Tuple with (location, size)
                The location that was written,
                and the size in bytes of the data written
        """
        from swift.common import client as swift_client
        container = options.get('swift_store_container',
                                DEFAULT_SWIFT_CONTAINER)

        # TODO(jaypipes): This needs to be checked every time
        # because of the decision to make glance.store.Backend's
        # interface all @classmethods. This is inefficient. Backend
        # should be a stateful object with options parsed once in
        # a constructor.
        auth_address = cls._option_get(options, 'swift_store_auth_address')
        user = cls._option_get(options, 'swift_store_user')
        key = cls._option_get(options, 'swift_store_key')

        scheme = 'swift+https'
        if auth_address.startswith('http://'):
            scheme = 'swift+http'
            full_auth_address = auth_address
        elif auth_address.startswith('https://'):
            full_auth_address = auth_address
        else:
            full_auth_address = 'https://' + auth_address  # Defaults https

        swift_conn = swift_client.Connection(
            authurl=full_auth_address, user=user, key=key, snet=False)

        logger.debug("Adding image object to Swift using "
                     "(auth_address=%(auth_address)s, user=%(user)s, "
                     "key=%(key)s)" % locals())

        create_container_if_missing(container, swift_conn, options)

        obj_name = str(id)
        location = StoreLocation({'scheme': scheme,
                                  'container': container,
                                  'obj': obj_name,
                                  'authurl': auth_address,
                                  'user': user,
                                  'key': key})

        try:
            obj_etag = swift_conn.put_object(container, obj_name, data)

            # NOTE: We return the user and key here! Have to because
            # location is used by the API server to return the actual
            # image data. We *really* should consider NOT returning
            # the location attribute from GET /images/<ID> and
            # GET /images/details

            # We do a HEAD on the newly-added image to determine the size
            # of the image. A bit slow, but better than taking the word
            # of the user adding the image with size attribute in the metadata
            resp_headers = swift_conn.head_object(container, obj_name)
            size = 0
            # header keys are lowercased by Swift
            if 'content-length' in resp_headers:
                size = int(resp_headers['content-length'])
            return (location.get_uri(), size, obj_etag)
        except swift_client.ClientException, e:
            if e.http_status == httplib.CONFLICT:
                raise exception.Duplicate("Swift already has an image at "
                                          "location %(location)s" % locals())
            msg = ("Failed to add object to Swift.\n"
                   "Got error from Swift: %(e)s" % locals())
            raise glance.store.BackendException(msg)

    @classmethod
    def delete(cls, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        """
        from swift.common import client as swift_client

        # TODO(sirp): snet=False for now, however, if the instance of
        # swift we're talking to is within our same region, we should set
        # snet=True
        loc = location.store_location
        swift_conn = swift_client.Connection(
            authurl=loc.authurl, user=loc.user, key=loc.key, snet=False)

        try:
            swift_conn.delete_object(loc.container, loc.obj)
        except swift_client.ClientException, e:
            if e.http_status == httplib.NOT_FOUND:
                uri = location.get_store_uri()
                raise exception.NotFound("Swift could not find image at "
                                         "uri %(uri)s" % locals())
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
    from swift.common import client as swift_client
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
                    msg = ("Failed to add container to Swift.\n"
                           "Got error from Swift: %(e)s" % locals())
                    raise glance.store.BackendException(msg)
            else:
                msg = ("The container %(container)s does not exist in "
                       "Swift. Please set the "
                       "swift_store_create_container_on_put option"
                       "to add container to Swift automatically."
                       % locals())
                raise glance.store.BackendException(msg)
        else:
            raise
