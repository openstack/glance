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

from oslo.config import cfg
import six.moves.urllib.parse as urlparse

from glance.common import exception
from glance.common import utils
import glance.openstack.common.log as logging
from glance.openstack.common import units
import glance.store.base
import glance.store.location

try:
    import rados
    import rbd
except ImportError:
    rados = None
    rbd = None

DEFAULT_POOL = 'images'
DEFAULT_CONFFILE = '/etc/ceph/ceph.conf'
DEFAULT_USER = None    # let librados decide based on the Ceph conf file
DEFAULT_CHUNKSIZE = 8  # in MiB
DEFAULT_SNAPNAME = 'snap'

LOG = logging.getLogger(__name__)

rbd_opts = [
    cfg.IntOpt('rbd_store_chunk_size', default=DEFAULT_CHUNKSIZE,
               help=_('RADOS images will be chunked into objects of this size '
                      '(in megabytes). For best performance, this should be '
                      'a power of two.')),
    cfg.StrOpt('rbd_store_pool', default=DEFAULT_POOL,
               help=_('RADOS pool in which images are stored.')),
    cfg.StrOpt('rbd_store_user', default=DEFAULT_USER,
               help=_('RADOS user to authenticate as (only applicable if '
                      'using Cephx. If <None>, a default will be chosen based '
                      'on the client. section in rbd_store_ceph_conf).')),
    cfg.StrOpt('rbd_store_ceph_conf', default=DEFAULT_CONFFILE,
               help=_('Ceph configuration file path. '
                      'If <None>, librados will locate the default config. '
                      'If using cephx authentication, this file should '
                      'include a reference to the right keyring '
                      'in a client.<USER> section.')),
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
            safe_fsid = urlparse.quote(self.fsid, '')
            safe_pool = urlparse.quote(self.pool, '')
            safe_image = urlparse.quote(self.image, '')
            safe_snapshot = urlparse.quote(self.snapshot, '')
            return "rbd://%s/%s/%s/%s" % (safe_fsid, safe_pool,
                                          safe_image, safe_snapshot)
        else:
            return "rbd://%s" % self.image

    def parse_uri(self, uri):
        prefix = 'rbd://'
        if not uri.startswith(prefix):
            reason = _('URI must start with rbd://')
            msg = (_("Invalid URI: %(uri)s: %(reason)s") % {'uri': uri,
                                                            'reason': reason})
            LOG.debug(msg)
            raise exception.BadStoreUri(message=reason)
        # convert to ascii since librbd doesn't handle unicode
        try:
            ascii_uri = str(uri)
        except UnicodeError:
            reason = _('URI contains non-ascii characters')
            msg = (_("Invalid URI: %(uri)s: %(reason)s") % {'uri': uri,
                                                            'reason': reason})
            LOG.debug(msg)
            raise exception.BadStoreUri(message=reason)
        pieces = ascii_uri[len(prefix):].split('/')
        if len(pieces) == 1:
            self.fsid, self.pool, self.image, self.snapshot = \
                (None, None, pieces[0], None)
        elif len(pieces) == 4:
            self.fsid, self.pool, self.image, self.snapshot = \
                map(urlparse.unquote, pieces)
        else:
            reason = _('URI must have exactly 1 or 4 components')
            msg = (_("Invalid URI: %(uri)s: %(reason)s") % {'uri': uri,
                                                            'reason': reason})
            LOG.debug(msg)
            raise exception.BadStoreUri(message=reason)
        if any(map(lambda p: p == '', pieces)):
            reason = _('URI cannot contain empty components')
            msg = (_("Invalid URI: %(uri)s: %(reason)s") % {'uri': uri,
                                                            'reason': reason})
            LOG.debug(msg)
            raise exception.BadStoreUri(message=reason)


class ImageIterator(object):
    """
    Reads data from an RBD image, one chunk at a time.
    """

    def __init__(self, pool, name, snapshot, store):
        self.pool = pool or store.pool
        self.name = name
        self.snapshot = snapshot
        self.user = store.user
        self.conf_file = store.conf_file
        self.chunk_size = store.chunk_size

    def __iter__(self):
        try:
            with rados.Rados(conffile=self.conf_file,
                             rados_id=self.user) as conn:
                with conn.open_ioctx(self.pool) as ioctx:
                    with rbd.Image(ioctx, self.name,
                                   snapshot=self.snapshot) as image:
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
            self.chunk_size = CONF.rbd_store_chunk_size * units.Mi

            # these must not be unicode since they will be passed to a
            # non-unicode-aware C library
            self.pool = str(CONF.rbd_store_pool)
            self.user = str(CONF.rbd_store_user)
            self.conf_file = str(CONF.rbd_store_ceph_conf)
        except cfg.ConfigFileValueError as e:
            reason = _("Error in store configuration: %s") % e
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name='rbd',
                                                  reason=reason)

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
        return (ImageIterator(loc.pool, loc.image, loc.snapshot, self),
                self.get_size(location))

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        loc = location.store_location
        # if there is a pool specific in the location, use it; otherwise
        # we fall back to the default pool specified in the config
        target_pool = loc.pool or self.pool
        with rados.Rados(conffile=self.conf_file,
                         rados_id=self.user) as conn:
            with conn.open_ioctx(target_pool) as ioctx:
                try:
                    with rbd.Image(ioctx, loc.image,
                                   snapshot=loc.snapshot) as image:
                        img_info = image.stat()
                        return img_info['size']
                except rbd.ImageNotFound:
                    msg = _('RBD image %s does not exist') % loc.get_uri()
                    LOG.debug(msg)
                    raise exception.NotFound(msg)

    def _create_image(self, fsid, ioctx, image_name, size, order):
        """
        Create an rbd image. If librbd supports it,
        make it a cloneable snapshot, so that copy-on-write
        volumes can be created from it.

        :param image_name Image's name

        :retval `glance.store.rbd.StoreLocation` object
        """
        librbd = rbd.RBD()
        if hasattr(rbd, 'RBD_FEATURE_LAYERING'):
            librbd.create(ioctx, image_name, size, order, old_format=False,
                          features=rbd.RBD_FEATURE_LAYERING)
            return StoreLocation({
                'fsid': fsid,
                'pool': self.pool,
                'image': image_name,
                'snapshot': DEFAULT_SNAPNAME,
            })
        else:
            librbd.create(ioctx, image_name, size, order, old_format=True)
            return StoreLocation({'image': image_name})

    def _delete_image(self, target_pool, image_name, snapshot_name=None):
        """
        Delete RBD image and snapshot.

        :param image_name Image's name
        :param snapshot_name Image snapshot's name

        :raises NotFound if image does not exist;
                InUseByStore if image is in use or snapshot unprotect failed
        """
        with rados.Rados(conffile=self.conf_file, rados_id=self.user) as conn:
            with conn.open_ioctx(target_pool) as ioctx:
                try:
                    # First remove snapshot.
                    if snapshot_name is not None:
                        with rbd.Image(ioctx, image_name) as image:
                            try:
                                image.unprotect_snap(snapshot_name)
                            except rbd.ImageBusy:
                                log_msg = _("snapshot %(image)s@%(snap)s "
                                            "could not be unprotected because "
                                            "it is in use")
                                LOG.debug(log_msg %
                                          {'image': image_name,
                                           'snap': snapshot_name})
                                raise exception.InUseByStore()
                            image.remove_snap(snapshot_name)

                    # Then delete image.
                    rbd.RBD().remove(ioctx, image_name)
                except rbd.ImageNotFound:
                    raise exception.NotFound(
                        _("RBD image %s does not exist") % image_name)
                except rbd.ImageBusy:
                    log_msg = _("image %s could not be removed "
                                "because it is in use")
                    LOG.debug(log_msg % image_name)
                    raise exception.InUseByStore()

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
        checksum = hashlib.md5()
        image_name = str(image_id)
        with rados.Rados(conffile=self.conf_file, rados_id=self.user) as conn:
            fsid = None
            if hasattr(conn, 'get_fsid'):
                fsid = conn.get_fsid()
            with conn.open_ioctx(self.pool) as ioctx:
                order = int(math.log(self.chunk_size, 2))
                LOG.debug('creating image %s with order %d and size %d',
                          image_name, order, image_size)
                if image_size == 0:
                    LOG.warning(_("since image size is zero we will be doing "
                                  "resize-before-write for each chunk which "
                                  "will be considerably slower than normal"))

                try:
                    loc = self._create_image(fsid, ioctx, image_name,
                                             image_size, order)
                except rbd.ImageExists:
                    raise exception.Duplicate(
                        _('RBD image %s already exists') % image_id)
                try:
                    with rbd.Image(ioctx, image_name) as image:
                        bytes_written = 0
                        offset = 0
                        chunks = utils.chunkreadable(image_file,
                                                     self.chunk_size)
                        for chunk in chunks:
                            # If the image size provided is zero we need to do
                            # a resize for the amount we are writing. This will
                            # be slower so setting a higher chunk size may
                            # speed things up a bit.
                            if image_size == 0:
                                chunk_length = len(chunk)
                                length = offset + chunk_length
                                bytes_written += chunk_length
                                LOG.debug(_("resizing image to %s KiB") %
                                          (length / units.Ki))
                                image.resize(length)
                            LOG.debug(_("writing chunk at offset %s") %
                                      (offset))
                            offset += image.write(chunk, offset)
                            checksum.update(chunk)
                        if loc.snapshot:
                            image.create_snap(loc.snapshot)
                            image.protect_snap(loc.snapshot)
                except Exception as exc:
                    # Delete image if one was created
                    try:
                        self._delete_image(loc.image, loc.snapshot)
                    except exception.NotFound:
                        pass

                    raise exc

        # Make sure we send back the image size whether provided or inferred.
        if image_size == 0:
            image_size = bytes_written

        return (loc.get_uri(), image_size, checksum.hexdigest(), {})

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete.

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist;
                InUseByStore if image is in use or snapshot unprotect failed
        """
        loc = location.store_location
        target_pool = loc.pool or self.pool
        self._delete_image(target_pool, loc.image, loc.snapshot)
