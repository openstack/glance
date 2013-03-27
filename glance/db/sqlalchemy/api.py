# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack LLC.
# Copyright 2012 Justin Santa Barbara
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

"""
Defines interface for DB access
"""

import logging
import time

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.sql

from glance.common import exception
from glance.db.sqlalchemy import migration
from glance.db.sqlalchemy import models
from glance.openstack.common import cfg
import glance.openstack.common.log as os_logging
from glance.openstack.common import timeutils


_ENGINE = None
_MAKER = None
_MAX_RETRIES = None
_RETRY_INTERVAL = None
BASE = models.BASE
sa_logger = None
LOG = os_logging.getLogger(__name__)


STATUSES = ['active', 'saving', 'queued', 'killed', 'pending_delete',
            'deleted']

db_opts = [
    cfg.IntOpt('sql_idle_timeout', default=3600),
    cfg.IntOpt('sql_max_retries', default=10),
    cfg.IntOpt('sql_retry_interval', default=1),
    cfg.BoolOpt('db_auto_create', default=False),
    ]

CONF = cfg.CONF
CONF.register_opts(db_opts)


def ping_listener(dbapi_conn, connection_rec, connection_proxy):

    """
    Ensures that MySQL connections checked out of the
    pool are alive.

    Borrowed from:
    http://groups.google.com/group/sqlalchemy/msg/a4ce563d802c929f
    """

    try:
        dbapi_conn.cursor().execute('select 1')
    except dbapi_conn.OperationalError, ex:
        if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
            msg = 'Got mysql server has gone away: %s' % ex
            LOG.warn(msg)
            raise sqlalchemy.exc.DisconnectionError(msg)
        else:
            raise


def configure_db():
    """
    Establish the database, create an engine if needed, and
    register the models.
    """
    global _ENGINE, sa_logger, _MAX_RETRIES, _RETRY_INTERVAL
    if not _ENGINE:
        sql_connection = CONF.sql_connection
        _MAX_RETRIES = CONF.sql_max_retries
        _RETRY_INTERVAL = CONF.sql_retry_interval
        connection_dict = sqlalchemy.engine.url.make_url(sql_connection)
        engine_args = {'pool_recycle': CONF.sql_idle_timeout,
                       'echo': False,
                       'convert_unicode': True
                       }

        try:
            _ENGINE = sqlalchemy.create_engine(sql_connection, **engine_args)

            if 'mysql' in connection_dict.drivername:
                sqlalchemy.event.listen(_ENGINE, 'checkout', ping_listener)

            _ENGINE.connect = wrap_db_error(_ENGINE.connect)
            _ENGINE.connect()
        except Exception, err:
            msg = _("Error configuring registry database with supplied "
                    "sql_connection '%(sql_connection)s'. "
                    "Got error:\n%(err)s") % locals()
            LOG.error(msg)
            raise

        sa_logger = logging.getLogger('sqlalchemy.engine')
        if CONF.debug:
            sa_logger.setLevel(logging.DEBUG)

        if CONF.db_auto_create:
            LOG.info('auto-creating glance registry DB')
            models.register_models(_ENGINE)
            try:
                migration.version_control()
            except exception.DatabaseMigrationError:
                # only arises when the DB exists and is under version control
                pass
        else:
            LOG.info('not auto-creating glance registry DB')


