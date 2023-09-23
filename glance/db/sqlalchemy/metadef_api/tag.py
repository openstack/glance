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
from sqlalchemy import func
import sqlalchemy.orm as sa_orm

from glance.common import exception as exc
from glance.db.sqlalchemy.metadef_api import namespace as namespace_api
import glance.db.sqlalchemy.metadef_api.utils as metadef_utils
from glance.db.sqlalchemy import models_metadef as models
from glance.i18n import _LW

LOG = logging.getLogger(__name__)


def _get(context, session, id):
    try:
        query = (session.query(models.MetadefTag).filter_by(id=id))
        metadef_tag = query.one()
    except sa_orm.exc.NoResultFound:
        msg = (_LW("Metadata tag not found for id %s") % id)
        LOG.warning(msg)
        raise exc.MetadefTagNotFound(message=msg)
    return metadef_tag


def _get_by_name(context, session, namespace_name, name):
    namespace = namespace_api.get(context, session, namespace_name)
    try:
        query = (session.query(models.MetadefTag).filter_by(
            name=name, namespace_id=namespace['id']))
        metadef_tag = query.one()
    except sa_orm.exc.NoResultFound:
        LOG.debug("The metadata tag with name=%(name)s"
                  " was not found in namespace=%(namespace_name)s.",
                  {'name': name, 'namespace_name': namespace_name})
        raise exc.MetadefTagNotFound(name=name,
                                     namespace_name=namespace_name)
    return metadef_tag


def get_all(context, session, namespace_name, filters=None, marker=None,
            limit=None, sort_key='created_at', sort_dir='desc'):
    """Get all tags that match zero or more filters.

    :param filters: dict of filter keys and values.
    :param marker: tag id after which to start page
    :param limit: maximum number of namespaces to return
    :param sort_key: namespace attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    """

    namespace = namespace_api.get(context, session, namespace_name)
    query = (session.query(models.MetadefTag).filter_by(
        namespace_id=namespace['id']))

    marker_tag = None
    if marker is not None:
        marker_tag = _get(context, session, marker)

    sort_keys = ['created_at', 'id']
    sort_keys.insert(0, sort_key) if sort_key not in sort_keys else sort_keys

    query = paginate_query(query=query,
                           model=models.MetadefTag,
                           limit=limit,
                           sort_keys=sort_keys,
                           marker=marker_tag, sort_dir=sort_dir)
    metadef_tag = query.all()
    metadef_tag_list = []
    for tag in metadef_tag:
        metadef_tag_list.append(tag.to_dict())

    return metadef_tag_list


def create(context, session, namespace_name, values):
    namespace = namespace_api.get(context, session, namespace_name)
    values.update({'namespace_id': namespace['id']})

    metadef_tag = models.MetadefTag()
    metadef_utils.drop_protected_attrs(models.MetadefTag, values)
    metadef_tag.update(values.copy())
    try:
        metadef_tag.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("A metadata tag name=%(name)s"
                  " already exists in namespace=%(namespace_name)s."
                  " (Please note that metadata tag names are"
                  " case insensitive).",
                  {'name': metadef_tag.name,
                   'namespace_name': namespace_name})
        raise exc.MetadefDuplicateTag(
            name=metadef_tag.name, namespace_name=namespace_name)

    return metadef_tag.to_dict()


def create_tags(context, session, namespace_name, tag_list, can_append):

    metadef_tags_list = []
    if tag_list:
        namespace = namespace_api.get(context, session, namespace_name)

        try:
            if not can_append:
                query = (session.query(models.MetadefTag).filter_by(
                         namespace_id=namespace['id']))
                query.delete(synchronize_session='fetch')
            for value in tag_list:
                value.update({'namespace_id': namespace['id']})
                metadef_utils.drop_protected_attrs(
                    models.MetadefTag, value)
                metadef_tag = models.MetadefTag()
                metadef_tag.update(value.copy())
                metadef_tag.save(session=session)
                metadef_tags_list.append(metadef_tag.to_dict())
        except db_exc.DBDuplicateEntry:
            LOG.debug("A metadata tag name=%(name)s"
                      " in namespace=%(namespace_name)s already exists.",
                      {'name': metadef_tag.name,
                       'namespace_name': namespace_name})
            raise exc.MetadefDuplicateTag(
                name=metadef_tag.name, namespace_name=namespace_name)

    return metadef_tags_list


def get(context, session, namespace_name, name):
    metadef_tag = _get_by_name(context, session, namespace_name, name)
    return metadef_tag.to_dict()


def update(context, session, namespace_name, id, values):
    """Update an tag, raise if ns not found/visible or duplicate result"""
    namespace_api.get(context, session, namespace_name)

    metadata_tag = _get(context, session, id)
    metadef_utils.drop_protected_attrs(models.MetadefTag, values)
    # values['updated_at'] = timeutils.utcnow() - done by TS mixin
    try:
        metadata_tag.update(values.copy())
        metadata_tag.save(session=session)
    except db_exc.DBDuplicateEntry:
        LOG.debug("Invalid update. It would result in a duplicate"
                  " metadata tag with same name=%(name)s"
                  " in namespace=%(namespace_name)s.",
                  {'name': values['name'],
                   'namespace_name': namespace_name})
        raise exc.MetadefDuplicateTag(
            name=values['name'], namespace_name=namespace_name)

    return metadata_tag.to_dict()


def delete(context, session, namespace_name, name):
    namespace_api.get(context, session, namespace_name)
    md_tag = _get_by_name(context, session, namespace_name, name)

    session.delete(md_tag)
    session.flush()

    return md_tag.to_dict()


def delete_namespace_content(context, session, namespace_id):
    """Use this def only if the ns for the id has been verified as visible"""
    count = 0
    query = (session.query(models.MetadefTag).filter_by(
        namespace_id=namespace_id))
    count = query.delete(synchronize_session='fetch')
    return count


def delete_by_namespace_name(context, session, namespace_name):
    namespace = namespace_api.get(context, session, namespace_name)
    return delete_namespace_content(context, session, namespace['id'])


def count(context, session, namespace_name):
    """Get the count of objects for a namespace, raise if ns not found"""
    namespace = namespace_api.get(context, session, namespace_name)
    query = (session.query(func.count(models.MetadefTag.id)).filter_by(
        namespace_id=namespace['id']))
    return query.scalar()
