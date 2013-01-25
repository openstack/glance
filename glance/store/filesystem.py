# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

"""
A simple filesystem-backed store
"""

import errno
import hashlib
import os
import urlparse

from glance.common import exception
from glance.common import utils
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
import glance.store
import glance.store.base
import glance.store.location

LOG = logging.getLogger(__name__)

datadir_opt = cfg.StrOpt('filesystem_store_datadir')

CONF = cfg.CONF
CONF.register_opt(datadir_opt)


class StoreLocation(glance.store.location.StoreLocation):

    """Class describing a Filesystem URI"""

    def process_specs(self):
        self.scheme = self.specs.get('scheme', 'file')
        self.path = self.specs.get('path')

    def get_uri(self):
        return "file://%s" % self.path

    def parse_uri(self, uri):
        """
        Parse URLs. This method fixes an issue where credentials specified
        in the URL are interpreted differently in Python 2.6.1+ than prior
        versions of Python.
        """
        pieces = urlparse.urlparse(uri)
        assert pieces.scheme in ('file', 'filesystem')
        self.scheme = pieces.scheme
        path = (pieces.netloc + pieces.path).strip()
        if path == '':
            reason = _("No path specified in URI: %s") % uri
            LOG.error(reason)
            raise exception.BadStoreUri('No path specified')
        self.path = path


class ChunkedFile(object):

    """
    We send this back to the Glance API server as
    something that can iterate over a large file
    """

    CHUNKSIZE = 65536

    def __init__(self, filepath):
        self.filepath = filepath
        self.fp = open(self.filepath, 'rb')

    def __iter__(self):
        """Return an iterator over the image file"""
        try:
            while True:
                chunk = self.fp.read(ChunkedFile.CHUNKSIZE)
                if chunk:
                    yield chunk
                else:
                    break
        finally:
            self.close()

    def close(self):
        """Close the internal file pointer"""
        if self.fp:
            self.fp.close()
            self.fp = None


class Store(glance.store.base.Store):

    def get_schemes(self):
        return ('file', 'filesystem')

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.datadir = CONF.filesystem_store_datadir
        if self.datadir is None:
            reason = (_("Could not find %s in configuration options.") %
                      'filesystem_store_datadir')
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="filesystem",
                                                  reason=reason)

        if not os.path.exists(self.datadir):
            msg = _("Directory to write image files does not exist "
                    "(%s). Creating.") % self.datadir
            LOG.info(msg)
            try:
                os.makedirs(self.datadir)
            except IOError:
                reason = _("Unable to create datadir: %s") % self.datadir
                LOG.error(reason)
                raise exception.BadStoreConfiguration(store_name="filesystem",
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
        filepath = loc.path
        if not os.path.exists(filepath):
            raise exception.NotFound(_("Image file %s not found") % filepath)
        else:
            msg = _("Found image at %s. Returning in ChunkedFile.") % filepath
            LOG.debug(msg)
            return (ChunkedFile(filepath), None)

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        :raises Forbidden if cannot delete because of permissions
        """
        loc = location.store_location
        fn = loc.path
        if os.path.exists(fn):
            try:
                LOG.debug(_("Deleting image at %(fn)s") % locals())
                os.unlink(fn)
            except OSError:
                raise exception.Forbidden(_("You cannot delete file %s") % fn)
        else:
            raise exception.NotFound(_("Image file %s does not exist") % fn)

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

        :note By default, the backend writes the image data to a file
              `/<DATADIR>/<ID>`, where <DATADIR> is the value of
              the filesystem_store_datadir configuration option and <ID>
              is the supplied image ID.
        """

        filepath = os.path.join(self.datadir, str(image_id))

        if os.path.exists(filepath):
            raise exception.Duplicate(_("Image file %s already exists!")
                                      % filepath)

        checksum = hashlib.md5()
        bytes_written = 0
        try:
            with open(filepath, 'wb') as f:
                for buf in utils.chunkreadable(image_file,
                                              ChunkedFile.CHUNKSIZE):
                    bytes_written += len(buf)
                    checksum.update(buf)
                    f.write(buf)
        except IOError as e:
            if e.errno != errno.EACCES:
                self._delete_partial(filepath, image_id)
            exceptions = {errno.EFBIG: exception.StorageFull(),
                          errno.ENOSPC: exception.StorageFull(),
                          errno.EACCES: exception.StorageWriteDenied()}
            raise exceptions.get(e.errno, e)
        except:
            self._delete_partial(filepath, image_id)
            raise

        checksum_hex = checksum.hexdigest()

        LOG.debug(_("Wrote %(bytes_written)d bytes to %(filepath)s with "
                    "checksum %(checksum_hex)s") % locals())
        return ('file://%s' % filepath, bytes_written, checksum_hex)

    @staticmethod
    def _delete_partial(filepath, id):
        try:
            os.unlink(filepath)
        except Exception as e:
            msg = _('Unable to remove partial image data for image %s: %s')
            LOG.error(msg % (id, e))