def check_mutate_authorization(context, image_ref):
    if not is_image_mutable(context, image_ref):
        LOG.info(_("Attempted to modify image user did not own."))
        msg = _("You do not own this image")
        if image_ref.is_public:
            exc_class = exception.ForbiddenPublicImage
        else:
            exc_class = exception.Forbidden

        raise exc_class(msg)


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session"""
    global _MAKER
    if not _MAKER:
        assert _ENGINE
        _MAKER = sqlalchemy.orm.sessionmaker(bind=_ENGINE,
                                             autocommit=autocommit,
                                             expire_on_commit=expire_on_commit)
    return _MAKER()


def is_db_connection_error(args):
    """Return True if error in connecting to db."""
    # NOTE(adam_g): This is currently MySQL specific and needs to be extended
    #               to support Postgres and others.
    conn_err_codes = ('2002', '2003', '2006')
    for err_code in conn_err_codes:
        if args.find(err_code) != -1:
            return True
    return False


def wrap_db_error(f):
    """Retry DB connection. Copied from nova and modified."""
    def _wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except sqlalchemy.exc.OperationalError, e:
            if not is_db_connection_error(e.args[0]):
                raise

            remaining_attempts = _MAX_RETRIES
            while True:
                LOG.warning(_('SQL connection failed. %d attempts left.'),
                                remaining_attempts)
                remaining_attempts -= 1
                time.sleep(_RETRY_INTERVAL)
                try:
                    return f(*args, **kwargs)
                except sqlalchemy.exc.OperationalError, e:
                    if (remaining_attempts == 0 or
                        not is_db_connection_error(e.args[0])):
                        raise
                except sqlalchemy.exc.DBAPIError:
                    raise
        except sqlalchemy.exc.DBAPIError:
            raise
    _wrap.func_name = f.func_name
    return _wrap


def image_create(context, values):
    """Create an image from the values dictionary."""
    return _image_update(context, values, None, False)


def image_update(context, image_id, values, purge_props=False):
    """
    Set the given properties on an image and update it.

    :raises NotFound if image does not exist.
    """
    return _image_update(context, values, image_id, purge_props)


def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    session = get_session()
    with session.begin():
        image_ref = image_get(context, image_id, session=session)

        # Perform authorization check
        check_mutate_authorization(context, image_ref)

        image_ref.delete(session=session)

        for prop_ref in image_ref.properties:
            image_property_delete(context, prop_ref, session=session)

        for memb_ref in image_member_find(context, image_id=image_id):
            image_member_delete(context, memb_ref, session=session)

        return image_ref


def image_get(context, image_id, session=None, force_show_deleted=False):
    """Get an image or raise if it does not exist."""
    session = session or get_session()

    try:
        query = session.query(models.Image).\
                options(sqlalchemy.orm.joinedload(models.Image.properties)).\
                filter_by(id=image_id)

        # filter out deleted images if context disallows it
        if not force_show_deleted and not can_show_deleted(context):
            query = query.filter_by(deleted=False)

        image = query.one()

    except sqlalchemy.orm.exc.NoResultFound:
        raise exception.NotFound("No image found with ID %s" % image_id)

    # Make sure they can look at it
    if not is_image_visible(context, image):
        raise exception.Forbidden("Image not visible to you")

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


def is_image_sharable(context, image, **kwargs):
    """Return True if the image can be shared to others in this context."""
    # Is admin == image sharable
    if context.is_admin:
        return True

    # Only allow sharing if we have an owner
    if context.owner is None:
        return False

    # If we own the image, we can share it
    if context.owner == image['owner']:
        return True

    # Let's get the membership association
    if 'membership' in kwargs:
        membership = kwargs['membership']
        if membership is None:
            # Not shared with us anyway
            return False
    else:
        members = image_member_find(context,
                                    image_id=image['id'],
                                    member=context.owner)
        if members:
            member = members[0]
        else:
            # Not shared with us anyway
            return False

    # It's the can_share attribute we're now interested in
    return member['can_share']


def is_image_visible(context, image):
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
                                    member=context.owner)
        if members:
            return not members[0]['deleted']

    # Private image
    return False


def paginate_query(query, model, limit, sort_keys, marker=None,
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

    # Add pagination
    if marker is not None:
        marker_values = []
        for sort_key in sort_keys:
            v = getattr(marker, sort_key)
            marker_values.append(v)

        # Build up an array of sort criteria as in the docstring
        criteria_list = []
        for i in xrange(0, len(sort_keys)):
            crit_attrs = []
            for j in xrange(0, i):
                model_attr = getattr(model, sort_keys[j])
                crit_attrs.append((model_attr == marker_values[j]))

            model_attr = getattr(model, sort_keys[i])
            if sort_dirs[i] == 'desc':
                crit_attrs.append((model_attr < marker_values[i]))
            elif sort_dirs[i] == 'asc':
                crit_attrs.append((model_attr > marker_values[i]))
            else:
                raise ValueError(_("Unknown sort direction, "
                                   "must be 'desc' or 'asc'"))

            criteria = sqlalchemy.sql.and_(*crit_attrs)
            criteria_list.append(criteria)

        f = sqlalchemy.sql.or_(*criteria_list)
        query = query.filter(f)

    if limit is not None:
        query = query.limit(limit)

    return query


def image_get_all(context, filters=None, marker=None, limit=None,
                  sort_key='created_at', sort_dir='desc'):
    """
    Get all images that match zero or more filters.

    :param filters: dict of filter keys and values. If a 'properties'
                    key is present, it is treated as a dict of key/value
                    filters on the image properties attribute
    :param marker: image id after which to start page
    :param limit: maximum number of images to return
    :param sort_key: image attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    """
    filters = filters or {}

    session = get_session()
    query = session.query(models.Image).\
            options(sqlalchemy.orm.joinedload(models.Image.properties))

    if 'is_public' in filters and filters['is_public'] is not None:
        the_filter = [models.Image.is_public == filters['is_public']]
        if filters['is_public'] and context.owner is not None:
            the_filter.extend([
                (models.Image.owner == context.owner),
                models.Image.members.any(member=context.owner, deleted=False)
            ])
        if len(the_filter) > 1:
            query = query.filter(sqlalchemy.sql.or_(*the_filter))
        else:
            query = query.filter(the_filter[0])
        del filters['is_public']

    showing_deleted = False
    if 'changes-since' in filters:
        # normalize timestamp to UTC, as sqlalchemy doesn't appear to
        # respect timezone offsets
        changes_since = timeutils.normalize_time(filters.pop('changes-since'))
        query = query.filter(models.Image.updated_at > changes_since)
        showing_deleted = True

    if 'deleted' in filters:
        deleted_filter = filters.pop('deleted')
        query = query.filter_by(deleted=deleted_filter)
        showing_deleted = deleted_filter
        # TODO(bcwaldon): handle this logic in registry server
        if not deleted_filter:
            query = query.filter(models.Image.status != 'killed')

    for (k, v) in filters.pop('properties', {}).items():
        query = query.filter(models.Image.properties.any(name=k,
                                                         value=v,
                                                         deleted=False))

    for (k, v) in filters.items():
        if v is not None:
            key = k
            if k.endswith('_min') or k.endswith('_max'):
                key = key[0:-4]
                try:
                    v = int(v)
                except ValueError:
                    msg = _("Unable to filter on a range "
                            "with a non-numeric value.")
                    raise exception.InvalidFilterRangeValue(msg)

            if k.endswith('_min'):
                query = query.filter(getattr(models.Image, key) >= v)
            elif k.endswith('_max'):
                query = query.filter(getattr(models.Image, key) <= v)
            elif hasattr(models.Image, key):
                query = query.filter(getattr(models.Image, key) == v)
            else:
                query = query.filter(models.Image.properties.any(name=key,
                                                                 value=v))

    marker_image = None
    if marker is not None:
        marker_image = image_get(context, marker,
                                 force_show_deleted=showing_deleted)

    query = paginate_query(query, models.Image, limit,
                           [sort_key, 'created_at', 'id'],
                           marker=marker_image,
                           sort_dir=sort_dir)

    return query.all()


def _drop_protected_attrs(model_class, values):
    """
    Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


