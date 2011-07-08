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

logger = logging.getLogger('glance.store.filesystem')


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
    def get(cls, parsed_uri, expected_size=None, options=None):
        """
        Filesystem-based backend

        file:///path/to/file.tar.gz.0
        """
        filepath = parsed_uri.path
        if not os.path.exists(filepath):
            raise exception.NotFound("Image file %s not found" % filepath)
        else:
            logger.debug("Found image at %s. Returning in ChunkedFile.",
                         filepath)
            return ChunkedFile(filepath)

    @classmethod
    def delete(cls, parsed_uri):
        """
        Removes a file from the filesystem backend.

        :param parsed_uri: Parsed pieces of URI in form of::
            file:///path/to/filename.ext

        :raises NotFound if file does not exist
        :raises NotAuthorized if cannot delete because of permissions
        """
        fn = parsed_uri.path
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
