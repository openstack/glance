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
    def lookup(cls, parsed_uri):
        """
        Takes a parsed_uri, checks if that image is registered in Parallax,
        and if so, returns the image metadata. If the image does not exist,
        we return None.
        """
        scheme = parsed_uri.scheme
        if scheme == 'http':
            conn_class = httplib.HTTPConnection
        elif scheme == 'https':
            conn_class = httplib.HTTPSConnection
        else:
            raise ImageRegistryException(
                "Unrecognized scheme '%s'" % scheme)

        conn = conn_class(parsed_uri.netloc)
        try:
            conn.request('GET', parsed_uri.path, "", {})
            response = conn.getresponse()

            # The image exists
            if response.status == 200: 
                result = response.read()
                image_json = json.loads(result)
                try:
                    return image_json["image"]
                except KeyError:
                    raise ImageRegistryException("Missing 'image' key")
        except Exception: # gaierror
            return None
        finally:
            conn.close()


REGISTRY_ADAPTERS = {
    'parallax': Parallax
}


def lookup_by_registry(registry, image_uri):
    """ Convenience function to lookup based on a registry protocol """
    try:
        adapter = REGISTRY_ADAPTERS[registry]
    except KeyError:
        raise UnknownImageRegistry("'%s' not found" % registry)
    
    parsed_uri = urlparse.urlparse(image_uri)
    return adapter.lookup(parsed_uri)
