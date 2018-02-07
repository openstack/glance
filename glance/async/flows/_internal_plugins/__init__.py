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


CONF = cfg.CONF


def get_import_plugin(**kwargs):
    method_list = CONF.enabled_import_methods
    import_method = kwargs.get('import_req')['method']['name'].replace("-",
                                                                       "_")
    if import_method in method_list:
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
