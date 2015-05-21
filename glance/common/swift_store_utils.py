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

from collections import OrderedDict
from oslo_config import cfg
from oslo_log import log as logging
from six.moves import configparser

from glance.common import exception
from glance import i18n

_ = i18n._
_LE = i18n._LE

swift_opts = [
    cfg.StrOpt('default_swift_reference',
               default="ref1",
               help=_('The reference to the default swift account/backing '
                      'store parameters to use for adding new images.')),
    cfg.StrOpt('swift_store_auth_address',
               help=_('The address where the Swift authentication service '
                      'is listening.(deprecated)')),
    cfg.StrOpt('swift_store_user', secret=True,
               help=_('The user to authenticate against the Swift '
                      'authentication service (deprecated)')),
    cfg.StrOpt('swift_store_key', secret=True,
               help=_('Auth key for the user authenticating against the '
                      'Swift authentication service. (deprecated)')),
    cfg.StrOpt('swift_store_config_file', secret=True,
               help=_('The config file that has the swift account(s)'
                      'configs.')),
]

# NOTE(bourke): The default dict_type is collections.OrderedDict in py27, but
# we must set manually for compatibility with py26
CONFIG = configparser.SafeConfigParser(dict_type=OrderedDict)
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
            except (ValueError, SyntaxError, configparser.NoOptionError) as e:
                LOG.exception(_LE("Invalid format of swift store config "
                                  "cfg"))
        return account_params
