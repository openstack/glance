# Copyright 2010 OpenStack Foundation
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

from oslo.config import cfg
import six
import six.moves.urllib.parse as urlparse

from glance.common import exception
from glance.common import utils
from glance.openstack.common import jsonutils
import glance.openstack.common.log as logging
from glance.openstack.common import processutils
import glance.store
import glance.store.base
import glance.store.location

LOG = logging.getLogger(__name__)

filesystem_opts = [
    cfg.StrOpt('filesystem_store_datadir',
               help=_('Directory to which the Filesystem backend '
                      'store writes images.')),
    cfg.MultiStrOpt('filesystem_store_datadirs',
                    help=_("List of directories and its priorities to which "
                           "the Filesystem backend store writes images.")),
    cfg.StrOpt('filesystem_store_metadata_file',
               help=_("The path to a file which contains the "
                      "metadata to be returned with any location "
                      "associated with this store.  The file must "
                      "contain a valid JSON dict."))]

CONF = cfg.CONF
CONF.register_opts(filesystem_opts)


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
            LOG.debug(reason)
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
            if self.fp:
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

    def _check_write_permission(self, datadir):
        """
        Checks if directory created to write image files has
        write permission.

        :datadir is a directory path in which glance wites image files.
        :raise BadStoreConfiguration exception if datadir is read-only.
        """
        if not os.access(datadir, os.W_OK):
            msg = (_("Permission to write in %s denied") % datadir)
            LOG.exception(msg)
            raise exception.BadStoreConfiguration(
                store_name="filesystem", reason=msg)

    def _create_image_directories(self, directory_paths):
        """
        Create directories to write image files if
        it does not exist.

        :directory_paths is a list of directories belonging to glance store.
        :raise BadStoreConfiguration exception if creating a directory fails.
        """
        for datadir in directory_paths:
            if os.path.exists(datadir):
                self._check_write_permission(datadir)
            else:
                msg = _("Directory to write image files does not exist "
                        "(%s). Creating.") % datadir
                LOG.info(msg)
                try:
                    os.makedirs(datadir)
                    self._check_write_permission(datadir)
                except (IOError, OSError):
                    if os.path.exists(datadir):
                        # NOTE(markwash): If the path now exists, some other
                        # process must have beat us in the race condition.
                        # But it doesn't hurt, so we can safely ignore
                        # the error.
                        self._check_write_permission(datadir)
                        continue
                    reason = _("Unable to create datadir: %s") % datadir
                    LOG.error(reason)
                    raise exception.BadStoreConfiguration(
                        store_name="filesystem", reason=reason)

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        if not (CONF.filesystem_store_datadir
                or CONF.filesystem_store_datadirs):
            reason = (_("Specify at least 'filesystem_store_datadir' or "
                        "'filesystem_store_datadirs' option"))
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="filesystem",
                                                  reason=reason)

        if CONF.filesystem_store_datadir and CONF.filesystem_store_datadirs:
            reason = (_("Specify either 'filesystem_store_datadir' or "
                        "'filesystem_store_datadirs' option"))
            LOG.error(reason)
            raise exception.BadStoreConfiguration(store_name="filesystem",
                                                  reason=reason)

        self.multiple_datadirs = False
        directory_paths = set()
        if CONF.filesystem_store_datadir:
            self.datadir = CONF.filesystem_store_datadir
            directory_paths.add(self.datadir)
        else:
            self.multiple_datadirs = True
            self.priority_data_map = {}
            for datadir in CONF.filesystem_store_datadirs:
                (datadir_path,
                 priority) = self._get_datadir_path_and_priority(datadir)
                self._check_directory_paths(datadir_path, directory_paths)
                directory_paths.add(datadir_path)
                self.priority_data_map.setdefault(int(priority),
                                                  []).append(datadir_path)

            self.priority_list = sorted(self.priority_data_map,
                                        reverse=True)

        self._create_image_directories(directory_paths)

    def _check_directory_paths(self, datadir_path, directory_paths):
        """
        Checks if directory_path is already present in directory_paths.

        :datadir_path is directory path.
        :datadir_paths is set of all directory paths.
        :raise BadStoreConfiguration exception if same directory path is
               already present in directory_paths.
        """
        if datadir_path in directory_paths:
            msg = (_("Directory %(datadir_path)s specified "
                     "multiple times in filesystem_store_datadirs "
                     "option of filesystem configuration") %
                   {'datadir_path': datadir_path})
            LOG.exception(msg)
            raise exception.BadStoreConfiguration(
                store_name="filesystem", reason=msg)

    def _get_datadir_path_and_priority(self, datadir):
        """
        Gets directory paths and its priority from
        filesystem_store_datadirs option in glance-api.conf.

        :datadir is directory path with its priority.
        :returns datadir_path as directory path
                 priority as priority associated with datadir_path
        :raise BadStoreConfiguration exception if priority is invalid or
               empty directory path is specified.
        """
        priority = 0
        parts = map(lambda x: x.strip(), datadir.rsplit(":", 1))
        datadir_path = parts[0]
        if len(parts) == 2 and parts[1]:
            priority = parts[1]
            if not priority.isdigit():
                msg = (_("Invalid priority value %(priority)s in "
                         "filesystem configuration") % {'priority': priority})
                LOG.exception(msg)
                raise exception.BadStoreConfiguration(
                    store_name="filesystem", reason=msg)

        if not datadir_path:
            msg = _("Invalid directory specified in filesystem configuration")
            LOG.exception(msg)
            raise exception.BadStoreConfiguration(
                store_name="filesystem", reason=msg)

        return datadir_path, priority

    @staticmethod
    def _resolve_location(location):
        filepath = location.store_location.path

        if not os.path.exists(filepath):
            raise exception.NotFound(_("Image file %s not found") % filepath)

        filesize = os.path.getsize(filepath)
        return filepath, filesize

    def _get_metadata(self):
        if CONF.filesystem_store_metadata_file is None:
            return {}

        try:
            with open(CONF.filesystem_store_metadata_file, 'r') as fptr:
                metadata = jsonutils.load(fptr)
            glance.store.check_location_metadata(metadata)
            return metadata
        except glance.store.BackendException as bee:
            LOG.error(_('The JSON in the metadata file %(file)s could not be '
                        'used: %(error)s  An empty dictionary will be '
                        'returned to the client.') %
                      {'file': CONF.filesystem_store_metadata_file,
                       'error': six.text_type(bee)})
            return {}
        except IOError as ioe:
            LOG.error(_('The path for the metadata file %(file)s could not be '
                        'opened: %(error)s  An empty dictionary will be '
                        'returned to the client.') %
                      {'file': CONF.filesystem_store_metadata_file,
                       'error': six.text_type(ioe)})
            return {}
        except Exception as ex:
            LOG.exception(_('An error occurred processing the storage systems '
                            'meta data file: %s.  An empty dictionary will be '
                            'returned to the client.') % six.text_type(ex))
            return {}

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        filepath, filesize = self._resolve_location(location)
        msg = _("Found image at %s. Returning in ChunkedFile.") % filepath
        LOG.debug(msg)
        return (ChunkedFile(filepath), filesize)

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file and returns the image size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        :rtype int
        """
        filepath, filesize = self._resolve_location(location)
        msg = _("Found image at %s.") % filepath
        LOG.debug(msg)
        return filesize

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
                LOG.debug(_("Deleting image at %(fn)s"), {'fn': fn})
                os.unlink(fn)
            except OSError:
                raise exception.Forbidden(_("You cannot delete file %s") % fn)
        else:
            raise exception.NotFound(_("Image file %s does not exist") % fn)

    def _get_capacity_info(self, mount_point):
        """Calculates total available space for given mount point.

        :mount_point is path of glance data directory
        """

        #Calculate total available space
        df = processutils.execute("df", "--block-size=1",
                                  mount_point)[0].strip("'\n'")
        total_available_space = int(df.split('\n')[1].split()[3])

        return max(0, total_available_space)

    def _find_best_datadir(self, image_size):
        """Finds the best datadir by priority and free space.

        Traverse directories returning the first one that has sufficient
        free space, in priority order. If two suitable directories have
        the same priority, choose the one with the most free space
        available.
        :image_size size of image being uploaded.
        :returns best_datadir as directory path of the best priority datadir.
        :raises exception.StorageFull if there is no datadir in
                self.priority_data_map that can accommodate the image.
        """
        if not self.multiple_datadirs:
            return self.datadir

        best_datadir = None
        max_free_space = 0
        for priority in self.priority_list:
            for datadir in self.priority_data_map.get(priority):
                free_space = self._get_capacity_info(datadir)
                if free_space >= image_size and free_space > max_free_space:
                    max_free_space = free_space
                    best_datadir = datadir

            # If datadir is found which can accommodate image and has maximum
            # free space for the given priority then break the loop,
            # else continue to lookup further.
            if best_datadir:
                break
        else:
            msg = (_("There is no enough disk space left on the image "
                     "storage media. requested=%s") % image_size)
            LOG.exception(msg)
            raise exception.StorageFull(message=msg)

        return best_datadir

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

        :note By default, the backend writes the image data to a file
              `/<DATADIR>/<ID>`, where <DATADIR> is the value of
              the filesystem_store_datadir configuration option and <ID>
              is the supplied image ID.
        """
        datadir = self._find_best_datadir(image_size)
        filepath = os.path.join(datadir, str(image_id))

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
        except Exception:
            self._delete_partial(filepath, image_id)
            raise

        checksum_hex = checksum.hexdigest()
        metadata = self._get_metadata()

        LOG.debug(_("Wrote %(bytes_written)d bytes to %(filepath)s with "
                    "checksum %(checksum_hex)s"),
                  {'bytes_written': bytes_written,
                   'filepath': filepath,
                   'checksum_hex': checksum_hex})
        return ('file://%s' % filepath, bytes_written, checksum_hex, metadata)

    @staticmethod
    def _delete_partial(filepath, id):
        try:
            os.unlink(filepath)
        except Exception as e:
            msg = _('Unable to remove partial image data for image %(id)s: '
                    '%(error)s')
            LOG.error(msg % {'id': id,
                             'error': e})
