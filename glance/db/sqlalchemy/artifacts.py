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

import copy
import operator
import uuid

from enum import Enum
from oslo_config import cfg
from oslo_db import exception as db_exc
from oslo_utils import timeutils
import sqlalchemy
from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import or_
import sqlalchemy.orm as orm
from sqlalchemy.orm import joinedload

import glance.artifacts as ga
from glance.common import exception
from glance.common import semver_db
from glance.db.sqlalchemy import models_artifacts as models
from glance import i18n
from oslo_log import log as os_logging

LOG = os_logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE

CONF = cfg.CONF


class Visibility(Enum):
    PRIVATE = 'private'
    PUBLIC = 'public'
    SHARED = 'shared'


class State(Enum):
    CREATING = 'creating'
    ACTIVE = 'active'
    DEACTIVATED = 'deactivated'
    DELETED = 'deleted'


TRANSITIONS = {
    State.CREATING: [State.ACTIVE, State.DELETED],
    State.ACTIVE: [State.DEACTIVATED, State.DELETED],
    State.DEACTIVATED: [State.ACTIVE, State.DELETED],
    State.DELETED: []
}


def create(context, values, session, type_name, type_version=None):
    return _out(_create_or_update(context, values, None, session,
                                  type_name, type_version))


def update(context, values, artifact_id, session,
           type_name, type_version=None):
    return _out(_create_or_update(context, values, artifact_id, session,
                                  type_name, type_version))


def delete(context, artifact_id, session, type_name, type_version=None):
    values = {'state': 'deleted'}
    return _out(_create_or_update(context, values, artifact_id, session,
                                  type_name, type_version))


def _create_or_update(context, values, artifact_id, session, type_name,
                      type_version=None):
    values = copy.deepcopy(values)
    with session.begin():
        _set_version_fields(values)
        _validate_values(values)
        _drop_protected_attrs(models.Artifact, values)
        if artifact_id:
            # update existing artifact
            state = values.get('state')
            show_level = ga.Showlevel.BASIC
            if state is not None:
                if state == 'active':
                    show_level = ga.Showlevel.DIRECT
                    values['published_at'] = timeutils.utcnow()
                if state == 'deleted':
                    values['deleted_at'] = timeutils.utcnow()

            artifact = _get(context, artifact_id, session, type_name,
                            type_version, show_level=show_level)
            _validate_transition(artifact.state,
                                 values.get('state') or artifact.state)
        else:
            # create new artifact
            artifact = models.Artifact()
            if 'id' not in values:
                artifact.id = str(uuid.uuid4())
            else:
                artifact.id = values['id']

        if 'tags' in values:
            tags = values.pop('tags')
            artifact.tags = _do_tags(artifact, tags)

        if 'properties' in values:
            properties = values.pop('properties', {})
            artifact.properties = _do_properties(artifact, properties)

        if 'blobs' in values:
            blobs = values.pop('blobs')
            artifact.blobs = _do_blobs(artifact, blobs)

        if 'dependencies' in values:
            dependencies = values.pop('dependencies')
            _do_dependencies(artifact, dependencies, session)

        if values.get('state', None) == 'publish':
            artifact.dependencies.extend(
                _do_transitive_dependencies(artifact, session))

        artifact.update(values)
        try:
            artifact.save(session=session)
        except db_exc.DBDuplicateEntry:
            LOG.warn(_LW("Artifact with the specified type, name and version "
                         "already exists"))
            raise exception.ArtifactDuplicateNameTypeVersion()

    return artifact


def get(context, artifact_id, session, type_name=None, type_version=None,
        show_level=ga.Showlevel.BASIC):
    artifact = _get(context, artifact_id, session, type_name, type_version,
                    show_level)
    return _out(artifact, show_level)


def publish(context, artifact_id, session, type_name,
            type_version=None):
    """
    Because transitive dependencies are not initially created it has to be done
    manually by calling this function.
    It creates transitive dependencies for the given artifact_id and saves
    them in DB.
    :returns artifact dict with Transitive show level
    """
    values = {'state': 'active'}
    return _out(_create_or_update(context, values, artifact_id, session,
                                  type_name, type_version))


