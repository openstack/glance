# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack Foundation
# Copyright 2012 Justin Santa Barbara
# Copyright 2013 IBM Corp.
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

from oslo.config import cfg
from six.moves import xrange
import sqlalchemy
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql as sa_sql

from glance.common import exception
from glance.db.sqlalchemy import models
from glance.openstack.common.db import exception as db_exception
from glance.openstack.common.db.sqlalchemy import session
import glance.openstack.common.log as os_logging
from glance.openstack.common import timeutils


BASE = models.BASE
sa_logger = None
LOG = os_logging.getLogger(__name__)


STATUSES = ['active', 'saving', 'queued', 'killed', 'pending_delete',
            'deleted']

CONF = cfg.CONF
CONF.import_opt('debug', 'glance.openstack.common.log')
CONF.import_opt('connection', 'glance.openstack.common.db.options',
                group='database')


_FACADE = None


def _create_facade_lazily():
    global _FACADE
    if _FACADE is None:
        _FACADE = session.EngineFacade(
            CONF.database.connection,
            **dict(CONF.database.iteritems()))
    return _FACADE


def get_engine():
    facade = _create_facade_lazily()
    return facade.get_engine()


def get_session(autocommit=True, expire_on_commit=False):
    facade = _create_facade_lazily()
    return facade.get_session(autocommit=autocommit,
                              expire_on_commit=expire_on_commit)


def clear_db_env():
    """
    Unset global configuration variables for database.
    """
    global _FACADE
    _FACADE = None


def _check_mutate_authorization(context, image_ref):
    if not is_image_mutable(context, image_ref):
        LOG.info(_("Attempted to modify image user did not own."))
        msg = _("You do not own this image")
        if image_ref.is_public:
            exc_class = exception.ForbiddenPublicImage
        else:
            exc_class = exception.Forbidden

        raise exc_class(msg)


def image_create(context, values):
    """Create an image from the values dictionary."""
    return _image_update(context, values, None, purge_props=False)


def image_update(context, image_id, values, purge_props=False,
                 from_state=None):
    """
    Set the given properties on an image and update it.

    :raises NotFound if image does not exist.
    """
    return _image_update(context, values, image_id, purge_props,
                         from_state=from_state)


def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    session = get_session()
    with session.begin():
        image_ref = _image_get(context, image_id, session=session)

        # Perform authorization check
        _check_mutate_authorization(context, image_ref)

        image_ref.delete(session=session)
        delete_time = image_ref.deleted_at

        _image_locations_delete_all(context, image_ref.id, delete_time,
                                    session)

        _image_property_delete_all(context, image_id, delete_time, session)

        _image_member_delete_all(context, image_id, delete_time, session)

        _image_tag_delete_all(context, image_id, delete_time, session)

    return _normalize_locations(image_ref)


def _normalize_locations(image):
    undeleted_locations = filter(lambda x: not x.deleted, image['locations'])
    image['locations'] = [{'url': loc['value'],
                           'metadata': loc['meta_data']}
                          for loc in undeleted_locations]
    return image


def image_get(context, image_id, session=None, force_show_deleted=False):
    image = _image_get(context, image_id, session=session,
                       force_show_deleted=force_show_deleted)
    image = _normalize_locations(image.to_dict())
    return image


def _check_image_id(image_id):
    """
    check if the given image id is valid before executing operations. For
    now, we only check its length. The original purpose of this method is
    wrapping the different behaviors between MySql and DB2 when the image id
    length is longer than the defined length in database model.
    :param image_id: The id of the image we want to check
    :return: Raise NoFound exception if given image id is invalid
    """
    if image_id and \
            len(image_id) > models.Image.id.property.columns[0].type.length:
        raise exception.NotFound()


