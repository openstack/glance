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

import copy

from oslo_config import cfg
import semantic_version
from stevedore import enabled

from glance.common.artifacts import definitions
from glance.common import exception
from glance import i18n
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE
_LW = i18n._LW
_LI = i18n._LI


plugins_opts = [
    cfg.BoolOpt('load_enabled', default=True,
                help=_('When false, no artifacts can be loaded regardless of'
                       ' available_plugins. When true, artifacts can be'
                       ' loaded.')),
    cfg.ListOpt('available_plugins', default=[],
                help=_('A list of artifacts that are allowed in the'
                       ' format name or name-version. Empty list means that'
                       ' any artifact can be loaded.'))
]


CONF = cfg.CONF
CONF.register_opts(plugins_opts)


class ArtifactsPluginLoader(object):
    def __init__(self, namespace):
        self.mgr = enabled.EnabledExtensionManager(
            check_func=self._gen_check_func(),
            namespace=namespace,
            propagate_map_exceptions=True,
            on_load_failure_callback=self._on_load_failure)
        self.plugin_map = {'by_typename': {},
                           'by_endpoint': {}}

        def _add_extension(ext):
            """
            Plugins can be loaded as entry_point=single plugin and
            entry_point=PLUGIN_LIST, where PLUGIN_LIST is a python variable
            holding a list of plugins
            """
            def _load_one(plugin):
                if issubclass(plugin, definitions.ArtifactType):
                    # make sure that have correct plugin name
                    art_name = plugin.metadata.type_name
                    if art_name != ext.name:
                        raise exception.ArtifactNonMatchingTypeName(
                            name=art_name, plugin=ext.name)
                    # make sure that no plugin with the same name and version
                    # already exists
                    exists = self._get_plugins(ext.name)
                    new_tv = plugin.metadata.type_version
                    if any(e.metadata.type_version == new_tv for e in exists):
                        raise exception.ArtifactDuplicateNameTypeVersion()
                self._add_plugin("by_endpoint", plugin.metadata.endpoint,
                                 plugin)
                self._add_plugin("by_typename", plugin.metadata.type_name,
                                 plugin)

            if isinstance(ext.plugin, list):
                for p in ext.plugin:
                    _load_one(p)
            else:
                _load_one(ext.plugin)

        # (ivasilevskaya) that looks pretty bad as RuntimeError is too general,
        # but stevedore has awful exception wrapping with no specific class
        # for this very case (no extensions for given namespace found)
        try:
            self.mgr.map(_add_extension)
        except RuntimeError as re:
            LOG.error(_LE("Unable to load artifacts: %s") % re.message)

    def _version(self, artifact):
        return semantic_version.Version.coerce(artifact.metadata.type_version)

    def _add_plugin(self, spec, name, plugin):
        """
        Inserts a new plugin into a sorted by desc type_version list
        of existing plugins in order to retrieve the latest by next()
        """
        def _add(name, value):
            self.plugin_map[spec][name] = value

        old_order = copy.copy(self._get_plugins(name, spec=spec))
        for i, p in enumerate(old_order):
            if self._version(p) < self._version(plugin):
                _add(name, old_order[0:i] + [plugin] + old_order[i:])
                return
        _add(name, old_order + [plugin])

    def _get_plugins(self, name, spec="by_typename"):
        if spec not in self.plugin_map.keys():
            return []
        return self.plugin_map[spec].get(name, [])

    def _gen_check_func(self):
        """generates check_func for EnabledExtensionManager"""

        def _all_forbidden(ext):
            LOG.warn(_LW("Can't load artifact %s: load disabled in config") %
                     ext.name)
            raise exception.ArtifactLoadError(name=ext.name)

        def _all_allowed(ext):
            LOG.info(
                _LI("Artifact %s has been successfully loaded") % ext.name)
            return True

        if not CONF.load_enabled:
            return _all_forbidden
        if len(CONF.available_plugins) == 0:
            return _all_allowed

        available = []
        for name in CONF.available_plugins:
            type_name, version = (name.split('-', 1)
                                  if '-' in name else (name, None))
            available.append((type_name, version))

        def _check_ext(ext):
            try:
                next(n for n, v in available
                     if n == ext.plugin.metadata.type_name and
                     (v is None or v == ext.plugin.metadata.type_version))
            except StopIteration:
                LOG.warn(_LW("Can't load artifact %s: not in"
                             " available_plugins list") % ext.name)
                raise exception.ArtifactLoadError(name=ext.name)
            LOG.info(
                _LI("Artifact %s has been successfully loaded") % ext.name)
            return True

        return _check_ext

    # this has to be done explicitly as stevedore is pretty ignorant when
    # face to face with an Exception and tries to swallow it and print sth
    # irrelevant instead of expected error message
    def _on_load_failure(self, manager, ep, exc):
        msg = (_LE("Could not load plugin from %(module)s: %(msg)s") %
               {"module": ep.module_name, "msg": exc})
        LOG.error(msg)
        raise exc

    def _find_class_in_collection(self, collection, name, version=None):
        try:
            def _cmp_version(plugin, version):
                ver = semantic_version.Version.coerce
                return (ver(plugin.metadata.type_version) ==
                        ver(version))

            if version:
                return next((p for p in collection
                             if _cmp_version(p, version)))
            return next((p for p in collection))
        except StopIteration:
            raise exception.ArtifactPluginNotFound(
                name="%s %s" % (name, "v %s" % version if version else ""))

    def get_class_by_endpoint(self, name, version=None):
        if version is None:
            classlist = self._get_plugins(name, spec="by_endpoint")
            if not classlist:
                raise exception.ArtifactPluginNotFound(name=name)
            return self._find_class_in_collection(classlist, name)
        return self._find_class_in_collection(
            self._get_plugins(name, spec="by_endpoint"), name, version)

    def get_class_by_typename(self, name, version=None):
        return self._find_class_in_collection(
            self._get_plugins(name, spec="by_typename"), name, version)