def _validate_transition(source_state, target_state):
    if target_state == source_state:
        return
    try:
        source_state = State(source_state)
        target_state = State(target_state)
    except ValueError:
        raise exception.InvalidArtifactStateTransition(source=source_state,
                                                       target=target_state)
    if (source_state not in TRANSITIONS or
       target_state not in TRANSITIONS[source_state]):
        raise exception.InvalidArtifactStateTransition(source=source_state,
                                                       target=target_state)


def _out(artifact, show_level=ga.Showlevel.BASIC, show_text_properties=True):
    """
    Transforms sqlalchemy object into dict depending on the show level.

    :param artifact: sql
    :param show_level: constant from Showlevel class
    :param show_text_properties: for performance optimization it's possible
    to disable loading of massive text properties
    :return: generated dict
    """
    res = artifact.to_dict(show_level=show_level,
                           show_text_properties=show_text_properties)

    if show_level >= ga.Showlevel.DIRECT:
        dependencies = artifact.dependencies
        dependencies.sort(key=lambda elem: (elem.artifact_origin,
                                            elem.name, elem.position))
        res['dependencies'] = {}
        if show_level == ga.Showlevel.DIRECT:
            new_show_level = ga.Showlevel.BASIC
        else:
            new_show_level = ga.Showlevel.TRANSITIVE
        for dep in dependencies:
            if dep.artifact_origin == artifact.id:
                # make array
                for p in res['dependencies'].keys():
                    if p == dep.name:
                        # add value to array
                        res['dependencies'][p].append(
                            _out(dep.dest, new_show_level))
                        break
                else:
                    # create new array
                    deparr = [_out(dep.dest, new_show_level)]
                    res['dependencies'][dep.name] = deparr
    return res


def _get(context, artifact_id, session, type_name=None, type_version=None,
         show_level=ga.Showlevel.BASIC):
    values = dict(id=artifact_id)
    if type_name is not None:
        values['type_name'] = type_name
    if type_version is not None:
        values['type_version'] = type_version
    _set_version_fields(values)
    try:
        if show_level == ga.Showlevel.NONE:
            query = (
                session.query(models.Artifact).
                options(joinedload(models.Artifact.tags)).
                filter_by(**values))
        else:
            query = (
                session.query(models.Artifact).
                options(joinedload(models.Artifact.properties)).
                options(joinedload(models.Artifact.tags)).
                options(joinedload(models.Artifact.blobs).
                        joinedload(models.ArtifactBlob.locations)).
                filter_by(**values))

        artifact = query.one()
    except orm.exc.NoResultFound:
        LOG.warn(_LW("Artifact with id=%s not found") % artifact_id)
        raise exception.ArtifactNotFound(id=artifact_id)
    if not _check_visibility(context, artifact):
        LOG.warn(_LW("Artifact with id=%s is not accessible") % artifact_id)
        raise exception.ArtifactForbidden(id=artifact_id)
    return artifact


def get_all(context, session, marker=None, limit=None,
            sort_keys=None, sort_dirs=None, filters=None,
            show_level=ga.Showlevel.NONE):
    """List all visible artifacts"""

    filters = filters or {}

    artifacts = _get_all(
        context, session, filters, marker,
        limit, sort_keys, sort_dirs, show_level)

    return map(lambda ns: _out(ns, show_level, show_text_properties=False),
               artifacts)