def _image_get(context, image_id, session=None, force_show_deleted=False):
    """Get an image or raise if it does not exist."""
    _check_image_id(image_id)
    session = session or get_session()

    try:
        query = session.query(models.Image)\
                       .options(sa_orm.joinedload(models.Image.properties))\
                       .options(sa_orm.joinedload(models.Image.locations))\
                       .filter_by(id=image_id)

        # filter out deleted images if context disallows it
        if not force_show_deleted and not _can_show_deleted(context):
            query = query.filter_by(deleted=False)

        image = query.one()

    except sa_orm.exc.NoResultFound:
        msg = (_("No image found with ID %s") % image_id)
        LOG.debug(msg)
        raise exception.NotFound(msg)

    # Make sure they can look at it
    if not is_image_visible(context, image):
        msg = (_("Forbidding request, image %s not visible") % image_id)
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
    # Is admin == image visible
    if context.is_admin:
        return True

    # No owner == image visible
    if image['owner'] is None:
        return True

    # Image is_public == image visible
    if image['is_public']:
        return True

    # Perform tests based on whether we have an owner
    if context.owner is not None:
        if context.owner == image['owner']:
            return True

        # Figure out if this image is shared with that tenant
        members = image_member_find(context,
                                    image_id=image['id'],
                                    member=context.owner,
                                    status=status)
        if members:
            return True

    # Private image
    return False


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
    :return: The query with sorting/pagination added.
    """

    if 'id' not in sort_keys:
        # TODO(justinsb): If this ever gives a false-positive, check
        # the actual primary key, rather than assuming its id
        LOG.warn(_('Id not in sort_keys; is sort_keys unique?'))

    assert(not (sort_dir and sort_dirs))

    # Default the sort direction to ascending
    if sort_dirs is None and sort_dir is None:
        sort_dir = 'asc'

    # Ensure a per-column sort direction
    if sort_dirs is None:
        sort_dirs = [sort_dir for _sort_key in sort_keys]

    assert(len(sort_dirs) == len(sort_keys))

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
        for i in xrange(len(sort_keys)):
            crit_attrs = []
            for j in xrange(i):
                model_attr = getattr(model, sort_keys[j])
                default = None if isinstance(
                    model_attr.property.columns[0].type,
                    sqlalchemy.DateTime) else ''
                attr = sa_sql.expression.case([(model_attr != None,
                                              model_attr), ],
                                              else_=default)
                crit_attrs.append((attr == marker_values[j]))

            model_attr = getattr(model, sort_keys[i])
            default = None if isinstance(model_attr.property.columns[0].type,
                                         sqlalchemy.DateTime) else ''
            attr = sa_sql.expression.case([(model_attr != None,
                                          model_attr), ],
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
    #NOTE(venkatesh) make copy of the filters are to be altered in this method.
    filters = filters.copy()

    image_conditions = []
    prop_conditions = []
    tag_conditions = []

    if is_public is not None:
        image_conditions.append(models.Image.is_public == is_public)

    if 'checksum' in filters:
        checksum = filters.pop('checksum')
        image_conditions.append(models.Image.checksum == checksum)

    if 'is_public' in filters:
        key = 'is_public'
        value = filters.pop('is_public')
        prop_filters = _make_image_property_condition(key=key, value=value)
        prop_conditions.append(prop_filters)

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
            tag_filters = [models.ImageTag.deleted == False]
            tag_filters.extend([models.ImageTag.value == tag])
            tag_conditions.append(tag_filters)

    filters = dict([(k, v) for k, v in filters.items() if v is not None])

    for (k, v) in filters.items():
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

    for (k, v) in filters.items():
        value = filters.pop(k)
        if hasattr(models.Image, k):
            image_conditions.append(getattr(models.Image, k) == value)
        else:
            prop_filters = _make_image_property_condition(key=k, value=value)
            prop_conditions.append(prop_filters)

    return image_conditions, prop_conditions, tag_conditions


def _make_image_property_condition(key, value):
    prop_filters = [models.ImageProperty.deleted == False]
    prop_filters.extend([models.ImageProperty.name == key])
    prop_filters.extend([models.ImageProperty.value == value])
    return prop_filters


def _select_images_query(context, image_conditions, admin_as_user,
                         member_status, visibility):
    session = get_session()

    img_conditional_clause = sa_sql.and_(*image_conditions)

    regular_user = (not context.is_admin) or admin_as_user

    query_member = session.query(models.Image) \
        .join(models.Image.members) \
        .filter(img_conditional_clause)
    if regular_user:
        member_filters = [models.ImageMember.deleted == False]
        if context.owner is not None:
            member_filters.extend([models.ImageMember.member == context.owner])
            if member_status != 'all':
                member_filters.extend([
                    models.ImageMember.status == member_status])
        query_member = query_member.filter(sa_sql.and_(*member_filters))

    #NOTE(venkatesh) if the 'visibility' is set to 'shared', we just
    # query the image members table. No union is required.
    if visibility is not None and visibility == 'shared':
        return query_member

    query_image = session.query(models.Image)\
        .filter(img_conditional_clause)
    if regular_user:
        query_image = query_image.filter(models.Image.is_public == True)
        query_image_owner = None
        if context.owner is not None:
            query_image_owner = session.query(models.Image) \
                .filter(models.Image.owner == context.owner) \
                .filter(img_conditional_clause)
        if query_image_owner is not None:
            query = query_image.union(query_image_owner, query_member)
        else:
            query = query_image.union(query_member)
        return query
    else:
        #Admin user
        return query_image


def image_get_all(context, filters=None, marker=None, limit=None,
                  sort_key='created_at', sort_dir='desc',
                  member_status='accepted', is_public=None,
                  admin_as_user=False):
    """
    Get all images that match zero or more filters.

    :param filters: dict of filter keys and values. If a 'properties'
                    key is present, it is treated as a dict of key/value
                    filters on the image properties attribute
    :param marker: image id after which to start page
    :param limit: maximum number of images to return
    :param sort_key: image attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    :param member_status: only return shared images that have this membership
                          status
    :param is_public: If true, return only public images. If false, return
                      only private and shared images.
    :param admin_as_user: For backwards compatibility. If true, then return to
                      an admin the equivalent set of images which it would see
                      if it were a regular user
    """
    filters = filters or {}

    visibility = filters.pop('visibility', None)
    showing_deleted = 'changes-since' in filters or filters.get('deleted',
                                                                False)

    img_conditions, prop_conditions, tag_conditions = \
        _make_conditions_from_filters(filters, is_public)

    query = _select_images_query(context,
                                 img_conditions,
                                 admin_as_user,
                                 member_status,
                                 visibility)

    if visibility is not None:
        if visibility == 'public':
            query = query.filter(models.Image.is_public == True)
        elif visibility == 'private':
            query = query.filter(models.Image.is_public == False)

    if prop_conditions:
        for prop_condition in prop_conditions:
            query = query.join(models.ImageProperty, aliased=True)\
                .filter(sa_sql.and_(*prop_condition))

    if tag_conditions:
        for tag_condition in tag_conditions:
            query = query.join(models.ImageTag, aliased=True)\
                .filter(sa_sql.and_(*tag_condition))

    marker_image = None
    if marker is not None:
        marker_image = _image_get(context,
                                  marker,
                                  force_show_deleted=showing_deleted)

    sort_keys = ['created_at', 'id']
    sort_keys.insert(0, sort_key) if sort_key not in sort_keys else sort_keys

    query = _paginate_query(query, models.Image, limit,
                            sort_keys,
                            marker=marker_image,
                            sort_dir=sort_dir)

    query = query.options(sa_orm.joinedload(models.Image.properties))\
                 .options(sa_orm.joinedload(models.Image.locations))

    return [_normalize_locations(image.to_dict()) for image in query.all()]


def _drop_protected_attrs(model_class, values):
    """
    Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


