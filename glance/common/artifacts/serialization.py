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

from glance import artifacts as ga
from glance.common.artifacts import declarative
from glance.common.artifacts import definitions
from glance.common import exception
from glance import i18n


_ = i18n._

COMMON_ARTIFACT_PROPERTIES = ['id',
                              'type_name',
                              'type_version',
                              'name',
                              'version',
                              'description',
                              'visibility',
                              'state',
                              'tags',
                              'owner',
                              'created_at',
                              'updated_at',
                              'published_at',
                              'deleted_at']


def _serialize_list_prop(prop, values):
    """
    A helper func called to correctly serialize an Array property.

    Returns a dict {'type': some_supported_db_type, 'value': serialized_data}
    """
    # FIXME(Due to a potential bug in declarative framework, for Arrays, that
    # are values to some dict items (Dict(properties={"foo": Array()})),
    # prop.get_value(artifact) returns not the real list of items, but the
    # whole dict). So we can't rely on prop.get_value(artifact) and will pass
    # correctly retrieved values to this function
    serialized_value = []
    for i, val in enumerate(values or []):
        db_type = prop.get_item_definition_at_index(i).DB_TYPE
        if db_type is None:
            continue
        serialized_value.append({
            'type': db_type,
            'value': val
        })
    return serialized_value


def _serialize_dict_prop(artifact, prop, key, value, save_prop_func):
    key_to_save = prop.name + '.' + key
    dict_key_prop = prop.get_prop_definition_at_key(key)
    db_type = dict_key_prop.DB_TYPE
    if (db_type is None and
        not isinstance(dict_key_prop,
                       declarative.ListAttributeDefinition)):
        # nothing to do here, don't know how to deal with this type
        return
    elif isinstance(dict_key_prop,
                    declarative.ListAttributeDefinition):
        serialized = _serialize_list_prop(
            dict_key_prop,
            # FIXME(see comment for _serialize_list_prop func)
            values=(dict_key_prop.get_value(artifact) or {}).get(key, []))
        save_prop_func(key_to_save, 'array', serialized)
    else:
        save_prop_func(key_to_save, db_type, value)


def _serialize_dependencies(artifact):
    """Returns a dict of serialized dependencies for given artifact"""
    dependencies = {}
    for relation in artifact.metadata.attributes.dependencies.values():
        serialized_dependency = []
        if isinstance(relation, declarative.ListAttributeDefinition):
            for dep in relation.get_value(artifact):
                serialized_dependency.append(dep.id)
        else:
            relation_data = relation.get_value(artifact)
            if relation_data:
                serialized_dependency.append(relation.get_value(artifact).id)
        dependencies[relation.name] = serialized_dependency
    return dependencies


def _serialize_blobs(artifact):
    """Return a dict of serialized blobs for given artifact"""
    blobs = {}
    for blob in artifact.metadata.attributes.blobs.values():
        serialized_blob = []
        if isinstance(blob, declarative.ListAttributeDefinition):
            for b in blob.get_value(artifact) or []:
                serialized_blob.append({
                    'size': b.size,
                    'locations': b.locations,
                    'checksum': b.checksum,
                    'item_key': b.item_key
                })
        else:
            b = blob.get_value(artifact)
            # if no value for blob has been set -> continue
            if not b:
                continue
            serialized_blob.append({
                'size': b.size,
                'locations': b.locations,
                'checksum': b.checksum,
                'item_key': b.item_key
            })
        blobs[blob.name] = serialized_blob
    return blobs


def serialize_for_db(artifact):
    result = {}
    custom_properties = {}

    def _save_prop(prop_key, prop_type, value):
        custom_properties[prop_key] = {
            'type': prop_type,
            'value': value
        }

    for prop in artifact.metadata.attributes.properties.values():
        if prop.name in COMMON_ARTIFACT_PROPERTIES:
            result[prop.name] = prop.get_value(artifact)
            continue
        if isinstance(prop, declarative.ListAttributeDefinition):
            serialized_value = _serialize_list_prop(prop,
                                                    prop.get_value(artifact))
            _save_prop(prop.name, 'array', serialized_value)
        elif isinstance(prop, declarative.DictAttributeDefinition):
            fields_to_set = prop.get_value(artifact) or {}
            # if some keys are not present (like in prop == {}), then have to
            # set their values to None.
            # XXX FIXME prop.properties may be a dict ({'foo': '', 'bar': ''})
            # or String\Integer\whatsoever, limiting the possible dict values.
            # In the latter case have no idea how to remove old values during
            # serialization process.
            if isinstance(prop.properties, dict):
                for key in [k for k in prop.properties
                            if k not in fields_to_set.keys()]:
                    _serialize_dict_prop(artifact, prop, key, None, _save_prop)
            # serialize values of properties present
            for key, value in six.iteritems(fields_to_set):
                _serialize_dict_prop(artifact, prop, key, value, _save_prop)
        elif prop.DB_TYPE is not None:
            _save_prop(prop.name, prop.DB_TYPE, prop.get_value(artifact))

    result['properties'] = custom_properties
    result['dependencies'] = _serialize_dependencies(artifact)
    result['blobs'] = _serialize_blobs(artifact)
    return result


