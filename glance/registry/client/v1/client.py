# Copyright 2013 OpenStack Foundation
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

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import excutils

from glance.common.client import BaseClient
from glance.common import crypt
from glance import i18n
from glance.registry.api.v1 import images

LOG = logging.getLogger(__name__)
_LE = i18n._LE


class RegistryClient(BaseClient):

    """A client for the Registry image metadata service."""

    DEFAULT_PORT = 9191

    def __init__(self, host=None, port=None, metadata_encryption_key=None,
                 identity_headers=None, **kwargs):
        """
        :param metadata_encryption_key: Key used to encrypt 'location' metadata
        """
        self.metadata_encryption_key = metadata_encryption_key
        # NOTE (dprince): by default base client overwrites host and port
        # settings when using keystone. configure_via_auth=False disables
        # this behaviour to ensure we still send requests to the Registry API
        self.identity_headers = identity_headers
        # store available passed request id for do_request call
        self._passed_request_id = kwargs.pop('request_id', None)
        BaseClient.__init__(self, host, port, configure_via_auth=False,
                            **kwargs)

    def decrypt_metadata(self, image_metadata):
        if self.metadata_encryption_key:
            if image_metadata.get('location'):
                location = crypt.urlsafe_decrypt(self.metadata_encryption_key,
                                                 image_metadata['location'])
                image_metadata['location'] = location
            if image_metadata.get('location_data'):
                ld = []
                for loc in image_metadata['location_data']:
                    url = crypt.urlsafe_decrypt(self.metadata_encryption_key,
                                                loc['url'])
                    ld.append({'id': loc['id'], 'url': url,
                               'metadata': loc['metadata'],
                               'status': loc['status']})
                image_metadata['location_data'] = ld
        return image_metadata

    def encrypt_metadata(self, image_metadata):
        if self.metadata_encryption_key:
            location_url = image_metadata.get('location')
            if location_url:
                location = crypt.urlsafe_encrypt(self.metadata_encryption_key,
                                                 location_url,
                                                 64)
                image_metadata['location'] = location
            if image_metadata.get('location_data'):
                ld = []
                for loc in image_metadata['location_data']:
                    if loc['url'] == location_url:
                        url = location
                    else:
                        url = crypt.urlsafe_encrypt(
                            self.metadata_encryption_key, loc['url'], 64)
                    ld.append({'url': url, 'metadata': loc['metadata'],
                               'status': loc['status'],
                               # NOTE(zhiyan): New location has no ID field.
                               'id': loc.get('id')})
                image_metadata['location_data'] = ld
        return image_metadata

    def get_images(self, **kwargs):
        """
        Returns a list of image id/name mappings from Registry

        :param filters: dict of keys & expected values to filter results
        :param marker: image id after which to start page
        :param limit: max number of images to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to order results (asc, desc)
        """
        params = self._extract_params(kwargs, images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images", params=params)
        image_list = jsonutils.loads(res.read())['images']
        for image in image_list:
            image = self.decrypt_metadata(image)
        return image_list

    def do_request(self, method, action, **kwargs):
        try:
            kwargs['headers'] = kwargs.get('headers', {})
            kwargs['headers'].update(self.identity_headers or {})
            if self._passed_request_id:
                kwargs['headers']['X-Openstack-Request-ID'] = (
                    self._passed_request_id)
            res = super(RegistryClient, self).do_request(method,
                                                         action,
                                                         **kwargs)
            status = res.status
            request_id = res.getheader('x-openstack-request-id')
            msg = ("Registry request %(method)s %(action)s HTTP %(status)s"
                   " request id %(request_id)s" %
                   {'method': method, 'action': action,
                    'status': status, 'request_id': request_id})
            LOG.debug(msg)

        except Exception as exc:
            with excutils.save_and_reraise_exception():
                exc_name = exc.__class__.__name__
                LOG.exception(_LE("Registry client request %(method)s "
                                  "%(action)s raised %(exc_name)s"),
                              {'method': method, 'action': action,
                               'exc_name': exc_name})
        return res

    def get_images_detailed(self, **kwargs):
        """
        Returns a list of detailed image data mappings from Registry

        :param filters: dict of keys & expected values to filter results
        :param marker: image id after which to start page
        :param limit: max number of images to return
        :param sort_key: results will be ordered by this image attribute
        :param sort_dir: direction in which to order results (asc, desc)
        """
        params = self._extract_params(kwargs, images.SUPPORTED_PARAMS)
        res = self.do_request("GET", "/images/detail", params=params)
        image_list = jsonutils.loads(res.read())['images']
        for image in image_list:
            image = self.decrypt_metadata(image)
        return image_list

    def get_image(self, image_id):
        """Returns a mapping of image metadata from Registry."""
        res = self.do_request("GET", "/images/%s" % image_id)
        data = jsonutils.loads(res.read())['image']
        return self.decrypt_metadata(data)

    def add_image(self, image_metadata):
        """
        Tells registry about an image's metadata
        """
        headers = {
            'Content-Type': 'application/json',
        }

        if 'image' not in image_metadata:
            image_metadata = dict(image=image_metadata)

        encrypted_metadata = self.encrypt_metadata(image_metadata['image'])
        image_metadata['image'] = encrypted_metadata
        body = jsonutils.dumps(image_metadata)

        res = self.do_request("POST", "/images", body=body, headers=headers)
        # Registry returns a JSONified dict(image=image_info)
        data = jsonutils.loads(res.read())
        image = data['image']
        return self.decrypt_metadata(image)

    def update_image(self, image_id, image_metadata, purge_props=False,
                     from_state=None):
        """
        Updates Registry's information about an image
        """
        if 'image' not in image_metadata:
            image_metadata = dict(image=image_metadata)

        encrypted_metadata = self.encrypt_metadata(image_metadata['image'])
        image_metadata['image'] = encrypted_metadata
        image_metadata['from_state'] = from_state
        body = jsonutils.dumps(image_metadata)

        headers = {
            'Content-Type': 'application/json',
        }

        if purge_props:
            headers["X-Glance-Registry-Purge-Props"] = "true"

        res = self.do_request("PUT", "/images/%s" % image_id, body=body,
                              headers=headers)
        data = jsonutils.loads(res.read())
        image = data['image']
        return self.decrypt_metadata(image)

    def delete_image(self, image_id):
        """
        Deletes Registry's information about an image
        """
        res = self.do_request("DELETE", "/images/%s" % image_id)
        data = jsonutils.loads(res.read())
        image = data['image']
        return image

    def get_image_members(self, image_id):
        """Return a list of membership associations from Registry."""
        res = self.do_request("GET", "/images/%s/members" % image_id)
        data = jsonutils.loads(res.read())['members']
        return data

    def get_member_images(self, member_id):
        """Return a list of membership associations from Registry."""
        res = self.do_request("GET", "/shared-images/%s" % member_id)
        data = jsonutils.loads(res.read())['shared_images']
        return data

    def replace_members(self, image_id, member_data):
        """Replace registry's information about image membership."""
        if isinstance(member_data, (list, tuple)):
            member_data = dict(memberships=list(member_data))
        elif (isinstance(member_data, dict) and
              'memberships' not in member_data):
            member_data = dict(memberships=[member_data])

        body = jsonutils.dumps(member_data)

        headers = {'Content-Type': 'application/json', }

        res = self.do_request("PUT", "/images/%s/members" % image_id,
                              body=body, headers=headers)
        return self.get_status_code(res) == 204

    def add_member(self, image_id, member_id, can_share=None):
        """Add to registry's information about image membership."""
        body = None
        headers = {}
        # Build up a body if can_share is specified
        if can_share is not None:
            body = jsonutils.dumps(dict(member=dict(can_share=can_share)))
            headers['Content-Type'] = 'application/json'

        url = "/images/%s/members/%s" % (image_id, member_id)
        res = self.do_request("PUT", url, body=body,
                              headers=headers)
        return self.get_status_code(res) == 204

    def delete_member(self, image_id, member_id):
        """Delete registry's information about image membership."""
        res = self.do_request("DELETE", "/images/%s/members/%s" %
                              (image_id, member_id))
        return self.get_status_code(res) == 204
