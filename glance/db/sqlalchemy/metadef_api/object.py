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
import glance.db.sqlalchemy.metadef_api.utils as metadef_utils
from glance.db.sqlalchemy import models_metadef as models
from glance.i18n import _

LOG = logging.getLogger(__name__)


def _get(context, session, object_id):
    try:
        query = session.query(models.MetadefObject).filter_by(id=object_id)
        metadef_object = query.one()
    except sa_orm.exc.NoResultFound:
        msg = (_("Metadata definition object not found for id=%s")
               % object_id)
        LOG.warning(msg)
        raise exc.MetadefObjectNotFound(msg)

    return metadef_object


def _get_by_name(context, session, namespace_name, name):
    namespace = namespace_api.get(context, session, namespace_name)
    try:
        query = session.query(models.MetadefObject).filter_by(
            name=name, namespace_id=namespace['id'])
        metadef_object = query.one()
    except sa_orm.exc.NoResultFound:
        LOG.debug("The metadata definition object with name=%(name)s"
                  " was not found in namespace=%(namespace_name)s.",
                  {'name': name, 'namespace_name': namespace_name})
        raise exc.MetadefObjectNotFound(object_name=name,
                                        namespace_name=namespace_name)

    return metadef_object


def get_all(context, session, namespace_name):
    namespace = namespace_api.get(context, session, namespace_name)
    query = session.query(models.MetadefObject).filter_by(
        namespace_id=namespace['id'])
    md_objects = query.all()

    md_objects_list = []
    for obj in md_objects:
        md_objects_list.append(obj.to_dict())
    return md_objects_list


def create(context, session, namespace_name, values):
    namespace = namespace_api.get(context, session, namespace_name)
    values.update({'namespace_id': namespace['id']})

    md_object = models.MetadefObject()
    metadef_utils.drop_protected_attrs(models.MetadefObject, values)
    md_object.update(values.copy())
    try:
        md_object.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("A metadata definition object with name=%(name)s"
                  " in namespace=%(namespace_name)s already exists.",
                  {'name': md_object.name,
                   'namespace_name': namespace_name})
        raise exc.MetadefDuplicateObject(
            object_name=md_object.name, namespace_name=namespace_name)

    return md_object.to_dict()


def get(context, session, namespace_name, name):
    md_object = _get_by_name(context, session, namespace_name, name)

    return md_object.to_dict()


def update(context, session, namespace_name, object_id, values):
    """Update an object, raise if ns not found/visible or duplicate result"""
    namespace_api.get(context, session, namespace_name)

    md_object = _get(context, session, object_id)
    metadef_utils.drop_protected_attrs(models.MetadefObject, values)
    # values['updated_at'] = timeutils.utcnow() - done by TS mixin
    try:
        md_object.update(values.copy())
        md_object.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Invalid update. It would result in a duplicate"
                  " metadata definition object with same name=%(name)s"
                  " in namespace=%(namespace_name)s.",
                  {'name': md_object.name, 'namespace_name': namespace_name})
        emsg = (_("Invalid update. It would result in a duplicate"
                  " metadata definition object with the same name=%(name)s"
                  " in namespace=%(namespace_name)s.")
                % {'name': md_object.name, 'namespace_name': namespace_name})
        raise exc.MetadefDuplicateObject(emsg)

    return md_object.to_dict()


def delete(context, session, namespace_name, object_name):
    namespace_api.get(context, session, namespace_name)
    md_object = _get_by_name(context, session, namespace_name, object_name)

    session.delete(md_object)
    session.flush()

    return md_object.to_dict()


def delete_namespace_content(context, session, namespace_id):
    """Use this def only if the ns for the id has been verified as visible"""

    count = 0
    query = session.query(models.MetadefObject).filter_by(
        namespace_id=namespace_id)
    count = query.delete(synchronize_session='fetch')
    return count


def delete_by_namespace_name(context, session, namespace_name):
    namespace = namespace_api.get(context, session, namespace_name)
    return delete_namespace_content(context, session, namespace['id'])


def count(context, session, namespace_name):
    """Get the count of objects for a namespace, raise if ns not found"""
    namespace = namespace_api.get(context, session, namespace_name)

    query = session.query(func.count(models.MetadefObject.id)).filter_by(
        namespace_id=namespace['id'])
    return query.scalar()
