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
from sqlalchemy import asc, create_engine, desc
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError,\
    DisconnectionError
from sqlalchemy.orm import exc
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import or_, and_

from glance.common import cfg
from glance.common import exception
from glance.common import utils
from glance.registry.db import migration
from glance.registry.db import models

_ENGINE = None
_MAKER = None
_MAX_RETRIES = None
_RETRY_INTERVAL = None
BASE = models.BASE
sa_logger = None
logger = logging.getLogger(__name__)

# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size',
                                      'disk_format', 'container_format',
                                      'min_disk', 'min_ram', 'is_public',
                                      'location', 'checksum', 'owner',
                                      'protected'])

CONTAINER_FORMATS = ['ami', 'ari', 'aki', 'bare', 'ovf']
DISK_FORMATS = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2', 'vdi',
               'iso']
STATUSES = ['active', 'saving', 'queued', 'killed', 'pending_delete',
            'deleted']

db_opts = [
    cfg.IntOpt('sql_idle_timeout', default=3600),
    cfg.StrOpt('sql_connection', default='sqlite:///glance.sqlite'),
    cfg.IntOpt('sql_max_retries', default=10),
    cfg.IntOpt('sql_retry_interval', default=1)
    ]


class MySQLPingListener(object):

    """
    Ensures that MySQL connections checked out of the
    pool are alive.

    Borrowed from:
    http://groups.google.com/group/sqlalchemy/msg/a4ce563d802c929f
    """

    def checkout(self, dbapi_con, con_record, con_proxy):
        try:
            dbapi_con.cursor().execute('select 1')
        except dbapi_con.OperationalError, ex:
            if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
                logger.warn('Got mysql server has gone away: %s', ex)
                raise DisconnectionError("Database server went away")
            else:
                raise


def configure_db(conf):
    """
    Establish the database, create an engine if needed, and
    register the models.

    :param conf: Mapping of configuration options
    """
    global _ENGINE, sa_logger, logger, _MAX_RETRIES, _RETRY_INTERVAL
    if not _ENGINE:
        conf.register_opts(db_opts)
        sql_connection = conf.sql_connection
        _MAX_RETRIES = conf.sql_max_retries
        _RETRY_INTERVAL = conf.sql_retry_interval
        connection_dict = sqlalchemy.engine.url.make_url(sql_connection)
        engine_args = {'pool_recycle': conf.sql_idle_timeout,
                       'echo': False,
                       'convert_unicode': True
                       }
        if 'mysql' in connection_dict.drivername:
            engine_args['listeners'] = [MySQLPingListener()]

        try:
            _ENGINE = create_engine(sql_connection, **engine_args)
            _ENGINE.connect = wrap_db_error(_ENGINE.connect)
            _ENGINE.connect()
        except Exception, err:
            msg = _("Error configuring registry database with supplied "
                    "sql_connection '%(sql_connection)s'. "
                    "Got error:\n%(err)s") % locals()
            logger.error(msg)
            raise

        sa_logger = logging.getLogger('sqlalchemy.engine')
        if conf.debug:
            sa_logger.setLevel(logging.DEBUG)
        elif conf.verbose:
            sa_logger.setLevel(logging.INFO)

        models.register_models(_ENGINE)
        try:
            migration.version_control(conf)
        except exception.DatabaseMigrationError:
            # only arises when the DB exists and is under version control
            pass


