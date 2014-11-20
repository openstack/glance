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
import sqlalchemy.exc as sa_exc
import sqlalchemy.orm as sa_orm

from glance.common import exception as exc
import glance.db.sqlalchemy.metadef_api.utils as metadef_utils
from glance.db.sqlalchemy import models_metadef as models

LOG = logging.getLogger(__name__)


def get(context, name, session):
    """Get a resource type, raise if not found"""

    try:
        query = session.query(models.MetadefResourceType).filter_by(name=name)
        resource_type = query.one()
    except sa_orm.exc.NoResultFound:
        msg = "No metadata definition resource-type found with name %s" % name
        LOG.debug(msg)
        raise exc.MetadefResourceTypeNotFound(resource_type_name=name)

    return resource_type.to_dict()


def get_all(context, session):
    """Get a list of all resource types"""

    query = session.query(models.MetadefResourceType)
    resource_types = query.all()

    resource_types_list = []
    for rt in resource_types:
        resource_types_list.append(rt.to_dict())

    return resource_types_list


def create(context, values, session):
    """Create a resource_type, raise if it already exists."""

    resource_type = models.MetadefResourceType()
    metadef_utils.drop_protected_attrs(models.MetadefResourceType, values)
    resource_type.update(values.copy())
    try:
        resource_type.save(session=session)
    except db_exc.DBDuplicateEntry:
        msg = ("Can not create the metadata definition resource-type."
               " A resource-type with name=%s already exists."
               % resource_type.name)
        LOG.debug(msg)
        raise exc.MetadefDuplicateResourceType(
            resource_type_name=resource_type.name)

    return resource_type.to_dict()


def update(context, values, session):
    """Update a resource type, raise if not found"""

    name = values['name']
    metadef_utils.drop_protected_attrs(models.MetadefResourceType, values)
    db_rec = get(context, name, session)
    db_rec.update(values.copy())
    db_rec.save(session=session)

    return db_rec.to_dict()


def delete(context, name, session):
    """Delete a resource type or raise if not found or is protected"""

    db_rec = get(context, name, session)
    if db_rec.protected is True:
        msg = ("Delete forbidden. Metadata definition resource-type %s is a"
               " seeded-system type and can not be deleted.") % name
        LOG.debug(msg)
        raise exc.ProtectedMetadefResourceTypeSystemDelete(
            resource_type_name=name)

    try:
        session.delete(db_rec)
        session.flush()
    except db_exc.DBError as e:
        if isinstance(e.inner_exception, sa_exc.IntegrityError):
            msg = ("Could not delete Metadata definition resource-type %s"
                   ". It still has content") % name
            LOG.debug(msg)
            raise exc.MetadefIntegrityError(
                record_type='resource-type', record_name=name)
        else:
            raise e

    return db_rec.to_dict()
