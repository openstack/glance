# Copyright 2013 Taobao Inc.
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

"""Storage backend for Sheepdog storage system"""

import hashlib

from oslo.config import cfg

from glance.common import exception
from glance.common import utils
from glance.openstack.common import excutils
import glance.openstack.common.log as logging
from glance.openstack.common import processutils
from glance.openstack.common import units
import glance.store
import glance.store.base
import glance.store.location


LOG = logging.getLogger(__name__)

DEFAULT_ADDR = '127.0.0.1'
DEFAULT_PORT = 7000
DEFAULT_CHUNKSIZE = 64  # in MiB

LOG = logging.getLogger(__name__)

sheepdog_opts = [
    cfg.IntOpt('sheepdog_store_chunk_size', default=DEFAULT_CHUNKSIZE,
               help=_('Images will be chunked into objects of this size '
                      '(in megabytes). For best performance, this should be '
                      'a power of two.')),
    cfg.IntOpt('sheepdog_store_port', default=DEFAULT_PORT,
               help=_('Port of sheep daemon.')),
    cfg.StrOpt('sheepdog_store_address', default=DEFAULT_ADDR,
               help=_('IP address of sheep daemon.'))
]

CONF = cfg.CONF
CONF.register_opts(sheepdog_opts)


class SheepdogImage:
    """Class describing an image stored in Sheepdog storage."""

    def __init__(self, addr, port, name, chunk_size):
        self.addr = addr
        self.port = port
        self.name = name
        self.chunk_size = chunk_size

    def _run_command(self, command, data, *params):
        cmd = ["collie", "vdi"]
        cmd.extend(command)
        cmd.extend(["-a", self.addr, "-p", self.port, self.name])
        cmd.extend(params)

        try:
            return processutils.execute(*cmd, process_input=data)[0]
        except (processutils.ProcessExecutionError, OSError) as exc:
            LOG.error(exc)
            raise glance.store.BackendException(exc)

    def get_size(self):
        """
        Return the size of the this iamge

        Sheepdog Usage: collie vdi list -r -a address -p port image
        """
        out = self._run_command(["list", "-r"], None)
        return long(out.split(' ')[3])

    def read(self, offset, count):
        """
        Read up to 'count' bytes from this image starting at 'offset' and
        return the data.

        Sheepdog Usage: collie vdi read -a address -p port image offset len
        """
        return self._run_command(["read"], None, str(offset), str(count))

    def write(self, data, offset, count):
        """
        Write up to 'count' bytes from the data to this image starting at
        'offset'

        Sheepdog Usage: collie vdi write -a address -p port image offset len
        """
        self._run_command(["write"], data, str(offset), str(count))

    def create(self, size):
        """
        Create this image in the Sheepdog cluster with size 'size'.

        Sheepdog Usage: collie vdi create -a address -p port image size
        """
        self._run_command(["create"], None, str(size))

    def delete(self):
        """
        Delete this image in the Sheepdog cluster

        Sheepdog Usage: collie vdi delete -a address -p port image
        """
        self._run_command(["delete"], None)

    def exist(self):
        """
        Check if this image exists in the Sheepdog cluster via 'list' command

        Sheepdog Usage: collie vdi list -r -a address -p port image
        """
        out = self._run_command(["list", "-r"], None)
        if not out:
            return False
        else:
            return True


class StoreLocation(glance.store.location.StoreLocation):
    """
    Class describing a Sheepdog URI. This is of the form:

        sheepdog://image-id

    """

    def process_specs(self):
        self.image = self.specs.get('image')

    def get_uri(self):
        return "sheepdog://%s" % self.image

    def parse_uri(self, uri):
        valid_schema = 'sheepdog://'
        if not uri.startswith(valid_schema):
            raise exception.BadStoreUri(_("URI must start with %s://") %
                                        valid_schema)
        self.image = uri[len(valid_schema):]
        if not utils.is_uuid_like(self.image):
            raise exception.BadStoreUri(_("URI must contains well-formated "
                                          "image id"))


class ImageIterator(object):
    """
    Reads data from an Sheepdog image, one chunk at a time.
    """

    def __init__(self, image):
        self.image = image

    def __iter__(self):
        image = self.image
        total = left = image.get_size()
        while left > 0:
            length = min(image.chunk_size, left)
            data = image.read(total - left, length)
            left -= len(data)
            yield data
        raise StopIteration()


class Store(glance.store.base.Store):
    """Sheepdog backend adapter."""

    EXAMPLE_URL = "sheepdog://image"

    def get_schemes(self):
        return ('sheepdog',)

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """

        try:
            self.chunk_size = CONF.sheepdog_store_chunk_size * units.Mi
            self.addr = CONF.sheepdog_store_address.strip()
            self.port = CONF.sheepdog_store_port
        except cfg.ConfigFileValueError as e:
            reason = _("Error in store configuration: %s") % e
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name='sheepdog',
                                                  reason=reason)

        if ' ' in self.addr:
            reason = (_("Invalid address configuration of sheepdog store: %s")
                      % self.addr)
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name='sheepdog',
                                                  reason=reason)

        try:
            cmd = ["collie", "vdi", "list", "-a", self.addr, "-p", self.port]
            processutils.execute(*cmd)
        except Exception as e:
            reason = _("Error in store configuration: %s") % e
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name='sheepdog',
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
        image = SheepdogImage(self.addr, self.port, loc.image,
                              self.chunk_size)
        if not image.exist():
            raise exception.NotFound(_("Sheepdog image %s does not exist")
                                     % image.name)
        return (ImageIterator(image), image.get_size())

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file and returns the image size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        :rtype int
        """

        loc = location.store_location
        image = SheepdogImage(self.addr, self.port, loc.image,
                              self.chunk_size)
        if not image.exist():
            raise exception.NotFound(_("Sheepdog image %s does not exist")
                                     % image.name)
        return image.get_size()

    def add(self, image_id, image_file, image_size):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns a tuple containing information
        about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes

        :retval tuple of URL in backing store, bytes written, and checksum
        :raises `glance.common.exception.Duplicate` if the image already
                existed
        """

        image = SheepdogImage(self.addr, self.port, image_id,
                              self.chunk_size)
        if image.exist():
            raise exception.Duplicate(_("Sheepdog image %s already exists")
                                      % image_id)

        location = StoreLocation({'image': image_id})
        checksum = hashlib.md5()

        image.create(image_size)

        try:
            total = left = image_size
            while left > 0:
                length = min(self.chunk_size, left)
                data = image_file.read(length)
                image.write(data, total - left, length)
                left -= length
                checksum.update(data)
        except Exception:
            # Note(zhiyan): clean up already received data when
            # error occurs such as ImageSizeLimitExceeded exception.
            with excutils.save_and_reraise_exception():
                image.delete()

        return (location.get_uri(), image_size, checksum.hexdigest(), {})

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """

        loc = location.store_location
        image = SheepdogImage(self.addr, self.port, loc.image,
                              self.chunk_size)
        if not image.exist():
            raise exception.NotFound(_("Sheepdog image %s does not exist") %
                                     loc.image)
        image.delete()
