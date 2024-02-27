# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack Foundation
# Copyright 2012 Justin Santa Barbara
# Copyright 2013 IBM Corp.
# Copyright 2015 Mirantis, Inc.
# All Rights Reserved.
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


"""Defines interface for DB access."""

import datetime
import itertools
import threading

from oslo_config import cfg
from oslo_db import exception as db_exception
from oslo_db.sqlalchemy import session as oslo_db_session
from oslo_log import log as logging
from oslo_utils import excutils
import osprofiler.sqlalchemy
from retrying import retry
import sqlalchemy
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import MetaData, Table
import sqlalchemy.orm as sa_orm
from sqlalchemy import sql
import sqlalchemy.sql as sa_sql

from glance.common import exception
from glance.common import timeutils
from glance.common import utils
from glance.db.sqlalchemy.metadef_api import (resource_type
                                              as metadef_resource_type_api)
from glance.db.sqlalchemy.metadef_api import (resource_type_association
                                              as metadef_association_api)
from glance.db.sqlalchemy.metadef_api import namespace as metadef_namespace_api
from glance.db.sqlalchemy.metadef_api import object as metadef_object_api
from glance.db.sqlalchemy.metadef_api import property as metadef_property_api
from glance.db.sqlalchemy.metadef_api import tag as metadef_tag_api
from glance.db.sqlalchemy import models
from glance.db import utils as db_utils
from glance.i18n import _, _LW, _LI, _LE

sa_logger = None
LOG = logging.getLogger(__name__)


STATUSES = ['active', 'saving', 'queued', 'killed', 'pending_delete',
            'deleted', 'deactivated', 'importing', 'uploading']

CONF = cfg.CONF
CONF.import_group("profiler", "glance.common.wsgi")

_FACADE = None
_LOCK = threading.Lock()


def _retry_on_deadlock(exc):
    """Decorator to retry a DB API call if Deadlock was received."""

    if isinstance(exc, db_exception.DBDeadlock):
        LOG.warning(_LW("Deadlock detected. Retrying..."))
        return True
    return False


def _create_facade_lazily():
    global _LOCK, _FACADE
    if _FACADE is None:
        with _LOCK:
            if _FACADE is None:
                _FACADE = oslo_db_session.EngineFacade.from_config(
                    CONF,
                    sqlite_fk=True,
                )

                if CONF.profiler.enabled and CONF.profiler.trace_sqlalchemy:
                    osprofiler.sqlalchemy.add_tracing(sqlalchemy,
                                                      _FACADE.get_engine(),
                                                      "db")
    return _FACADE


def get_engine():
    facade = _create_facade_lazily()
    return facade.get_engine()


def get_session(expire_on_commit=False):
    facade = _create_facade_lazily()
    return facade.get_session(autocommit=False,
                              expire_on_commit=expire_on_commit)


def _validate_db_int(**kwargs):
    """Make sure that all arguments are less than or equal to 2 ** 31 - 1.

    This limitation is introduced because databases stores INT in 4 bytes.
    If the validation fails for some argument, exception.Invalid is raised with
    appropriate information.
    """
    max_int = (2 ** 31) - 1

    for param_key, param_value in kwargs.items():
        if param_value and param_value > max_int:
            msg = _("'%(param)s' value out of range, "
                    "must not exceed %(max)d.") % {"param": param_key,
                                                   "max": max_int}
            raise exception.Invalid(msg)


def clear_db_env():
    """
    Unset global configuration variables for database.
    """
    global _FACADE
    _FACADE = None


def _check_mutate_authorization(context, image_ref):
    if not is_image_mutable(context, image_ref):
        LOG.warning(_LW("Attempted to modify image user did not own."))
        msg = _("You do not own this image")
        if image_ref.visibility in ['private', 'shared']:
            exc_class = exception.Forbidden
        else:
            # 'public', or 'community'
            exc_class = exception.ForbiddenPublicImage

        raise exc_class(msg)


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def image_create(context, values, v1_mode=False):
    """Create an image from the values dictionary."""
    session = get_session()
    with session.begin():
        image_ref = _image_update(
            context, session, None, values, purge_props=False)

    session.expire_all()

    with session.begin():
        image = _image_get(context, session, image_ref.id)
        image = _normalize_locations(context, image.to_dict())

    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def image_update(context, image_id, values, purge_props=False,
                 from_state=None, v1_mode=False, atomic_props=None):
    """
    Set the given properties on an image and update it.

    :raises: ImageNotFound if image does not exist.
    """
    session = get_session()
    with session.begin():
        image_ref = _image_update(
            context, session, image_id, values, purge_props,
            from_state=from_state, atomic_props=atomic_props)

    session.expire_all()

    with session.begin():
        image = _image_get(context, session, image_ref.id)

    image = _normalize_locations(context, image.to_dict())

    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


def image_restore(context, image_id):
    """Restore the pending-delete image to active."""
    session = get_session()
    with session.begin():
        image_ref = _image_get(context, session, image_id)
        if image_ref.status != 'pending_delete':
            msg = (_('cannot restore the image from %s to active (wanted '
                     'from_state=pending_delete)') % image_ref.status)
            raise exception.Conflict(msg)

        query = session.query(models.Image).filter_by(id=image_id)
        values = {'status': 'active', 'deleted': 0}
        query.update(values, synchronize_session='fetch')


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    session = get_session()
    with session.begin():
        image_ref = _image_get(context, session, image_id)

        # Perform authorization check
        _check_mutate_authorization(context, image_ref)

        image_ref.delete(session=session)
        delete_time = image_ref.deleted_at

        _image_locations_delete_all(context, session, image_id, delete_time)

        _image_property_delete_all(context, session, image_id, delete_time)

        _image_member_delete_all(context, session, image_id, delete_time)

        _image_tag_delete_all(context, session, image_id, delete_time)

    return _normalize_locations(context, image_ref.to_dict())


def _normalize_locations(context, image, force_show_deleted=False):
    """
    Generate suitable dictionary list for locations field of image.

    We don't need to set other data fields of location record which return
    from image query.
    """

    if image['status'] == 'deactivated' and not context.is_admin:
        # Locations are not returned for a deactivated image for non-admin user
        image['locations'] = []
        return image

    if force_show_deleted:
        locations = image['locations']
    else:
        locations = [x for x in image['locations'] if not x.deleted]
    image['locations'] = [{'id': loc['id'],
                           'url': loc['value'],
                           'metadata': loc['meta_data'],
                           'status': loc['status']}
                          for loc in locations]
    return image


def _normalize_tags(image):
    undeleted_tags = [x for x in image['tags'] if not x.deleted]
    image['tags'] = [tag['value'] for tag in undeleted_tags]
    return image


def image_get(context, image_id, force_show_deleted=False, v1_mode=False):
    session = get_session()
    with session.begin():
        image = _image_get(context, session, image_id,
                           force_show_deleted=force_show_deleted)
    image = _normalize_locations(context, image.to_dict(),
                                 force_show_deleted=force_show_deleted)
    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


def _check_image_id(image_id):
    """
    check if the given image id is valid before executing operations. For
    now, we only check its length. The original purpose of this method is
    wrapping the different behaviors between MySql and DB2 when the image id
    length is longer than the defined length in database model.
    :param image_id: The id of the image we want to check
    :returns: Raise NoFound exception if given image id is invalid
    """
    if (image_id and
       len(image_id) > models.Image.id.property.columns[0].type.length):
        raise exception.ImageNotFound()


def _image_get(context, session, image_id, force_show_deleted=False):
    """Get an image or raise if it does not exist."""
    _check_image_id(image_id)

    try:
        query = session.query(models.Image).options(
            sa_orm.joinedload(models.Image.properties)).options(
                sa_orm.joinedload(
                    models.Image.locations)).filter_by(id=image_id)

        # filter out deleted images if context disallows it
        if not force_show_deleted and not context.can_see_deleted:
            query = query.filter_by(deleted=False)

        image = query.one()

    except sa_orm.exc.NoResultFound:
        msg = "No image found with ID %s" % image_id
        LOG.debug(msg)
        raise exception.ImageNotFound(msg)

    # Make sure they can look at it
    if not is_image_visible(context, image):
        msg = "Forbidding request, image %s not visible" % image_id
        LOG.debug(msg)
        raise exception.Forbidden(msg)

    return image


def is_image_mutable(context, image):
    """Return True if the image is mutable in this context."""
    # Is admin == image mutable
    if context.is_admin:
        return True

    # No owner == image not mutable
    if image['owner'] is None or context.owner is None:
        return False

    # Image only mutable by its owner
    return image['owner'] == context.owner


def is_image_visible(context, image, status=None):
    """Return True if the image is visible in this context."""
    return db_utils.is_image_visible(context, image, image_member_find, status)


def _get_default_column_value(column_type):
    """Return the default value of the columns from DB table

    In postgreDB case, if no right default values are being set, an
    psycopg2.DataError will be thrown.
    """
    type_schema = {
        'datetime': None,
        'big_integer': 0,
        'integer': 0,
        'string': ''
    }

    if isinstance(column_type, sa_sql.type_api.Variant):
        return _get_default_column_value(column_type.impl)

    return type_schema[column_type.__visit_name__]


