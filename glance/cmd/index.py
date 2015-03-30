# Copyright 2015 Intel Corporation
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

import sys

from oslo_config import cfg
from oslo_log import log as logging
import stevedore

from glance.common import config
from glance import i18n


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_LE = i18n._LE


def main():
    try:
        logging.register_options(CONF)
        cfg_files = cfg.find_config_files(project='glance',
                                          prog='glance-api')
        cfg_files.extend(cfg.find_config_files(project='glance',
                                               prog='glance-search'))
        config.parse_args(default_config_files=cfg_files)
        logging.setup(CONF, 'glance')

        namespace = 'glance.search.index_backend'
        ext_manager = stevedore.extension.ExtensionManager(
            namespace, invoke_on_load=True)
        for ext in ext_manager.extensions:
            try:
                ext.obj.setup()
            except Exception as e:
                LOG.error(_LE("Failed to setup index extension "
                              "%(ext)s: %(e)s") % {'ext': ext.name,
                                                   'e': e})
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)