def _get_all(context, session, filters=None, marker=None,
             limit=None, sort_keys=None, sort_dirs=None,
             show_level=ga.Showlevel.NONE):
    """Get all namespaces that match zero or more filters.

    :param filters: dict of filter keys and values.
    :param marker: namespace id after which to start page
    :param limit: maximum number of namespaces to return
    :param sort_keys: namespace attributes by which results should be sorted
    :param sort_dirs: directions in which results should be sorted (asc, desc)
    """

    filters = filters or {}

    query = _do_artifacts_query(context, session, show_level)
    basic_conds, tag_conds, prop_conds = _do_query_filters(filters)

    if basic_conds:
        for basic_condition in basic_conds:
            query = query.filter(and_(*basic_condition))

    if tag_conds:
        for tag_condition in tag_conds:
            query = query.join(models.ArtifactTag, aliased=True).filter(
                and_(*tag_condition))

    if prop_conds:
        for prop_condition in prop_conds:
            query = query.join(models.ArtifactProperty, aliased=True).filter(
                and_(*prop_condition))

    marker_artifact = None
    if marker is not None:
        marker_artifact = _get(context, marker, session, None, None)

    if sort_keys is None:
        sort_keys = [('created_at', None), ('id', None)]
        sort_dirs = ['desc', 'desc']
    else:
        for key in [('created_at', None), ('id', None)]:
            if key not in sort_keys:
                sort_keys.append(key)
                sort_dirs.append('desc')

    # Note(mfedosin): Workaround to deal with situation that sqlalchemy cannot
    # work with composite keys correctly
    if ('version', None) in sort_keys:
        i = sort_keys.index(('version', None))
        version_sort_dir = sort_dirs[i]
        sort_keys[i:i + 1] = [('version_prefix', None),
                              ('version_suffix', None),
                              ('version_meta', None)]
        sort_dirs[i:i + 1] = [version_sort_dir] * 3

    query = _do_paginate_query(query=query,
                               limit=limit,
                               sort_keys=sort_keys,
                               marker=marker_artifact,
                               sort_dirs=sort_dirs)

    return query.all()


def _do_paginate_query(query, sort_keys=None, sort_dirs=None,
                       marker=None, limit=None):
    # Default the sort direction to ascending
    if sort_dirs is None:
        sort_dir = 'asc'

    # Ensure a per-column sort direction
    if sort_dirs is None:
        sort_dirs = [sort_dir for _sort_key in sort_keys]

    assert(len(sort_dirs) == len(sort_keys))

    # Add sorting
    for current_sort_key, current_sort_dir in zip(sort_keys, sort_dirs):
        try:
            sort_dir_func = {
                'asc': sqlalchemy.asc,
                'desc': sqlalchemy.desc,
            }[current_sort_dir]
        except KeyError:
            raise ValueError(_LE("Unknown sort direction, "
                                 "must be 'desc' or 'asc'"))

        if current_sort_key[1] is None:
            # sort by generic property
            query = query.order_by(sort_dir_func(getattr(
                models.Artifact,
                current_sort_key[0])))
        else:
            # sort by custom property
            prop_type = current_sort_key[1] + "_value"
            query = (
                query.join(models.ArtifactProperty).
                filter(models.ArtifactProperty.name == current_sort_key[0]).
                order_by(sort_dir_func(getattr(models.ArtifactProperty,
                                               prop_type))))

    default = ''

    # Add pagination
    if marker is not None:
        marker_values = []
        for sort_key in sort_keys:
            v = getattr(marker, sort_key[0])
            if v is None:
                v = default
            marker_values.append(v)

        # Build up an array of sort criteria as in the docstring
        criteria_list = []
        for i in range(len(sort_keys)):
            crit_attrs = []
            if marker_values[i] is None:
                continue
            for j in range(i):
                if sort_keys[j][1] is None:
                    model_attr = getattr(models.Artifact, sort_keys[j][0])
                else:
                    model_attr = getattr(models.ArtifactProperty,
                                         sort_keys[j][1] + "_value")
                default = None if isinstance(
                    model_attr.property.columns[0].type,
                    sqlalchemy.DateTime) else ''
                attr = case([(model_attr != None,
                              model_attr), ],
                            else_=default)
                crit_attrs.append((attr == marker_values[j]))

            if sort_keys[i][1] is None:
                model_attr = getattr(models.Artifact, sort_keys[i][0])
            else:
                model_attr = getattr(models.ArtifactProperty,
                                     sort_keys[i][1] + "_value")

            default = None if isinstance(model_attr.property.columns[0].type,
                                         sqlalchemy.DateTime) else ''
            attr = case([(model_attr != None,
                          model_attr), ],
                        else_=default)

            if sort_dirs[i] == 'desc':
                crit_attrs.append((attr < marker_values[i]))
            else:
                crit_attrs.append((attr > marker_values[i]))

            criteria = and_(*crit_attrs)
            criteria_list.append(criteria)

        f = or_(*criteria_list)
        query = query.filter(f)

    if limit is not None:
        query = query.limit(limit)

    return query


