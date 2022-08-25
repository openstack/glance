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
    'list_scrubber_opts',
    'list_cache_opts',
    'list_manage_opts',
    'list_image_import_opts',
]

import copy
import itertools

from osprofiler import opts as profiler

import glance.api.middleware.context
import glance.api.versions
import glance.async_.flows._internal_plugins
import glance.async_.flows.api_image_import
import glance.async_.flows.convert
from glance.async_.flows.plugins import plugin_opts
import glance.async_.taskflow_executor
import glance.common.config
import glance.common.location_strategy
import glance.common.location_strategy.store_type
import glance.common.property_utils
import glance.common.wsgi
import glance.image_cache
import glance.image_cache.drivers.sqlite
import glance.notifier
import glance.scrubber


_api_opts = [
    (None, list(itertools.chain(
        glance.api.middleware.context.context_opts,
        glance.api.versions.versions_opts,
        glance.common.config.common_opts,
        glance.common.location_strategy.location_strategy_opts,
        glance.common.property_utils.property_opts,
        glance.common.wsgi.bind_opts,
        glance.common.wsgi.eventlet_opts,
        glance.common.wsgi.socket_opts,
        glance.common.wsgi.store_opts,
        glance.common.wsgi.cli_opts,
        glance.image_cache.drivers.sqlite.sqlite_opts,
        glance.image_cache.image_cache_opts,
        glance.notifier.notifier_opts,
        glance.scrubber.scrubber_opts))),
    ('image_format', glance.common.config.image_format_opts),
    ('task', glance.common.config.task_opts),
    ('taskflow_executor', list(itertools.chain(
        glance.async_.taskflow_executor.taskflow_executor_opts,
        glance.async_.flows.convert.convert_task_opts))),
    ('store_type_location_strategy',
     glance.common.location_strategy.store_type.store_type_opts),
    profiler.list_opts()[0],
    ('paste_deploy', glance.common.config.paste_deploy_opts),
    ('wsgi', glance.common.config.wsgi_opts),
]
_scrubber_opts = [
    (None, list(itertools.chain(
        glance.common.config.common_opts,
        glance.scrubber.scrubber_opts,
        glance.scrubber.scrubber_cmd_opts,
        glance.scrubber.scrubber_cmd_cli_opts))),
]
_cache_opts = [
    (None, list(itertools.chain(
        glance.common.config.common_opts,
        glance.image_cache.drivers.sqlite.sqlite_opts,
        glance.image_cache.image_cache_opts))),
]
_manage_opts = [
    (None, [])
]
_image_import_opts = [
    ('image_import_opts',
     glance.async_.flows.api_image_import.api_import_opts),
    ('import_filtering_opts',
     glance.async_.flows._internal_plugins.import_filtering_opts),
    ('glance_download_opts',
     glance.async_.flows.api_image_import.glance_download_opts)
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


def list_image_import_opts():
    """Return a list of oslo_config options available for Image Import"""

    opts = copy.deepcopy(_image_import_opts)
    opts.extend(plugin_opts.get_plugin_opts())
    return [(g, copy.deepcopy(o)) for g, o in opts]
