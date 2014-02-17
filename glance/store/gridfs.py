# Copyright 2013 Red Hat, Inc
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

"""Storage backend for GridFS"""
from __future__ import absolute_import

from oslo.config import cfg
import six.moves.urllib.parse as urlparse

from glance.common import exception
from glance.openstack.common import excutils
import glance.openstack.common.log as logging
import glance.store.base
import glance.store.location

try:
    import gridfs
    import gridfs.errors
    import pymongo
    import pymongo.uri_parser as uri_parser
except ImportError:
    pymongo = None

LOG = logging.getLogger(__name__)

gridfs_opts = [
    cfg.StrOpt('mongodb_store_uri',
               help="Hostname or IP address of the instance to connect to, "
                    "or a mongodb URI, or a list of hostnames / mongodb URIs. "
                    "If host is an IPv6 literal it must be enclosed "
                    "in '[' and ']' characters following the RFC2732 "
                    "URL syntax (e.g. '[::1]' for localhost)."),
    cfg.StrOpt('mongodb_store_db', default=None, help='Database to use.'),
]

CONF = cfg.CONF
CONF.register_opts(gridfs_opts)


class StoreLocation(glance.store.location.StoreLocation):
    """
    Class describing an gridfs URI:

        gridfs://<IMAGE_ID>

    Connection information has been consciously omitted for
    security reasons, since this location will be stored in glance's
    database and can be queried from outside.

    Note(flaper87): Make connection info available if user wants so
    by adding a new configuration parameter `mongdb_store_insecure`.
    """

    def get_uri(self):
        return "gridfs://%s" % self.specs.get("image_id")

    def parse_uri(self, uri):
        """
        This method should fix any issue with the passed URI. Right now,
        it just sets image_id value in the specs dict.

        :param uri: Current set URI
        """
        parsed = urlparse.urlparse(uri)
        assert parsed.scheme in ('gridfs',)
        self.specs["image_id"] = parsed.netloc


class Store(glance.store.base.Store):
    """GridFS adapter"""

    EXAMPLE_URL = "gridfs://<IMAGE_ID>"

    def get_schemes(self):
        return ('gridfs',)

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        if pymongo is None:
            msg = _("Missing dependencies: pymongo")
            raise exception.BadStoreConfiguration(store_name="gridfs",
                                                  reason=msg)

        self.mongodb_uri = self._option_get('mongodb_store_uri')

        parsed = uri_parser.parse_uri(self.mongodb_uri)
        self.mongodb_db = self._option_get('mongodb_store_db') or \
            parsed.get("database")

        self.mongodb = pymongo.MongoClient(self.mongodb_uri)
        self.fs = gridfs.GridFS(self.mongodb[self.mongodb_db])

    def _option_get(self, param):
        result = getattr(CONF, param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % {'param': param})
            LOG.debug(reason)
            raise exception.BadStoreConfiguration(store_name="gridfs",
                                                  reason=reason)
        return result

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        image = self._get_file(location)
        return (image, image.length)

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the image_size (or 0
        if unavailable)

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        """
        try:
            key = self._get_file(location)
            return key.length
        except Exception:
            return 0

    def _get_file(self, location):
        store_location = location
        if isinstance(location, glance.store.location.Location):
            store_location = location.store_location
        try:

            parsed = urlparse.urlparse(store_location.get_uri())
            return self.fs.get(parsed.netloc)
        except gridfs.errors.NoFile:
            msg = _("Could not find %s image in GridFS") % \
                store_location.get_uri()
            LOG.debug(msg)
            raise exception.NotFound(msg)

    def add(self, image_id, image_file, image_size):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns a tuple containing information
        about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes

        :retval tuple of URL in backing store, bytes written, checksum
                and a dictionary with storage system specific information
        :raises `glance.common.exception.Duplicate` if the image already
                existed
        """
        loc = StoreLocation({'image_id': image_id})

        if self.fs.exists(image_id):
            raise exception.Duplicate(_("GridFS already has an image at "
                                        "location %s") % loc.get_uri())

        LOG.debug(_("Adding a new image to GridFS with id %(id)s and "
                    "size %(size)s") % {'id': image_id,
                                        'size': image_size})

        try:
            self.fs.put(image_file, _id=image_id)
            image = self._get_file(loc)
        except Exception:
            # Note(zhiyan): clean up already received data when
            # error occurs such as ImageSizeLimitExceeded exception.
            with excutils.save_and_reraise_exception():
                self.fs.delete(image_id)

        LOG.debug(_("Uploaded image %(id)s, md5 %(md5)s, length %(length)s "
                    "to GridFS") % {'id': image._id,
                                    'md5': image.md5,
                                    'length': image.length})

        return (loc.get_uri(), image.length, image.md5, {})

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """
        image = self._get_file(location)
        self.fs.delete(image._id)
        LOG.debug("Deleted image %s from GridFS")
