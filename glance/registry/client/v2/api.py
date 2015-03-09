# Copyright 2013 Red Hat, Inc
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
Registry's Client V2
"""

import os

from oslo_config import cfg
from oslo_log import log as logging

from glance.common import exception
from glance import i18n
from glance.registry.client.v2 import client

LOG = logging.getLogger(__name__)
_ = i18n._

CONF = cfg.CONF
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

_CLIENT_CREDS = None
_CLIENT_HOST = None
_CLIENT_PORT = None
_CLIENT_KWARGS = {}


def configure_registry_client():
    """
    Sets up a registry client for use in registry lookups
    """
    global _CLIENT_KWARGS, _CLIENT_HOST, _CLIENT_PORT
    try:
        host, port = CONF.registry_host, CONF.registry_port
    except cfg.ConfigFileValueError:
        msg = _("Configuration option was not valid")
        LOG.error(msg)
        raise exception.BadRegistryConnectionConfiguration(msg)
    except IndexError:
        msg = _("Could not find required configuration option")
        LOG.error(msg)
        raise exception.BadRegistryConnectionConfiguration(msg)

    _CLIENT_HOST = host
    _CLIENT_PORT = port
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
    kwargs = _CLIENT_KWARGS.copy()
    if CONF.use_user_token:
        kwargs['auth_token'] = cxt.auth_token
    if _CLIENT_CREDS:
        kwargs['creds'] = _CLIENT_CREDS
    return client.RegistryClient(_CLIENT_HOST, _CLIENT_PORT, **kwargs)
