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

import httplib
import json
import urlparse

from glance import client


class ImageRegistryException(Exception):
    """ Base class for all RegistryAdapter exceptions """
    pass


class UnknownImageRegistry(ImageRegistryException):
    """ Raised if we don't recognize the requested Registry protocol """
    pass


class ImageRegistry(object):
    """ Base class for all image endpoints """

    @classmethod
    def lookup(cls, parsed_uri):
        """ Subclasses must define a lookup method which returns an dictionary
        representing the image.
        """
        raise NotImplementedError


class Parallax(ImageRegistry):
    """
    Parallax stuff
    """

    @classmethod
    def lookup(cls, image_id):
        """
        Takes an image ID and checks if that image is registered in Parallax,
        and if so, returns the image metadata. If the image does not exist,
        we raise NotFound
        """
        # TODO(jaypipes): Make parallax client configurable via options.
        # Unfortunately, the decision to make all adapters have no state
        # hinders this...
        c = client.ParallaxClient()
        return c.get_image(image_id)


REGISTRY_ADAPTERS = {
    'parallax': Parallax
}


def lookup_by_registry(registry, image_id):
    """
    Convenience function to lookup image metadata for the given
    opaque image identifier and registry.

    :param registry: String name of registry to use for lookups
    :param image_id: Opaque image identifier
    """
    try:
        adapter = REGISTRY_ADAPTERS[registry]
    except KeyError:
        raise UnknownImageRegistry("'%s' not found" % registry)

    return adapter.lookup(image_id)
