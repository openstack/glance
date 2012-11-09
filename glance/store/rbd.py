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
import math
import urllib
import urlparse

from glance.common import exception
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
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
DEFAULT_SNAPNAME = 'snap'

LOG = logging.getLogger(__name__)

rbd_opts = [
    cfg.IntOpt('rbd_store_chunk_size', default=DEFAULT_CHUNKSIZE),
    cfg.StrOpt('rbd_store_pool', default=DEFAULT_POOL),
    cfg.StrOpt('rbd_store_user', default=DEFAULT_USER),
    cfg.StrOpt('rbd_store_ceph_conf', default=DEFAULT_CONFFILE),
    ]

CONF = cfg.CONF
CONF.register_opts(rbd_opts)


class StoreLocation(glance.store.location.StoreLocation):
    """
    Class describing a RBD URI. This is of the form:

        rbd://image

        or

        rbd://fsid/pool/image/snapshot
    """

    def process_specs(self):
        # convert to ascii since librbd doesn't handle unicode
        for key, value in self.specs.iteritems():
            self.specs[key] = str(value)
        self.fsid = self.specs.get('fsid')
        self.pool = self.specs.get('pool')
        self.image = self.specs.get('image')
        self.snapshot = self.specs.get('snapshot')

    def get_uri(self):
        if self.fsid and self.pool and self.snapshot:
            # ensure nothing contains / or any other url-unsafe character
            safe_fsid = urllib.quote(self.fsid, '')
            safe_pool = urllib.quote(self.pool, '')
            safe_image = urllib.quote(self.image, '')
            safe_snapshot = urllib.quote(self.snapshot, '')
            return "rbd://%s/%s/%s/%s" % (safe_fsid, safe_pool,
                                          safe_image, safe_snapshot)
        else:
            return "rbd://%s" % self.image

    def parse_uri(self, uri):
        prefix = 'rbd://'
        if not uri.startswith(prefix):
            reason = _('URI must start with rbd://')
            LOG.error(_("Invalid URI: %(uri)s: %(reason)s") % locals())
            raise exception.BadStoreUri(message=reason)
        # convert to ascii since librbd doesn't handle unicode
        try:
            ascii_uri = str(uri)
        except UnicodeError:
            reason = _('URI contains non-ascii characters')
            LOG.error(_("Invalid URI: %(uri)s: %(reason)s") % locals())
            raise exception.BadStoreUri(message=reason)
        pieces = ascii_uri[len(prefix):].split('/')
        if len(pieces) == 1:
            self.fsid, self.pool, self.image, self.snapshot = \
                (None, None, pieces[0], None)
        elif len(pieces) == 4:
            self.fsid, self.pool, self.image, self.snapshot = \
                map(urllib.unquote, pieces)
        else:
            reason = _('URI must have exactly 1 or 4 components')
            LOG.error(_("Invalid URI: %(uri)s: %(reason)s") % locals())
            raise exception.BadStoreUri(message=reason)
        if any(map(lambda p: p == '', pieces)):
            reason = _('URI cannot contain empty components')
            LOG.error(_("Invalid URI: %(uri)s: %(reason)s") % locals())
            raise exception.BadStoreUri(message=reason)


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

    EXAMPLE_URL = "rbd://<FSID>/<POOL>/<IMAGE>/<SNAP>"

    def get_schemes(self):
        return ('rbd',)

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        try:
            self.chunk_size = CONF.rbd_store_chunk_size * 1024 * 1024

            # these must not be unicode since they will be passed to a
            # non-unicode-aware C library
            self.pool = str(CONF.rbd_store_pool)
            self.user = str(CONF.rbd_store_user)
            self.conf_file = str(CONF.rbd_store_ceph_conf)
        except cfg.ConfigFileValueError, e:
            reason = _("Error in store configuration: %s") % e
            LOG.error(reason)
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

    def _create_image(self, fsid, ioctx, name, size, order):
        """
        Create an rbd image. If librbd supports it,
        make it a cloneable snapshot, so that copy-on-write
        volumes can be created from it.

        :retval `glance.store.rbd.StoreLocation` object
        """
        librbd = rbd.RBD()
        if hasattr(rbd, 'RBD_FEATURE_LAYERING'):
            librbd.create(ioctx, name, size, order, old_format=False,
                          features=rbd.RBD_FEATURE_LAYERING)
            return StoreLocation({
                    'fsid': fsid,
                    'pool': self.pool,
                    'image': name,
                    'snapshot': DEFAULT_SNAPNAME,
                    })
        else:
            librbd.create(ioctx, name, size, order, old_format=True)
            return StoreLocation({'image': name})

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
        checksum = hashlib.md5()
        image_name = str(image_id)
        with rados.Rados(conffile=self.conf_file, rados_id=self.user) as conn:
            fsid = None
            if hasattr(conn, 'get_fsid'):
                fsid = conn.get_fsid()
            with conn.open_ioctx(self.pool) as ioctx:
                order = int(math.log(self.chunk_size, 2))
                LOG.debug('creating image %s with order %d',
                          image_name, order)
                try:
                    location = self._create_image(fsid, ioctx, image_name,
                                                  image_size, order)
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
                    if location.snapshot:
                        image.create_snap(location.snapshot)
                        image.protect_snap(location.snapshot)

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
                if loc.snapshot:
                    with rbd.Image(ioctx, loc.image) as image:
                        try:
                            image.unprotect_snap(loc.snapshot)
                        except rbd.ImageBusy:
                            log_msg = _("snapshot %s@%s could not be "
                                        "unprotected because it is in use")
                            LOG.error(log_msg % (loc.image, loc.snapshot))
                            raise exception.InUseByStore()
                        image.remove_snap(loc.snapshot)
                try:
                    rbd.RBD().remove(ioctx, str(loc.image))
                except rbd.ImageNotFound:
                    raise exception.NotFound(
                        _('RBD image %s does not exist') % loc.image)
                except rbd.ImageBusy:
                    log_msg = _("image %s could not be removed"
                                "because it is in use")
                    LOG.error(log_msg % loc.image)
                    raise exception.InUseByStore()
