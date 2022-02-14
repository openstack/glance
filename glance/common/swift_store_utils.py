#    Copyright 2014 Rackspace
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

import configparser

from oslo_config import cfg
from oslo_log import log as logging

from glance.common import exception
from glance.i18n import _, _LE

swift_opts = [
    cfg.StrOpt('default_swift_reference',
               default="ref1",
               help=_("""
Reference to default Swift account/backing store parameters.

Provide a string value representing a reference to the default set
of parameters required for using swift account/backing store for
image storage. The default reference value for this configuration
option is 'ref1'. This configuration option dereferences the
parameters and facilitates image storage in Swift storage backend
every time a new image is added.

Possible values:
    * A valid string value

Related options:
    * None

""")),
    cfg.StrOpt('swift_store_auth_address',
               deprecated_reason=("""
The option auth_address in the Swift back-end configuration file is
used instead.
"""),
               help=_('The address where the Swift authentication service '
                      'is listening.')),
    cfg.StrOpt('swift_store_user', secret=True,
               deprecated_reason=("""
The option 'user' in the Swift back-end configuration file is set instead.
"""),
               help=_('The user to authenticate against the Swift '
                      'authentication service.')),
    cfg.StrOpt('swift_store_key', secret=True,
               deprecated_reason=("""
The option 'key' in the Swift back-end configuration file is used
to set the authentication key instead.
"""),
               help=_('Auth key for the user authenticating against the '
                      'Swift authentication service.')),
    cfg.StrOpt('swift_store_config_file', secret=True,
               help=_("""
File containing the swift account(s) configurations.

Include a string value representing the path to a configuration
file that has references for each of the configured Swift
account(s)/backing stores. By default, no file path is specified
and customized Swift referencing is disabled. Configuring this option
is highly recommended while using Swift storage backend for image
storage as it helps avoid storage of credentials in the
database.

Possible values:
    * None
    * String value representing a valid configuration file path

Related options:
    * None

""")),
]

CONFIG = configparser.ConfigParser()

LOG = logging.getLogger(__name__)


CONF = cfg.CONF
CONF.register_opts(swift_opts)


def is_multiple_swift_store_accounts_enabled():
    if CONF.swift_store_config_file is None:
        return False
    return True


class SwiftParams(object):
    def __init__(self):
        if is_multiple_swift_store_accounts_enabled():
            self.params = self._load_config()
        else:
            self.params = self._form_default_params()

    def _form_default_params(self):
        default = {}
        if (CONF.swift_store_user and CONF.swift_store_key
           and CONF.swift_store_auth_address):
            default['user'] = CONF.swift_store_user
            default['key'] = CONF.swift_store_key
            default['auth_address'] = CONF.swift_store_auth_address
            return {CONF.default_swift_reference: default}
        return {}

    def _load_config(self):
        try:
            conf_file = CONF.find_file(CONF.swift_store_config_file)
            CONFIG.read(conf_file)
        except Exception as e:
            msg = (_LE("swift config file %(conf_file)s:%(exc)s not found") %
                   {'conf_file': CONF.swift_store_config_file, 'exc': e})
            LOG.error(msg)
            raise exception.InvalidSwiftStoreConfiguration()
        account_params = {}
        account_references = CONFIG.sections()
        for ref in account_references:
            reference = {}
            try:
                reference['auth_address'] = CONFIG.get(ref, 'auth_address')
                reference['user'] = CONFIG.get(ref, 'user')
                reference['key'] = CONFIG.get(ref, 'key')
                account_params[ref] = reference
            except (ValueError, SyntaxError, configparser.NoOptionError):
                LOG.exception(_LE("Invalid format of swift store config "
                                  "cfg"))
        return account_params
