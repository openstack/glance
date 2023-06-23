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

import copy

import glance_store as g_store
from oslo_config import cfg
from oslo_log import log as logging
import oslo_serialization.jsonutils as json
import webob.exc

from glance.api import policy
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import wsgi
import glance.db
from glance.i18n import _
from glance.quota import keystone as ks_quota

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class InfoController(object):
    def __init__(self, policy_enforcer=None):
        self.policy = policy_enforcer or policy.Enforcer()

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

    @staticmethod
    def _get_rbd_properties(store_detail):
        return {
            'chunk_size': store_detail.chunk_size,
            'pool': store_detail.pool,
            'thin_provisioning': store_detail.thin_provisioning
        }

    @staticmethod
    def _get_file_properties(store_detail):
        return {
            'data_dir': store_detail.datadir,
            'chunk_size': store_detail.chunk_size,
            'thin_provisioning': store_detail.thin_provisioning
        }

    @staticmethod
    def _get_cinder_properties(store_detail):
        return {
            'volume_type': store_detail.store_conf.cinder_volume_type,
            'use_multipath': store_detail.store_conf.cinder_use_multipath
        }

    @staticmethod
    def _get_swift_properties(store_detail):
        return {
            'container': store_detail.container,
            'large_object_size': store_detail.large_object_size,
            'large_object_chunk_size': store_detail.large_object_chunk_size
        }

    @staticmethod
    def _get_s3_properties(store_detail):
        return {
            's3_store_large_object_size':
            store_detail.s3_store_large_object_size,
            's3_store_large_object_chunk_size':
            store_detail.s3_store_large_object_chunk_size,
            's3_store_thread_pools':
            store_detail.s3_store_thread_pools
        }

    @staticmethod
    def _get_http_properties(store_detail):
        # NOTE(mrjoshi): Thre are no useful properties
        # to be exposed.
        return {}

    def get_stores_detail(self, req):
        enabled_backends = CONF.enabled_backends
        stores = self.get_stores(req).get('stores')
        try:
            api_policy.DiscoveryAPIPolicy(
                req.context,
                enforcer=self.policy).stores_info_detail()

            store_mapper = {
                'rbd': self._get_rbd_properties,
                'file': self._get_file_properties,
                'cinder': self._get_cinder_properties,
                'swift': self._get_swift_properties,
                's3': self._get_s3_properties,
                'http': self._get_http_properties
            }

            for store in stores:
                store_type = enabled_backends[store['id']]
                store['type'] = store_type
                store_detail = g_store.get_store_from_store_identifier(
                    store['id'])
                store['properties'] = store_mapper.get(store_type)(
                    store_detail)
                store['weight'] = getattr(CONF, store['id']).weight

        except exception.Forbidden as e:
            LOG.debug("User not permitted to view details")
            raise webob.exc.HTTPForbidden(explanation=e.msg)

        return {'stores': stores}

    def get_usage(self, req):
        project_usage = ks_quota.get_usage(req.context)
        return {'usage':
                {name: {'usage': usage.usage,
                        'limit': usage.limit}
                 for name, usage in project_usage.items()}}


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, usage_schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = usage_schema or get_usage_schema()

    def get_usage(self, response, usage):
        body = json.dumps(self.schema.filter(usage), ensure_ascii=False)
        response.unicode_body = str(body)
        response.content_type = 'application/json'


_USAGE_SCHEMA = {
    'usage': {
        'type': 'array',
        'items': {
            'type': 'object',
            'additionalProperties': True,
            'validation_data': {
                'type': 'object',
                'additonalProperties': False,
                'properties': {
                    'usage': {'type': 'integer'},
                    'limit': {'type': 'integer'},
                },
            },
        },
    },
}


def get_usage_schema():
    return glance.schema.Schema('usage', copy.deepcopy(_USAGE_SCHEMA))


def create_resource():
    usage_schema = get_usage_schema()
    serializer = ResponseSerializer(usage_schema)
    return wsgi.Resource(InfoController(), None, serializer)
