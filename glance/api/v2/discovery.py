# Copyright (c) 2017 RedHat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg
import webob.exc

from glance.common import wsgi
from glance.i18n import _


CONF = cfg.CONF


class InfoController(object):
    def get_image_import(self, req):
        # TODO(jokke): All the rest of the boundaries should be implemented.
        import_methods = {
            'description': 'Import methods available.',
            'type': 'array',
            'value': CONF.get('enabled_import_methods')
        }

        return {
            'import-methods': import_methods
        }

    def get_stores(self, req):
        # TODO(abhishekk): This will be removed after config options
        # 'stores' and 'default_store' are removed.
        enabled_backends = CONF.enabled_backends
        if not enabled_backends:
            msg = _("Multi backend is not supported at this site.")
            raise webob.exc.HTTPNotFound(explanation=msg)

        backends = []
        for backend in enabled_backends:
            if backend.startswith("os_glance_"):
                continue

            stores = {}
            stores['id'] = backend
            description = getattr(CONF, backend).store_description
            if description:
                stores['description'] = description
            if backend == CONF.glance_store.default_backend:
                stores['default'] = "true"
            # Check if http store is configured then mark it as read-only
            if enabled_backends[backend] == 'http':
                stores['read-only'] = "true"
            backends.append(stores)

        return {'stores': backends}


def create_resource():
    return wsgi.Resource(InfoController())
