# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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


from oslo_db import exception as db_exc
from oslo_log import log as logging
import sqlalchemy.orm as sa_orm

from glance.common import exception as exc
from glance.db.sqlalchemy.metadef_api import namespace as namespace_api
from glance.db.sqlalchemy.metadef_api import resource_type as resource_type_api
from glance.db.sqlalchemy.metadef_api import utils as metadef_utils
from glance.db.sqlalchemy import models_metadef as models

LOG = logging.getLogger(__name__)


def _to_db_dict(namespace_id, resource_type_id, model_dict):
    """transform a model dict to a metadef_namespace_resource_type dict"""
    db_dict = {'namespace_id': namespace_id,
               'resource_type_id': resource_type_id,
               'properties_target': model_dict['properties_target'],
               'prefix': model_dict['prefix']}
    return db_dict


def _to_model_dict(resource_type_name, ns_res_type_dict):
    """transform a metadef_namespace_resource_type dict to a model dict"""
    model_dict = {'name': resource_type_name,
                  'properties_target': ns_res_type_dict['properties_target'],
                  'prefix': ns_res_type_dict['prefix'],
                  'created_at': ns_res_type_dict['created_at'],
                  'updated_at': ns_res_type_dict['updated_at']}
    return model_dict


def _set_model_dict(resource_type_name, properties_target, prefix,
                    created_at, updated_at):
    """return a model dict set with the passed in key values"""
    model_dict = {'name': resource_type_name,
                  'properties_target': properties_target,
                  'prefix': prefix,
                  'created_at': created_at,
                  'updated_at': updated_at}
    return model_dict


def _get(context, namespace_name, resource_type_name,
         namespace_id, resource_type_id, session):
    """Get a namespace resource_type association"""

    # visibility check assumed done in calling routine via namespace_get
    try:
        query = session.query(models.MetadefNamespaceResourceType).filter_by(
            namespace_id=namespace_id, resource_type_id=resource_type_id)
        db_rec = query.one()
    except sa_orm.exc.NoResultFound:
        msg = ("The metadata definition resource-type association of"
               " resource_type=%(resource_type_name)s to"
               " namespace_name=%(namespace_name)s was not found."
               % {'resource_type_name': resource_type_name,
                  'namespace_name': namespace_name})
        LOG.debug(msg)
        raise exc.MetadefResourceTypeAssociationNotFound(
            resource_type_name=resource_type_name,
            namespace_name=namespace_name)

    return db_rec


def _create_association(
        context, namespace_name, resource_type_name, values, session):
    """Create an association, raise if it already exists."""

    namespace_resource_type_rec = models.MetadefNamespaceResourceType()
    metadef_utils.drop_protected_attrs(
        models.MetadefNamespaceResourceType, values)
    # values['updated_at'] = timeutils.utcnow() # TS mixin should do this
    namespace_resource_type_rec.update(values.copy())
    try:
        namespace_resource_type_rec.save(session=session)
    except db_exc.DBDuplicateEntry:
        msg = ("The metadata definition resource-type association of"
               " resource_type=%(resource_type_name)s to"
               " namespace=%(namespace_name)s, already exists."
               % {'resource_type_name': resource_type_name,
                  'namespace_name': namespace_name})
        LOG.debug(msg)
        raise exc.MetadefDuplicateResourceTypeAssociation(
            resource_type_name=resource_type_name,
            namespace_name=namespace_name)

    return namespace_resource_type_rec.to_dict()


def _delete(context, namespace_name, resource_type_name,
            namespace_id, resource_type_id, session):
    """Delete a resource type association or raise if not found."""

    db_rec = _get(context, namespace_name, resource_type_name,
                  namespace_id, resource_type_id, session)
    session.delete(db_rec)
    session.flush()

    return db_rec.to_dict()


def get(context, namespace_name, resource_type_name, session):
    """Get a resource_type associations; raise if not found"""
    namespace = namespace_api.get(
        context, namespace_name, session)

    resource_type = resource_type_api.get(
        context, resource_type_name, session)

    found = _get(context, namespace_name, resource_type_name,
                 namespace['id'], resource_type['id'], session)

    return _to_model_dict(resource_type_name, found)


def get_all_by_namespace(context, namespace_name, session):
    """List resource_type associations by namespace, raise if not found"""

    # namespace get raises an exception if not visible
    namespace = namespace_api.get(
        context, namespace_name, session)

    db_recs = (
        session.query(models.MetadefResourceType)
        .join(models.MetadefResourceType.associations)
        .filter_by(namespace_id=namespace['id'])
        .values(models.MetadefResourceType.name,
                models.MetadefNamespaceResourceType.properties_target,
                models.MetadefNamespaceResourceType.prefix,
                models.MetadefNamespaceResourceType.created_at,
                models.MetadefNamespaceResourceType.updated_at))

    model_dict_list = []
    for name, properties_target, prefix, created_at, updated_at in db_recs:
        model_dict_list.append(
            _set_model_dict
            (name, properties_target, prefix, created_at, updated_at)
        )

    return model_dict_list


def create(context, namespace_name, values, session):
    """Create an association, raise if already exists or ns not found."""

    namespace = namespace_api.get(
        context, namespace_name, session)

    # if the resource_type does not exist, create it
    resource_type_name = values['name']
    metadef_utils.drop_protected_attrs(
        models.MetadefNamespaceResourceType, values)
    try:
        resource_type = resource_type_api.get(
            context, resource_type_name, session)
    except exc.NotFound:
        resource_type = None
        LOG.debug("Creating resource-type %s" % resource_type_name)

    if resource_type is None:
        resource_type_dict = {'name': resource_type_name, 'protected': False}
        resource_type = resource_type_api.create(
            context, resource_type_dict, session)

    # Create the association record, set the field values
    ns_resource_type_dict = _to_db_dict(
        namespace['id'], resource_type['id'], values)
    new_rec = _create_association(context, namespace_name, resource_type_name,
                                  ns_resource_type_dict, session)

    return _to_model_dict(resource_type_name, new_rec)


def delete(context, namespace_name, resource_type_name, session):
    """Delete an association or raise if not found"""

    namespace = namespace_api.get(
        context, namespace_name, session)

    resource_type = resource_type_api.get(
        context, resource_type_name, session)

    deleted = _delete(context, namespace_name, resource_type_name,
                      namespace['id'], resource_type['id'], session)

    return _to_model_dict(resource_type_name, deleted)


def delete_namespace_content(context, namespace_id, session):
    """Use this def only if the ns for the id has been verified as visible"""

    count = 0
    query = session.query(models.MetadefNamespaceResourceType).filter_by(
        namespace_id=namespace_id)
    count = query.delete(synchronize_session='fetch')
    return count
