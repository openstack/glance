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


class RegistryAdapterException(Exception):
    """ Base class for all RegistryAdapter exceptions """
    pass


class UnknownRegistryAdapter(RegistryAdapterException):
    """ Raised if we don't recognize the requested Registry protocol """
    pass


class RegistryAdapter(object):
    """ Base class for all image endpoints """

    @classmethod
    def lookup(cls, parsed_uri):
        """ Subclasses must define a lookup method which returns an dictionary
        representing the image.
        """
        raise NotImplementedError


class ParallaxAdapter(RegistryAdapter):
    """
    ParallaxAdapter stuff
    """

    @classmethod
    def lookup(cls, parsed_uri):
        """
        Take an image uri from Nova, and check if that parallax instance has a
        register of it. Takes an unparsed URI, returns a dict of the image 
        registration metadata or None.
        """
        scheme = parsed_uri.scheme
        if scheme == 'http':
            conn_class = httplib.HTTPConnection
        elif scheme == 'https':
            conn_class = httplib.HTTPSConnection
        else:
            raise RegistryAdapterException(
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
                    raise RegistryAdapterException("Missing 'image' key")
        finally:
            conn.close()


class FakeParallaxAdapter(ParallaxAdapter):
    """
    A Mock ParallaxAdapter returns a mocked response for any uri with 
    one or more 'success' and None for everything else.
    """

    @classmethod
    def lookup(cls, parsed_uri):
        if parsed_uri.netloc.count("success"):
            # A successful attempt
            files = [dict(location="teststr://chunk0", size=1235),
                     dict(location="teststr://chunk1", size=12345)]
            
            return dict(files=files)


REGISTRY_ADAPTERS = {
    'parallax': ParallaxAdapter,
    'fake_parallax': FakeParallaxAdapter
}

def lookup_by_registry(registry, image_uri):
    """ Convenience function to lookup based on a registry protocol """
    try:
        adapter = REGISTRY_ADAPTERS[registry]
    except KeyError:
        raise UnknownRegistryAdapter("'%s' not found" % registry)
    
    parsed_uri = urlparse.urlparse(image_uri)
    return adapter.lookup(parsed_uri)