def _paginate_query(query, model, limit, sort_keys, marker=None,
                    sort_dir=None, sort_dirs=None):
    """Returns a query with sorting / pagination criteria added.

    Pagination works by requiring a unique sort_key, specified by sort_keys.
    (If sort_keys is not unique, then we risk looping through values.)
    We use the last row in the previous page as the 'marker' for pagination.
    So we must return values that follow the passed marker in the order.
    With a single-valued sort_key, this would be easy: sort_key > X.
    With a compound-values sort_key, (k1, k2, k3) we must do this to repeat
    the lexicographical ordering:
    (k1 > X1) or (k1 == X1 && k2 > X2) or (k1 == X1 && k2 == X2 && k3 > X3)

    We also have to cope with different sort_directions.

    Typically, the id of the last row is used as the client-facing pagination
    marker, then the actual marker object must be fetched from the db and
    passed in to us as marker.

    :param query: the query object to which we should add paging/sorting
    :param model: the ORM model class
    :param limit: maximum number of items to return
    :param sort_keys: array of attributes by which results should be sorted
    :param marker: the last item of the previous page; we returns the next
                    results after this value.
    :param sort_dir: direction in which results should be sorted (asc, desc)
    :param sort_dirs: per-column array of sort_dirs, corresponding to sort_keys

    :rtype: sqlalchemy.orm.query.Query
    :returns: The query with sorting/pagination added.
    """

    if 'id' not in sort_keys:
        # TODO(justinsb): If this ever gives a false-positive, check
        # the actual primary key, rather than assuming its id
        LOG.warning(_LW('Id not in sort_keys; is sort_keys unique?'))

    assert (not (sort_dir and sort_dirs))  # nosec
    # nosec: This function runs safely if the assertion fails.

    # Default the sort direction to ascending
    if sort_dir is None:
        sort_dir = 'asc'

    # Ensure a per-column sort direction
    if sort_dirs is None:
        sort_dirs = [sort_dir] * len(sort_keys)

    assert (len(sort_dirs) == len(sort_keys))  # nosec
    # nosec: This function runs safely if the assertion fails.
    if len(sort_dirs) < len(sort_keys):
        sort_dirs += [sort_dir] * (len(sort_keys) - len(sort_dirs))

    # Add sorting
    for current_sort_key, current_sort_dir in zip(sort_keys, sort_dirs):
        sort_dir_func = {
            'asc': sqlalchemy.asc,
            'desc': sqlalchemy.desc,
        }[current_sort_dir]

        try:
            sort_key_attr = getattr(model, current_sort_key)
        except AttributeError:
            raise exception.InvalidSortKey()
        query = query.order_by(sort_dir_func(sort_key_attr))

    default = ''  # Default to an empty string if NULL

    # Add pagination
    if marker is not None:
        marker_values = []
        for sort_key in sort_keys:
            v = getattr(marker, sort_key)
            if v is None:
                v = default
            marker_values.append(v)

        # Build up an array of sort criteria as in the docstring
        criteria_list = []
        for i in range(len(sort_keys)):
            crit_attrs = []
            for j in range(i):
                model_attr = getattr(model, sort_keys[j])
                default = _get_default_column_value(
                    model_attr.property.columns[0].type)
                attr = sa_sql.expression.case(
                    (model_attr != None, model_attr),
                    else_=default)
                crit_attrs.append((attr == marker_values[j]))

            model_attr = getattr(model, sort_keys[i])
            default = _get_default_column_value(
                model_attr.property.columns[0].type)
            attr = sa_sql.expression.case(
                (model_attr != None, model_attr),
                else_=default)
            if sort_dirs[i] == 'desc':
                crit_attrs.append((attr < marker_values[i]))
            elif sort_dirs[i] == 'asc':
                crit_attrs.append((attr > marker_values[i]))
            else:
                raise ValueError(_("Unknown sort direction, "
                                   "must be 'desc' or 'asc'"))

            criteria = sa_sql.and_(*crit_attrs)
            criteria_list.append(criteria)

        f = sa_sql.or_(*criteria_list)
        query = query.filter(f)

    if limit is not None:
        query = query.limit(limit)

    return query


def _make_conditions_from_filters(filters, is_public=None):
    # NOTE(venkatesh) make copy of the filters are to be altered in this
    # method.
    filters = filters.copy()

    image_conditions = []
    prop_conditions = []
    tag_conditions = []

    if is_public is not None:
        if is_public:
            image_conditions.append(models.Image.visibility == 'public')
        else:
            image_conditions.append(models.Image.visibility != 'public')

    if 'os_hidden' in filters:
        os_hidden = filters.pop('os_hidden')
        image_conditions.append(models.Image.os_hidden == os_hidden)

    if 'checksum' in filters:
        checksum = filters.pop('checksum')
        image_conditions.append(models.Image.checksum == checksum)

    if 'os_hash_value' in filters:
        os_hash_value = filters.pop('os_hash_value')
        image_conditions.append(models.Image.os_hash_value == os_hash_value)

    for (k, v) in filters.pop('properties', {}).items():
        prop_filters = _make_image_property_condition(key=k, value=v)
        prop_conditions.append(prop_filters)

    if 'changes-since' in filters:
        # normalize timestamp to UTC, as sqlalchemy doesn't appear to
        # respect timezone offsets
        changes_since = timeutils.normalize_time(filters.pop('changes-since'))
        image_conditions.append(models.Image.updated_at > changes_since)

    if 'deleted' in filters:
        deleted_filter = filters.pop('deleted')
        image_conditions.append(models.Image.deleted == deleted_filter)
        # TODO(bcwaldon): handle this logic in registry server
        if not deleted_filter:
            image_statuses = [s for s in STATUSES if s != 'killed']
            image_conditions.append(models.Image.status.in_(image_statuses))

    if 'tags' in filters:
        tags = filters.pop('tags')
        for tag in tags:
            alias = sa_orm.aliased(models.ImageTag)
            tag_filters = [alias.deleted == False]
            tag_filters.extend([alias.value == tag])
            tag_conditions.append((alias, tag_filters))

    filters = {k: v for k, v in filters.items() if v is not None}

    # need to copy items because filters is modified in the loop body
    # (filters.pop(k))
    keys = list(filters.keys())
    for k in keys:
        key = k
        if k.endswith('_min') or k.endswith('_max'):
            key = key[0:-4]
            try:
                v = int(filters.pop(k))
            except ValueError:
                msg = _("Unable to filter on a range "
                        "with a non-numeric value.")
                raise exception.InvalidFilterRangeValue(msg)

            if k.endswith('_min'):
                image_conditions.append(getattr(models.Image, key) >= v)
            if k.endswith('_max'):
                image_conditions.append(getattr(models.Image, key) <= v)
        elif k in ['created_at', 'updated_at']:
            attr_value = getattr(models.Image, key)
            operator, isotime = utils.split_filter_op(filters.pop(k))
            try:
                parsed_time = timeutils.parse_isotime(isotime)
                threshold = timeutils.normalize_time(parsed_time)
            except ValueError:
                msg = (_("Bad \"%s\" query filter format. "
                         "Use ISO 8601 DateTime notation.") % k)
                raise exception.InvalidParameterValue(msg)

            comparison = utils.evaluate_filter_op(attr_value, operator,
                                                  threshold)
            image_conditions.append(comparison)

        elif k in ['name', 'id', 'status', 'container_format', 'disk_format']:
            attr_value = getattr(models.Image, key)
            operator, list_value = utils.split_filter_op(filters.pop(k))
            if operator == 'in':
                threshold = utils.split_filter_value_for_quotes(list_value)
                comparison = attr_value.in_(threshold)
                image_conditions.append(comparison)
            elif operator == 'eq':
                image_conditions.append(attr_value == list_value)
            else:
                msg = (_("Unable to filter by unknown operator '%s'.")
                       % operator)
                raise exception.InvalidFilterOperatorValue(msg)

    for (k, value) in filters.items():
        if hasattr(models.Image, k):
            image_conditions.append(getattr(models.Image, k) == value)
        else:
            prop_filters = _make_image_property_condition(key=k, value=value)
            prop_conditions.append(prop_filters)

    return image_conditions, prop_conditions, tag_conditions


def _make_image_property_condition(key, value):
    alias = sa_orm.aliased(models.ImageProperty)
    prop_filters = [alias.deleted == False]
    prop_filters.extend([alias.name == key])
    prop_filters.extend([alias.value == value])
    return alias, prop_filters


def _select_images_query(context, session, image_conditions, admin_as_user,
                         member_status, visibility):
    img_conditional_clause = sa_sql.and_(True, *image_conditions)

    regular_user = (not context.is_admin) or admin_as_user

    query_member = session.query(models.Image).join(
        models.Image.members).filter(img_conditional_clause)
    if regular_user:
        member_filters = [models.ImageMember.deleted == False]
        member_filters.extend([models.Image.visibility == 'shared'])
        if context.owner is not None:
            member_filters.extend([models.ImageMember.member == context.owner])
            if member_status != 'all':
                member_filters.extend([
                    models.ImageMember.status == member_status])
        query_member = query_member.filter(sa_sql.and_(*member_filters))

    query_image = session.query(models.Image).filter(img_conditional_clause)
    if regular_user:
        visibility_filters = [
            models.Image.visibility == 'public',
            models.Image.visibility == 'community',
        ]
        query_image = query_image .filter(sa_sql.or_(*visibility_filters))
        query_image_owner = None
        if context.owner is not None:
            query_image_owner = session.query(models.Image).filter(
                models.Image.owner == context.owner).filter(
                    img_conditional_clause)
        if query_image_owner is not None:
            query = query_image.union(query_image_owner, query_member)
        else:
            query = query_image.union(query_member)
        return query
    else:
        # Admin user
        return query_image


