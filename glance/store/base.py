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

"""Base class for all storage backends"""


class Store(object):

    CHUNKSIZE = (16 * 1024 * 1024)  # 16M

    def __init__(self, options=None):
        """
        Initialize the Store

        :param options: Optional dictionary of configuration options
        """
        self.options = options or {}

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a generator for reading
        the image file

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        raise NotImplementedError

    def add(self, image_id, image_file):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns an `glance.store.ImageAddResult` object
        containing information about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object

        :retval `glance.store.ImageAddResult` object
        :raises `glance.common.exception.Duplicate` if the image already
                existed
        """
        raise NotImplementedError

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        raise NotImplementedError
