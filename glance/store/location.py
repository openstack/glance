# Copyright 2011 OpenStack Foundation
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
A class that describes the location of an image in Glance.

In Glance, an image can either be **stored** in Glance, or it can be
**registered** in Glance but actually be stored somewhere else.

We needed a class that could support the various ways that Glance
describes where exactly an image is stored.

An image in Glance has two location properties: the image URI
and the image storage URI.

The image URI is essentially the permalink identifier for the image.
It is displayed in the output of various Glance API calls and,
while read-only, is entirely user-facing. It shall **not** contain any
security credential information at all. The Glance image URI shall
be the host:port of that Glance API server along with /images/<IMAGE_ID>.

The Glance storage URI is an internal URI structure that Glance
uses to maintain critical information about how to access the images
that it stores in its storage backends. It **may contain** security
credentials and is **not** user-facing.
"""

import six.moves.urllib.parse as urlparse

from glance.common import exception
import glance.openstack.common.log as logging

LOG = logging.getLogger(__name__)

SCHEME_TO_CLS_MAP = {}


def get_location_from_uri(uri):
    """
    Given a URI, return a Location object that has had an appropriate
    store parse the URI.

    :param uri: A URI that could come from the end-user in the Location
                attribute/header

    Example URIs:
        https://user:pass@example.com:80/images/some-id
        http://images.oracle.com/123456
        swift://example.com/container/obj-id
        swift://user:account:pass@authurl.com/container/obj-id
        swift+http://user:account:pass@authurl.com/container/obj-id
        s3://accesskey:secretkey@s3.amazonaws.com/bucket/key-id
        s3+https://accesskey:secretkey@s3.amazonaws.com/bucket/key-id
        file:///var/lib/glance/images/1
        cinder://volume-id
        vsphere://server_host/folder/file_path?dcPath=dc_path&dsName=ds_name
    """
    pieces = urlparse.urlparse(uri)
    if pieces.scheme not in SCHEME_TO_CLS_MAP.keys():
        raise exception.UnknownScheme(scheme=pieces.scheme)
    scheme_info = SCHEME_TO_CLS_MAP[pieces.scheme]
    return Location(pieces.scheme, uri=uri,
                    store_location_class=scheme_info['location_class'])


def register_scheme_map(scheme_map):
    """
    Given a mapping of 'scheme' to store_name, adds the mapping to the
    known list of schemes if it does not already exist.
    """
    for (k, v) in scheme_map.items():
        if k not in SCHEME_TO_CLS_MAP:
            LOG.debug(_("Registering scheme %(k)s with %(v)s") % {'k': k,
                                                                  'v': v})
            SCHEME_TO_CLS_MAP[k] = v


class Location(object):

    """
    Class describing the location of an image that Glance knows about
    """

    def __init__(self, store_name, store_location_class,
                 uri=None, image_id=None, store_specs=None):
        """
        Create a new Location object.

        :param store_name: The string identifier/scheme of the storage backend
        :param store_location_class: The store location class to use
                                     for this location instance.
        :param image_id: The identifier of the image in whatever storage
                         backend is used.
        :param uri: Optional URI to construct location from
        :param store_specs: Dictionary of information about the location
                            of the image that is dependent on the backend
                            store
        """
        self.store_name = store_name
        self.image_id = image_id
        self.store_specs = store_specs or {}
        self.store_location = store_location_class(self.store_specs)
        if uri:
            self.store_location.parse_uri(uri)

    def get_store_uri(self):
        """
        Returns the Glance image URI, which is the host:port of the API server
        along with /images/<IMAGE_ID>
        """
        return self.store_location.get_uri()

    def get_uri(self):
        return None


class StoreLocation(object):

    """
    Base class that must be implemented by each store
    """

    def __init__(self, store_specs):
        self.specs = store_specs
        if self.specs:
            self.process_specs()

    def process_specs(self):
        """
        Subclasses should implement any processing of the self.specs collection
        such as storing credentials and possibly establishing connections.
        """
        pass

    def get_uri(self):
        """
        Subclasses should implement a method that returns an internal URI that,
        when supplied to the StoreLocation instance, can be interpreted by the
        StoreLocation's parse_uri() method. The URI returned from this method
        shall never be public and only used internally within Glance, so it is
        fine to encode credentials in this URI.
        """
        raise NotImplementedError("StoreLocation subclass must implement "
                                  "get_uri()")

    def parse_uri(self, uri):
        """
        Subclasses should implement a method that accepts a string URI and
        sets appropriate internal fields such that a call to get_uri() will
        return a proper internal URI
        """
        raise NotImplementedError("StoreLocation subclass must implement "
                                  "parse_uri()")