def image_get_all(
    context, filters=None, marker=None, limit=None,
    sort_key=None, sort_dir=None,
    member_status='accepted', is_public=None,
    admin_as_user=False, return_tag=False, v1_mode=False,
):
    """
    Get all images that match zero or more filters.

    :param filters: dict of filter keys and values. If a 'properties'
                    key is present, it is treated as a dict of key/value
                    filters on the image properties attribute
    :param marker: image id after which to start page
    :param limit: maximum number of images to return
    :param sort_key: list of image attributes by which results should be sorted
    :param sort_dir: directions in which results should be sorted (asc, desc)
    :param member_status: only return shared images that have this membership
                          status
    :param is_public: If true, return only public images. If false, return
                      only private and shared images.
    :param admin_as_user: For backwards compatibility. If true, then return to
                      an admin the equivalent set of images which it would see
                      if it was a regular user
    :param return_tag: To indicates whether image entry in result includes it
                       relevant tag entries. This could improve upper-layer
                       query performance, to prevent using separated calls
    :param v1_mode: If true, mutates the 'visibility' value of each image
                    into the v1-compatible field 'is_public'
    """
    session = get_session()

    with session.begin():
        return _image_get_all(
            context, session, filters=filters, marker=marker, limit=limit,
            sort_key=sort_key, sort_dir=sort_dir,
            member_status=member_status, is_public=is_public,
            admin_as_user=admin_as_user, return_tag=return_tag,
            v1_mode=v1_mode)


def _image_get_all(
    context, session, filters=None, marker=None, limit=None,
    sort_key=None, sort_dir=None,
    member_status='accepted', is_public=None,
    admin_as_user=False, return_tag=False, v1_mode=False,
):
    sort_key = ['created_at'] if not sort_key else sort_key

    default_sort_dir = 'desc'

    if not sort_dir:
        sort_dir = [default_sort_dir] * len(sort_key)
    elif len(sort_dir) == 1:
        default_sort_dir = sort_dir[0]
        sort_dir *= len(sort_key)

    filters = filters or {}

    visibility = filters.pop('visibility', None)
    showing_deleted = 'changes-since' in filters or filters.get('deleted',
                                                                False)

    img_cond, prop_cond, tag_cond = _make_conditions_from_filters(
        filters, is_public)

    query = _select_images_query(context,
                                 session,
                                 img_cond,
                                 admin_as_user,
                                 member_status,
                                 visibility)
    if visibility is not None:
        # with a visibility, we always and only include images with that
        # visibility except when using the 'all' visibility
        if visibility != 'all':
            query = query.filter(models.Image.visibility == visibility)
    elif context.owner is None:
        # without either a visibility or an owner, we never include
        # 'community' images
        query = query.filter(models.Image.visibility != 'community')
    else:
        # without a visibility and with an owner, we only want to include
        # 'community' images if and only if they are owned by this owner
        community_filters = [
            models.Image.owner == context.owner,
            models.Image.visibility != 'community',
        ]
        query = query.filter(sa_sql.or_(*community_filters))

    if prop_cond:
        for alias, prop_condition in prop_cond:
            query = query.join(alias).filter(sa_sql.and_(*prop_condition))

    if tag_cond:
        for alias, tag_condition in tag_cond:
            query = query.join(alias).filter(sa_sql.and_(*tag_condition))

    marker_image = None
    if marker is not None:
        marker_image = _image_get(context,
                                  session,
                                  marker,
                                  force_show_deleted=showing_deleted)

    for key in ['created_at', 'id']:
        if key not in sort_key:
            sort_key.append(key)
            sort_dir.append(default_sort_dir)

    query = _paginate_query(query, models.Image, limit,
                            sort_key,
                            marker=marker_image,
                            sort_dir=None,
                            sort_dirs=sort_dir)

    query = query.options(sa_orm.joinedload(
        models.Image.properties)).options(
            sa_orm.joinedload(models.Image.locations))
    if return_tag:
        query = query.options(sa_orm.joinedload(models.Image.tags))

    images = []
    for image in query.all():
        image_dict = image.to_dict()
        image_dict = _normalize_locations(
            context, image_dict, force_show_deleted=showing_deleted)
        if return_tag:
            image_dict = _normalize_tags(image_dict)
        if v1_mode:
            image_dict = db_utils.mutate_image_dict_to_v1(image_dict)
        images.append(image_dict)
    return images


