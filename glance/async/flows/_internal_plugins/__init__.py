# Copyright 2018 Red Hat, Inc.
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
from stevedore import named

from glance.i18n import _


CONF = cfg.CONF

import_filtering_opts = [

    cfg.ListOpt('allowed_schemes',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                default=['http', 'https'],
                help=_("""
Specify the allowed url schemes for web-download.

This option provides whitelisting for uri schemes that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the schemes but obeys host and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.

Possible values:
    * List containing normalized url schemes as they are returned from
    urllib.parse. For example ['ftp','https']

Related options:
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('disallowed_schemes',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                default=[],
                help=_("""
Specify the blacklisted url schemes for web-download.

This option provides blacklisting for uri schemes that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the schemes but obeys host and port filtering. Blacklisting
can be used to prevent specific scheme to be used when whitelisting is not
in use.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.

Possible values:
    * List containing normalized url schemes as they are returned from
    urllib.parse. For example ['ftp','https']
    * By default the list is empty

Related options:
    * allowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('allowed_hosts',
                item_type=cfg.types.HostAddress(),
                bounds=True,
                default=[],
                help=_("""
Specify the allowed target hosts for web-download.

This option provides whitelisting for hosts that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the hosts but obeys scheme and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.
Same way the whitelisted example.com is only obeyed on the allowed schemes
and or ports. Whitelisting of the host does not allow all schemes and ports
accessed.

Possible values:
    * List containing normalized hostname or ip like it would be returned
    in the urllib.parse netloc without the port
    * By default the list is empty

Related options:
    * allowed_schemes
    * disallowed_schemes
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('disallowed_hosts',
                item_type=cfg.types.HostAddress(),
                bounds=True,
                default=[],
                help=_("""
Specify the blacklisted hosts for web-download.

This option provides blacklisting for hosts that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting but obeys scheme and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.
The blacklisted example.com is obeyed on any url pointing to that host
regardless of what their scheme or port is.

Possible values:
    * List containing normalized hostname or ip like it would be returned
    in the urllib.parse netloc without the port
    * By default the list is empty

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('allowed_ports',
                item_type=cfg.types.Integer(min=1, max=65535),
                bounds=True,
                default=[80, 443],
                help=_("""
Specify the allowed ports for web-download.

This option provides whitelisting for uri ports that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the ports but obeys host and scheme filtering.

For example: If scheme blacklisting contains '80' and whitelist contains
['80', '443'] the whitelist is obeyed on http://example.com:80 but any
other port like ftp://example.com:21 is blocked even it's not blacklisted.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
    field. For example ['80','443']

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * disallowed_ports
""")),
    cfg.ListOpt('disallowed_ports',
                item_type=cfg.types.Integer(min=1, max=65535),
                bounds=True,
                default=[],
                help=_("""
Specify the disallowed ports for web-download.

This option provides blacklisting for uri ports that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the ports but obeys host and scheme filtering.

For example: If scheme blacklisting contains '80' and whitelist contains
['80', '443'] the whitelist is obeyed on http://example.com:80 but any
other port like ftp://example.com:21 is blocked even it's not blacklisted.
If no whitelisting is defined any scheme and host combination is disallowed
for the blacklisted port.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
    field. For example ['80','443']
    * By default this list is empty.

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports

""")),
]

CONF.register_opts(import_filtering_opts, group='import_filtering_opts')


def get_import_plugin(**kwargs):
    method_list = CONF.enabled_import_methods
    import_method = kwargs.get('import_req')['method']['name']
    if import_method in method_list:
        import_method = import_method.replace("-", "_")
        task_list = [import_method]
        # TODO(jokke): Implement error handling of non-listed methods.
    extensions = named.NamedExtensionManager(
        'glance.image_import.internal_plugins',
        names=task_list,
        name_order=True,
        invoke_on_load=True,
        invoke_kwds=kwargs)
    for extension in extensions.extensions:
        return extension.obj
