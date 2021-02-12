# Copyright 2020 Red Hat, Inc
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
from glance.i18n import _
from oslo_config import cfg

removed_opts = [
    cfg.BoolOpt('owner_is_tenant',
                default=True,
                help=_("""
This option has been removed in Wallaby.  Because there is no migration path
for installations that had owner_is_tenant==False, we have defined this option
so that the code can probe the config file and refuse to start the api service
if the deployment has been using that setting.
""")),
]


def register_removed_options():
    # NOTE(cyril): This should only be called when we need to use options that
    # have been removed and are therefore no longer relevant. This is the case
    # of upgrade checks, for instance.
    cfg.CONF.register_opts(removed_opts)
