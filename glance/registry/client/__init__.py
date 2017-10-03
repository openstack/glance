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
    cfg.StrOpt('registry_client_protocol',
               default='http',
               choices=('http', 'https'),
               deprecated_for_removal=True,
               deprecated_since="Queens",
               deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
               help=_("""
Protocol to use for communication with the registry server.

Provide a string value representing the protocol to use for
communication with the registry server. By default, this option is
set to ``http`` and the connection is not secure.

This option can be set to ``https`` to establish a secure connection
to the registry server. In this case, provide a key to use for the
SSL connection using the ``registry_client_key_file`` option. Also
include the CA file and cert file using the options
``registry_client_ca_file`` and ``registry_client_cert_file``
respectively.

Possible values:
    * http
    * https

Related options:
    * registry_client_key_file
    * registry_client_cert_file
    * registry_client_ca_file

""")),
    cfg.StrOpt('registry_client_key_file',
               sample_default='/etc/ssl/key/key-file.pem',
               deprecated_for_removal=True,
               deprecated_since="Queens",
               deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
               help=_("""
Absolute path to the private key file.

Provide a string value representing a valid absolute path to the
private key file to use for establishing a secure connection to
the registry server.

NOTE: This option must be set if ``registry_client_protocol`` is
set to ``https``. Alternatively, the GLANCE_CLIENT_KEY_FILE
environment variable may be set to a filepath of the key file.

Possible values:
    * String value representing a valid absolute path to the key
      file.

Related options:
    * registry_client_protocol

""")),
    cfg.StrOpt('registry_client_cert_file',
               sample_default='/etc/ssl/certs/file.crt',
               deprecated_for_removal=True,
               deprecated_since="Queens",
               deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
               help=_("""
Absolute path to the certificate file.

Provide a string value representing a valid absolute path to the
certificate file to use for establishing a secure connection to
the registry server.

NOTE: This option must be set if ``registry_client_protocol`` is
set to ``https``. Alternatively, the GLANCE_CLIENT_CERT_FILE
environment variable may be set to a filepath of the certificate
file.

Possible values:
    * String value representing a valid absolute path to the
      certificate file.

Related options:
    * registry_client_protocol

""")),
    cfg.StrOpt('registry_client_ca_file',
               sample_default='/etc/ssl/cafile/file.ca',
               deprecated_for_removal=True,
               deprecated_since="Queens",
               deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
               help=_("""
Absolute path to the Certificate Authority file.

Provide a string value representing a valid absolute path to the
certificate authority file to use for establishing a secure
connection to the registry server.

NOTE: This option must be set if ``registry_client_protocol`` is
set to ``https``. Alternatively, the GLANCE_CLIENT_CA_FILE
environment variable may be set to a filepath of the CA file.
This option is ignored if the ``registry_client_insecure`` option
is set to ``True``.

Possible values:
    * String value representing a valid absolute path to the CA
      file.

Related options:
    * registry_client_protocol
    * registry_client_insecure

""")),
    cfg.BoolOpt('registry_client_insecure',
                default=False,
                deprecated_for_removal=True,
                deprecated_since="Queens",
                deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
                help=_("""
Set verification of the registry server certificate.

Provide a boolean value to determine whether or not to validate
SSL connections to the registry server. By default, this option
is set to ``False`` and the SSL connections are validated.

If set to ``True``, the connection to the registry server is not
validated via a certifying authority and the
``registry_client_ca_file`` option is ignored. This is the
registry's equivalent of specifying --insecure on the command line
using glanceclient for the API.

Possible values:
    * True
    * False

Related options:
    * registry_client_protocol
    * registry_client_ca_file

""")),
    cfg.IntOpt('registry_client_timeout',
               default=600,
               min=0,
               deprecated_for_removal=True,
               deprecated_since="Queens",
               deprecated_reason=_("""
Glance registry service is deprecated for removal.

More information can be found from the spec:
http://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/deprecate-registry.html
"""),
               help=_("""
Timeout value for registry requests.

Provide an integer value representing the period of time in seconds
that the API server will wait for a registry request to complete.
The default value is 600 seconds.

A value of 0 implies that a request will never timeout.

Possible values:
    * Zero
    * Positive integer

Related options:
    * None

""")),
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