def _drop_protected_attrs(model_class, values):
    """
    Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


def _image_get_disk_usage_by_owner(context, session, owner, image_id=None):
    query = session.query(models.Image)
    query = query.filter(models.Image.owner == owner)
    if image_id is not None:
        query = query.filter(models.Image.id != image_id)
    query = query.filter(models.Image.size > 0)
    query = query.filter(~models.Image.status.in_(['killed', 'deleted']))
    images = query.all()

    total = 0
    for i in images:
        locations = [location for location in i.locations
                     if location['status'] != 'deleted']
        total += (i.size * len(locations))
    return total


def _image_get_staging_usage_by_owner(context, session, owner):
    # NOTE(danms): We could do this in a single query, but I think it is
    # easier to understand as two that we concatenate while generating
    # results.

    # Images in uploading or importing state are consuming staging
    # space.
    query = session.query(models.Image)
    query = query.filter(models.Image.owner == owner)
    query = query.filter(models.Image.size > 0)
    query = query.filter(models.Image.status.in_(('uploading',
                                                  'importing')))
    importing_images = query.all()

    # Images with non-empty os_glance_importing_to_stores properties
    # may also be consuming staging space. Filter our deleted images
    # or importing ones included in the above query.
    props = session.query(models.ImageProperty).filter(
        models.ImageProperty.name == 'os_glance_importing_to_stores',
        models.ImageProperty.value != '').subquery()
    query = session.query(models.Image)
    query = query.join(props, props.c.image_id == models.Image.id)
    query = query.filter(models.Image.owner == owner)
    query = query.filter(models.Image.size > 0)
    query = query.filter(~models.Image.status.in_(('uploading',
                                                   'importing',
                                                   'killed',
                                                   'deleted')))
    copying_images = query.all()

    return sum(i.size for i in itertools.chain(importing_images,
                                               copying_images))


def _image_get_count_by_owner(context, session, owner):
    query = session.query(models.Image)
    query = query.filter(models.Image.owner == owner)
    query = query.filter(~models.Image.status.in_(['killed', 'deleted']))
    return query.count()


def _image_get_uploading_count_by_owner(context, session, owner):
    """Return a count of the images uploading or importing."""

    importing_statuses = ('saving', 'uploading', 'importing')

    # Images in any state indicating uploading, including through image_upload
    # or importing count for this.
    query = session.query(models.Image)
    query = query.filter(models.Image.owner == owner)
    query = query.filter(models.Image.status.in_(importing_statuses))
    uploading = query.count()

    # Images that are not in the above list, but are not deleted and
    # in the process of doing a copy count for this.
    props = session.query(models.ImageProperty).filter(
        models.ImageProperty.name == 'os_glance_importing_to_stores',
        models.ImageProperty.value != '').subquery()
    query = session.query(models.Image)
    query = query.join(props, props.c.image_id == models.Image.id)
    query = query.filter(models.Image.owner == owner)
    query = query.filter(~models.Image.status.in_(importing_statuses +
                                                  ('killed', 'deleted')))
    copying = query.count()

    return uploading + copying


def _validate_image(values, mandatory_status=True):
    """
    Validates the incoming data and raises a Invalid exception
    if anything is out of order.

    :param values: Mapping of image metadata to check
    :param mandatory_status: Whether to validate status from values
    """

    if mandatory_status:
        status = values.get('status')
        if not status:
            msg = "Image status is required."
            raise exception.Invalid(msg)

        if status not in STATUSES:
            msg = "Invalid image status '%s' for image." % status
            raise exception.Invalid(msg)

    # validate integer values to eliminate DBError on save
    _validate_db_int(min_disk=values.get('min_disk'),
                     min_ram=values.get('min_ram'))

    return values


def _update_values(image_ref, values):
    for k in values:
        if getattr(image_ref, k) != values[k]:
            setattr(image_ref, k, values[k])


def image_set_property_atomic(image_id, name, value):
    """
    Atomically set an image property to a value.

    This will only succeed if the property does not currently exist
    and it was created successfully. This can be used by multiple
    competing threads to ensure that only one of those threads
    succeeded in creating the property.

    Note that ImageProperty objects are marked as deleted=$id and so we must
    first try to atomically update-and-undelete such a property, if it
    exists. If that does not work, we should try to create the property. The
    latter should fail with DBDuplicateEntry because of the UniqueConstraint
    across ImageProperty(image_id, name).

    :param image_id: The ID of the image on which to create the property
    :param name: The property name
    :param value: The value to set for the property
    :raises Duplicate: If the property already exists
    """
    session = get_session()
    with session.begin():
        connection = session.connection()
        table = models.ImageProperty.__table__

        # This should be:
        #   UPDATE image_properties SET value=$value, deleted=False
        #     WHERE name=$name AND deleted!=False
        result = connection.execute(table.update().where(
            sa_sql.and_(table.c.name == name,
                        table.c.image_id == image_id,
                        table.c.deleted != False)).values(
                            value=value, deleted=False))
        if result.rowcount == 1:
            # Found and updated a deleted property, so we win
            return

        # There might have been no deleted property, or the property
        # exists and is undeleted, so try to create it and use that
        # to determine if we've lost the race or not.

        try:
            connection.execute(table.insert(),
                               dict(deleted=False,
                                    created_at=timeutils.utcnow(),
                                    image_id=image_id,
                                    name=name,
                                    value=value))
        except db_exception.DBDuplicateEntry:
            # Lost the race to create the new property
            raise exception.Duplicate()

        # If we got here, we created a new row, UniqueConstraint would have
        # caused us to fail if we lost the race


def image_delete_property_atomic(image_id, name, value):
    """
    Atomically delete an image property.

    This will only succeed if the referenced image has a property set
    to exactly the value provided.

    :param image_id: The ID of the image on which to delete the property
    :param name: The property name
    :param value: The value the property is expected to be set to
    :raises NotFound: If the property does not exist
    """
    session = get_session()
    with session.begin():
        connection = session.connection()
        table = models.ImageProperty.__table__

        result = connection.execute(table.delete().where(
            sa_sql.and_(table.c.name == name,
                        table.c.value == value,
                        table.c.image_id == image_id,
                        table.c.deleted == False)))
        if result.rowcount == 1:
            return

        raise exception.NotFound()


@utils.no_4byte_params
def _image_update(context, session, image_id, values, purge_props=False,
                  from_state=None, atomic_props=None):
    """
    Used internally by image_create and image_update

    :param context: Request context
    :param image_id: If None, create the image, otherwise, find and update it
    :param values: A dict of attributes to set
    :param from_state: If not None, reequire the image be in this state to do
                       the update
    :param purge_props: If True, delete properties found in the database but
                        not present in values
    :param atomic_props: If non-None, refuse to create or update properties
                         in this list
    """
    # NOTE(jbresnah) values is altered in this so a copy is needed
    values = values.copy()

    # Remove the properties passed in the values mapping. We
    # handle properties separately from base image attributes,
    # and leaving properties in the values mapping will cause
    # a SQLAlchemy model error because SQLAlchemy expects the
    # properties attribute of an Image model to be a list and
    # not a dict.
    properties = values.pop('properties', {})

    location_data = values.pop('locations', None)

    new_status = values.get('status')
    if image_id:
        image_ref = _image_get(context, session, image_id)
        current = image_ref.status
        # Perform authorization check
        _check_mutate_authorization(context, image_ref)
    else:
        if values.get('size') is not None:
            values['size'] = int(values['size'])

        if 'min_ram' in values:
            values['min_ram'] = int(values['min_ram'] or 0)

        if 'min_disk' in values:
            values['min_disk'] = int(values['min_disk'] or 0)

        values['protected'] = bool(values.get('protected', False))
        image_ref = models.Image()

    values = db_utils.ensure_image_dict_v2_compliant(values)

    # Need to canonicalize ownership
    if 'owner' in values and not values['owner']:
        values['owner'] = None

    if image_id:
        # Don't drop created_at if we're passing it in...
        _drop_protected_attrs(models.Image, values)
        # NOTE(iccha-sethi): updated_at must be explicitly set in case
        #                   only ImageProperty table was modifited
        values['updated_at'] = timeutils.utcnow()

    if image_id:
        query = session.query(models.Image).filter_by(id=image_id)
        if from_state:
            query = query.filter_by(status=from_state)

        mandatory_status = True if new_status else False
        _validate_image(values, mandatory_status=mandatory_status)

        # Validate fields for Images table. This is similar to what is done
        # for the query result update except that we need to do it prior
        # in this case.
        values = {key: values[key] for key in values
                  if key in image_ref.to_dict()}
        updated = query.update(values, synchronize_session='fetch')

        if not updated:
            msg = (_('cannot transition from %(current)s to '
                     '%(next)s in update (wanted '
                     'from_state=%(from)s)') %
                   {'current': current, 'next': new_status,
                    'from': from_state})
            raise exception.Conflict(msg)

        image_ref = _image_get(context, session, image_id)
    else:
        image_ref.update(values)
        # Validate the attributes before we go any further. From my
        # investigation, the @validates decorator does not validate
        # on new records, only on existing records, which is, well,
        # idiotic.
        values = _validate_image(image_ref.to_dict())
        _update_values(image_ref, values)

        try:
            image_ref.save(session=session)
        except db_exception.DBDuplicateEntry:
            raise exception.Duplicate("Image ID %s already exists!"
                                      % values['id'])

    _set_properties_for_image(
        context, session, image_ref, properties, purge_props,
        atomic_props)

    if location_data:
        _image_locations_set(
            context, session, image_ref.id, location_data)

    return image_ref


def image_location_add(context, image_id, location):
    session = get_session()
    with session.begin():
        _image_location_add(context, session, image_id, location)


@utils.no_4byte_params
def _image_location_add(context, session, image_id, location):
    deleted = location['status'] in ('deleted', 'pending_delete')
    delete_time = timeutils.utcnow() if deleted else None
    location_ref = models.ImageLocation(image_id=image_id,
                                        value=location['url'],
                                        meta_data=location['metadata'],
                                        status=location['status'],
                                        deleted=deleted,
                                        deleted_at=delete_time)
    location_ref.save(session=session)


def image_location_update(context, image_id, location):
    session = get_session()
    with session.begin():
        _image_location_update(context, session, image_id, location)


@utils.no_4byte_params
def _image_location_update(context, session, image_id, location):
    loc_id = location.get('id')
    if loc_id is None:
        msg = _("The location data has an invalid ID: %d") % loc_id
        raise exception.Invalid(msg)

    try:
        location_ref = session.query(models.ImageLocation).filter_by(
            id=loc_id).filter_by(image_id=image_id).one()

        deleted = location['status'] in ('deleted', 'pending_delete')
        updated_time = timeutils.utcnow()
        delete_time = updated_time if deleted else None

        location_ref.update({"value": location['url'],
                             "meta_data": location['metadata'],
                             "status": location['status'],
                             "deleted": deleted,
                             "updated_at": updated_time,
                             "deleted_at": delete_time})
        location_ref.save(session=session)
    except sa_orm.exc.NoResultFound:
        msg = (_("No location found with ID %(loc)s from image %(img)s") %
               dict(loc=loc_id, img=image_id))
        LOG.warning(msg)
        raise exception.NotFound(msg)


def image_location_delete(context, image_id, location_id, status,
                          delete_time=None):
    session = get_session()
    with session.begin():
        _image_location_delete(
            context, session, image_id, location_id, status, delete_time=None,
        )


def _image_location_delete(
    context, session, image_id, location_id, status, delete_time=None,
):
    if status not in ('deleted', 'pending_delete'):
        msg = _("The status of deleted image location can only be set to "
                "'pending_delete' or 'deleted'")
        raise exception.Invalid(msg)

    try:
        location_ref = session.query(models.ImageLocation).filter_by(
            id=location_id).filter_by(image_id=image_id).one()

        delete_time = delete_time or timeutils.utcnow()

        location_ref.update({"deleted": True,
                             "status": status,
                             "updated_at": delete_time,
                             "deleted_at": delete_time})
        location_ref.save(session=session)
    except sa_orm.exc.NoResultFound:
        msg = (_("No location found with ID %(loc)s from image %(img)s") %
               dict(loc=location_id, img=image_id))
        LOG.warning(msg)
        raise exception.NotFound(msg)


def _image_locations_set(context, session, image_id, locations):
    # NOTE(zhiyan): 1. Remove records from DB for deleted locations
    query = session.query(models.ImageLocation).filter_by(
        image_id=image_id).filter_by(deleted=False)

    loc_ids = [loc['id'] for loc in locations if loc.get('id')]
    if loc_ids:
        query = query.filter(~models.ImageLocation.id.in_(loc_ids))

    for loc_id in [loc_ref.id for loc_ref in query.all()]:
        _image_location_delete(context, session, image_id, loc_id, 'deleted')

    # NOTE(zhiyan): 2. Adding or update locations
    for loc in locations:
        if loc.get('id') is None:
            _image_location_add(context, session, image_id, loc)
        else:
            _image_location_update(context, session, image_id, loc)


def _image_locations_delete_all(
    context, session, image_id, delete_time=None,
):
    """Delete all image locations for given image"""
    location_refs = session.query(models.ImageLocation).filter_by(
        image_id=image_id).filter_by(deleted=False).all()

    for loc_id in [loc_ref.id for loc_ref in location_refs]:
        _image_location_delete(context, session, image_id, loc_id, 'deleted',
                               delete_time=delete_time)


@utils.no_4byte_params
def _set_properties_for_image(context, session, image_ref, properties,
                              purge_props=False, atomic_props=None):
    """
    Create or update a set of image_properties for a given image

    :param context: Request context
    :param session: A SQLAlchemy session to use
    :param image_ref: An Image object
    :param properties: A dict of properties to set
    :param purge_props: If True, delete properties in the database
                        that are not in properties
    :param atomic_props: If non-None, skip update/create/delete of properties
                         named in this list
    """

    if atomic_props is None:
        atomic_props = []

    orig_properties = {}
    for prop_ref in image_ref.properties:
        orig_properties[prop_ref.name] = prop_ref

    for name, value in properties.items():
        prop_values = {'image_id': image_ref.id,
                       'name': name,
                       'value': value}
        if name in atomic_props:
            # NOTE(danms): Never update or create properties in the list
            # of atomics
            continue
        elif name in orig_properties:
            prop_ref = orig_properties[name]
            _image_property_update(context, session, prop_ref, prop_values)
        else:
            _image_property_create(context, session, prop_values)

    if purge_props:
        for key in orig_properties.keys():
            if key in atomic_props:
                continue
            elif key not in properties:
                prop_ref = orig_properties[key]
                _image_property_delete(context, session, prop_ref.name,
                                       image_ref.id)


def _image_child_entry_delete_all(
    context, session, child_model_cls, image_id, delete_time=None,
):
    """Deletes all the child entries for the given image id.

    Deletes all the child entries of the given child entry ORM model class
    using the parent image's id.

    The child entry ORM model class can be one of the following:
    model.ImageLocation, model.ImageProperty, model.ImageMember and
    model.ImageTag.

    :param context: Request context
    :param session: A SQLAlchemy session to use
    :param child_model_cls: the ORM model class.
    :param image_id: id of the image whose child entries are to be deleted.
    :param delete_time: datetime of deletion to be set.
                        If None, uses current datetime.

    :rtype: int
    :returns: The number of child entries got soft-deleted.
    """
    query = session.query(child_model_cls).filter_by(
        image_id=image_id).filter_by(deleted=False)

    delete_time = delete_time or timeutils.utcnow()

    count = query.update({"deleted": True, "deleted_at": delete_time})
    return count


def image_property_create(context, values):
    """Create an ImageProperty object."""
    session = get_session()
    with session.begin():
        return _image_property_create(context, session, values)


def _image_property_create(context, session, values):
    prop_ref = models.ImageProperty()
    prop = _image_property_update(context, session, prop_ref, values)
    return prop.to_dict()


def _image_property_update(context, session, prop_ref, values):
    """
    Used internally by image_property_create and image_property_update.
    """
    _drop_protected_attrs(models.ImageProperty, values)
    values["deleted"] = False
    prop_ref.update(values)
    prop_ref.save(session=session)
    return prop_ref


def image_property_delete(context, prop_ref, image_ref):
    session = get_session()
    with session.begin():
        return _image_property_delete(context, session, prop_ref, image_ref)


def _image_property_delete(context, session, prop_ref, image_ref):
    """
    Used internally by _set_properties_for_image().
    """
    prop = session.query(models.ImageProperty).filter_by(image_id=image_ref,
                                                         name=prop_ref).one()
    try:
        prop.delete(session=session)
    except sa_orm.exc.StaleDataError as e:
        LOG.debug(('StaleDataError while deleting property %(prop)r '
                   'from image %(image)r likely means we raced during delete: '
                   '%(err)s'),
                  {'prop': prop_ref, 'image': image_ref,
                   'err': str(e)})
        return
    return prop


def _image_property_delete_all(context, session, image_id, delete_time=None):
    """Delete all image properties for given image"""
    props_updated_count = _image_child_entry_delete_all(
        context,
        session,
        models.ImageProperty,
        image_id,
        delete_time)
    return props_updated_count


@utils.no_4byte_params
def image_member_create(context, values):
    """Create an ImageMember object."""
    session = get_session()
    with session.begin():
        memb_ref = models.ImageMember()
        _image_member_update(context, session, memb_ref, values)
        return _image_member_format(memb_ref)


def _image_member_format(member_ref):
    """Format a member ref for consumption outside of this module."""
    return {
        'id': member_ref['id'],
        'image_id': member_ref['image_id'],
        'member': member_ref['member'],
        'can_share': member_ref['can_share'],
        'status': member_ref['status'],
        'created_at': member_ref['created_at'],
        'updated_at': member_ref['updated_at'],
        'deleted': member_ref['deleted']
    }


def image_member_update(context, memb_id, values):
    """Update an ImageMember object."""
    session = get_session()
    with session.begin():
        memb_ref = _image_member_get(context, session, memb_id)
        _image_member_update(context, session, memb_ref, values)
        return _image_member_format(memb_ref)


def _image_member_update(context, session, memb_ref, values):
    """Apply supplied dictionary of values to a Member object."""
    _drop_protected_attrs(models.ImageMember, values)
    values["deleted"] = False
    values.setdefault('can_share', False)
    memb_ref.update(values)
    memb_ref.save(session=session)
    return memb_ref


def image_member_delete(context, memb_id):
    """Delete an ImageMember object."""
    session = get_session()
    with session.begin():
        member_ref = _image_member_get(context, session, memb_id)
        _image_member_delete(context, session, member_ref)


def _image_member_delete(context, session, memb_ref):
    memb_ref.delete(session=session)


def _image_member_delete_all(context, session, image_id, delete_time=None):
    """Delete all image members for given image"""
    members_updated_count = _image_child_entry_delete_all(
        context,
        session,
        models.ImageMember,
        image_id,
        delete_time)
    return members_updated_count


def _image_member_get(context, session, memb_id):
    """Fetch an ImageMember entity by id."""
    query = session.query(models.ImageMember)
    query = query.filter_by(id=memb_id)
    return query.one()


def image_member_find(context, image_id=None, member=None,
                      status=None, include_deleted=False):
    """Find all members that meet the given criteria.

    Note, currently include_deleted should be true only when create a new
    image membership, as there may be a deleted image membership between
    the same image and tenant, the membership will be reused in this case.
    It should be false in other cases.

    :param image_id: identifier of image entity
    :param member: tenant to which membership has been granted
    :include_deleted: A boolean indicating whether the result should include
                      the deleted record of image member
    """
    session = get_session()
    with session.begin():
        members = _image_member_find(context, session, image_id,
                                     member, status, include_deleted)
        return [_image_member_format(m) for m in members]


def _image_member_find(context, session, image_id=None,
                       member=None, status=None, include_deleted=False):
    query = session.query(models.ImageMember)
    if not include_deleted:
        query = query.filter_by(deleted=False)

    if not context.is_admin:
        query = query.join(models.Image)
        filters = [
            models.Image.owner == context.owner,
            models.ImageMember.member == context.owner,
        ]
        query = query.filter(sa_sql.or_(*filters))

    if image_id is not None:
        query = query.filter(models.ImageMember.image_id == image_id)
    if member is not None:
        query = query.filter(models.ImageMember.member == member)
    if status is not None:
        query = query.filter(models.ImageMember.status == status)

    return query.all()


def image_member_count(context, image_id):
    """Return the number of image members for this image

    :param image_id: identifier of image entity
    """
    session = get_session()

    if not image_id:
        msg = _("Image id is required.")
        raise exception.Invalid(msg)

    with session.begin():
        query = session.query(models.ImageMember)
        query = query.filter_by(deleted=False)
        query = query.filter(models.ImageMember.image_id == str(image_id))

        return query.count()


def image_tag_set_all(context, image_id, tags):
    # NOTE(kragniz): tag ordering should match exactly what was provided, so a
    # subsequent call to image_tag_get_all returns them in the correct order

    session = get_session()
    with session.begin():
        existing_tags = _image_tag_get_all(context, session, image_id)

        tags_created = []
        for tag in tags:
            if tag not in tags_created and tag not in existing_tags:
                tags_created.append(tag)
                _image_tag_create(context, session, image_id, tag)

        for tag in existing_tags:
            if tag not in tags:
                _image_tag_delete(context, session, image_id, tag)


def image_tag_create(context, image_id, value):
    session = get_session()
    with session.begin():
        return _image_tag_create(context, session, image_id, value)


@utils.no_4byte_params
def _image_tag_create(context, session, image_id, value):
    """Create an image tag."""
    tag_ref = models.ImageTag(image_id=image_id, value=value)
    tag_ref.save(session=session)
    return tag_ref['value']


def image_tag_delete(context, image_id, value):
    session = get_session()
    with session.begin():
        _image_tag_delete(context, session, image_id, value)


def _image_tag_delete(context, session, image_id, value):
    """Delete an image tag."""
    _check_image_id(image_id)
    query = session.query(models.ImageTag).filter_by(
        image_id=image_id).filter_by(
            value=value).filter_by(deleted=False)
    try:
        tag_ref = query.one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    tag_ref.delete(session=session)


def _image_tag_delete_all(context, session, image_id, delete_time=None):
    """Delete all image tags for given image"""
    tags_updated_count = _image_child_entry_delete_all(
        context,
        session,
        models.ImageTag,
        image_id,
        delete_time)
    return tags_updated_count


def image_tag_get_all(context, image_id):
    session = get_session()
    with session.begin():
        return _image_tag_get_all(context, session, image_id)


def _image_tag_get_all(context, session, image_id):
    """Get a list of tags for a specific image."""
    _check_image_id(image_id)
    tags = session.query(models.ImageTag.value).filter_by(
        image_id=image_id).filter_by(deleted=False).all()
    return [tag[0] for tag in tags]


class DeleteFromSelect(sa_sql.expression.UpdateBase):
    inherit_cache = False

    def __init__(self, table, select, column):
        self.table = table
        self.select = select
        self.column = column


# NOTE(abhishekk): MySQL doesn't yet support subquery with
# 'LIMIT & IN/ALL/ANY/SOME' We need work around this with nesting select.
@compiles(DeleteFromSelect)
def visit_delete_from_select(element, compiler, **kw):
    return "DELETE FROM %s WHERE %s in (SELECT T1.%s FROM (%s) as T1)" % (
        compiler.process(element.table, asfrom=True),
        compiler.process(element.column),
        element.column.name,
        compiler.process(element.select))


def purge_deleted_rows(context, age_in_days, max_rows):
    """Purges soft deleted rows

    Deletes rows of table images, table tasks and all dependent tables
    according to given age for relevant models.
    """
    # check max_rows for its maximum limit
    _validate_db_int(max_rows=max_rows)

    session = get_session()
    metadata = MetaData()
    engine = get_engine()
    deleted_age = timeutils.utcnow() - datetime.timedelta(days=age_in_days)

    tables = []
    for model_class in models.__dict__.values():
        if not hasattr(model_class, '__tablename__'):
            continue
        if hasattr(model_class, 'deleted'):
            tables.append(model_class.__tablename__)

    # First force purging of records that are not soft deleted but
    # are referencing soft deleted tasks/images records (e.g. task_info
    # records). Then purge all soft deleted records in glance tables in the
    # right order to avoid FK constraint violation.
    t = Table("tasks", metadata, autoload_with=engine)
    ti = Table("task_info", metadata, autoload_with=engine)
    joined_rec = ti.join(t, t.c.id == ti.c.task_id)
    deleted_task_info = sql.\
        select(ti.c.task_id).where(t.c.deleted_at < deleted_age).\
        select_from(joined_rec).\
        order_by(t.c.deleted_at)
    if max_rows != -1:
        deleted_task_info = deleted_task_info.limit(max_rows)
    delete_statement = DeleteFromSelect(ti, deleted_task_info,
                                        ti.c.task_id)
    LOG.info(_LI('Purging deleted rows older than %(age_in_days)d day(s) '
                 'from table %(tbl)s'),
             {'age_in_days': age_in_days, 'tbl': ti})
    try:
        with session.begin():
            result = session.execute(delete_statement)
    except (db_exception.DBError, db_exception.DBReferenceError) as ex:
        LOG.exception(_LE('DBError detected when force purging '
                          'table=%(table)s: %(error)s'),
                      {'table': ti, 'error': str(ex)})
        raise

    rows = result.rowcount
    LOG.info(_LI('Deleted %(rows)d row(s) from table %(tbl)s'),
             {'rows': rows, 'tbl': ti})

    # get rid of FK constraints
    for tbl in ('images', 'tasks'):
        try:
            tables.remove(tbl)
        except ValueError:
            LOG.warning(_LW('Expected table %(tbl)s was not found in DB.'),
                        {'tbl': tbl})
        else:
            # NOTE(abhishekk): To mitigate OSSN-0075 images records should be
            # purged with new ``purge-images-table`` command.
            if tbl == 'images':
                continue

            tables.append(tbl)

    for tbl in tables:
        tab = Table(tbl, metadata, autoload_with=engine)
        LOG.info(
            _LI('Purging deleted rows older than %(age_in_days)d day(s) '
                'from table %(tbl)s'),
            {'age_in_days': age_in_days, 'tbl': tbl})

        column = tab.c.id
        deleted_at_column = tab.c.deleted_at

        query_delete = sql.select(column).\
            where(deleted_at_column < deleted_age).\
            order_by(deleted_at_column)
        if max_rows != -1:
            query_delete = query_delete.limit(max_rows)

        delete_statement = DeleteFromSelect(tab, query_delete, column)

        try:
            with session.begin():
                result = session.execute(delete_statement)
        except db_exception.DBReferenceError as ex:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE('DBError detected when purging from '
                          "%(tablename)s: %(error)s"),
                          {'tablename': tbl, 'error': str(ex)})

        rows = result.rowcount
        LOG.info(_LI('Deleted %(rows)d row(s) from table %(tbl)s'),
                 {'rows': rows, 'tbl': tbl})


def purge_deleted_rows_from_images(context, age_in_days, max_rows):
    """Purges soft deleted rows

    Deletes rows of table images table according to given age for
    relevant models.
    """
    # check max_rows for its maximum limit
    _validate_db_int(max_rows=max_rows)

    session = get_session()
    metadata = MetaData()
    engine = get_engine()
    deleted_age = timeutils.utcnow() - datetime.timedelta(days=age_in_days)

    tbl = 'images'
    tab = Table(tbl, metadata, autoload_with=engine)
    LOG.info(
        _LI('Purging deleted rows older than %(age_in_days)d day(s) '
            'from table %(tbl)s'),
        {'age_in_days': age_in_days, 'tbl': tbl})

    column = tab.c.id
    deleted_at_column = tab.c.deleted_at

    query_delete = sql.\
        select(column).\
        where(deleted_at_column < deleted_age).\
        order_by(deleted_at_column)
    if max_rows != -1:
        query_delete = query_delete.limit(max_rows)

    delete_statement = DeleteFromSelect(tab, query_delete, column)

    try:
        with session.begin():
            result = session.execute(delete_statement)
    except db_exception.DBReferenceError as ex:
        with excutils.save_and_reraise_exception():
            LOG.error(_LE('DBError detected when purging from '
                      "%(tablename)s: %(error)s"),
                      {'tablename': tbl, 'error': str(ex)})

    rows = result.rowcount
    LOG.info(_LI('Deleted %(rows)d row(s) from table %(tbl)s'),
             {'rows': rows, 'tbl': tbl})


def user_get_storage_usage(context, owner_id, image_id=None):
    _check_image_id(image_id)
    session = get_session()
    with session.begin():
        total_size = _image_get_disk_usage_by_owner(
            context, session, owner_id, image_id=image_id)
    return total_size


def user_get_staging_usage(context, owner_id):
    session = get_session()
    with session.begin():
        return _image_get_staging_usage_by_owner(context, session, owner_id)


def user_get_image_count(context, owner_id):
    session = get_session()
    with session.begin():
        return _image_get_count_by_owner(context, session, owner_id)


def user_get_uploading_count(context, owner_id):
    session = get_session()
    with session.begin():
        return _image_get_uploading_count_by_owner(context, session, owner_id)


def _task_info_format(task_info_ref):
    """Format a task info ref for consumption outside of this module"""
    if task_info_ref is None:
        return {}
    return {
        'task_id': task_info_ref['task_id'],
        'input': task_info_ref['input'],
        'result': task_info_ref['result'],
        'message': task_info_ref['message'],
    }


def _task_info_create(context, session, task_id, values):
    """Create an TaskInfo object"""
    task_info_ref = models.TaskInfo()
    task_info_ref.task_id = task_id
    task_info_ref.update(values)
    task_info_ref.save(session=session)
    return _task_info_format(task_info_ref)


def _task_info_update(context, session, task_id, values):
    """Update an TaskInfo object"""
    task_info_ref = _task_info_get(context, session, task_id)
    if task_info_ref:
        task_info_ref.update(values)
        task_info_ref.save(session=session)
    return _task_info_format(task_info_ref)


def _task_info_get(context, session, task_id):
    """Fetch an TaskInfo entity by task_id"""
    query = session.query(models.TaskInfo)
    query = query.filter_by(task_id=task_id)
    try:
        task_info_ref = query.one()
    except sa_orm.exc.NoResultFound:
        LOG.debug("TaskInfo was not found for task with id %(task_id)s",
                  {'task_id': task_id})
        task_info_ref = None

    return task_info_ref


def task_create(context, values):
    """Create a task object"""
    values = values.copy()
    session = get_session()
    with session.begin():
        task_info_values = _pop_task_info_values(values)

        task_ref = models.Task()
        _task_update(context, session, task_ref, values)

        _task_info_create(context,
                          session,
                          task_ref.id,
                          task_info_values)

    with session.begin():
        task_ref = _task_get(context, session, task_ref.id)
        return _task_format(task_ref, task_ref.info)


def _pop_task_info_values(values):
    task_info_values = {}
    for k, v in list(values.items()):
        if k in ['input', 'result', 'message']:
            values.pop(k)
            task_info_values[k] = v

    return task_info_values


def task_update(context, task_id, values):
    """Update a task object"""
    session = get_session()
    with session.begin():
        task_info_values = _pop_task_info_values(values)

        task_ref = _task_get(context, session, task_id)
        _drop_protected_attrs(models.Task, values)

        values['updated_at'] = timeutils.utcnow()

        _task_update(context, session, task_ref, values)

        if task_info_values:
            _task_info_update(context,
                              session,
                              task_id,
                              task_info_values)

    with session.begin():
        task_ref = _task_get(context, session, task_id)
        return _task_format(task_ref, task_ref.info)


def task_get(context, task_id, force_show_deleted=False):
    """Fetch a task entity by id"""
    session = get_session()
    with session.begin():
        task_ref = _task_get(context, session, task_id,
                             force_show_deleted=force_show_deleted)
        return _task_format(task_ref, task_ref.info)


def tasks_get_by_image(context, image_id):
    """Fetch all tasks associated with image_id"""
    session = get_session()
    with session.begin():
        return _tasks_get_by_image(context, session, image_id)


def _tasks_get_by_image(context, session, image_id):
    tasks = []
    _task_soft_delete(context, session)

    query = session.query(models.Task).options(
        sa_orm.joinedload(models.Task.info)
    ).filter_by(image_id=image_id)

    expires_at = models.Task.expires_at
    query = query.filter(sa_sql.or_(expires_at == None,
                                    expires_at >= timeutils.utcnow()))
    updated_at = models.Task.updated_at
    query.filter(
        updated_at <= (timeutils.utcnow() +
                       datetime.timedelta(hours=CONF.task.task_time_to_live)))

    if not context.can_see_deleted:
        query = query.filter_by(deleted=False)

    try:
        task_refs = query.all()
    except sa_orm.exc.NoResultFound:
        LOG.debug("No task found for image with ID %s", image_id)
        return tasks

    for task_ref in task_refs:
        # Make sure the task is visible
        if not _is_task_visible(context, task_ref):
            msg = "Task %s is not visible, excluding" % task_ref.id
            LOG.debug(msg)
            continue
        tasks.append(_task_format(task_ref, task_ref.info))

    return tasks


def task_delete(context, task_id):
    """Delete a task"""
    session = get_session()
    with session.begin():
        task_ref = _task_get(context, session, task_id)
        task_ref.delete(session=session)
        return _task_format(task_ref, task_ref.info)


def _task_soft_delete(context, session):
    """Scrub task entities which are expired """
    expires_at = models.Task.expires_at
    query = session.query(models.Task)

    query = (query.filter(models.Task.owner == context.owner)
                  .filter_by(deleted=False)
                  .filter(expires_at <= timeutils.utcnow()))
    values = {'deleted': True, 'deleted_at': timeutils.utcnow()}

    query.update(values)


def task_get_all(context, filters=None, marker=None, limit=None,
                 sort_key='created_at', sort_dir='desc', admin_as_user=False):
    """
    Get all tasks that match zero or more filters.

    :param filters: dict of filter keys and values.
    :param marker: task id after which to start page
    :param limit: maximum number of tasks to return
    :param sort_key: task attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    :param admin_as_user: For backwards compatibility. If true, then return to
                      an admin the equivalent set of tasks which it would see
                      if it were a regular user
    :returns: tasks set
    """
    session = get_session()

    with session.begin():
        return _task_get_all(
            context, session, filters=filters, marker=marker, limit=limit,
            sort_key=sort_key, sort_dir=sort_dir, admin_as_user=admin_as_user,
        )


def _task_get_all(
    context, session, filters=None, marker=None, limit=None,
    sort_key='created_at', sort_dir='desc', admin_as_user=False,
):
    filters = filters or {}

    query = session.query(models.Task)

    if not (context.is_admin or admin_as_user) and context.owner is not None:
        query = query.filter(models.Task.owner == context.owner)

    _task_soft_delete(context, session)

    showing_deleted = False

    if 'deleted' in filters:
        deleted_filter = filters.pop('deleted')
        query = query.filter_by(deleted=deleted_filter)
        showing_deleted = deleted_filter

    for (k, v) in filters.items():
        if v is not None:
            key = k
            if hasattr(models.Task, key):
                query = query.filter(getattr(models.Task, key) == v)

    marker_task = None
    if marker is not None:
        marker_task = _task_get(context, session, marker,
                                force_show_deleted=showing_deleted)

    sort_keys = ['created_at', 'id']
    if sort_key not in sort_keys:
        sort_keys.insert(0, sort_key)

    query = _paginate_query(query, models.Task, limit,
                            sort_keys,
                            marker=marker_task,
                            sort_dir=sort_dir)

    task_refs = query.all()

    tasks = []
    for task_ref in task_refs:
        tasks.append(_task_format(task_ref, task_info_ref=None))

    return tasks


def _is_task_visible(context, task):
    """Return True if the task is visible in this context."""
    # Is admin == task visible
    if context.is_admin:
        return True

    # No owner == task visible
    if task['owner'] is None:
        return True

    # Perform tests based on whether we have an owner
    if context.owner is not None:
        if context.owner == task['owner']:
            return True

    return False


def _task_get(context, session, task_id, force_show_deleted=False):
    """Fetch a task entity by id"""
    query = session.query(models.Task).options(
        sa_orm.joinedload(models.Task.info)
    ).filter_by(id=task_id)

    if not force_show_deleted and not context.can_see_deleted:
        query = query.filter_by(deleted=False)
    try:
        task_ref = query.one()
    except sa_orm.exc.NoResultFound:
        LOG.debug("No task found with ID %s", task_id)
        raise exception.TaskNotFound(task_id=task_id)

    # Make sure the task is visible
    if not _is_task_visible(context, task_ref):
        msg = "Forbidding request, task %s is not visible" % task_id
        LOG.debug(msg)
        raise exception.Forbidden(msg)

    return task_ref


def _task_update(context, session, task_ref, values):
    """Apply supplied dictionary of values to a task object."""
    if 'deleted' not in values:
        values["deleted"] = False
    task_ref.update(values)
    task_ref.save(session=session)
    return task_ref


def _task_format(task_ref, task_info_ref=None):
    """Format a task ref for consumption outside of this module"""
    task_dict = {
        'id': task_ref['id'],
        'type': task_ref['type'],
        'status': task_ref['status'],
        'owner': task_ref['owner'],
        'expires_at': task_ref['expires_at'],
        'created_at': task_ref['created_at'],
        'updated_at': task_ref['updated_at'],
        'deleted_at': task_ref['deleted_at'],
        'deleted': task_ref['deleted'],
        'image_id': task_ref['image_id'],
        'request_id': task_ref['request_id'],
        'user_id': task_ref['user_id'],
    }

    if task_info_ref:
        task_info_dict = {
            'input': task_info_ref['input'],
            'result': task_info_ref['result'],
            'message': task_info_ref['message'],
        }
        task_dict.update(task_info_dict)

    return task_dict


def metadef_namespace_get_all(
    context, marker=None, limit=None, sort_key='created_at',
    sort_dir='desc', filters=None,
):
    """List all available namespaces."""
    session = get_session()
    with session.begin():
        return metadef_namespace_api.get_all(
            context, session, marker, limit, sort_key, sort_dir, filters)


def metadef_namespace_get(context, namespace_name):
    """Get a namespace or raise if it does not exist or is not visible."""
    session = get_session()
    with session.begin():
        return metadef_namespace_api.get(
            context, session, namespace_name)


@utils.no_4byte_params
def metadef_namespace_create(context, values):
    """Create a namespace or raise if it already exists."""
    session = get_session()
    with session.begin():
        return metadef_namespace_api.create(context, session, values)


@utils.no_4byte_params
def metadef_namespace_update(context, namespace_id, namespace_dict):
    """Update a namespace or raise if it does not exist or not visible"""
    session = get_session()
    with session.begin():
        return metadef_namespace_api.update(
            context, session, namespace_id, namespace_dict)


def metadef_namespace_delete(context, namespace_name):
    """Delete the namespace and all foreign references"""
    session = get_session()
    with session.begin():
        return metadef_namespace_api.delete_cascade(
            context, session, namespace_name)


def metadef_object_get_all(context, namespace_name):
    """Get a metadata-schema object or raise if it does not exist."""
    session = get_session()
    with session.begin():
        return metadef_object_api.get_all(
            context, session, namespace_name)


def metadef_object_get(context, namespace_name, object_name):
    """Get a metadata-schema object or raise if it does not exist."""
    session = get_session()
    with session.begin():
        return metadef_object_api.get(
            context, session, namespace_name, object_name)


@utils.no_4byte_params
def metadef_object_create(context, namespace_name, object_dict):
    """Create a metadata-schema object or raise if it already exists."""
    session = get_session()
    with session.begin():
        return metadef_object_api.create(
            context, session, namespace_name, object_dict)


@utils.no_4byte_params
def metadef_object_update(context, namespace_name, object_id, object_dict):
    """Update an object or raise if it does not exist or not visible."""
    session = get_session()
    with session.begin():
        return metadef_object_api.update(
            context, session, namespace_name, object_id, object_dict)


def metadef_object_delete(context, namespace_name, object_name):
    """Delete an object or raise if namespace or object doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_object_api.delete(
            context, session, namespace_name, object_name)