def _image_get_disk_usage_by_owner(owner, session, image_id=None):
    query = session.query(models.Image)
    query = query.filter(models.Image.owner == owner)
    if image_id is not None:
        query = query.filter(models.Image.id != image_id)
    query = query.filter(models.Image.size > 0)
    query = query.filter(~models.Image.status.in_(['killed',
                                                   'pending_delete',
                                                   'deleted']))
    images = query.all()

    total = 0
    for i in images:
        locations = [l for l in i.locations if not l['deleted']]
        total += (i.size * len(locations))
    return total


def _validate_image(values):
    """
    Validates the incoming data and raises a Invalid exception
    if anything is out of order.

    :param values: Mapping of image metadata to check
    """

    status = values.get('status')
    if not status:
        msg = "Image status is required."
        raise exception.Invalid(msg)

    if status not in STATUSES:
        msg = "Invalid image status '%s' for image." % status
        raise exception.Invalid(msg)

    return values


def _update_values(image_ref, values):
    for k in values:
        if getattr(image_ref, k) != values[k]:
            setattr(image_ref, k, values[k])


def _image_update(context, values, image_id, purge_props=False,
                  from_state=None):
    """
    Used internally by image_create and image_update

    :param context: Request context
    :param values: A dict of attributes to set
    :param image_id: If None, create the image, otherwise, find and update it
    """

    #NOTE(jbresnah) values is altered in this so a copy is needed
    values = values.copy()

    session = get_session()
    with session.begin():

        # Remove the properties passed in the values mapping. We
        # handle properties separately from base image attributes,
        # and leaving properties in the values mapping will cause
        # a SQLAlchemy model error because SQLAlchemy expects the
        # properties attribute of an Image model to be a list and
        # not a dict.
        properties = values.pop('properties', {})

        location_data = values.pop('locations', None)

        new_status = values.get('status', None)
        if image_id:
            image_ref = _image_get(context, image_id, session=session)
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

            values['is_public'] = bool(values.get('is_public', False))
            values['protected'] = bool(values.get('protected', False))
            image_ref = models.Image()

        # Need to canonicalize ownership
        if 'owner' in values and not values['owner']:
            values['owner'] = None

        if image_id:
            # Don't drop created_at if we're passing it in...
            _drop_protected_attrs(models.Image, values)
            #NOTE(iccha-sethi): updated_at must be explicitly set in case
            #                   only ImageProperty table was modifited
            values['updated_at'] = timeutils.utcnow()

        if image_id:
            query = session.query(models.Image).filter_by(id=image_id)
            if from_state:
                query = query.filter_by(status=from_state)

            if new_status:
                _validate_image(values)

            # Validate fields for Images table. This is similar to what is done
            # for the query result update except that we need to do it prior
            # in this case.
            # TODO(dosaboy): replace this with a dict comprehension once py26
            #                support is deprecated.
            keys = values.keys()
            for k in keys:
                if k not in image_ref.to_dict():
                    del values[k]
            updated = query.update(values, synchronize_session='fetch')

            if not updated:
                msg = (_('cannot transition from %(current)s to '
                         '%(next)s in update (wanted '
                         'from_state=%(from)s)') %
                       {'current': current, 'next': new_status,
                        'from': from_state})
                raise exception.Conflict(msg)

            image_ref = _image_get(context, image_id, session=session)
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

        _set_properties_for_image(context, image_ref, properties, purge_props,
                                  session)

    if location_data is not None:
        _image_locations_set(image_ref.id, location_data, session)

    return image_get(context, image_ref.id)


