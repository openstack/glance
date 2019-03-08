# Copyright 2018 RedHat Inc.
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

import os

from oslo_serialization import jsonutils as json

from glance.common import client as base_client
from glance.common import exception
from glance.i18n import _


class CacheClient(base_client.BaseClient):

    DEFAULT_PORT = 9292
    DEFAULT_DOC_ROOT = '/v2'

    def delete_cached_image(self, image_id):
        """
        Delete a specified image from the cache
        """
        self.do_request("DELETE", "/cached_images/%s" % image_id)
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


def get_client(host, port=None, timeout=None, use_ssl=False, username=None,
               password=None, project=None,
               user_domain_id=None, project_domain_id=None,
               auth_url=None, auth_strategy=None,
               auth_token=None, region=None, insecure=False):
    """
    Returns a new client Glance client object based on common kwargs.
    If an option isn't specified falls back to common environment variable
    defaults.
    """

    if auth_url or os.getenv('OS_AUTH_URL'):
        force_strategy = 'keystone'
    else:
        force_strategy = None

    creds = {
        'username': username or
        os.getenv('OS_AUTH_USER', os.getenv('OS_USERNAME')),
        'password': password or
        os.getenv('OS_AUTH_KEY', os.getenv('OS_PASSWORD')),
        'project': project or
        os.getenv('OS_AUTH_PROJECT', os.getenv('OS_PROJECT_NAME')),
        'auth_url': auth_url or
        os.getenv('OS_AUTH_URL'),
        'strategy': force_strategy or
        auth_strategy or
        os.getenv('OS_AUTH_STRATEGY', 'noauth'),
        'region': region or
        os.getenv('OS_REGION_NAME'),
        'user_domain_id': user_domain_id or os.getenv(
            'OS_USER_DOMAIN_ID', 'default'),
        'project_domain_id': project_domain_id or os.getenv(
            'OS_PROJECT_DOMAIN_ID', 'default')
    }

    if creds['strategy'] == 'keystone' and not creds['auth_url']:
        msg = _("--os_auth_url option or OS_AUTH_URL environment variable "
                "required when keystone authentication strategy is enabled\n")
        raise exception.ClientConfigurationError(msg)

    return CacheClient(
        host=host,
        port=port,
        timeout=timeout,
        use_ssl=use_ssl,
        auth_token=auth_token or
        os.getenv('OS_TOKEN'),
        creds=creds,
        insecure=insecure,
        configure_via_auth=False)
