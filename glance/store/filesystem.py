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

import os
import urlparse

from glance.common import exception
import glance.store


class FilesystemBackend(glance.store.Backend):
    @classmethod
    def get(cls, parsed_uri, expected_size, opener=lambda p: open(p, "rb")):
        """ Filesystem-based backend

        file:///path/to/file.tar.gz.0
        """
        #FIXME: must prevent attacks using ".." and "." paths
        with opener(parsed_uri.path) as f:
            return glance.store._file_iter(f, cls.CHUNKSIZE)

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
            raise exception.NotFound("File %s does not exist" % fn) 
