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

from oslo_config import cfg

from glance.i18n import _


registry_client_opts = [
    cfg.StrOpt('registry_client_protocol', default='http',
               help=_('The protocol to use for communication with the '
                      'registry server.  Either http or https.')),
    cfg.StrOpt('registry_client_key_file',
               help=_('The path to the key file to use in SSL connections '
                      'to the registry server, if any. Alternately, you may '
                      'set the GLANCE_CLIENT_KEY_FILE environment variable to '
                      'a filepath of the key file')),
    cfg.StrOpt('registry_client_cert_file',
               help=_('The path to the cert file to use in SSL connections '
                      'to the registry server, if any. Alternately, you may '
                      'set the GLANCE_CLIENT_CERT_FILE environment variable '
                      'to a filepath of the CA cert file')),
    cfg.StrOpt('registry_client_ca_file',
               help=_('The path to the certifying authority cert file to use '
                      'in SSL connections to the registry server, if any. '
                      'Alternately, you may set the GLANCE_CLIENT_CA_FILE '
                      'environment variable to a filepath of the CA cert '
                      'file.')),
    cfg.BoolOpt('registry_client_insecure', default=False,
                help=_('When using SSL in connections to the registry server, '
                       'do not require validation via a certifying '
                       'authority. This is the registry\'s equivalent of '
                       'specifying --insecure on the command line using '
                       'glanceclient for the API.')),
    cfg.IntOpt('registry_client_timeout', default=600,
               help=_('The period of time, in seconds, that the API server '
                      'will wait for a registry request to complete. A '
                      'value of 0 implies no timeout.')),
]

_DEPRECATE_USE_USER_TOKEN_MSG = ('This option was considered harmful and '
                                 'has been deprecated in M release. It will '
                                 'be removed in O release. For more '
                                 'information read OSSN-0060. '
                                 'Related functionality with uploading big '
                                 'images has been implemented with Keystone '
                                 'trusts support.')

registry_client_ctx_opts = [
    cfg.BoolOpt('use_user_token', default=True, deprecated_for_removal=True,
                deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
                help=_('Whether to pass through the user token when '
                       'making requests to the registry. To prevent '
                       'failures with token expiration during big '
                       'files upload, it is recommended to set this '
                       'parameter to False.'
                       'If "use_user_token" is not in effect, then '
                       'admin credentials can be specified.')),
    cfg.StrOpt('admin_user', secret=True, deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The administrators user name. '
                      'If "use_user_token" is not in effect, then '
                      'admin credentials can be specified.')),
    cfg.StrOpt('admin_password', secret=True, deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The administrators password. '
                      'If "use_user_token" is not in effect, then '
                      'admin credentials can be specified.')),
    cfg.StrOpt('admin_tenant_name', secret=True, deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The tenant name of the administrative user. '
                      'If "use_user_token" is not in effect, then '
                      'admin tenant name can be specified.')),
    cfg.StrOpt('auth_url', deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The URL to the keystone service. '
                      'If "use_user_token" is not in effect and '
                      'using keystone auth, then URL of keystone '
                      'can be specified.')),
    cfg.StrOpt('auth_strategy', default='noauth', deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The strategy to use for authentication. '
                      'If "use_user_token" is not in effect, then '
                      'auth strategy can be specified.')),
    cfg.StrOpt('auth_region', deprecated_for_removal=True,
               deprecated_reason=_DEPRECATE_USE_USER_TOKEN_MSG,
               help=_('The region for the authentication service. '
                      'If "use_user_token" is not in effect and '
                      'using keystone auth, then region name can '
                      'be specified.')),
]

CONF = cfg.CONF
CONF.register_opts(registry_client_opts)
CONF.register_opts(registry_client_ctx_opts)