def metadef_object_delete_namespace_content(context, namespace_name):
    """Delete an object or raise if namespace or object doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_object_api.delete_by_namespace_name(
            context, session, namespace_name)


def metadef_object_count(context, namespace_name):
    """Get count of properties for a namespace, raise if ns doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_object_api.count(context, session, namespace_name)


def metadef_property_get_all(context, namespace_name):
    """Get a metadef property or raise if it does not exist."""
    session = get_session()
    with session.begin():
        return metadef_property_api.get_all(context, session, namespace_name)


def metadef_property_get(context, namespace_name, property_name):
    """Get a metadef property or raise if it does not exist."""
    session = get_session()
    with session.begin():
        return metadef_property_api.get(
            context, session, namespace_name, property_name)


@utils.no_4byte_params
def metadef_property_create(context, namespace_name, property_dict):
    """Create a metadef property or raise if it already exists."""
    session = get_session()
    with session.begin():
        return metadef_property_api.create(
            context, session, namespace_name, property_dict)


@utils.no_4byte_params
def metadef_property_update(context, namespace_name, property_id,
                            property_dict):
    """Update an object or raise if it does not exist or not visible."""
    session = get_session()
    with session.begin():
        return metadef_property_api.update(
            context, session, namespace_name, property_id, property_dict)