def _image_locations_set(image_id, locations, session):
    location_refs = session.query(models.ImageLocation)\
                           .filter_by(image_id=image_id)\
                           .filter_by(deleted=False)\
                           .all()
    for location_ref in location_refs:
        location_ref.delete(session=session)

    for location in locations:
        location_ref = models.ImageLocation(image_id=image_id,
                                            value=location['url'],
                                            meta_data=location['metadata'])
        location_ref.save()


def _image_locations_delete_all(context, image_id, delete_time=None,
                                session=None):
    """Delete all image locations for given image"""
    locs_updated_count = _image_child_entry_delete_all(models.ImageLocation,
                                                       image_id,
                                                       delete_time,
                                                       session)
    return locs_updated_count


def _set_properties_for_image(context, image_ref, properties,
                              purge_props=False, session=None):
    """
    Create or update a set of image_properties for a given image

    :param context: Request context
    :param image_ref: An Image object
    :param properties: A dict of properties to set
    :param session: A SQLAlchemy session to use (if present)
    """
    orig_properties = {}
    for prop_ref in image_ref.properties:
        orig_properties[prop_ref.name] = prop_ref

    for name, value in properties.iteritems():
        prop_values = {'image_id': image_ref.id,
                       'name': name,
                       'value': value}
        if name in orig_properties:
            prop_ref = orig_properties[name]
            _image_property_update(context, prop_ref, prop_values,
                                   session=session)
        else:
            image_property_create(context, prop_values, session=session)

    if purge_props:
        for key in orig_properties.keys():
            if key not in properties:
                prop_ref = orig_properties[key]
                image_property_delete(context, prop_ref.name,
                                      image_ref.id, session=session)