def _do_artifacts_query(context, session, show_level=ga.Showlevel.NONE):
    """Build the query to get all artifacts based on the context"""

    LOG.debug("context.is_admin=%(is_admin)s; context.owner=%(owner)s" %
              {'is_admin': context.is_admin, 'owner': context.owner})

    if show_level == ga.Showlevel.NONE:
        query = session.query(models.Artifact).options(
            joinedload(models.Artifact.tags))
    elif show_level == ga.Showlevel.BASIC:
        query = (
            session.query(models.Artifact).
            options(joinedload(
                models.Artifact.properties).
                defer(models.ArtifactProperty.text_value)).
            options(joinedload(models.Artifact.tags)).
            options(joinedload(models.Artifact.blobs).
                    joinedload(models.ArtifactBlob.locations)))
    else:
        # other show_levels aren't supported
        msg = _LW("Show level %s is not supported in this "
                  "operation") % ga.Showlevel.to_str(show_level)
        LOG.warn(msg)
        raise exception.ArtifactUnsupportedShowLevel(shl=show_level)

    # If admin, return everything.
    if context.is_admin:
        return query
    else:
        # If regular user, return only public artifacts.
        # However, if context.owner has a value, return both
        # public and private artifacts of the context.owner.
        if context.owner is not None:
            query = query.filter(
                or_(models.Artifact.owner == context.owner,
                    models.Artifact.visibility == 'public'))
        else:
            query = query.filter(
                models.Artifact.visibility == 'public')
        return query

op_mappings = {
    'EQ': operator.eq,
    'GT': operator.gt,
    'GE': operator.ge,
    'LT': operator.lt,
    'LE': operator.le,
    'NE': operator.ne,
    'IN': operator.eq  # it must be eq
}


