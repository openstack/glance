# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 Josh Durgin
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

"""Storage backend for RBD
   (RADOS (Reliable Autonomic Distributed Object Store) Block Device)"""
from __future__ import absolute_import
from __future__ import with_statement

import hashlib
import logging
import math

from glance.common import cfg
from glance.common import exception
import glance.store
import glance.store.base
import glance.store.location

try:
    import rados
    import rbd
except ImportError:
    pass

DEFAULT_POOL = 'rbd'
DEFAULT_CONFFILE = ''  # librados will locate the default conf file
DEFAULT_USER = None    # let librados decide based on the Ceph conf file
DEFAULT_CHUNKSIZE = 4  # in MiB

logger = logging.getLogger('glance.store.rbd')


class StoreLocation(glance.store.location.StoreLocation):
    """
    Class describing a RBD URI. This is of the form:

        rbd://image

    """

    def process_specs(self):
        self.image = self.specs.get('image')

    def get_uri(self):
        return ("rbd://%s" % self.image)

    def parse_uri(self, uri):
        if not uri.startswith('rbd://'):
            raise exception.BadStoreUri(uri, _('URI must start with rbd://'))
        self.image = uri[6:]


class ImageIterator(object):
    """
    Reads data from an RBD image, one chunk at a time.
    """

    def __init__(self, name, store):
        self.name = name
        self.pool = store.pool
        self.user = store.user
        self.conf_file = store.conf_file
        self.chunk_size = store.chunk_size

    def __iter__(self):
        try:
            with rados.Rados(conffile=self.conf_file,
                             rados_id=self.user) as conn:
                with conn.open_ioctx(self.pool) as ioctx:
                    with rbd.Image(ioctx, self.name) as image:
                        img_info = image.stat()
                        size = img_info['size']
                        bytes_left = size
                        while bytes_left > 0:
                            length = min(self.chunk_size, bytes_left)
                            data = image.read(size - bytes_left, length)
                            bytes_left -= len(data)
                            yield data
                        raise StopIteration()
        except rbd.ImageNotFound:
            raise exception.NotFound(
                _('RBD image %s does not exist') % self.name)


class Store(glance.store.base.Store):
    """An implementation of the RBD backend adapter."""

    EXAMPLE_URL = "rbd://<IMAGE>"

    opts = [
        cfg.IntOpt('rbd_store_chunk_size', default=DEFAULT_CHUNKSIZE),
        cfg.StrOpt('rbd_store_pool', default=DEFAULT_POOL),
        cfg.StrOpt('rbd_store_user', default=DEFAULT_USER),
        cfg.StrOpt('rbd_store_ceph_conf', default=DEFAULT_CONFFILE),
        ]

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.conf.register_opts(self.opts)
        try:
            self.chunk_size = self.conf.rbd_store_chunk_size * 1024 * 1024

            # these must not be unicode since they will be passed to a
            # non-unicode-aware C library
            self.pool = str(self.conf.rbd_store_pool)
            self.user = str(self.conf.rbd_store_user)
            self.conf_file = str(self.conf.rbd_store_ceph_conf)
        except cfg.ConfigFileValueError, e:
            reason = _("Error in store configuration: %s") % e
            logger.error(reason)
            raise exception.BadStoreConfiguration(store_name='rbd',
                                                  reason=reason)

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator for reading
        the image file

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        loc = location.store_location
        return (ImageIterator(str(loc.image), self), None)

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
        """
        location = StoreLocation({'image': image_id})
        checksum = hashlib.md5()
        image_name = str(image_id)
        with rados.Rados(conffile=self.conf_file, rados_id=self.user) as conn:
            with conn.open_ioctx(self.pool) as ioctx:
                order = int(math.log(self.chunk_size, 2))
                logger.debug('creating image %s with order %d',
                             image_name, order)
                try:
                    rbd.RBD().create(ioctx, image_name, image_size, order)
                except rbd.ImageExists:
                    raise exception.Duplicate(
                        _('RBD image %s already exists') % image_id)
                with rbd.Image(ioctx, image_name) as image:
                    bytes_left = image_size
                    while bytes_left > 0:
                        length = min(self.chunk_size, bytes_left)
                        data = image_file.read(length)
                        image.write(data, image_size - bytes_left)
                        bytes_left -= length
                        checksum.update(data)

        return (location.get_uri(), image_size, checksum.hexdigest())

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """
        loc = location.store_location

        with rados.Rados(conffile=self.conf_file, rados_id=self.user) as conn:
            with conn.open_ioctx(self.pool) as ioctx:
                try:
                    rbd.RBD().remove(ioctx, str(loc.image))
                except rbd.ImageNotFound:
                    raise exception.NotFound(
                        _('RBD image %s does not exist') % loc.image)


glance.store.register_store(__name__, ['rbd'])
