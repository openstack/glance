# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from glance.common import wsgi
from glance.registry.api import v1
from glance.registry.api import v2

CONF = cfg.CONF
CONF.import_opt('enable_v1_registry', 'glance.common.config')
CONF.import_opt('enable_v2_registry', 'glance.common.config')


class API(wsgi.Router):
    """WSGI entry point for all Registry requests."""

    def __init__(self, mapper):
        mapper = mapper or wsgi.APIMapper()
        if CONF.enable_v1_registry:
            v1.init(mapper)
        if CONF.enable_v2_registry:
            v2.init(mapper)

        super(API, self).__init__(mapper)