def metadef_property_delete(context, namespace_name, property_name):
    """Delete a property or raise if it or namespace doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_property_api.delete(
            context, session, namespace_name, property_name)


def metadef_property_delete_namespace_content(context, namespace_name):
    """Delete a property or raise if it or namespace doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_property_api.delete_by_namespace_name(
            context, session, namespace_name)


def metadef_property_count(context, namespace_name):
    """Get count of properties for a namespace, raise if ns doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_property_api.count(context, session, namespace_name)


def metadef_resource_type_create(context, values):
    """Create a resource_type"""
    session = get_session()
    with session.begin():
        return metadef_resource_type_api.create(
            context, session, values)


def metadef_resource_type_get(context, resource_type_name):
    """Get a resource_type"""
    session = get_session()
    with session.begin():
        return metadef_resource_type_api.get(
            context, session, resource_type_name)


def metadef_resource_type_get_all(context):
    """list all resource_types"""
    session = get_session()
    with session.begin():
        return metadef_resource_type_api.get_all(context, session)


def metadef_resource_type_delete(context, resource_type_name):
    """Get a resource_type"""
    session = get_session()
    with session.begin():
        return metadef_resource_type_api.delete(
            context, session, resource_type_name)


def metadef_resource_type_association_get(
    context, namespace_name, resource_type_name,
):
    session = get_session()
    with session.begin():
        return metadef_association_api.get(
            context, session, namespace_name, resource_type_name)


def metadef_resource_type_association_create(
    context, namespace_name, values,
):
    session = get_session()
    with session.begin():
        return metadef_association_api.create(
            context, session, namespace_name, values)


def metadef_resource_type_association_delete(
    context, namespace_name, resource_type_name,
):
    session = get_session()
    with session.begin():
        return metadef_association_api.delete(
            context, session, namespace_name, resource_type_name)


def metadef_resource_type_association_get_all_by_namespace(
    context, namespace_name,
):
    session = get_session()
    with session.begin():
        return metadef_association_api.get_all_by_namespace(
            context, session, namespace_name)


def metadef_tag_get_all(
    context, namespace_name, filters=None, marker=None, limit=None,
    sort_key='created_at', sort_dir='desc',
):
    """Get metadata-schema tags or raise if none exist."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.get_all(
            context, session, namespace_name,
            filters, marker, limit, sort_key, sort_dir)


