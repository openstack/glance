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
from oslo_db.sqlalchemy.utils import paginate_query
from oslo_log import log as logging
import sqlalchemy.exc as sa_exc
from sqlalchemy import or_
import sqlalchemy.orm as sa_orm

from glance.common import exception as exc
import glance.db.sqlalchemy.metadef_api as metadef_api
from glance.db.sqlalchemy import models_metadef as models
from glance.i18n import _

LOG = logging.getLogger(__name__)


def _is_namespace_visible(context, namespace, status=None):
    """Return True if the namespace is visible in this context."""

    # Is admin == visible
    if context.is_admin:
        return True

    # No owner == visible
    if namespace['owner'] is None:
        return True

    # Is public == visible
    if 'visibility' in namespace:
        if namespace['visibility'] == 'public':
            return True

    # context.owner has a value and is the namespace owner == visible
    if context.owner is not None:
        if context.owner == namespace['owner']:
            return True

    # Private
    return False


def _select_namespaces_query(context, session):
    """Build the query to get all namespaces based on the context"""

    LOG.debug("context.is_admin=%(is_admin)s; context.owner=%(owner)s",
              {'is_admin': context.is_admin, 'owner': context.owner})

    # If admin, return everything.
    query_ns = session.query(models.MetadefNamespace)
    if context.is_admin:
        return query_ns
    else:
        # If regular user, return only public namespaces.
        # However, if context.owner has a value, return both
        # public and private namespaces of the context.owner.
        if context.owner is not None:
            query = (
                query_ns.filter(
                    or_(models.MetadefNamespace.owner == context.owner,
                        models.MetadefNamespace.visibility == 'public')))
        else:
            query = query_ns.filter(
                models.MetadefNamespace.visibility == 'public')
        return query


def _get(context, namespace_id, session):
    """Get a namespace by id, raise if not found"""

    try:
        query = session.query(models.MetadefNamespace).filter_by(
            id=namespace_id)
        namespace_rec = query.one()
    except sa_orm.exc.NoResultFound:
        msg = (_("Metadata definition namespace not found for id=%s")
               % namespace_id)
        LOG.warn(msg)
        raise exc.MetadefNamespaceNotFound(msg)

    # Make sure they are allowed to view it.
    if not _is_namespace_visible(context, namespace_rec.to_dict()):
        LOG.debug("Forbidding request, metadata definition namespace=%s"
                  " is not visible.", namespace_rec.namespace)
        emsg = _("Forbidding request, metadata definition namespace=%s"
                 " is not visible.") % namespace_rec.namespace
        raise exc.MetadefForbidden(emsg)

    return namespace_rec


def _get_by_name(context, name, session):
    """Get a namespace by name, raise if not found"""

    try:
        query = session.query(models.MetadefNamespace).filter_by(
            namespace=name)
        namespace_rec = query.one()
    except sa_orm.exc.NoResultFound:
        LOG.debug("Metadata definition namespace=%s was not found.", name)
        raise exc.MetadefNamespaceNotFound(namespace_name=name)

    # Make sure they are allowed to view it.
    if not _is_namespace_visible(context, namespace_rec.to_dict()):
        LOG.debug("Forbidding request, metadata definition namespace=%s"
                  " is not visible.", name)
        emsg = _("Forbidding request, metadata definition namespace=%s"
                 " is not visible.") % name
        raise exc.MetadefForbidden(emsg)

    return namespace_rec


def _get_all(context, session, filters=None, marker=None,
             limit=None, sort_key='created_at', sort_dir='desc'):
    """Get all namespaces that match zero or more filters.

    :param filters: dict of filter keys and values.
    :param marker: namespace id after which to start page
    :param limit: maximum number of namespaces to return
    :param sort_key: namespace attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    """

    filters = filters or {}

    query = _select_namespaces_query(context, session)

    # if visibility filter, apply it to the context based query
    visibility = filters.pop('visibility', None)
    if visibility is not None:
        query = query.filter(models.MetadefNamespace.visibility == visibility)

    # if id_list filter, apply it to the context based query
    id_list = filters.pop('id_list', None)
    if id_list is not None:
        query = query.filter(models.MetadefNamespace.id.in_(id_list))

    marker_namespace = None
    if marker is not None:
        marker_namespace = _get(context, marker, session)

    sort_keys = ['created_at', 'id']
    sort_keys.insert(0, sort_key) if sort_key not in sort_keys else sort_keys

    query = paginate_query(query=query,
                           model=models.MetadefNamespace,
                           limit=limit,
                           sort_keys=sort_keys,
                           marker=marker_namespace, sort_dir=sort_dir)

    return query.all()


