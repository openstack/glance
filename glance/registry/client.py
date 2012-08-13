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
Simple client class to speak with any RESTful service that implements
the Glance Registry API
"""

import json

from glance.common.client import BaseClient
from glance.common import crypt
import glance.openstack.common.log as logging
from glance.registry.api.v1 import images

LOG = logging.getLogger(__name__)


class RegistryClient(BaseClient):

    """A client for the Registry image metadata service"""

    DEFAULT_PORT = 9191

    def __init__(self, host=None, port=None, metadata_encryption_key=None,
                 **kwargs):
        """
        :param metadata_encryption_key: Key used to encrypt 'location' metadata
        """
        self.metadata_encryption_key = metadata_encryption_key
        # NOTE (dprince): by default base client overwrites host and port
        # settings when using keystone. configure_via_auth=False disables
        # this behaviour to ensure we still send requests to the Registry API
        BaseClient.__init__(self, host, port, configure_via_auth=False,
                            **kwargs)

    def decrypt_metadata(self, image_metadata):
        if (self.metadata_encryption_key is not None
            and 'location' in image_metadata.keys()
            and image_metadata['location'] is not None):
            location = crypt.urlsafe_decrypt(self.metadata_encryption_key,
                                             image_metadata['location'])
            image_metadata['location'] = location
        return image_metadata

    def encrypt_metadata(self, image_metadata):
        if (self.metadata_encryption_key is not None
            and 'location' in image_metadata.keys()
            and image_metadata['location'] is not None):
            location = crypt.urlsafe_encrypt(self.metadata_encryption_key,
                                             image_metadata['location'], 64)
            image_metadata['location'] = location
        return image_metadata

    def get_images(self, **kwargs):
        """
        Returns a list of image id/name mappings from Registry

        :param filters: dict of keys & expected values to filter results
        :param marker: image id after which to start page
        :param limit: max number of images to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to to order results (asc, desc)
        """
        params = self._extract_params(kwargs, images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images", params=params)
        image_list = json.loads(res.read())['images']
        for image in image_list:
            image = self.decrypt_metadata(image)
        return image_list

    def do_request(self, method, action, **kwargs):
        try:
            res = super(RegistryClient, self).do_request(method,
                  action, **kwargs)
            status = res.status
            request_id = res.getheader('x-openstack-request-id')
            msg = _("Registry request %(method)s %(action)s HTTP %(status)s"\
                  " request id %(request_id)s")
            LOG.debug(msg % locals())

        except:
            LOG.exception(_("Registry request %(method)s %(action)s Exception")
                        % locals())
            raise
        return res

    def get_images_detailed(self, **kwargs):
        """
        Returns a list of detailed image data mappings from Registry

        :param filters: dict of keys & expected values to filter results
        :param marker: image id after which to start page
        :param limit: max number of images to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to to order results (asc, desc)
        """
        params = self._extract_params(kwargs, images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images/detail", params=params)
        image_list = json.loads(res.read())['images']
        for image in image_list:
            image = self.decrypt_metadata(image)
        return image_list

    def get_image(self, image_id):
        """Returns a mapping of image metadata from Registry"""
        res = self.do_request("GET", "/images/%s" % image_id)
        data = json.loads(res.read())['image']
        return self.decrypt_metadata(data)

    def add_image(self, image_metadata):
        """
        Tells registry about an image's metadata
        """
        headers = {
            'Content-Type': 'application/json',
        }

        if 'image' not in image_metadata.keys():
            image_metadata = dict(image=image_metadata)

        image_metadata['image'] = self.encrypt_metadata(
                                      image_metadata['image'])
        body = json.dumps(image_metadata)

        res = self.do_request("POST", "/images", body=body, headers=headers)
        # Registry returns a JSONified dict(image=image_info)
        data = json.loads(res.read())
        image = data['image']
        return self.decrypt_metadata(image)

    def update_image(self, image_id, image_metadata, purge_props=False):
        """
        Updates Registry's information about an image
        """
        if 'image' not in image_metadata.keys():
            image_metadata = dict(image=image_metadata)

        image_metadata['image'] = self.encrypt_metadata(
                                      image_metadata['image'])
        body = json.dumps(image_metadata)

        headers = {
            'Content-Type': 'application/json',
        }

        if purge_props:
            headers["X-Glance-Registry-Purge-Props"] = "true"

        res = self.do_request("PUT", "/images/%s" % image_id, body=body,
                              headers=headers)
        data = json.loads(res.read())
        image = data['image']
        return self.decrypt_metadata(image)

    def delete_image(self, image_id):
        """
        Deletes Registry's information about an image
        """
        res = self.do_request("DELETE", "/images/%s" % image_id)
        data = json.loads(res.read())
        image = data['image']
        return image

    def get_image_members(self, image_id):
        """Returns a list of membership associations from Registry"""
        res = self.do_request("GET", "/images/%s/members" % image_id)
        data = json.loads(res.read())['members']
        return data

    def get_member_images(self, member_id):
        """Returns a list of membership associations from Registry"""
        res = self.do_request("GET", "/shared-images/%s" % member_id)
        data = json.loads(res.read())['shared_images']
        return data

    def replace_members(self, image_id, member_data):
        """Replaces Registry's information about image membership"""
        if isinstance(member_data, (list, tuple)):
            member_data = dict(memberships=list(member_data))
        elif (isinstance(member_data, dict) and
              'memberships' not in member_data):
            member_data = dict(memberships=[member_data])

        body = json.dumps(member_data)

        headers = {'Content-Type': 'application/json', }

        res = self.do_request("PUT", "/images/%s/members" % image_id,
                              body=body, headers=headers)
        return self.get_status_code(res) == 204

    def add_member(self, image_id, member_id, can_share=None):
        """Adds to Registry's information about image membership"""
        body = None
        headers = {}
        # Build up a body if can_share is specified
        if can_share is not None:
            body = json.dumps(dict(member=dict(can_share=can_share)))
            headers['Content-Type'] = 'application/json'

        url = "/images/%s/members/%s" % (image_id, member_id)
        res = self.do_request("PUT", url, body=body,
                              headers=headers)
        return self.get_status_code(res) == 204

    def delete_member(self, image_id, member_id):
        """Deletes Registry's information about image membership"""
        res = self.do_request("DELETE", "/images/%s/members/%s" %
                              (image_id, member_id))
        return self.get_status_code(res) == 204