def metadef_tag_get(context, namespace_name, name):
    """Get a metadata-schema tag or raise if it does not exist."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.get(
            context, session, namespace_name, name)


@utils.no_4byte_params
def metadef_tag_create(context, namespace_name, tag_dict):
    """Create a metadata-schema tag or raise if it already exists."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.create(
            context, session, namespace_name, tag_dict)


def metadef_tag_create_tags(context, namespace_name, tag_list,
                            can_append=False):
    """Create a metadata-schema tag or raise if it already exists."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.create_tags(
            context, session, namespace_name, tag_list, can_append)


@utils.no_4byte_params
def metadef_tag_update(context, namespace_name, id, tag_dict):
    """Update an tag or raise if it does not exist or not visible."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.update(
            context, session, namespace_name, id, tag_dict)


def metadef_tag_delete(context, namespace_name, name):
    """Delete an tag or raise if namespace or tag doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.delete(
            context, session, namespace_name, name)


def metadef_tag_delete_namespace_content(context, namespace_name):
    """Delete an tag or raise if namespace or tag doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.delete_by_namespace_name(
            context, session, namespace_name)


def metadef_tag_count(context, namespace_name):
    """Get count of tags for a namespace, raise if ns doesn't exist."""
    session = get_session()
    with session.begin():
        return metadef_tag_api.count(context, session, namespace_name)


