# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

__all__ = [
    'list_api_opts',
    'list_registry_opts',
    'list_scrubber_opts',
    'list_cache_opts',
    'list_manage_opts'
]

import copy
import itertools

import glance.api.middleware.context
import glance.api.versions
import glance.async.taskflow_executor
import glance.common.config
import glance.common.location_strategy
import glance.common.location_strategy.store_type
import glance.common.property_utils
import glance.common.rpc
import glance.common.wsgi
import glance.image_cache
import glance.image_cache.drivers.sqlite
import glance.notifier
import glance.registry
import glance.registry.client
import glance.registry.client.v1.api
import glance.scrubber


_api_opts = [
    (None, list(itertools.chain(
        glance.api.middleware.context.context_opts,
        glance.api.versions.versions_opts,
        glance.common.config.common_opts,
        glance.common.location_strategy.location_strategy_opts,
        glance.common.property_utils.property_opts,
        glance.common.rpc.rpc_opts,
        glance.common.wsgi.bind_opts,
        glance.common.wsgi.eventlet_opts,
        glance.common.wsgi.socket_opts,
        glance.common.wsgi.profiler_opts,
        glance.image_cache.drivers.sqlite.sqlite_opts,
        glance.image_cache.image_cache_opts,
        glance.notifier.notifier_opts,
        glance.registry.registry_addr_opts,
        glance.registry.client.registry_client_ctx_opts,
        glance.registry.client.registry_client_opts,
        glance.registry.client.v1.api.registry_client_ctx_opts,
        glance.scrubber.scrubber_opts))),
    ('image_format', glance.common.config.image_format_opts),
    ('task', glance.common.config.task_opts),
    ('taskflow_executor',
     glance.async.taskflow_executor.taskflow_executor_opts),
    ('store_type_location_strategy',
     glance.common.location_strategy.store_type.store_type_opts),
    ('paste_deploy', glance.common.config.paste_deploy_opts)
]
_registry_opts = [
    (None, list(itertools.chain(
        glance.api.middleware.context.context_opts,
        glance.common.config.common_opts,
        glance.common.wsgi.bind_opts,
        glance.common.wsgi.socket_opts,
        glance.common.wsgi.eventlet_opts))),
    ('paste_deploy', glance.common.config.paste_deploy_opts)
]
_scrubber_opts = [
    (None, list(itertools.chain(
        glance.common.config.common_opts,
        glance.scrubber.scrubber_opts,
        glance.scrubber.scrubber_cmd_opts,
        glance.scrubber.scrubber_cmd_cli_opts,
        glance.registry.client.registry_client_ctx_opts,
        glance.registry.registry_addr_opts))),
]
_cache_opts = [
    (None, list(itertools.chain(
        glance.common.config.common_opts,
        glance.image_cache.drivers.sqlite.sqlite_opts,
        glance.image_cache.image_cache_opts,
        glance.registry.registry_addr_opts,
        glance.registry.client.registry_client_ctx_opts))),
]
_manage_opts = [
    (None, [])
]


def list_api_opts():
    """Return a list of oslo_config options available in Glance API service.

    Each element of the list is a tuple. The first element is the name of the
    group under which the list of elements in the second element will be
    registered. A group name of None corresponds to the [DEFAULT] group in
    config files.

    This function is also discoverable via the 'glance.api' entry point
    under the 'oslo_config.opts' namespace.

    The purpose of this is to allow tools like the Oslo sample config file
    generator to discover the options exposed to users by Glance.

    :returns: a list of (group_name, opts) tuples
    """

    return [(g, copy.deepcopy(o)) for g, o in _api_opts]


def list_registry_opts():
    """Return a list of oslo_config options available in Glance Registry
    service.
    """
    return [(g, copy.deepcopy(o)) for g, o in _registry_opts]


def list_scrubber_opts():
    """Return a list of oslo_config options available in Glance Scrubber
    service.
    """
    return [(g, copy.deepcopy(o)) for g, o in _scrubber_opts]


def list_cache_opts():
    """Return a list of oslo_config options available in Glance Cache
    service.
    """
    return [(g, copy.deepcopy(o)) for g, o in _cache_opts]


def list_manage_opts():
    """Return a list of oslo_config options available in Glance manage."""
    return [(g, copy.deepcopy(o)) for g, o in _manage_opts]