def _image_child_entry_delete_all(child_model_cls, image_id, delete_time=None,
                                  session=None):
    """Deletes all the child entries for the given image id.

    Deletes all the child entries of the given child entry ORM model class
    using the parent image's id.

    The child entry ORM model class can be one of the following:
    model.ImageLocation, model.ImageProperty, model.ImageMember and
    model.ImageTag.

    :param child_model_cls: the ORM model class.
    :param image_id: id of the image whose child entries are to be deleted.
    :param delete_time: datetime of deletion to be set.
                        If None, uses current datetime.
    :param session: A SQLAlchemy session to use (if present)

    :rtype: int
    :return: The number of child entries got soft-deleted.
    """
    session = session or get_session()

    query = session.query(child_model_cls) \
        .filter_by(image_id=image_id) \
        .filter_by(deleted=False)

    delete_time = delete_time or timeutils.utcnow()

    count = query.update({"deleted": True, "deleted_at": delete_time})
    return count


def image_property_create(context, values, session=None):
    """Create an ImageProperty object."""
    prop_ref = models.ImageProperty()
    prop = _image_property_update(context, prop_ref, values, session=session)
    return prop.to_dict()


def _image_property_update(context, prop_ref, values, session=None):
    """
    Used internally by image_property_create and image_property_update.
    """
    _drop_protected_attrs(models.ImageProperty, values)
    values["deleted"] = False
    prop_ref.update(values)
    prop_ref.save(session=session)
    return prop_ref


def image_property_delete(context, prop_ref, image_ref, session=None):
    """
    Used internally by image_property_create and image_property_update.
    """
    session = session or get_session()
    prop = session.query(models.ImageProperty).filter_by(image_id=image_ref,
                                                         name=prop_ref).one()
    prop.delete(session=session)
    return prop


def _image_property_delete_all(context, image_id, delete_time=None,
                               session=None):
    """Delete all image properties for given image"""
    props_updated_count = _image_child_entry_delete_all(models.ImageProperty,
                                                        image_id,
                                                        delete_time,
                                                        session)
    return props_updated_count


def image_member_create(context, values, session=None):
    """Create an ImageMember object."""
    memb_ref = models.ImageMember()
    _image_member_update(context, memb_ref, values, session=session)
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
        'updated_at': member_ref['updated_at']
    }


def image_member_update(context, memb_id, values):
    """Update an ImageMember object."""
    session = get_session()
    memb_ref = _image_member_get(context, memb_id, session)
    _image_member_update(context, memb_ref, values, session)
    return _image_member_format(memb_ref)


def _image_member_update(context, memb_ref, values, session=None):
    """Apply supplied dictionary of values to a Member object."""
    _drop_protected_attrs(models.ImageMember, values)
    values["deleted"] = False
    values.setdefault('can_share', False)
    memb_ref.update(values)
    memb_ref.save(session=session)
    return memb_ref


def image_member_delete(context, memb_id, session=None):
    """Delete an ImageMember object."""
    session = session or get_session()
    member_ref = _image_member_get(context, memb_id, session)
    _image_member_delete(context, member_ref, session)


