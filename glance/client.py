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
        try:
            self.connection_type = {'http': httplib.HTTPConnection,
                                    'https': httplib.HTTPSConnection}\
                                    [url.scheme]
            # Do a quick ping to see if the server is even available...
            c = self.connection_type(self.netloc, self.port)
            c.connect()
            c.close()
        except KeyError:
            raise ClientConnectionError("Unsupported protocol %s. Unable to "
                                        "connect to server." % url.scheme)
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


class TellerClient(BaseClient):

    """A client for the Teller image caching service"""

    DEFAULT_ADDRESS = 'http://127.0.0.1'
    DEFAULT_PORT = 9191

    def __init__(self, **kwargs):
        """
        Creates a new client to a Teller service.  All args are keyword
        arguments.

        :param address: The address where Teller resides (defaults to
                        http://127.0.0.1)
        :param port: The port where Teller resides (defaults to 9191)
        """
        super(TellerClient, self).__init__(**kwargs)


class ParallaxClient(BaseClient):

    """A client for the Parallax image metadata service"""

    DEFAULT_ADDRESS = 'http://127.0.0.1'
    DEFAULT_PORT = 9292

    def __init__(self, **kwargs):
        """
        Creates a new client to a Parallax service.  All args are keyword
        arguments.

        :param address: The address where Parallax resides (defaults to
                        http://127.0.0.1)
        :param port: The port where Parallax resides (defaults to 9292)
        """
        super(ParallaxClient, self).__init__(**kwargs)

    def get_image_index(self):
        """
        Returns a list of image id/name mappings from Parallax
        """
        try:
            c = self.connection_type(self.netloc, self.port)
            c.request("GET", "images")
            res = c.getresponse()
            if self.get_status_code(res) == 200:
                # Parallax returns a JSONified dict(images=image_list)
                data = json.loads(res.read())['images']
                return data
            else:
                logging.warn("Parallax returned HTTP error %d from "
                             "request for /images", res.status_int)
                return []
        except (socket.error, IOError), e:
            raise ClientConnectionError("Unable to connect to Parallax "
                                        "server. Got error: %s" % e)
        finally:
            c.close()

    def get_image_details(self):
        """
        Returns a list of detailed image data mappings from Parallax
        """
        try:
            c = self.connection_type(self.netloc, self.port)
            c.request("GET", "images/detail")
            res = c.getresponse()
            if self.get_status_code(res) == 200:
                # Parallax returns a JSONified dict(images=image_list)
                data = json.loads(res.read())['images']
                return data
            else:
                logging.warn("Parallax returned HTTP error %d from "
                             "request for /images/detail", res.status_int)
                return []
        finally:
            c.close()

    def get_image_metadata(self, image_id):
        """
        Returns a mapping of image metadata from Parallax

        :raises exception.NotFound if image is not in registry
        """
        try:
            c = self.connection_type(self.netloc, self.port)
            c.request("GET", "images/%s" % image_id)
            res = c.getresponse()
            status_code = self.get_status_code(res)
            if status_code == 200:
                # Parallax returns a JSONified dict(image=image_info)
                data = json.loads(res.read())['image']
                return data
            elif status_code == 404:
                raise exception.NotFound()
        finally:
            c.close()

    def add_image_metadata(self, image_metadata):
        """
        Tells parallax about an image's metadata
        """
        try:
            c = self.connection_type(self.netloc, self.port)
            if 'image' not in image_metadata.keys():
                image_metadata = dict(image=image_metadata)
            body = json.dumps(image_metadata)
            c.request("POST", "images", body)
            res = c.getresponse()
            status_code = self.get_status_code(res)
            if status_code == 200:
                # Parallax returns a JSONified dict(image=image_info)
                data = json.loads(res.read())
                return data['image']['id']
            elif status_code == 400:
                raise BadInputError("Unable to add metadata to Parallax")
            else:
                raise RuntimeError("Unknown error code: %d" % status_code)
        finally:
            c.close()

    def update_image_metadata(self, image_id, image_metadata):
        """
        Updates Parallax's information about an image
        """
        try:
            if 'image' not in image_metadata.keys():
                image_metadata = dict(image=image_metadata)
            c = self.connection_type(self.netloc, self.port)
            body = json.dumps(image_metadata)
            c.request("PUT", "images/%s" % image_id, body)
            res = c.getresponse()
            return self.get_status_code(res) == 200
        finally:
            c.close()

    def delete_image_metadata(self, image_id):
        """
        Deletes Parallax's information about an image
        """
        try:
            c = self.connection_type(self.netloc, self.port)
            c.request("DELETE", "images/%s" % image_id)
            res = c.getresponse()
            return self.get_status_code(res) == 200
        finally:
            c.close()
