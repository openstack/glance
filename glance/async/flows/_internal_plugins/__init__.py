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
Specify the "whitelist" of allowed url schemes for web-download.

This option provides whitelisting of uri schemes that will be allowed when
an end user imports an image using the web-download import method. The
whitelist has priority such that if there is also a blacklist defined for
schemes, the blacklist will be ignored.  Host and port filtering, however,
will be applied.

See the Glance Administration Guide for more information.

Possible values:
    * List containing normalized url schemes as they are returned from
      urllib.parse. For example ['ftp','https']
    * Hint: leave the whitelist empty if you want the disallowed_schemes
      blacklist to be processed

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
Specify the "blacklist" of uri schemes disallowed for web-download.

This option provides blacklisting of uri schemes that will be rejected when
an end user imports an image using the web-download import method.  Note
that if a scheme whitelist is defined using the 'allowed_schemes' option,
*this option will be ignored*.  Host and port filtering, however, will be
applied.

See the Glance Administration Guide for more information.

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
Specify the "whitelist" of allowed target hosts for web-download.

This option provides whitelisting of hosts that will be allowed when an end
user imports an image using the web-download import method. The whitelist
has priority such that if there is also a blacklist defined for hosts, the
blacklist will be ignored.  The uri must have already passed scheme
filtering before this host filter will be applied.  If the uri passes, port
filtering will then be applied.

See the Glance Administration Guide for more information.

Possible values:
    * List containing normalized hostname or ip like it would be returned
      in the urllib.parse netloc without the port
    * By default the list is empty
    * Hint: leave the whitelist empty if you want the disallowed_hosts
      blacklist to be processed

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
Specify the "blacklist" of hosts disallowed for web-download.

This option provides blacklisting of hosts that will be rejected when an end
user imports an image using the web-download import method.  Note that if a
host whitelist is defined using the 'allowed_hosts' option, *this option
will be ignored*.

The uri must have already passed scheme filtering before this host filter
will be applied.  If the uri passes, port filtering will then be applied.

See the Glance Administration Guide for more information.

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
Specify the "whitelist" of allowed ports for web-download.

This option provides whitelisting of ports that will be allowed when an end
user imports an image using the web-download import method.  The whitelist
has priority such that if there is also a blacklist defined for ports, the
blacklist will be ignored.  Note that scheme and host filtering have already
been applied by the time a uri hits the port filter.

See the Glance Administration Guide for more information.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
      field.  Thus the value is a list of integer values, for example
      [80, 443]
    * Hint: leave the whitelist empty if you want the disallowed_ports
      blacklist to be processed

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
Specify the "blacklist" of disallowed ports for web-download.

This option provides blacklisting of target ports that will be rejected when
an end user imports an image using the web-download import method.  Note
that if a port whitelist is defined using the 'allowed_ports' option, *this
option will be ignored*.  Note that scheme and host filtering have already
been applied by the time a uri hits the port filter.

See the Glance Administration Guide for more information.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
      field.  Thus the value is a list of integer values, for example
      [22, 88]
    * By default this list is empty

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