def _image_member_delete(context, memb_ref, session):
    memb_ref.delete(session=session)


def _image_member_delete_all(context, image_id, delete_time=None,
                             session=None):
    """Delete all image members for given image"""
    members_updated_count = _image_child_entry_delete_all(models.ImageMember,
                                                          image_id,
                                                          delete_time,
                                                          session)
    return members_updated_count


def _image_member_get(context, memb_id, session):
    """Fetch an ImageMember entity by id."""
    query = session.query(models.ImageMember)
    query = query.filter_by(id=memb_id)
    return query.one()


def image_member_find(context, image_id=None, member=None, status=None):
    """Find all members that meet the given criteria

    :param image_id: identifier of image entity
    :param member: tenant to which membership has been granted
    """
    session = get_session()
    members = _image_member_find(context, session, image_id, member, status)
    return [_image_member_format(m) for m in members]


def _image_member_find(context, session, image_id=None,
                       member=None, status=None):
    query = session.query(models.ImageMember)
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

    query = session.query(models.ImageMember)
    query = query.filter_by(deleted=False)
    query = query.filter(models.ImageMember.image_id == str(image_id))

    return query.count()


# pylint: disable-msg=C0111
def _can_show_deleted(context):
    """
    Calculates whether to include deleted objects based on context.
    Currently just looks for a flag called deleted in the context dict.
    """
    if hasattr(context, 'show_deleted'):
        return context.show_deleted
    if not hasattr(context, 'get'):
        return False
    return context.get('deleted', False)


def image_tag_set_all(context, image_id, tags):
    session = get_session()
    existing_tags = set(image_tag_get_all(context, image_id, session))
    tags = set(tags)

    tags_to_create = tags - existing_tags
    #NOTE(bcwaldon): we call 'reversed' here to ensure the ImageTag.id fields
    # will be populated in the order required to reflect the correct ordering
    # on a subsequent call to image_tag_get_all
    for tag in reversed(list(tags_to_create)):
        image_tag_create(context, image_id, tag, session)

    tags_to_delete = existing_tags - tags
    for tag in tags_to_delete:
        image_tag_delete(context, image_id, tag, session)


def image_tag_create(context, image_id, value, session=None):
    """Create an image tag."""
    session = session or get_session()
    tag_ref = models.ImageTag(image_id=image_id, value=value)
    tag_ref.save(session=session)
    return tag_ref['value']


def image_tag_delete(context, image_id, value, session=None):
    """Delete an image tag."""
    _check_image_id(image_id)
    session = session or get_session()
    query = session.query(models.ImageTag)\
                   .filter_by(image_id=image_id)\
                   .filter_by(value=value)\
                   .filter_by(deleted=False)
    try:
        tag_ref = query.one()
    except sa_orm.exc.NoResultFound:
        raise exception.NotFound()

    tag_ref.delete(session=session)


def _image_tag_delete_all(context, image_id, delete_time=None, session=None):
    """Delete all image tags for given image"""
    tags_updated_count = _image_child_entry_delete_all(models.ImageTag,
                                                       image_id,
                                                       delete_time,
                                                       session)
    return tags_updated_count


def image_tag_get_all(context, image_id, session=None):
    """Get a list of tags for a specific image."""
    _check_image_id(image_id)
    session = session or get_session()
    tags = session.query(models.ImageTag)\
                  .filter_by(image_id=image_id)\
                  .filter_by(deleted=False)\
                  .order_by(sqlalchemy.asc(models.ImageTag.created_at))\
                  .all()
    return [tag['value'] for tag in tags]


def user_get_storage_usage(context, owner_id, image_id=None, session=None):
    _check_image_id(image_id)
    session = session or get_session()
    total_size = _image_get_disk_usage_by_owner(
        owner_id, session, image_id=image_id)
    return total_size


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


def _task_info_create(context, task_id, values, session=None):
    """Create an TaskInfo object"""
    session = session or get_session()
    task_info_ref = models.TaskInfo()
    task_info_ref.task_id = task_id
    task_info_ref.update(values)
    task_info_ref.save(session=session)
    return _task_info_format(task_info_ref)


