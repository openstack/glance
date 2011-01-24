# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

import os
import urlparse

from glance.common import exception
from glance.common import flags
import glance.store


flags.DEFINE_string('filesystem_store_datadir', '/var/lib/glance/images/',
                    'Location to write image data. '
                    'Default: /var/lib/glance/images/')

FLAGS = flags.FLAGS


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
    def get(cls, parsed_uri, opener=lambda p: open(p, "rb"),
            expected_size=None):
        """ Filesystem-based backend

        file:///path/to/file.tar.gz.0
        """

        filepath = parsed_uri.path
        if not os.path.exists(filepath):
            raise exception.NotFound("Image file %s not found" % filepath)
        else:
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
                os.unlink(fn)
            except OSError:
                raise exception.NotAuthorized("You cannot delete file %s" % fn)
        else:
            raise exception.NotFound("Image file %s does not exist" % fn)

    @classmethod
    def add(cls, id, data):
        """
        Stores image data to disk and returns a location that the image was
        written to. By default, the backend writes the image data to a file
        `/<DATADIR>/<ID>`, where <DATADIR> is the value of
        FLAGS.filesystem_store_datadir and <ID> is the supplied image ID.

        :param id: The opaque image identifier
        :param data: The image data to write, as a file-like object

        :retval Tuple with (location, size)
                The location that was written, with file:// scheme prepended
                and the size in bytes of the data written
        """
        datadir = FLAGS.filesystem_store_datadir

        if not os.path.exists(datadir):
            os.makedirs(datadir)

        filepath = os.path.join(datadir, str(id))

        if os.path.exists(filepath):
            raise exception.Duplicate("Image file %s already exists!"
                                      % filepath)

        bytes_written = 0
        with open(filepath, 'wb') as f:
            while True:
                buf = data.read(ChunkedFile.CHUNKSIZE)
                if not buf:
                    break
                bytes_written += len(buf)
                f.write(buf)

        return ('file://%s' % filepath, bytes_written)
