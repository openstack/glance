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

from oslo.config import cfg

registry_client_opts = [
    cfg.StrOpt('registry_client_protocol', default='http',
               help=_('The protocol to use for communication with the '
                      'registry server.  Either http or https.')),
    cfg.StrOpt('registry_client_key_file',
               help=_('The path to the key file to use in SSL connections '
                      'to the registry server.')),
    cfg.StrOpt('registry_client_cert_file',
               help=_('The path to the cert file to use in SSL connections '
                      'to the registry server.')),
    cfg.StrOpt('registry_client_ca_file',
               help=_('The path to the certifying authority cert file to '
                      'use in SSL connections to the registry server.')),
    cfg.BoolOpt('registry_client_insecure', default=False,
                help=_('When using SSL in connections to the registry server, '
                       'do not require validation via a certifying '
                       'authority.')),
    cfg.IntOpt('registry_client_timeout', default=600,
               help=_('The period of time, in seconds, that the API server '
                      'will wait for a registry request to complete. A '
                      'value of 0 implies no timeout.')),
]

registry_client_ctx_opts = [
    cfg.BoolOpt('use_user_token', default=True,
                help=_('Whether to pass through the user token when '
                       'making requests to the registry.')),
    cfg.StrOpt('admin_user', secret=True,
               help=_('The administrators user name.')),
    cfg.StrOpt('admin_password', secret=True,
               help=_('The administrators password.')),
    cfg.StrOpt('admin_tenant_name', secret=True,
               help=_('The tenant name of the administrative user.')),
    cfg.StrOpt('auth_url',
               help=_('The URL to the keystone service.')),
    cfg.StrOpt('auth_strategy', default='noauth',
               help=_('The strategy to use for authentication.')),
    cfg.StrOpt('auth_region',
               help=_('The region for the authentication service.')),
]

CONF = cfg.CONF
CONF.register_opts(registry_client_opts)
CONF.register_opts(registry_client_ctx_opts)
