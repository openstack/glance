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
from sqlalchemy import func
import sqlalchemy.orm as sa_orm

from glance.common import exception as exc
from glance.db.sqlalchemy.metadef_api import namespace as namespace_api
from glance.db.sqlalchemy.metadef_api import utils as metadef_utils
from glance.db.sqlalchemy import models_metadef as models
from glance.i18n import _

LOG = logging.getLogger(__name__)


def _get(context, session, property_id):

    try:
        query = session.query(models.MetadefProperty).filter_by(id=property_id)
        property_rec = query.one()

    except sa_orm.exc.NoResultFound:
        msg = (_("Metadata definition property not found for id=%s")
               % property_id)
        LOG.warning(msg)
        raise exc.MetadefPropertyNotFound(msg)

    return property_rec


def _get_by_name(context, session, namespace_name, name):
    """get a property; raise if ns not found/visible or property not found"""

    namespace = namespace_api.get(context, session, namespace_name)
    try:
        query = session.query(models.MetadefProperty).filter_by(
            name=name, namespace_id=namespace['id'])
        property_rec = query.one()

    except sa_orm.exc.NoResultFound:
        LOG.debug("The metadata definition property with name=%(name)s"
                  " was not found in namespace=%(namespace_name)s.",
                  {'name': name, 'namespace_name': namespace_name})
        raise exc.MetadefPropertyNotFound(property_name=name,
                                          namespace_name=namespace_name)

    return property_rec


def get(context, session, namespace_name, name):
    """get a property; raise if ns not found/visible or property not found"""

    property_rec = _get_by_name(context, session, namespace_name, name)
    return property_rec.to_dict()


def get_all(context, session, namespace_name):
    namespace = namespace_api.get(context, session, namespace_name)
    query = session.query(models.MetadefProperty).filter_by(
        namespace_id=namespace['id'])
    properties = query.all()

    properties_list = []
    for prop in properties:
        properties_list.append(prop.to_dict())
    return properties_list


def create(context, session, namespace_name, values):
    namespace = namespace_api.get(context, session, namespace_name)
    values.update({'namespace_id': namespace['id']})

    property_rec = models.MetadefProperty()
    metadef_utils.drop_protected_attrs(models.MetadefProperty, values)
    property_rec.update(values.copy())

    try:
        property_rec.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Can not create metadata definition property. A property"
                  " with name=%(name)s already exists in"
                  " namespace=%(namespace_name)s.",
                  {'name': property_rec.name,
                   'namespace_name': namespace_name})
        raise exc.MetadefDuplicateProperty(
            property_name=property_rec.name,
            namespace_name=namespace_name)

    return property_rec.to_dict()


def update(context, session, namespace_name, property_id, values):
    """Update a property, raise if ns not found/visible or duplicate result"""

    namespace_api.get(context, session, namespace_name)
    property_rec = _get(context, session, property_id)
    metadef_utils.drop_protected_attrs(models.MetadefProperty, values)
    # values['updated_at'] = timeutils.utcnow() - done by TS mixin
    try:
        property_rec.update(values.copy())
        property_rec.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Invalid update. It would result in a duplicate"
                  " metadata definition property with the same name=%(name)s"
                  " in namespace=%(namespace_name)s.",
                  {'name': property_rec.name,
                   'namespace_name': namespace_name})
        emsg = (_("Invalid update. It would result in a duplicate"
                  " metadata definition property with the same name=%(name)s"
                  " in namespace=%(namespace_name)s.")
                % {'name': property_rec.name,
                   'namespace_name': namespace_name})
        raise exc.MetadefDuplicateProperty(emsg)

    return property_rec.to_dict()


def delete(context, session, namespace_name, property_name):
    property_rec = _get_by_name(
        context, session, namespace_name, property_name)
    if property_rec:
        session.delete(property_rec)
        session.flush()

    return property_rec.to_dict()


def delete_namespace_content(context, session, namespace_id):
    """Use this def only if the ns for the id has been verified as visible"""

    count = 0
    query = session.query(models.MetadefProperty).filter_by(
        namespace_id=namespace_id)
    count = query.delete(synchronize_session='fetch')
    return count


def delete_by_namespace_name(context, session, namespace_name):
    namespace = namespace_api.get(context, session, namespace_name)
    return delete_namespace_content(context, session, namespace['id'])


def count(context, session, namespace_name):
    """Get the count of properties for a namespace, raise if ns not found"""

    namespace = namespace_api.get(context, session, namespace_name)

    query = session.query(func.count(models.MetadefProperty.id)).filter_by(
        namespace_id=namespace['id'])
    return query.scalar()
