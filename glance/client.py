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

import errno
import json
import logging
import os

import glance.api.v1
from glance.common import client as base_client
from glance.common import exception
from glance.common import utils

logger = logging.getLogger(__name__)
SUPPORTED_PARAMS = glance.api.v1.SUPPORTED_PARAMS
SUPPORTED_FILTERS = glance.api.v1.SUPPORTED_FILTERS


class V1Client(base_client.BaseClient):

    """Main client class for accessing Glance resources"""

    DEFAULT_PORT = 9292
    DEFAULT_DOC_ROOT = "/v1"

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
        params = self._extract_params(kwargs, SUPPORTED_PARAMS)
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
        params = self._extract_params(kwargs, SUPPORTED_PARAMS)
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

    def _get_image_size(self, image_data):
        """
        Analyzes the incoming image file and attempts to determine
        its size.

        :param image_data: The input to the client, typically a file
                           redirected from stdin.
        :retval The image file's size or None if it cannot be determined.
        """
        # For large images, we need to supply the size of the
        # image file. See LP Bugs #827660 and #845788.
        if hasattr(image_data, 'seek') and hasattr(image_data, 'tell'):
            try:
                image_data.seek(0, os.SEEK_END)
                image_size = image_data.tell()
                image_data.seek(0)
                return image_size
            except IOError, e:
                if e.errno == errno.ESPIPE:
                    # Illegal seek. This means the user is trying
                    # to pipe image data to the client, e.g.
                    # echo testdata | bin/glance add blah..., or
                    # that stdin is empty
                    return None
                else:
                    raise

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
            image_size = self._get_image_size(image_data)
            if image_size:
                headers['x-image-meta-size'] = image_size
                headers['content-length'] = image_size
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
            image_size = self._get_image_size(image_data)
            if image_size:
                headers['x-image-meta-size'] = image_size
                headers['content-length'] = image_size
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

    def get_cached_images(self, **kwargs):
        """
        Returns a list of images stored in the image cache.
        """
        res = self.do_request("GET", "/cached_images")
        data = json.loads(res.read())['cached_images']
        return data

    def get_queued_images(self, **kwargs):
        """
        Returns a list of images queued for caching
        """
        res = self.do_request("GET", "/queued_images")
        data = json.loads(res.read())['queued_images']
        return data

    def delete_cached_image(self, image_id):
        """
        Delete a specified image from the cache
        """
        self.do_request("DELETE", "/cached_images/%s" % image_id)
        return True

    def delete_all_cached_images(self):
        """
        Delete all cached images
        """
        res = self.do_request("DELETE", "/cached_images")
        data = json.loads(res.read())
        num_deleted = data['num_deleted']
        return num_deleted

    def queue_image_for_caching(self, image_id):
        """
        Queue an image for prefetching into cache
        """
        self.do_request("PUT", "/queued_images/%s" % image_id)
        return True

    def delete_queued_image(self, image_id):
        """
        Delete a specified image from the cache queue
        """
        self.do_request("DELETE", "/queued_images/%s" % image_id)
        return True

    def delete_all_queued_images(self):
        """
        Delete all queued images
        """
        res = self.do_request("DELETE", "/queued_images")
        data = json.loads(res.read())
        num_deleted = data['num_deleted']
        return num_deleted

    def get_image_members(self, image_id):
        """Returns a mapping of image memberships from Registry"""
        res = self.do_request("GET", "/images/%s/members" % image_id)
        data = json.loads(res.read())['members']
        return data

    def get_member_images(self, member_id):
        """Returns a mapping of image memberships from Registry"""
        res = self.do_request("GET", "/shared-images/%s" % member_id)
        data = json.loads(res.read())['shared_images']
        return data

    def _validate_assocs(self, assocs):
        """
        Validates membership associations and returns an appropriate
        list of associations to send to the server.
        """
        validated = []
        for assoc in assocs:
            assoc_data = dict(member_id=assoc['member_id'])
            if 'can_share' in assoc:
                assoc_data['can_share'] = bool(assoc['can_share'])
            validated.append(assoc_data)
        return validated

    def replace_members(self, image_id, *assocs):
        """
        Replaces the membership associations for a given image_id.
        Each subsequent argument is a dictionary mapping containing a
        'member_id' that should have access to the image_id.  A
        'can_share' boolean can also be specified to allow the member
        to further share the image.  An example invocation allowing
        'rackspace' to access image 1 and 'google' to access image 1
        with permission to share::

            c = glance.client.Client(...)
            c.update_members(1, {'member_id': 'rackspace'},
                             {'member_id': 'google', 'can_share': True})
        """
        # Understand the associations
        body = json.dumps(self._validate_assocs(assocs))
        self.do_request("PUT", "/images/%s/members" % image_id, body,
                        {'content-type': 'application/json'})
        return True

    def add_member(self, image_id, member_id, can_share=None):
        """
        Adds a membership association between image_id and member_id.
        If can_share is not specified and the association already
        exists, no change is made; if the association does not already
        exist, one is created with can_share defaulting to False.
        When can_share is specified, the association is created if it
        doesn't already exist, and the can_share attribute is set
        accordingly.  Example invocations allowing 'rackspace' to
        access image 1 and 'google' to access image 1 with permission
        to share::

            c = glance.client.Client(...)
            c.add_member(1, 'rackspace')
            c.add_member(1, 'google', True)
        """
        body = None
        headers = {}
        # Generate the body if appropriate
        if can_share is not None:
            body = json.dumps(dict(member=dict(can_share=bool(can_share))))
            headers['content-type'] = 'application/json'

        self.do_request("PUT", "/images/%s/members/%s" %
                        (image_id, member_id), body, headers)
        return True

    def delete_member(self, image_id, member_id):
        """
        Deletes the membership assocation.  If the
        association does not exist, no action is taken; otherwise, the
        indicated association is deleted.  An example invocation
        removing the accesses of 'rackspace' to image 1 and 'google'
        to image 2::

            c = glance.client.Client(...)
            c.delete_member(1, 'rackspace')
            c.delete_member(2, 'google')
        """
        self.do_request("DELETE", "/images/%s/members/%s" %
                        (image_id, member_id))
        return True


Client = V1Client
