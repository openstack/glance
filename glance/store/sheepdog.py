# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011, Nebula, Inc
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

"""Storage backend for Sheepdog"""

import hashlib
import logging
import subprocess

from glance.common import cfg
from glance.common import exception
import glance.store
import glance.store.base
import glance.store.location


logger = logging.getLogger('glance.store.sheepdog')

DEFAULT_CHUNKSIZE_MB = 64  # 64 MiB
DEFAULT_COLLIEPATH = '/usr/sbin/collie'
DEFAULT_GATEWAY = '127.0.0.1'
DEFAULT_PORT = '7000'

# return values from the collie command
EXIT_SUCCESS = 0  # command executed successfully
EXIT_FAILURE = 1  # command failed to execute
EXIT_SYSFAIL = 2  # something is wrong with the cluster or local host
EXIT_EXISTS  = 3  # the object already exists so cannot be created
EXIT_FULL    = 4  # no more space is left in the cluster
EXIT_MISSING = 5  # the specified object does not exist
EXIT_USAGE   = 64  # invalid command, arguments or options


class StoreLocation(glance.store.location.StoreLocation):
    """
    Class describing a Sheepdog URI. This is of the form:

        sheepdog://image

    """

    def process_specs(self):
        self.image = self.specs.get('image')

    def get_uri(self):
        return ("sheepdog://%s" % self.image)

    def parse_uri(self, uri):
        if not uri.startswith('sheepdog://'):
            raise exception.BadStoreUri(uri,
                _('URI must start with sheepdog://'))
        self.image = uri[len('sheepdog://'):]


class ChunkedRead(object):
    """
    Reads data from a Sheepdog image, one chunk at a time.
    """
    def __init__(self, image, store):
        self.offset = 0
        self.image = image
        self.store = store
        self.is_block_device = True

    def __iter__(self):
        store = self.store

        while True:
            obj = store._exec_collie(['vdi', 'read', str(self.image),
                               str(self.offset), str(store.chunk_size)])
            output = obj.communicate()
            if obj.returncode != 0:
                if obj.returncode == EXIT_MISSING:
                    raise exception.NotFound(
                        _('Sheepdog image %s does not exist') % self.image)
                return
            yield output[0]
            self.offset += store.chunk_size


class Store(glance.store.base.Store):
    """An implementation of the Sheepdog backend adapter."""

    EXAMPLE_URL = "sheepdog://<IMAGE>"
    sheepdog_store_opts = [
        cfg.IntOpt('sheepdog_store_chunk_size_mb',
                   default=DEFAULT_CHUNKSIZE_MB,
                   help='The chunk size for the underlying '
                        'sheepdog store, in MB.'),
        cfg.StrOpt('sheepdog_gateway',
                   default=DEFAULT_GATEWAY,
                   help='The IP of the sheepdog gateway.'),
        cfg.StrOpt('sheepdog_collie_path',
                   default=DEFAULT_COLLIEPATH,
                   help='The path of the collie binary.'),
        cfg.StrOpt('sheepdog_port',
                   default=DEFAULT_PORT,
                   help='The port that the sheepdog gateway '
                        'listens on.'),
        ]

    def _exec_collie(self, args):
        """
        Helper to execute the collie command with the given arguments.
        """

        # note that collie expects getopt style arguments to come last
        return subprocess.Popen([self.collie_path] +
                                args +
                                ['-a'] + [self.gateway] +
                                ['-p'] + [self.port],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.conf.register_opts(self.sheepdog_store_opts)
        self.chunk_size = getattr(self.conf,
            'sheepdog_store_chunk_size_mb') * 1024 ** 2
        self.collie_path = getattr(self.conf, 'sheepdog_collie_path')
        self.gateway = getattr(self.conf, 'sheepdog_gateway')
        self.port = getattr(self.conf, 'sheepdog_port')

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
        return (ChunkedRead(str(loc.image), self), None)

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

        obj = self._exec_collie(["vdi", "create", image_name, str(image_size)])
        obj.communicate()

        # XXX(hch): what should we do about other errors?
        if obj.returncode == EXIT_EXISTS:
            raise exception.Duplicate(
                 _('Sheepdog image %s already exists') % image_id)

        offset = 0
        bytes_left = image_size

        while bytes_left > 0:
            length = min(self.chunk_size, bytes_left)
            data = image_file.read(length)

            obj = self._exec_collie(['vdi', 'write', image_name, str(offset),
                               str(length)])
            output = obj.communicate(data)
            obj.stdin.close()
            # XXX(hch): what should we do about errors?

            bytes_left -= length
            offset += length
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

        obj = self._exec_collie(['vdi', 'delete', str(loc.image)])
        obj.communicate()
        if obj.returncode == EXIT_MISSING:
            raise exception.NotFound(
                 _('Sheepdog image %s does not exist') % loc.image)

glance.store.register_store(__name__, ['sheepdog'])