def validate_image(values):
    """
    Validates the incoming data and raises a Invalid exception
    if anything is out of order.

    :param values: Mapping of image metadata to check
    """
    status = values.get('status')

    status = values.get('status', None)
    if not status:
        msg = "Image status is required."
        raise exception.Invalid(msg)

    if status not in STATUSES:
        msg = "Invalid image status '%s' for image." % status
        raise exception.Invalid(msg)

    return values


def _update_values(image_ref, values):
    for k in values.keys():
        if getattr(image_ref, k) != values[k]:
            setattr(image_ref, k, values[k])


def _image_update(context, values, image_id, purge_props=False):
    """
    Used internally by image_create and image_update

    :param context: Request context
    :param values: A dict of attributes to set
    :param image_id: If None, create the image, otherwise, find and update it
    """
    session = get_session()
    with session.begin():

        # Remove the properties passed in the values mapping. We
        # handle properties separately from base image attributes,
        # and leaving properties in the values mapping will cause
        # a SQLAlchemy model error because SQLAlchemy expects the
        # properties attribute of an Image model to be a list and
        # not a dict.
        properties = values.pop('properties', {})

        if image_id:
            image_ref = image_get(context, image_id, session=session)

            # Perform authorization check
            check_mutate_authorization(context, image_ref)
        else:
            if 'size' in values:
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
        image_ref.update(values)

        # Validate the attributes before we go any further. From my
        # investigation, the @validates decorator does not validate
        # on new records, only on existing records, which is, well,
        # idiotic.
        values = validate_image(image_ref.to_dict())
        _update_values(image_ref, values)

        try:
            image_ref.save(session=session)
        except sqlalchemy.exc.IntegrityError:
            raise exception.Duplicate("Image ID %s already exists!"
                                      % values['id'])

        _set_properties_for_image(context, image_ref, properties, purge_props,
                                  session)

    return image_get(context, image_ref.id)


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
            image_property_update(context, prop_ref, prop_values,
                                  session=session)
        else:
            image_property_create(context, prop_values, session=session)

    if purge_props:
        for key in orig_properties.keys():
            if not key in properties:
                prop_ref = orig_properties[key]
                image_property_delete(context, prop_ref, session=session)


