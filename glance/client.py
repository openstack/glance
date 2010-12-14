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
Client classes for callers of a Glance system
"""

import httplib
import json
import logging
import urlparse
import socket
import sys

from glance.common import exception

#TODO(jaypipes) Allow a logger param for client classes
#TODO(jaypipes) Raise proper errors or OpenStack API faults


class UnsupportedProtocolError(Exception):
    """
    Error resulting from a client connecting to a server
    on an unsupported protocol
    """
    pass


class ClientConnectionError(Exception):
    """Error resulting from a client connecting to a server"""
    pass


class BadInputError(Exception):
    """Error resulting from a client sending bad input to a server"""
    pass


class BaseClient(object):

    """A base client class"""

    DEFAULT_ADDRESS = 'http://127.0.0.1'
    DEFAULT_PORT = 9090

    def __init__(self, **kwargs):
        """
        Creates a new client to some service.  All args are keyword
        arguments.

        :param address: The address where service resides (defaults to
                        http://127.0.0.1)
        :param port: The port where service resides (defaults to 9090)
        """
        self.address = kwargs.get('address', self.DEFAULT_ADDRESS)
        self.port = kwargs.get('port', self.DEFAULT_PORT)
        url = urlparse.urlparse(self.address)
        self.netloc = url.netloc
        self.protocol = url.scheme
        self.connection = None

    def get_connection_type(self):
        """
        Returns the proper connection type
        """
        try:
            connection_type = {'http': httplib.HTTPConnection,
                               'https': httplib.HTTPSConnection}\
                               [self.protocol]
            return connection_type
        except KeyError:
            raise UnsupportedProtocolError("Unsupported protocol %s. Unable "
                                           " to connect to server."
                                           % self.protocol)

    def do_request(self, method, action, body=None):
        """
        Connects to the server and issues a request.  Handles converting
        any returned HTTP error status codes to OpenStack/Glance exceptions
        and closing the server connection. Returns the result data, or
        raises an appropriate exception.

        :param method: HTTP method ("GET", "POST", "PUT", etc...)
        :param action: part of URL after root netloc
        :param headers: mapping of headers to send
        :param data: string of data to send, or None (default)
        """
        try:
            connection_type = self.get_connection_type()
            c = connection_type(self.netloc, self.port)
            c.request(method, action, body)
            res = c.getresponse()
            status_code = self.get_status_code(res)
            if status_code == httplib.OK:
                return res
            elif status_code == httplib.UNAUTHORIZED:
                raise exception.NotAuthorized
            elif status_code == httplib.FORBIDDEN:
                raise exception.NotAuthorized
            elif status_code == httplib.NOT_FOUND:
                raise exception.NotFound
            elif status_code == httplib.CONFLICT:
                raise exception.Duplicate
            elif status_code == httplib.BAD_REQUEST:
                raise BadInputError
            else:
                raise Exception("Unknown error occurred! %d" % status_code)

        except (socket.error, IOError), e:
            raise ClientConnectionError("Unable to connect to "
                                        "server. Got error: %s" % e)

    def get_status_code(self, response):
        """
        Returns the integer status code from the response, which
        can be either a Webob.Response (used in testing) or httplib.Response
        """
        if hasattr(response, 'status_int'):
            return response.status_int
        else:
            return response.status


class GlanceClient(BaseClient):

    """Main client class for accessing Glance resources"""

    DEFAULT_ADDRESS = 'http://127.0.0.1'
    DEFAULT_PORT = 9292

    def __init__(self, **kwargs):
        """
        Creates a new client to a Glance service.  All args are keyword
        arguments.

        :param address: The address where Glance resides (defaults to
                        http://127.0.0.1)
        :param port: The port where Glance resides (defaults to 9292)
        """
        super(GlanceClient, self).__init__(**kwargs)

    def get_image(self, image_id):
        """
        Returns the raw disk image as a mime-encoded blob stream for the
        supplied opaque image identifier.

        :param image_id: The opaque image identifier

        :raises exception.NotFound if image is not found
        """
        # TODO(jaypipes): Handle other registries than Registry...

        res = self.do_request("GET", "/images/%s" % image_id)
        return res.read()

    def delete_image(self, image_id):
        """
        Deletes Glances's information about an image.
        """
        self.do_request("DELETE", "/images/%s" % image_id)
        return True


class RegistryClient(BaseClient):

    """A client for the Registry image metadata service"""

    DEFAULT_ADDRESS = 'http://127.0.0.1'
    DEFAULT_PORT = 9191

    def __init__(self, **kwargs):
        """
        Creates a new client to a Registry service.  All args are keyword
        arguments.

        :param address: The address where Registry resides (defaults to
                        http://127.0.0.1)
        :param port: The port where Registry resides (defaults to 9191)
        """
        super(RegistryClient, self).__init__(**kwargs)

    def get_images(self):
        """
        Returns a list of image id/name mappings from Registry
        """
        res = self.do_request("GET", "/images")
        data = json.loads(res.read())['images']
        return data

    def get_images_detailed(self):
        """
        Returns a list of detailed image data mappings from Registry
        """
        res = self.do_request("GET", "/images/detail")
        data = json.loads(res.read())['images']
        return data

    def get_image(self, image_id):
        """
        Returns a mapping of image metadata from Registry

        :raises exception.NotFound if image is not in registry
        """
        res = self.do_request("GET", "/images/%s" % image_id)
        data = json.loads(res.read())['image']
        return data

    def add_image(self, image_metadata):
        """
        Tells registry about an image's metadata
        """
        if 'image' not in image_metadata.keys():
            image_metadata = dict(image=image_metadata)
        body = json.dumps(image_metadata)
        res = self.do_request("POST", "/images", body)
        # Registry returns a JSONified dict(image=image_info)
        data = json.loads(res.read())
        return data['image']['id']

    def update_image(self, image_id, image_metadata):
        """
        Updates Registry's information about an image
        """
        if 'image' not in image_metadata.keys():
            image_metadata = dict(image=image_metadata)
        body = json.dumps(image_metadata)
        self.do_request("PUT", "/images/%s" % image_id, body)
        return True

    def delete_image(self, image_id):
        """
        Deletes Registry's information about an image
        """
        self.do_request("DELETE", "/images/%s" % image_id)
        return True