def _task_info_update(context, task_id, values, session=None):
    """Update an TaskInfo object"""
    session = session or get_session()
    task_info_ref = _task_info_get(context, task_id, session=session)
    if task_info_ref:
        task_info_ref.update(values)
        task_info_ref.save(session=session)
    return _task_info_format(task_info_ref)


def _task_info_get(context, task_id, session=None):
    """Fetch an TaskInfo entity by task_id"""
    session = session or get_session()
    query = session.query(models.TaskInfo)
    query = query.filter_by(task_id=task_id)
    try:
        task_info_ref = query.one()
    except sa_orm.exc.NoResultFound:
        msg = (_("TaskInfo was not found for task with id %(task_id)s") %
               {'task_id': task_id})
        LOG.debug(msg)
        task_info_ref = None

    return task_info_ref


def task_create(context, values, session=None):
    """Create a task object"""

    values = values.copy()
    session = session or get_session()
    with session.begin():
        task_info_values = _pop_task_info_values(values)

        task_ref = models.Task()
        _task_update(context, task_ref, values, session=session)

        _task_info_create(context,
                          task_ref.id,
                          task_info_values,
                          session=session)

    return task_get(context, task_ref.id, session)


def _pop_task_info_values(values):
    task_info_values = {}
    for k, v in values.items():
        if k in ['input', 'result', 'message']:
            values.pop(k)
            task_info_values[k] = v

    return task_info_values


def task_update(context, task_id, values, session=None):
    """Update a task object"""

    session = session or get_session()

    with session.begin():
        task_info_values = _pop_task_info_values(values)

        task_ref = _task_get(context, task_id, session)
        _drop_protected_attrs(models.Task, values)

        values['updated_at'] = timeutils.utcnow()

        _task_update(context, task_ref, values, session)

        if task_info_values:
            _task_info_update(context,
                              task_id,
                              task_info_values,
                              session)

    return task_get(context, task_id, session)


def task_get(context, task_id, session=None, force_show_deleted=False):
    """Fetch a task entity by id"""
    task_ref = _task_get(context, task_id, session=session,
                         force_show_deleted=force_show_deleted)
    return _task_format(task_ref, task_ref.info)


def task_delete(context, task_id, session=None):
    """Delete a task"""
    session = session or get_session()
    task_ref = _task_get(context, task_id, session=session)
    task_ref.delete(session=session)
    return _task_format(task_ref, task_ref.info)


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
    :return: tasks set
    """
    filters = filters or {}

    session = get_session()
    query = session.query(models.Task)

    if not (context.is_admin or admin_as_user == True) and \
            context.owner is not None:
        query = query.filter(models.Task.owner == context.owner)

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
        marker_task = _task_get(context, marker,
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


def _task_get(context, task_id, session=None, force_show_deleted=False):
    """Fetch a task entity by id"""
    session = session or get_session()
    query = session.query(models.Task).options(
        sa_orm.joinedload(models.Task.info)
    ).filter_by(id=task_id)

    if not force_show_deleted and not _can_show_deleted(context):
        query = query.filter_by(deleted=False)
    try:
        task_ref = query.one()
    except sa_orm.exc.NoResultFound:
        msg = (_("No task found with ID %s") % task_id)
        LOG.debug(msg)
        raise exception.TaskNotFound(task_id=task_id)

    # Make sure the task is visible
    if not _is_task_visible(context, task_ref):
        msg = (_("Forbidding request, task %s is not visible") % task_id)
        LOG.debug(msg)
        raise exception.Forbidden(msg)

    return task_ref


def _task_update(context, task_ref, values, session=None):
    """Apply supplied dictionary of values to a task object."""
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
        'deleted': task_ref['deleted']
    }

    if task_info_ref:
        task_info_dict = {
            'input': task_info_ref['input'],
            'result': task_info_ref['result'],
            'message': task_info_ref['message'],
        }
        task_dict.update(task_info_dict)

    return task_dict