def _cached_image_format(cached_image):
    """Format a cached image for consumption outside of this module"""
    image_dict = {
        'id': cached_image['id'],
        'image_id': cached_image['image_id'],
        'last_accessed': cached_image['last_accessed'].timestamp(),
        'last_modified': cached_image['last_modified'].timestamp(),
        'size': cached_image['size'],
        'hits': cached_image['hits'],
        'checksum': cached_image['checksum']
    }

    return image_dict


def node_reference_get_by_url(context, node_reference_url):
    """Get a node reference by node reference url"""
    session = get_session()
    with session.begin():
        try:
            query = session.query(models.NodeReference)
            query = query.filter_by(node_reference_url=node_reference_url)
            return query.one()
        except sa_orm.exc.NoResultFound:
            msg = _("The node reference %s"
                    " was not found." % node_reference_url)
            LOG.debug(msg)
            raise exception.NotFound(msg)


@utils.no_4byte_params
def node_reference_create(context, node_reference_url):
    """Create a node_reference  or raise if it already exists."""
    session = get_session()
    values = {'node_reference_url': node_reference_url}

    with session.begin():
        node_reference = models.NodeReference()
        node_reference.update(values.copy())
        try:
            node_reference.save(session=session)
        except db_exception.DBDuplicateEntry:
            raise exception.Duplicate()

    return node_reference


def get_hit_count(context, image_id, node_reference_url):
    session = get_session()
    node_id = models.NodeReference.node_reference_id
    filters = [
        models.CachedImages.image_id == image_id,
        models.NodeReference.node_reference_url == node_reference_url,
    ]
    with session.begin():
        try:
            query = session.query(
                models.CachedImages.hits).join(
                models.NodeReference,
                node_id == models.CachedImages.node_reference_id,
                isouter=True).filter(sa_sql.and_(*filters))
            return query.one()[0]
        except sa_orm.exc.NoResultFound:
            msg = _("Referenced %s is not cached on"
                    " %s." % (image_id, node_reference_url))
            LOG.debug(msg)
            # NOTE(abhishekk): Since image is not cached yet, assuming
            # hit count as 0
            return 0


def get_cached_images(context, node_reference_url):
    node_id = models.NodeReference.node_reference_id
    session = get_session()
    with session.begin():
        query = session.query(
            models.CachedImages).join(
            models.NodeReference,
            node_id == models.CachedImages.node_reference_id,
            isouter=True).filter(
            models.NodeReference.node_reference_url == node_reference_url)

        cached_images = []
        for image in query.all():
            cached_images.append(_cached_image_format(image))
        return cached_images


@utils.no_4byte_params
def delete_all_cached_images(context, node_reference_url):
    session = get_session()
    with session.begin():
        node_id = session.query(models.NodeReference.node_reference_id).filter(
            models.NodeReference.node_reference_url == node_reference_url
        ).scalar_subquery()

        query = session.query(models.CachedImages)
        query = query.filter_by(node_reference_id=node_id)

        query.delete(synchronize_session=False)


def delete_cached_image(context, image_id, node_reference_url):
    session = get_session()
    with session.begin():
        node_id = session.query(models.NodeReference.node_reference_id).filter(
            models.NodeReference.node_reference_url == node_reference_url
        ).scalar_subquery()

        query = session.query(models.CachedImages)
        query = query.filter(
            models.CachedImages.image_id == image_id)
        query = query.filter_by(node_reference_id=node_id)

        query.delete(synchronize_session=False)


def get_least_recently_accessed(context, node_reference_url):
    node_id = models.NodeReference.node_reference_id
    session = get_session()
    with session.begin():
        query = session.query(
            models.CachedImages.image_id).join(
            models.NodeReference,
            node_id == models.CachedImages.node_reference_id,
            isouter=True).filter(
            models.NodeReference.node_reference_url == node_reference_url)
        query = query.order_by(models.CachedImages.last_accessed)
        try:
            image_id = query.first()[0]
        except TypeError:
            # There are no more cached images
            return None

    return image_id


def is_image_cached_for_node(context, node_reference_url, image_id):
    node_id = models.NodeReference.node_reference_id
    filters = [
        models.CachedImages.image_id == image_id,
        models.NodeReference.node_reference_url == node_reference_url,
    ]
    session = get_session()
    with session.begin():
        try:
            query = session.query(
                models.CachedImages.id).join(
                models.NodeReference,
                node_id == models.CachedImages.node_reference_id,
                isouter=True).filter(sa_sql.and_(*filters))
            if query.one()[0]:
                return True
        except sa_orm.exc.NoResultFound:
            msg = _("Referenced %s is not cached on"
                    " %s." % (image_id, node_reference_url))
            LOG.debug(msg)
            return False


@utils.no_4byte_params
def insert_cache_details(context, node_reference_url, image_id,
                         filesize, checksum=None, last_accessed=None,
                         last_modified=None, hits=None):
    node_reference = node_reference_get_by_url(context, node_reference_url)
    session = get_session()
    accessed = last_accessed or timeutils.utcnow()
    modified = last_modified or timeutils.utcnow()

    values = {
        'image_id': image_id,
        'size': filesize,
        'last_accessed': accessed,
        'last_modified': modified,
        'hits': hits or 0,
        'checksum': checksum,
        'node_reference_id': node_reference['node_reference_id']
    }

    with session.begin():
        cached_image = models.CachedImages()
        cached_image.update(values.copy())
        try:
            cached_image.save(session=session)
        except db_exception.DBDuplicateEntry:
            msg = _("Cache entry for %s for %s"
                    " already exists." % (image_id, node_reference_url))
            LOG.debug(msg)


@utils.no_4byte_params
def update_hit_count(context, image_id, node_reference_url):
    session = get_session()
    last_accessed = timeutils.utcnow()

    with session.begin():
        node_id = session.query(models.NodeReference.node_reference_id).filter(
            models.NodeReference.node_reference_url == node_reference_url
        ).scalar_subquery()

        query = session.query(models.CachedImages)
        query = query.filter(
            models.CachedImages.image_id == image_id)
        query = query.filter_by(node_reference_id=node_id)

        query.update({
            'hits': models.CachedImages.hits + 1,
            'last_accessed': last_accessed
        }, synchronize_session='fetch')
