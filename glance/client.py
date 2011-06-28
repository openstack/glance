# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import json

from glance.api.v1 import images as v1_images
from glance.common import client as base_client
from glance.common import exception
from glance import utils

#TODO(jaypipes) Allow a logger param for client classes


class V1Client(base_client.BaseClient):

    """Main client class for accessing Glance resources"""

    DEFAULT_PORT = 9292

    def __init__(self, host, port=None, use_ssl=False, doc_root="/v1"):
        """
        Creates a new client to a Glance API service.

        :param host: The host where Glance resides
        :param port: The port where Glance resides (defaults to 9292)
        :param use_ssl: Should we use HTTPS? (defaults to False)
        :param doc_root: Prefix for all URLs we request from host
        """

        port = port or self.DEFAULT_PORT
        self.doc_root = doc_root
        super(Client, self).__init__(host, port, use_ssl)

    def do_request(self, method, action, body=None, headers=None, params=None):
        action = "%s/%s" % (self.doc_root, action.lstrip("/"))
        return super(V1Client, self).do_request(method, action, body,
                                                headers, params)

    def get_images(self, **kwargs):
        """
        Returns a list of image id/name mappings from Registry

        :param filters: dictionary of attributes by which the resulting
                        collection of images should be filtered
        :param marker: id after which to start the page of images
        :param limit: maximum number of items to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to to order results (asc, desc)
        """
        params = self._extract_params(kwargs, v1_images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images", params=params)
        data = json.loads(res.read())['images']
        return data

    def get_images_detailed(self, **kwargs):
        """
        Returns a list of detailed image data mappings from Registry

        :param filters: dictionary of attributes by which the resulting
                        collection of images should be filtered
        :param marker: id after which to start the page of images
        :param limit: maximum number of items to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to to order results (asc, desc)
        """

        print kwargs
        params = self._extract_params(kwargs, v1_images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images/detail", params=params)
        data = json.loads(res.read())['images']
        return data

    def get_image(self, image_id):
        """
        Returns a tuple with the image's metadata and the raw disk image as
        a mime-encoded blob stream for the supplied opaque image identifier.

        :param image_id: The opaque image identifier

        :retval Tuple containing (image_meta, image_blob)
        :raises exception.NotFound if image is not found
        """
        res = self.do_request("GET", "/images/%s" % image_id)

        image = utils.get_image_meta_from_headers(res)
        return image, base_client.ImageBodyIterator(res)

    def get_image_meta(self, image_id):
        """
        Returns a mapping of image metadata from Registry

        :raises exception.NotFound if image is not in registry
        """
        res = self.do_request("HEAD", "/images/%s" % image_id)

        image = utils.get_image_meta_from_headers(res)
        return image

    def add_image(self, image_meta=None, image_data=None):
        """
        Tells Glance about an image's metadata as well
        as optionally the image_data itself

        :param image_meta: Optional Mapping of information about the
                           image
        :param image_data: Optional string of raw image data
                           or file-like object that can be
                           used to read the image data

        :retval The newly-stored image's metadata.
        """

        headers = utils.image_meta_to_http_headers(image_meta or {})

        if image_data:
            body = image_data
            headers['content-type'] = 'application/octet-stream'
        else:
            body = None

        res = self.do_request("POST", "/images", body, headers)
        data = json.loads(res.read())
        return data['image']

    def update_image(self, image_id, image_meta=None, image_data=None):
        """
        Updates Glance's information about an image
        """
        if image_meta is None:
            image_meta = {}

        headers = utils.image_meta_to_http_headers(image_meta)

        if image_data:
            body = image_data
            headers['content-type'] = 'application/octet-stream'
        else:
            body = None

        res = self.do_request("PUT", "/images/%s" % image_id, body, headers)
        data = json.loads(res.read())
        return data['image']

    def delete_image(self, image_id):
        """
        Deletes Glance's information about an image
        """
        self.do_request("DELETE", "/images/%s" % image_id)
        return True


Client = V1Client
