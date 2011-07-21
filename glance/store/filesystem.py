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

import hashlib
import logging
import os
import urlparse

from glance.common import exception
import glance.store
import glance.store.location

logger = logging.getLogger('glance.store.filesystem')

glance.store.location.add_scheme_map({'file': 'filesystem'})


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
        assert pieces.scheme == 'file'
        self.scheme = pieces.scheme
        path = (pieces.netloc + pieces.path).strip()
        if path == '':
            reason = "No path specified"
            raise exception.BadStoreUri(uri, reason)
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


class FilesystemBackend(glance.store.Backend):
    @classmethod
    def get(cls, location, expected_size=None, options=None):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator to use in
        reading the image file.

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if file does not exist
        """
        loc = location.store_location
        filepath = loc.path
        if not os.path.exists(filepath):
            raise exception.NotFound("Image file %s not found" % filepath)
        else:
            logger.debug("Found image at %s. Returning in ChunkedFile.",
                         filepath)
            return ChunkedFile(filepath)

    @classmethod
    def delete(cls, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if file does not exist
        :raises NotAuthorized if cannot delete because of permissions
        """
        loc = location.store_location
        fn = loc.path
        if os.path.exists(fn):
            try:
                logger.debug("Deleting image at %s", fn)
                os.unlink(fn)
            except OSError:
                raise exception.NotAuthorized("You cannot delete file %s" % fn)
        else:
            raise exception.NotFound("Image file %s does not exist" % fn)

    @classmethod
    def add(cls, id, data, options):
        """
        Stores image data to disk and returns a location that the image was
        written to. By default, the backend writes the image data to a file
        `/<DATADIR>/<ID>`, where <DATADIR> is the value of
        options['filesystem_store_datadir'] and <ID> is the supplied image ID.

        :param id: The opaque image identifier
        :param data: The image data to write, as a file-like object
        :param options: Conf mapping

        :retval Tuple with (location, size, checksum)
                The location that was written, with file:// scheme prepended,
                the size in bytes of the data written, and the checksum of
                the image added.
        """
        datadir = options['filesystem_store_datadir']

        if not os.path.exists(datadir):
            logger.info("Directory to write image files does not exist "
                        "(%s). Creating.", datadir)
            os.makedirs(datadir)

        filepath = os.path.join(datadir, str(id))

        if os.path.exists(filepath):
            raise exception.Duplicate("Image file %s already exists!"
                                      % filepath)

        checksum = hashlib.md5()
        bytes_written = 0
        with open(filepath, 'wb') as f:
            while True:
                buf = data.read(ChunkedFile.CHUNKSIZE)
                if not buf:
                    break
                bytes_written += len(buf)
                checksum.update(buf)
                f.write(buf)

        checksum_hex = checksum.hexdigest()

        logger.debug("Wrote %(bytes_written)d bytes to %(filepath)s with "
                     "checksum %(checksum_hex)s" % locals())
        return ('file://%s' % filepath, bytes_written, checksum_hex)