def image_property_create(context, values, session=None):
    """Create an ImageProperty object"""
    prop_ref = models.ImageProperty()
    return _image_property_update(context, prop_ref, values, session=session)


def image_property_update(context, prop_ref, values, session=None):
    """Update an ImageProperty object"""
    return _image_property_update(context, prop_ref, values, session=session)


def _image_property_update(context, prop_ref, values, session=None):
    """
    Used internally by image_property_create and image_property_update
    """
    _drop_protected_attrs(models.ImageProperty, values)
    values["deleted"] = False
    prop_ref.update(values)
    prop_ref.save(session=session)
    return prop_ref


def image_property_delete(context, prop_ref, session=None):
    """
    Used internally by image_property_create and image_property_update
    """
    prop_ref.delete(session=session)
    return prop_ref


def image_member_create(context, values, session=None):
    """Create an ImageMember object"""
    memb_ref = models.ImageMember()
    return _image_member_update(context, memb_ref, values, session=session)


def image_member_update(context, memb_ref, values, session=None):
    """Update an ImageMember object"""
    return _image_member_update(context, memb_ref, values, session=session)


def _image_member_update(context, memb_ref, values, session=None):
    """Apply supplied dictionary of values to a Member object."""
    _drop_protected_attrs(models.ImageMember, values)
    values["deleted"] = False
    values.setdefault('can_share', False)
    memb_ref.update(values)
    memb_ref.save(session=session)
    return memb_ref


def image_member_delete(context, memb_ref, session=None):
    """Delete an ImageMember object"""
    session = session or get_session()
    memb_ref.delete(session=session)
    return memb_ref


def image_member_find(context, image_id=None, member=None, session=None,
                      show_deleted=True):
    """Find all members that meet the given criteria

    :param image_id: identifier of image entity
    :param member: tenant to which membership has been granted
    :param session: an existing sqlalchemy session to use
    :param show_deleted: set to False to override use of the context to
                         determine if deleted memberships are included
    """
    session = session or get_session()

    # Note lack of permissions check; this function is called from
    # is_image_visible(), so avoid recursive calls
    query = session.query(models.ImageMember)

    if image_id is not None:
        query = query.filter_by(image_id=image_id)
    if member is not None:
        query = query.filter_by(member=member)
    if not (show_deleted and can_show_deleted(context)):
        query = query.filter_by(deleted=False)

    return query.all()


# pylint: disable-msg=C0111
def can_show_deleted(context):
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
    for tag in tags_to_create:
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
    session = session or get_session()
    query = session.query(models.ImageTag).\
                    filter_by(image_id=image_id).\
                    filter_by(value=value).\
                    filter_by(deleted=False)
    try:
        tag_ref = query.one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise exception.NotFound()

    tag_ref.delete(session=session)


def image_tag_get_all(context, image_id, session=None):
    """Get a list of tags for a specific image."""
    session = session or get_session()
    tags = session.query(models.ImageTag).\
                   filter_by(image_id=image_id).\
                   filter_by(deleted=False).\
                   order_by(sqlalchemy.asc(models.ImageTag.created_at)).\
                   all()
    return [tag['value'] for tag in tags]