def _get_all_by_resource_types(context, session, filters, marker=None,
                               limit=None, sort_key=None, sort_dir=None):
    """get all visible namespaces for the specified resource_types"""

    resource_types = filters['resource_types']
    resource_type_list = resource_types.split(',')
    db_recs = (
        session.query(models.MetadefResourceType)
        .join(models.MetadefResourceType.associations)
        .filter(models.MetadefResourceType.name.in_(resource_type_list))
        .values(models.MetadefResourceType.name,
                models.MetadefNamespaceResourceType.namespace_id)
    )

    namespace_id_list = []
    for name, namespace_id in db_recs:
        namespace_id_list.append(namespace_id)

    if len(namespace_id_list) == 0:
        return []

    filters2 = filters
    filters2.update({'id_list': namespace_id_list})

    return _get_all(context, session, filters2,
                    marker, limit, sort_key, sort_dir)


def get_all(context, session, marker=None, limit=None,
            sort_key=None, sort_dir=None, filters=None):
    """List all visible namespaces"""

    namespaces = []
    filters = filters or {}

    if 'resource_types' in filters:
        namespaces = _get_all_by_resource_types(
            context, session, filters, marker, limit, sort_key, sort_dir)
    else:
        namespaces = _get_all(
            context, session, filters, marker, limit, sort_key, sort_dir)

    return [ns.to_dict() for ns in namespaces]


def get(context, name, session):
    """Get a namespace by name, raise if not found"""
    namespace_rec = _get_by_name(context, name, session)
    return namespace_rec.to_dict()


def create(context, values, session):
    """Create a namespace, raise if namespace already exists."""

    namespace_name = values['namespace']
    namespace = models.MetadefNamespace()
    metadef_api.utils.drop_protected_attrs(models.MetadefNamespace, values)
    namespace.update(values.copy())
    try:
        namespace.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Can not create the metadata definition namespace."
                  " Namespace=%s already exists.", namespace_name)
        raise exc.MetadefDuplicateNamespace(
            namespace_name=namespace_name)

    return namespace.to_dict()


def update(context, namespace_id, values, session):
    """Update a namespace, raise if not found/visible or duplicate result"""

    namespace_rec = _get(context, namespace_id, session)
    metadef_api.utils.drop_protected_attrs(models.MetadefNamespace, values)

    try:
        namespace_rec.update(values.copy())
        namespace_rec.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Invalid update. It would result in a duplicate"
                  " metadata definition namespace with the same name of %s",
                  values['namespace'])
        emsg = (_("Invalid update. It would result in a duplicate"
                  " metadata definition namespace with the same name of %s")
                % values['namespace'])
        raise exc.MetadefDuplicateNamespace(emsg)

    return namespace_rec.to_dict()


def delete(context, name, session):
    """Raise if not found, has references or not visible"""

    namespace_rec = _get_by_name(context, name, session)
    try:
        session.delete(namespace_rec)
        session.flush()
    except db_exc.DBError as e:
        if isinstance(e.inner_exception, sa_exc.IntegrityError):
            LOG.debug("Metadata definition namespace=%s not deleted. "
                      "Other records still refer to it.", name)
            raise exc.MetadefIntegrityError(
                record_type='namespace', record_name=name)
        else:
            raise

    return namespace_rec.to_dict()


def delete_cascade(context, name, session):
    """Raise if not found, has references or not visible"""

    namespace_rec = _get_by_name(context, name, session)
    with session.begin():
        try:
            metadef_api.tag.delete_namespace_content(
                context, namespace_rec.id, session)
            metadef_api.object.delete_namespace_content(
                context, namespace_rec.id, session)
            metadef_api.property.delete_namespace_content(
                context, namespace_rec.id, session)
            metadef_api.resource_type_association.delete_namespace_content(
                context, namespace_rec.id, session)
            session.delete(namespace_rec)
            session.flush()
        except db_exc.DBError as e:
            if isinstance(e.inner_exception, sa_exc.IntegrityError):
                LOG.debug("Metadata definition namespace=%s not deleted. "
                          "Other records still refer to it.", name)
                raise exc.MetadefIntegrityError(
                    record_type='namespace', record_name=name)
            else:
                raise

    return namespace_rec.to_dict()
