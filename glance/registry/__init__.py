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
Registry API
"""

import logging

from glance.common import cfg
from glance.common import exception
from glance.registry import client

logger = logging.getLogger('glance.registry')

_CLIENT_HOST = None
_CLIENT_PORT = None
_CLIENT_KWARGS = {}
# AES key used to encrypt 'location' metadata
_METADATA_ENCRYPTION_KEY = None


registry_addr_opts = [
    cfg.StrOpt('registry_host', default='0.0.0.0'),
    cfg.IntOpt('registry_port', default=9191),
    ]
registry_client_opts = [
    cfg.StrOpt('registry_client_protocol', default='http'),
    cfg.StrOpt('registry_client_key_file'),
    cfg.StrOpt('registry_client_cert_file'),
    cfg.StrOpt('registry_client_ca_file'),
    cfg.StrOpt('metadata_encryption_key'),
    ]
admin_token_opt = cfg.StrOpt('admin_token')


def get_registry_addr(conf):
    conf.register_opts(registry_addr_opts)
    return (conf.registry_host, conf.registry_port)


def configure_registry_client(conf):
    """
    Sets up a registry client for use in registry lookups

    :param conf: Configuration options coming from controller
    """
    global _CLIENT_KWARGS, _CLIENT_HOST, _CLIENT_PORT, _METADATA_ENCRYPTION_KEY
    try:
        host, port = get_registry_addr(conf)
    except cfg.ConfigFileValueError:
        msg = _("Configuration option was not valid")
        logger.error(msg)
        raise exception.BadRegistryConnectionConfiguration(msg)
    except IndexError:
        msg = _("Could not find required configuration option")
        logger.error(msg)
        raise exception.BadRegistryConnectionConfiguration(msg)

    conf.register_opts(registry_client_opts)

    _CLIENT_HOST = host
    _CLIENT_PORT = port
    _METADATA_ENCRYPTION_KEY = conf.metadata_encryption_key
    _CLIENT_KWARGS = {
        'use_ssl': conf.registry_client_protocol.lower() == 'https',
        'key_file': conf.registry_client_key_file,
        'cert_file': conf.registry_client_cert_file,
        'ca_file': conf.registry_client_ca_file
        }


def get_client_context(conf, **kwargs):
    conf.register_opt(admin_token_opt)
    from glance.common import context
    return context.RequestContext(auth_tok=conf.admin_token, **kwargs)


def get_registry_client(cxt):
    global _CLIENT_KWARGS, _CLIENT_HOST, _CLIENT_PORT, _METADATA_ENCRYPTION_KEY
    kwargs = _CLIENT_KWARGS.copy()
    kwargs['auth_tok'] = cxt.auth_tok
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
    logger.debug(_("Adding image metadata..."))
    c = get_registry_client(context)
    return c.add_image(image_meta)


def update_image_metadata(context, image_id, image_meta,
                          purge_props=False):
    logger.debug(_("Updating image metadata for image %s..."), image_id)
    c = get_registry_client(context)
    return c.update_image(image_id, image_meta, purge_props)


def delete_image_metadata(context, image_id):
    logger.debug(_("Deleting image metadata for image %s..."), image_id)
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
