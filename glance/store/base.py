# Copyright 2011 OpenStack Foundation
# Copyright 2012 RedHat Inc.
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

from glance.common import exception
from glance.openstack.common import importutils
import glance.openstack.common.log as logging
from glance.openstack.common import strutils
from glance.openstack.common import units

LOG = logging.getLogger(__name__)


def _exception_to_unicode(exc):
    try:
        return unicode(exc)
    except UnicodeError:
        try:
            return strutils.safe_decode(str(exc), errors='ignore')
        except UnicodeError:
            msg = (_("Caught '%(exception)s' exception.") %
                   {"exception": exc.__class__.__name__})
            return strutils.safe_decode(msg, errors='ignore')


class Store(object):

    CHUNKSIZE = 16 * units.Mi  # 16M

    def __init__(self, context=None, location=None):
        """
        Initialize the Store
        """
        self.store_location_class = None
        self.context = context
        self.configure()

        try:
            self.configure_add()
        except exception.BadStoreConfiguration as e:
            self.add = self.add_disabled
            msg = (_(u"Failed to configure store correctly: %s "
                     "Disabling add method.") % _exception_to_unicode(e))
            LOG.warn(msg)

    def configure(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method.
        """
        pass

    def get_schemes(self):
        """
        Returns a tuple of schemes which this store can handle.
        """
        raise NotImplementedError

    def get_store_location_class(self):
        """
        Returns the store location class that is used by this store.
        """
        if not self.store_location_class:
            class_name = "%s.StoreLocation" % (self.__module__)
            LOG.debug("Late loading location class %s", class_name)
            self.store_location_class = importutils.import_class(class_name)
        return self.store_location_class

    def configure_add(self):
        """
        This is like `configure` except that it's specifically for
        configuring the store to accept objects.

        If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`.
        """
        pass

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        raise NotImplementedError

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        raise NotImplementedError

    def add_disabled(self, *args, **kwargs):
        """
        Add method that raises an exception because the Store was
        not able to be configured properly and therefore the add()
        method would error out.
        """
        raise exception.StoreAddDisabled

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

    def set_acls(self, location, public=False, read_tenants=[],
                 write_tenants=[]):
        """
        Sets the read and write access control list for an image in the
        backend store.

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()
        :public A boolean indicating whether the image should be public.
        :read_tenants A list of tenant strings which should be granted
                      read access for an image.
        :write_tenants A list of tenant strings which should be granted
                      write access for an image.
        """
        raise NotImplementedError
