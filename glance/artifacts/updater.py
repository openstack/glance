# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from glance.artifacts.domain import proxy
from glance.common import exception as exc
from glance import i18n

_ = i18n._


class ArtifactProxy(proxy.Artifact):
    """A proxy that is capable of modifying an artifact via jsonpatch methods.

    Currently supported methods are update, remove, replace.
    """
    def __init__(self, artifact):
        self.artifact = artifact
        super(ArtifactProxy, self).__init__(artifact)

    def __getattr__(self, name):
        if not hasattr(self, name):
            raise exc.ArtifactInvalidProperty(prop=name)
        return super(ArtifactProxy, self).__getattr__(name)

    def _perform_op(self, op, **kwargs):
        path = kwargs.get("path")
        value = kwargs.get("value")
        prop_name, delimiter, path_left = path.lstrip('/').partition('/')
        if not path_left:
            return setattr(self, prop_name, value)
        try:
            prop = self._get_prop_to_update(prop_name, path_left)
            # correct path_left and call corresponding update method
            kwargs["path"] = path_left
            getattr(prop, op)(path=kwargs["path"], value=kwargs.get("value"))
            return setattr(self, prop_name, prop)
        except exc.InvalidJsonPatchPath:
            # NOTE(ivasilevskaya): here exception is reraised with
            # 'part of path' substituted with with 'full path' to form a
            # more relevant message
            raise exc.InvalidJsonPatchPath(
                path=path, explanation=_("No property to access"))

    def _get_prop_to_update(self, prop_name, path):
        """Proxies properties that can be modified via update request.

        All properties can be updated save for 'metadata' and blobs.
        Due to the fact that empty lists and dicts are represented with null
        values, have to check precise type definition by consulting metadata.
        """
        prop = super(ArtifactProxy, self).get_type_specific_property(
            prop_name)
        if (prop_name == "metadata" or
                prop_name in self.artifact.metadata.attributes.blobs):
            return prop
        if not prop:
            # get correct type for empty list/dict
            klass = self.artifact.metadata.attributes.all[prop_name]
            if isinstance(klass, list):
                prop = []
            elif isinstance(klass, dict):
                prop = {}
        return wrap_property(prop, path)

    def replace(self, path, value):
        self._perform_op("replace", path=path, value=value)

    def remove(self, path, value=None):
        self._perform_op("remove", path=path)

    def add(self, path, value):
        self._perform_op("add", path=path, value=value)


class ArtifactFactoryProxy(proxy.ArtifactFactory):
    def __init__(self, factory):
        super(ArtifactFactoryProxy, self).__init__(factory)


class ArtifactRepoProxy(proxy.ArtifactRepo):
    def __init__(self, repo):
        super(ArtifactRepoProxy, self).__init__(
            repo, item_proxy_class=ArtifactProxy)


def wrap_property(prop_value, full_path):
    if isinstance(prop_value, list):
        return ArtifactListPropertyProxy(prop_value, full_path)
    if isinstance(prop_value, dict):
        return ArtifactDictPropertyProxy(prop_value, full_path)
    # no other types are supported
    raise exc.InvalidJsonPatchPath(path=full_path)


class ArtifactListPropertyProxy(proxy.List):
    """A class to wrap a list property.

    Makes possible to modify the property value via supported jsonpatch
    requests (update/remove/replace).
    """
    def __init__(self, prop_value, path):
        super(ArtifactListPropertyProxy, self).__init__(
            prop_value)

    def _proc_key(self, idx_str, should_exist=True):
        """JsonPatchUpdateMixin method overload.

        Only integers less than current array length and '-' (last elem)
        in path are allowed.
        Raises an InvalidJsonPatchPath exception if any of the conditions above
        are not met.
        """
        if idx_str == '-':
            return len(self) - 1
        try:
            idx = int(idx_str)
            if not should_exist and len(self) == 0:
                return 0
            if len(self) < idx + 1:
                msg = _("Array has no element at position %d") % idx
                raise exc.InvalidJsonPatchPath(explanation=msg, path=idx)
            return idx
        except (ValueError, TypeError):
            msg = _("Not an array idx '%s'") % idx_str
            raise exc.InvalidJsonPatchPath(explanation=msg, path=idx_str)

    def add(self, path, value):
        # by now arrays can't contain complex structures (due to Declarative
        # Framework limitations and DB storage model),
        # so will 'path' == idx equality is implied.
        idx = self._proc_key(path, False)
        if idx == len(self) - 1:
            self.append(value)
        else:
            self.insert(idx, value)
        return self.base

    def remove(self, path, value=None):
        # by now arrays can't contain complex structures, so will imply that
        # 'path' == idx [see comment for add()]
        del self[self._proc_key(path)]
        return self.base

    def replace(self, path, value):
        # by now arrays can't contain complex structures, so will imply that
        # 'path' == idx [see comment for add()]
        self[self._proc_key(path)] = value
        return self.base


class ArtifactDictPropertyProxy(proxy.Dict):
    """A class to wrap a dict property.

    Makes possible to modify the property value via supported jsonpatch
    requests (update/remove/replace).
    """
    def __init__(self, prop_value, path):
        super(ArtifactDictPropertyProxy, self).__init__(
            prop_value)

    def _proc_key(self, key_str, should_exist=True):
        """JsonPatchUpdateMixin method overload"""
        if should_exist and key_str not in self.keys():
            msg = _("No such key '%s' in a dict") % key_str
            raise exc.InvalidJsonPatchPath(path=key_str, explanation=msg)
        return key_str

    def replace(self, path, value):
        start, delimiter, rest = path.partition('/')
        # the full path MUST exist in replace operation, so let's check
        # that such key exists
        key = self._proc_key(start)
        if not rest:
            self[key] = value
        else:
            prop = wrap_property(self[key], rest)
            self[key] = prop.replace(rest, value)

    def remove(self, path, value=None):
        start, delimiter, rest = path.partition('/')
        key = self._proc_key(start)
        if not rest:
            del self[key]
        else:
            prop = wrap_property(self[key], rest)
            prop.remove(rest)

    def add(self, path, value):
        start, delimiter, rest = path.partition('/')
        if not rest:
            self[start] = value
        else:
            key = self._proc_key(start)
            prop = wrap_property(self[key], rest)
            self[key] = prop.add(rest, value)