def _do_query_filters(filters):
    basic_conds = []
    tag_conds = []
    prop_conds = []

    # don't show deleted artifacts
    basic_conds.append([models.Artifact.state != 'deleted'])

    visibility = filters.pop('visibility', None)
    if visibility is not None:
        # ignore operator. always consider it EQ
        basic_conds.append(
            [models.Artifact.visibility == visibility[0]['value']])

    type_name = filters.pop('type_name', None)
    if type_name is not None:
        # ignore operator. always consider it EQ
        basic_conds.append([models.Artifact.type_name == type_name['value']])
        type_version = filters.pop('type_version', None)
        if type_version is not None:
            # ignore operator. always consider it EQ
            # TODO(mfedosin) add support of LIKE operator
            type_version = semver_db.parse(type_version['value'])
            basic_conds.append([models.Artifact.type_version == type_version])

    name = filters.pop('name', None)
    if name is not None:
        # ignore operator. always consider it EQ
        basic_conds.append([models.Artifact.name == name[0]['value']])

    versions = filters.pop('version', None)
    if versions is not None:
        for version in versions:
            value = semver_db.parse(version['value'])
            op = version['operator']
            fn = op_mappings[op]
            basic_conds.append([fn(models.Artifact.version, value)])

    state = filters.pop('state', None)
    if state is not None:
        # ignore operator. always consider it EQ
        basic_conds.append([models.Artifact.state == state['value']])

    owner = filters.pop('owner', None)
    if owner is not None:
        # ignore operator. always consider it EQ
        basic_conds.append([models.Artifact.owner == owner[0]['value']])

    id_list = filters.pop('id_list', None)
    if id_list is not None:
        basic_conds.append([models.Artifact.id.in_(id_list['value'])])

    name_list = filters.pop('name_list', None)
    if name_list is not None:
        basic_conds.append([models.Artifact.name.in_(name_list['value'])])

    tags = filters.pop('tags', None)
    if tags is not None:
        for tag in tags:
            tag_conds.append([models.ArtifactTag.value == tag['value']])

    # process remaining filters
    for filtername, filtervalues in filters.items():
        for filtervalue in filtervalues:

            db_prop_op = filtervalue['operator']
            db_prop_value = filtervalue['value']
            db_prop_type = filtervalue['type'] + "_value"
            db_prop_position = filtervalue.get('position')

            conds = [models.ArtifactProperty.name == filtername]

            if db_prop_op in op_mappings:
                fn = op_mappings[db_prop_op]
                result = fn(getattr(models.ArtifactProperty, db_prop_type),
                            db_prop_value)

                cond = [result]
                if db_prop_position is not 'any':
                    cond.append(
                        models.ArtifactProperty.position == db_prop_position)
                if db_prop_op == 'IN':
                    if (db_prop_position is not None and
                            db_prop_position is not 'any'):
                        msg = _LE("Cannot use this parameter with "
                                  "the operator IN")
                        LOG.error(msg)
                        raise exception.ArtifactInvalidPropertyParameter(
                            op='IN')
                    cond = [result,
                            models.ArtifactProperty.position >= 0]
            else:
                msg = _LE("Operator %s is not supported") % db_prop_op
                LOG.error(msg)
                raise exception.ArtifactUnsupportedPropertyOperator(
                    op=db_prop_op)

            conds.extend(cond)

            prop_conds.append(conds)
    return basic_conds, tag_conds, prop_conds


def _do_tags(artifact, new_tags):
    tags_to_update = []
    # don't touch existing tags
    for tag in artifact.tags:
        if tag.value in new_tags:
            tags_to_update.append(tag)
            new_tags.remove(tag.value)
    # add new tags
    for tag in new_tags:
        db_tag = models.ArtifactTag()
        db_tag.value = tag
        tags_to_update.append(db_tag)
    return tags_to_update


def _do_property(propname, prop, position=None):
    db_prop = models.ArtifactProperty()
    db_prop.name = propname
    setattr(db_prop,
            (prop['type'] + "_value"),
            prop['value'])
    db_prop.position = position
    return db_prop


def _do_properties(artifact, new_properties):

    props_to_update = []
    # don't touch existing properties
    for prop in artifact.properties:
        if prop.name not in new_properties:
            props_to_update.append(prop)

    for propname, prop in new_properties.items():
        if prop['type'] == 'array':
            for pos, arrprop in enumerate(prop['value']):
                props_to_update.append(
                    _do_property(propname, arrprop, pos)
                )
        else:
            props_to_update.append(
                _do_property(propname, prop)
            )
    return props_to_update


def _do_blobs(artifact, new_blobs):
    blobs_to_update = []

    # don't touch existing blobs
    for blob in artifact.blobs:
        if blob.name not in new_blobs:
            blobs_to_update.append(blob)

    for blobname, blobs in new_blobs.items():
        for pos, blob in enumerate(blobs):
            for db_blob in artifact.blobs:
                if db_blob.name == blobname and db_blob.position == pos:
                    # update existing blobs
                    db_blob.size = blob['size']
                    db_blob.checksum = blob['checksum']
                    db_blob.item_key = blob['item_key']
                    db_blob.locations = _do_locations(db_blob,
                                                      blob['locations'])
                    blobs_to_update.append(db_blob)
                    break
            else:
                # create new blob
                db_blob = models.ArtifactBlob()
                db_blob.name = blobname
                db_blob.size = blob['size']
                db_blob.checksum = blob['checksum']
                db_blob.item_key = blob['item_key']
                db_blob.position = pos
                db_blob.locations = _do_locations(db_blob, blob['locations'])
                blobs_to_update.append(db_blob)
    return blobs_to_update