def _deserialize_blobs(artifact_type, blobs_from_db, artifact_properties):
    """Retrieves blobs from database"""
    for blob_name, blob_value in six.iteritems(blobs_from_db):
        if not blob_value:
            continue
        if isinstance(artifact_type.metadata.attributes.blobs.get(blob_name),
                      declarative.ListAttributeDefinition):
            val = []
            for v in blob_value:
                b = definitions.Blob(size=v['size'],
                                     locations=v['locations'],
                                     checksum=v['checksum'],
                                     item_key=v['item_key'])
                val.append(b)
        elif len(blob_value) == 1:
            val = definitions.Blob(size=blob_value[0]['size'],
                                   locations=blob_value[0]['locations'],
                                   checksum=blob_value[0]['checksum'],
                                   item_key=blob_value[0]['item_key'])
        else:
            raise exception.InvalidArtifactPropertyValue(
                message=_('Blob %(name)s may not have multiple values'),
                name=blob_name)
        artifact_properties[blob_name] = val


def _deserialize_dependencies(artifact_type, deps_from_db,
                              artifact_properties, plugins):
    """Retrieves dependencies from database"""
    for dep_name, dep_value in six.iteritems(deps_from_db):
        if not dep_value:
            continue
        if isinstance(
                artifact_type.metadata.attributes.dependencies.get(dep_name),
                declarative.ListAttributeDefinition):
            val = []
            for v in dep_value:
                val.append(deserialize_from_db(v, plugins))
        elif len(dep_value) == 1:
            val = deserialize_from_db(dep_value[0], plugins)
        else:
            raise exception.InvalidArtifactPropertyValue(
                message=_('Relation %(name)s may not have multiple values'),
                name=dep_name)
        artifact_properties[dep_name] = val


def deserialize_from_db(db_dict, plugins):
    artifact_properties = {}
    type_name = None
    type_version = None

    for prop_name in COMMON_ARTIFACT_PROPERTIES:
        prop_value = db_dict.pop(prop_name, None)
        if prop_name == 'type_name':
            type_name = prop_value
        elif prop_name == 'type_version':
            type_version = prop_value
        else:
            artifact_properties[prop_name] = prop_value

    try:
        artifact_type = plugins.get_class_by_typename(type_name, type_version)
    except exception.ArtifactPluginNotFound:
        raise exception.UnknownArtifactType(name=type_name,
                                            version=type_version)

    type_specific_properties = db_dict.pop('properties', {})
    for prop_name, prop_value in six.iteritems(type_specific_properties):
        prop_type = prop_value.get('type')
        prop_value = prop_value.get('value')
        if prop_value is None:
            continue
        if '.' in prop_name:  # dict-based property
            name, key = prop_name.split('.', 1)
            artifact_properties.setdefault(name, {})
            if prop_type == 'array':
                artifact_properties[name][key] = [item.get('value') for item in
                                                  prop_value]
            else:
                artifact_properties[name][key] = prop_value
        elif prop_type == 'array':  # list-based property
            artifact_properties[prop_name] = [item.get('value') for item in
                                              prop_value]
        else:
            artifact_properties[prop_name] = prop_value

    blobs = db_dict.pop('blobs', {})
    _deserialize_blobs(artifact_type, blobs, artifact_properties)

    dependencies = db_dict.pop('dependencies', {})
    _deserialize_dependencies(artifact_type, dependencies,
                              artifact_properties, plugins)

    return artifact_type(**artifact_properties)


def _process_blobs_for_client(artifact, result):
    """Processes artifact's blobs: adds download links and pretty-printed data.

    The result is stored in 'result' dict.
    """
    def build_uri(blob_attr, position=None):
        """A helper func to build download uri"""
        template = "/artifacts/%(type)s/v%(version)s/%(id)s/%(prop)s/download"
        format_dict = {
            "type": artifact.metadata.endpoint,
            "version": artifact.type_version,
            "id": artifact.id,
            "prop": blob_attr.name
        }
        if position is not None:
            template = ("/artifacts/%(type)s/v%(version)s/"
                        "%(id)s/%(prop)s/%(position)s/download")
            format_dict["position"] = position

        return template % format_dict

    for blob_attr in artifact.metadata.attributes.blobs.values():
        value = blob_attr.get_value(artifact)
        if value is None:
            result[blob_attr.name] = None
        elif isinstance(value, collections.Iterable):
            res_list = []
            for pos, blob in enumerate(value):
                blob_dict = blob.to_dict()
                blob_dict["download_link"] = build_uri(blob_attr, pos)
                res_list.append(blob_dict)
            result[blob_attr.name] = res_list
        else:
            result[blob_attr.name] = value.to_dict()
            result[blob_attr.name]["download_link"] = build_uri(blob_attr)


def serialize_for_client(artifact, show_level=ga.Showlevel.NONE):
    # use serialize_for_db and modify some fields
    # (like properties, show only value, not type)
    result = {}

    for prop in artifact.metadata.attributes.properties.values():
        result[prop.name] = prop.get_value(artifact)

    if show_level > ga.Showlevel.NONE:
        for dep in artifact.metadata.attributes.dependencies.values():
            inner_show_level = (ga.Showlevel.DIRECT
                                if show_level == ga.Showlevel.DIRECT
                                else ga.Showlevel.NONE)
            value = dep.get_value(artifact)
            if value is None:
                result[dep.name] = None
            elif isinstance(value, list):
                result[dep.name] = [serialize_for_client(v, inner_show_level)
                                    for v in value]
            else:
                result[dep.name] = serialize_for_client(value,
                                                        inner_show_level)
    _process_blobs_for_client(artifact, result)
    return result
