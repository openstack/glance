# Copyright 2010-2011 OpenStack Foundation
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
Registry's Client API
"""

import os

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils

from glance.common import exception
from glance import i18n
from glance.registry.client.v1 import client

LOG = logging.getLogger(__name__)
_ = i18n._

registry_client_ctx_opts = [
    cfg.BoolOpt('send_identity_headers', default=False,
                help=_("Whether to pass through headers containing user "
                       "and tenant information when making requests to "
                       "the registry. This allows the registry to use the "
                       "context middleware without keystonemiddleware's "
                       "auth_token middleware, removing calls to the keystone "
                       "auth service. It is recommended that when using this "
                       "option, secure communication between glance api and "
                       "glance registry is ensured by means other than "
                       "auth_token middleware.")),
]

CONF = cfg.CONF
CONF.register_opts(registry_client_ctx_opts)
_registry_client = 'glance.registry.client'
CONF.import_opt('registry_client_protocol', _registry_client)
CONF.import_opt('registry_client_key_file', _registry_client)
CONF.import_opt('registry_client_cert_file', _registry_client)
CONF.import_opt('registry_client_ca_file', _registry_client)
CONF.import_opt('registry_client_insecure', _registry_client)
CONF.import_opt('registry_client_timeout', _registry_client)
CONF.import_opt('use_user_token', _registry_client)
CONF.import_opt('admin_user', _registry_client)
CONF.import_opt('admin_password', _registry_client)
CONF.import_opt('admin_tenant_name', _registry_client)
CONF.import_opt('auth_url', _registry_client)
CONF.import_opt('auth_strategy', _registry_client)
CONF.import_opt('auth_region', _registry_client)
CONF.import_opt('metadata_encryption_key', 'glance.common.config')

_CLIENT_CREDS = None
_CLIENT_HOST = None
_CLIENT_PORT = None
_CLIENT_KWARGS = {}
# AES key used to encrypt 'location' metadata
_METADATA_ENCRYPTION_KEY = None


def configure_registry_client():
    """
    Sets up a registry client for use in registry lookups
    """
    global _CLIENT_KWARGS, _CLIENT_HOST, _CLIENT_PORT, _METADATA_ENCRYPTION_KEY
    try:
        host, port = CONF.registry_host, CONF.registry_port
    except cfg.ConfigFileValueError:
        msg = _("Configuration option was not valid")
        LOG.error(msg)
        raise exception.BadRegistryConnectionConfiguration(reason=msg)
    except IndexError:
        msg = _("Could not find required configuration option")
        LOG.error(msg)
        raise exception.BadRegistryConnectionConfiguration(reason=msg)

    _CLIENT_HOST = host
    _CLIENT_PORT = port
    _METADATA_ENCRYPTION_KEY = CONF.metadata_encryption_key
    _CLIENT_KWARGS = {
        'use_ssl': CONF.registry_client_protocol.lower() == 'https',
        'key_file': CONF.registry_client_key_file,
        'cert_file': CONF.registry_client_cert_file,
        'ca_file': CONF.registry_client_ca_file,
        'insecure': CONF.registry_client_insecure,
        'timeout': CONF.registry_client_timeout,
    }

    if not CONF.use_user_token:
        configure_registry_admin_creds()


def configure_registry_admin_creds():
    global _CLIENT_CREDS

    if CONF.auth_url or os.getenv('OS_AUTH_URL'):
        strategy = 'keystone'
    else:
        strategy = CONF.auth_strategy

    _CLIENT_CREDS = {
        'user': CONF.admin_user,
        'password': CONF.admin_password,
        'username': CONF.admin_user,
        'tenant': CONF.admin_tenant_name,
        'auth_url': os.getenv('OS_AUTH_URL') or CONF.auth_url,
        'strategy': strategy,
        'region': CONF.auth_region,
    }


def get_registry_client(cxt):
    global _CLIENT_CREDS, _CLIENT_KWARGS, _CLIENT_HOST, _CLIENT_PORT
    global _METADATA_ENCRYPTION_KEY
    kwargs = _CLIENT_KWARGS.copy()
    if CONF.use_user_token:
        kwargs['auth_token'] = cxt.auth_token
    if _CLIENT_CREDS:
        kwargs['creds'] = _CLIENT_CREDS

    if CONF.send_identity_headers:
        identity_headers = {
            'X-User-Id': cxt.user or '',
            'X-Tenant-Id': cxt.tenant or '',
            'X-Roles': ','.join(cxt.roles),
            'X-Identity-Status': 'Confirmed',
            'X-Service-Catalog': jsonutils.dumps(cxt.service_catalog),
        }
        kwargs['identity_headers'] = identity_headers

    kwargs['request_id'] = cxt.request_id

    return client.RegistryClient(_CLIENT_HOST, _CLIENT_PORT,
                                 _METADATA_ENCRYPTION_KEY, **kwargs)


def get_images_list(context, **kwargs):
    c = get_registry_client(context)
    return c.get_images(**kwargs)


def get_images_detail(context, **kwargs):
    c = get_registry_client(context)
    return c.get_images_detailed(**kwargs)


def get_image_metadata(context, image_id):
    c = get_registry_client(context)
    return c.get_image(image_id)


def add_image_metadata(context, image_meta):
    LOG.debug("Adding image metadata...")
    c = get_registry_client(context)
    return c.add_image(image_meta)


def update_image_metadata(context, image_id, image_meta,
                          purge_props=False, from_state=None):
    LOG.debug("Updating image metadata for image %s...", image_id)
    c = get_registry_client(context)
    return c.update_image(image_id, image_meta, purge_props=purge_props,
                          from_state=from_state)


def delete_image_metadata(context, image_id):
    LOG.debug("Deleting image metadata for image %s...", image_id)
    c = get_registry_client(context)
    return c.delete_image(image_id)


def get_image_members(context, image_id):
    c = get_registry_client(context)
    return c.get_image_members(image_id)


def get_member_images(context, member_id):
    c = get_registry_client(context)
    return c.get_member_images(member_id)


def replace_members(context, image_id, member_data):
    c = get_registry_client(context)
    return c.replace_members(image_id, member_data)


def add_member(context, image_id, member_id, can_share=None):
    c = get_registry_client(context)
    return c.add_member(image_id, member_id, can_share=can_share)


def delete_member(context, image_id, member_id):
    c = get_registry_client(context)
    return c.delete_member(image_id, member_id)
