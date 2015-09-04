# Copyright 2011-2012 OpenStack Foundation
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
import paste.urlmap

CONF = cfg.CONF


def root_app_factory(loader, global_conf, **local_conf):
    if not CONF.enable_v1_api and '/v1' in local_conf:
        del local_conf['/v1']
    if not CONF.enable_v2_api and '/v2' in local_conf:
        del local_conf['/v2']
    if not CONF.enable_v3_api and '/v3' in local_conf:
        del local_conf['/v3']
    return paste.urlmap.urlmap_factory(loader, global_conf, **local_conf)
