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

import collections

import six

from glance.common import exception as exc
from glance.domain import proxy as image_proxy


def _proxy_artifact_property(attr):
    def getter(self):
        return self.get_type_specific_property(attr)

    def setter(self, value):
        return self.set_type_specific_property(attr, value)

    return property(getter, setter)


class ArtifactHelper(image_proxy.Helper):
    """
    Artifact-friendly proxy helper: does all the same as regular helper
    but also dynamically proxies all the type-specific attributes,
    including properties, blobs and dependencies
    """
    def proxy(self, obj):
        if obj is None or self.proxy_class is None:
            return obj
        if not hasattr(obj, 'metadata'):
            return super(ArtifactHelper, self).proxy(obj)
        extra_attrs = {}
        for att_name in six.iterkeys(obj.metadata.attributes.all):
            extra_attrs[att_name] = _proxy_artifact_property(att_name)
        new_proxy_class = type("%s(%s)" % (obj.metadata.type_name,
                                           self.proxy_class.__module__),
                               (self.proxy_class,),
                               extra_attrs)
        return new_proxy_class(obj, **self.proxy_kwargs)


class ArtifactRepo(object):
    def __init__(self, base, proxy_helper=None, item_proxy_class=None,
                 item_proxy_kwargs=None):
        self.base = base
        if proxy_helper is None:
            proxy_helper = ArtifactHelper(item_proxy_class, item_proxy_kwargs)
        self.helper = proxy_helper

    def get(self, *args, **kwargs):
        return self.helper.proxy(self.base.get(*args, **kwargs))

    def list(self, *args, **kwargs):
        items = self.base.list(*args, **kwargs)
        return [self.helper.proxy(item) for item in items]

    def add(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.add(base_item)
        return self.helper.proxy(result)

    def save(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.save(base_item)
        return self.helper.proxy(result)

    def remove(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.helper.proxy(result)

    def publish(self, item, *args, **kwargs):
        base_item = self.helper.unproxy(item)
        result = self.base.publish(base_item, *args, **kwargs)
        return self.helper.proxy(result)


class Artifact(object):
    def __init__(self, base, proxy_class=None, proxy_kwargs=None):
        self.base = base
        self.helper = ArtifactHelper(proxy_class, proxy_kwargs)

    # it is enough to proxy metadata only, other properties will be proxied
    # automatically by ArtifactHelper
    metadata = _proxy_artifact_property('metadata')

    def set_type_specific_property(self, prop_name, value):
        setattr(self.base, prop_name, value)

    def get_type_specific_property(self, prop_name):
        try:
            return getattr(self.base, prop_name)
        except AttributeError:
            raise exc.ArtifactInvalidProperty(prop=prop_name)

    def __pre_publish__(self, *args, **kwargs):
        self.base.__pre_publish__(*args, **kwargs)


class ArtifactFactory(object):
    def __init__(self, base,
                 artifact_proxy_class=Artifact,
                 artifact_proxy_kwargs=None):
        self.artifact_helper = ArtifactHelper(artifact_proxy_class,
                                              artifact_proxy_kwargs)
        self.base = base

    def new_artifact(self, *args, **kwargs):
        t = self.base.new_artifact(*args, **kwargs)
        return self.artifact_helper.proxy(t)


class ArtifactBlob(object):
    def __init__(self, base, artifact_blob_proxy_class=None,
                 artifact_blob_proxy_kwargs=None):
        self.base = base
        self.helper = image_proxy.Helper(artifact_blob_proxy_class,
                                         artifact_blob_proxy_kwargs)

    size = _proxy_artifact_property('size')
    locations = _proxy_artifact_property('locations')
    checksum = _proxy_artifact_property('checksum')
    item_key = _proxy_artifact_property('item_key')

    def set_type_specific_property(self, prop_name, value):
        setattr(self.base, prop_name, value)

    def get_type_specific_property(self, prop_name):
        return getattr(self.base, prop_name)

    def to_dict(self):
        return self.base.to_dict()


class ArtifactProperty(object):
    def __init__(self, base, proxy_class=None, proxy_kwargs=None):
        self.base = base
        self.helper = ArtifactHelper(proxy_class, proxy_kwargs)

    def set_type_specific_property(self, prop_name, value):
        setattr(self.base, prop_name, value)

    def get_type_specific_property(self, prop_name):
        return getattr(self.base, prop_name)


class List(collections.MutableSequence):
    def __init__(self, base, item_proxy_class=None,
                 item_proxy_kwargs=None):
        self.base = base
        self.helper = image_proxy.Helper(item_proxy_class, item_proxy_kwargs)

    def __len__(self):
        return len(self.base)

    def __delitem__(self, index):
        del self.base[index]

    def __getitem__(self, index):
        item = self.base[index]
        return self.helper.proxy(item)

    def insert(self, index, value):
        self.base.insert(index, self.helper.unproxy(value))

    def __setitem__(self, index, value):
        self.base[index] = self.helper.unproxy(value)


class Dict(collections.MutableMapping):
    def __init__(self, base, item_proxy_class=None, item_proxy_kwargs=None):
        self.base = base
        self.helper = image_proxy.Helper(item_proxy_class, item_proxy_kwargs)

    def __setitem__(self, key, value):
        self.base[key] = self.helper.unproxy(value)

    def __getitem__(self, key):
        item = self.base[key]
        return self.helper.proxy(item)

    def __delitem__(self, key):
        del self.base[key]

    def __len__(self):
        return len(self.base)

    def __iter__(self):
        for key in self.base.keys():
            yield key