def _do_locations(blob, new_locations):
    locs_to_update = []
    for pos, loc in enumerate(new_locations):
        for db_loc in blob.locations:
            if db_loc.value == loc['value']:
                # update existing location
                db_loc.position = pos
                db_loc.status = loc['status']
                locs_to_update.append(db_loc)
                break
        else:
            # create new location
            db_loc = models.ArtifactBlobLocation()
            db_loc.value = loc['value']
            db_loc.status = loc['status']
            db_loc.position = pos
            locs_to_update.append(db_loc)
    return locs_to_update


def _do_dependencies(artifact, new_dependencies, session):
    deps_to_update = []
    # small check that all dependencies are new
    if artifact.dependencies is not None:
        for db_dep in artifact.dependencies:
            for dep in new_dependencies.keys():
                if db_dep.name == dep:
                    msg = _LW("Artifact with the specified type, name "
                              "and versions already has the direct "
                              "dependency=%s") % dep
                    LOG.warn(msg)
        # change values of former dependency
        for dep in artifact.dependencies:
            session.delete(dep)
        artifact.dependencies = []
    for depname, depvalues in new_dependencies.items():
        for pos, depvalue in enumerate(depvalues):
            db_dep = models.ArtifactDependency()
            db_dep.name = depname
            db_dep.artifact_source = artifact.id
            db_dep.artifact_dest = depvalue
            db_dep.artifact_origin = artifact.id
            db_dep.is_direct = True
            db_dep.position = pos
            deps_to_update.append(db_dep)
    artifact.dependencies = deps_to_update


def _do_transitive_dependencies(artifact, session):
    deps_to_update = []
    for dependency in artifact.dependencies:
        depvalue = dependency.artifact_dest
        transitdeps = session.query(models.ArtifactDependency).filter_by(
            artifact_source=depvalue).all()
        for transitdep in transitdeps:
            if not transitdep.is_direct:
                # transitive dependencies are already created
                msg = _LW("Artifact with the specified type, "
                          "name and version already has the "
                          "direct dependency=%d") % transitdep.id
                LOG.warn(msg)
                raise exception.ArtifactDuplicateTransitiveDependency(
                    dep=transitdep.id)

            db_dep = models.ArtifactDependency()
            db_dep.name = transitdep['name']
            db_dep.artifact_source = artifact.id
            db_dep.artifact_dest = transitdep.artifact_dest
            db_dep.artifact_origin = transitdep.artifact_source
            db_dep.is_direct = False
            db_dep.position = transitdep.position
            deps_to_update.append(db_dep)
    return deps_to_update


def _check_visibility(context, artifact):
    if context.is_admin:
        return True

    if not artifact.owner:
        return True

    if artifact.visibility == Visibility.PUBLIC.value:
        return True

    if artifact.visibility == Visibility.PRIVATE.value:
        if context.owner and context.owner == artifact.owner:
            return True
        else:
            return False

    if artifact.visibility == Visibility.SHARED.value:
        return False

    return False


def _set_version_fields(values):
    if 'type_version' in values:
        values['type_version'] = semver_db.parse(values['type_version'])
    if 'version' in values:
        values['version'] = semver_db.parse(values['version'])


def _validate_values(values):
    if 'state' in values:
        try:
            State(values['state'])
        except ValueError:
            msg = "Invalid artifact state '%s'" % values['state']
            raise exception.Invalid(msg)
    if 'visibility' in values:
        try:
            Visibility(values['visibility'])
        except ValueError:
            msg = "Invalid artifact visibility '%s'" % values['visibility']
            raise exception.Invalid(msg)
    # TODO(mfedosin): it's an idea to validate tags someday
    # (check that all tags match the regexp)


def _drop_protected_attrs(model_class, values):
    """
    Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]