def check_mutate_authorization(context, image_ref):
    if not context.is_image_mutable(image_ref):
        logger.info(_("Attempted to modify image user did not own."))
        msg = _("You do not own this image")
        if image_ref.is_public:
            exc_class = exception.ForbiddenPublicImage
        else:
            exc_class = exception.Forbidden

        raise exc_class(msg)


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session"""
    global _MAKER, _ENGINE
    if not _MAKER:
        assert _ENGINE
        _MAKER = sessionmaker(bind=_ENGINE,
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
        except OperationalError, e:
            if not is_db_connection_error(e.args[0]):
                raise

            global _MAX_RETRIES
            global _RETRY_INTERVAL
            remaining_attempts = _MAX_RETRIES
            while True:
                logger.warning(_('SQL connection failed. %d attempts left.'),
                                remaining_attempts)
                remaining_attempts -= 1
                time.sleep(_RETRY_INTERVAL)
                try:
                    return f(*args, **kwargs)
                except OperationalError, e:
                    if remaining_attempts == 0 or \
                       not is_db_connection_error(e.args[0]):
                        raise
                except DBAPIError:
                    raise
        except DBAPIError:
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

        for memb_ref in image_ref.members:
            image_member_delete(context, memb_ref, session=session)


def image_get(context, image_id, session=None, force_show_deleted=False):
    """Get an image or raise if it does not exist."""
    session = session or get_session()

    try:
        query = session.query(models.Image).\
                        options(joinedload(models.Image.properties)).\
                        options(joinedload(models.Image.members)).\
                        filter_by(id=image_id)

        # filter out deleted images if context disallows it
        if not force_show_deleted and not can_show_deleted(context):
            query = query.filter_by(deleted=False)

        image = query.one()

    except exc.NoResultFound:
        raise exception.NotFound("No image found with ID %s" % image_id)

    # Make sure they can look at it
    if not context.is_image_visible(image):
        raise exception.Forbidden("Image not visible to you")

    return image


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
        # the actual primary key, rather than assuming it's id
        logger.warn(_('Id not in sort_keys; is sort_keys unique?'))

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
            'asc': asc,
            'desc': desc,
        }[current_sort_dir]

        sort_key_attr = getattr(model, current_sort_key)
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

            criteria = and_(*crit_attrs)
            criteria_list.append(criteria)

        f = or_(*criteria_list)
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
                   options(joinedload(models.Image.properties)).\
                   options(joinedload(models.Image.members))

    if 'size_min' in filters:
        query = query.filter(models.Image.size >= filters['size_min'])
        del filters['size_min']

    if 'size_max' in filters:
        query = query.filter(models.Image.size <= filters['size_max'])
        del filters['size_max']

    if 'is_public' in filters and filters['is_public'] is not None:
        the_filter = [models.Image.is_public == filters['is_public']]
        if filters['is_public'] and context.owner is not None:
            the_filter.extend([(models.Image.owner == context.owner),
                               models.Image.members.any(member=context.owner,
                                                        deleted=False)])
        if len(the_filter) > 1:
            query = query.filter(or_(*the_filter))
        else:
            query = query.filter(the_filter[0])
        del filters['is_public']

    showing_deleted = False
    if 'changes-since' in filters:
        # normalize timestamp to UTC, as sqlalchemy doesn't appear to
        # respect timezone offsets
        changes_since = utils.normalize_time(filters.pop('changes-since'))
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
        query = query.filter(models.Image.properties.any(name=k, value=v))

    for (k, v) in filters.items():
        if v is not None:
            query = query.filter(getattr(models.Image, k) == v)

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
    disk_format = values.get('disk_format')
    container_format = values.get('container_format')

    status = values.get('status', None)
    if not status:
        msg = "Image status is required."
        raise exception.Invalid(msg)

    if status not in STATUSES:
        msg = "Invalid image status '%s' for image." % status
        raise exception.Invalid(msg)

    def _required_format_absent(format, formats):
        activating = status == 'active'
        unrecognized = format not in formats
        # We don't mind having format = None when we're just registering
        # an image, but if the image is being activated, make sure that the
        # format is valid. Conversely if the format happens to be set on
        # registration, it must be one of the recognized formats.
        return ((activating and (not format or unrecognized))
                or (not activating and format and unrecognized))

    if _required_format_absent(disk_format, DISK_FORMATS):
        msg = "Invalid disk format '%s' for image." % disk_format
        raise exception.Invalid(msg)

    if _required_format_absent(container_format, CONTAINER_FORMATS):
        msg = "Invalid container format '%s' for image." % container_format
        raise exception.Invalid(msg)

    if disk_format in ('aki', 'ari', 'ami') or\
            container_format in ('aki', 'ari', 'ami'):
        if container_format != disk_format:
            msg = ("Invalid mix of disk and container formats. "
                   "When setting a disk or container format to "
                   "one of 'ami', 'ari', or 'ami', the container "
                   "and disk formats must match.")
            raise exception.Invalid(msg)

    name = values.get('name')
    if name and len(name) > 255:
        msg = _('Image name too long: %d') % len(name)
        raise exception.Invalid(msg)


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
        image_ref.update(values)

        # Validate the attributes before we go any further. From my
        # investigation, the @validates decorator does not validate
        # on new records, only on existing records, which is, well,
        # idiotic.
        validate_image(image_ref.to_dict())

        try:
            image_ref.save(session=session)
        except IntegrityError, e:
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
    prop_ref.update(dict(deleted=True))
    prop_ref.save(session=session)
    return prop_ref


def image_member_create(context, values, session=None):
    """Create an ImageMember object"""
    memb_ref = models.ImageMember()
    return _image_member_update(context, memb_ref, values, session=session)


def image_member_update(context, memb_ref, values, session=None):
    """Update an ImageMember object"""
    return _image_member_update(context, memb_ref, values, session=session)


def _image_member_update(context, memb_ref, values, session=None):
    """
    Used internally by image_member_create and image_member_update
    """
    _drop_protected_attrs(models.ImageMember, values)
    values["deleted"] = False
    values.setdefault('can_share', False)
    memb_ref.update(values)
    memb_ref.save(session=session)
    return memb_ref


def image_member_delete(context, memb_ref, session=None):
    """Delete an ImageMember object"""
    session = session or get_session()
    memb_ref.update(dict(deleted=True))
    memb_ref.save(session=session)
    return memb_ref


def image_member_get(context, member_id, session=None):
    """Get an image member or raise if it does not exist."""
    session = session or get_session()
    try:
        query = session.query(models.ImageMember).\
                        options(joinedload(models.ImageMember.image)).\
                        filter_by(id=member_id)

        if not can_show_deleted(context):
            query = query.filter_by(deleted=False)

        member = query.one()

    except exc.NoResultFound:
        raise exception.NotFound("No membership found with ID %s" % member_id)

    # Make sure they can look at it
    if not context.is_image_visible(member.image):
        raise exception.Forbidden("Image not visible to you")

    return member


def image_member_find(context, image_id, member, session=None):
    """Find a membership association between image and member."""
    session = session or get_session()
    try:
        # Note lack of permissions check; this function is called from
        # RequestContext.is_image_visible(), so avoid recursive calls
        query = session.query(models.ImageMember).\
                        options(joinedload(models.ImageMember.image)).\
                        filter_by(image_id=image_id).\
                        filter_by(member=member)

        if not can_show_deleted(context):
            query = query.filter_by(deleted=False)

        return query.one()

    except exc.NoResultFound:
        raise exception.NotFound("No membership found for image %s member %s" %
                                 (image_id, member))


def image_member_get_memberships(context, member, marker=None, limit=None,
                                 sort_key='created_at', sort_dir='desc'):
    """
    Get all image memberships for the given member.

    :param member: the member to look up memberships for
    :param marker: membership id after which to start page
    :param limit: maximum number of memberships to return
    :param sort_key: membership attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    """

    session = get_session()
    query = session.query(models.ImageMember).\
                   options(joinedload(models.ImageMember.image)).\
                   filter_by(member=member)

    if not can_show_deleted(context):
        query = query.filter_by(deleted=False)

    marker_membership = None
    if marker is not None:
        # memberships returned should be created before the membership
        # defined by marker
        marker_membership = image_member_get(context, marker)

    query = paginate_query(query, models.ImageMember, limit,
                           [sort_key, 'id'],
                           marker=marker_membership,
                           sort_dir=sort_dir)

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
