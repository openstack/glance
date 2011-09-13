# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack LLC.
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

from sqlalchemy import asc, create_engine, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import exc
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import or_, and_

from glance.common import config
from glance.common import exception
from glance.common import utils
from glance.registry.db import models

_ENGINE = None
_MAKER = None
BASE = models.BASE
logger = None

# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size',
                                      'disk_format', 'container_format',
                                      'is_public', 'location', 'checksum',
                                      'owner'])

CONTAINER_FORMATS = ['ami', 'ari', 'aki', 'bare', 'ovf']
DISK_FORMATS = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2', 'vdi',
               'iso']
STATUSES = ['active', 'saving', 'queued', 'killed', 'pending_delete',
            'deleted']


def configure_db(options):
    """
    Establish the database, create an engine if needed, and
    register the models.

    :param options: Mapping of configuration options
    """
    global _ENGINE
    global logger
    if not _ENGINE:
        debug = config.get_option(
            options, 'debug', type='bool', default=False)
        verbose = config.get_option(
            options, 'verbose', type='bool', default=False)
        timeout = config.get_option(
            options, 'sql_idle_timeout', type='int', default=3600)
        _ENGINE = create_engine(options['sql_connection'],
                                pool_recycle=timeout)
        logger = logging.getLogger('sqlalchemy.engine')
        if debug:
            logger.setLevel(logging.DEBUG)
        elif verbose:
            logger.setLevel(logging.INFO)

        models.register_models(_ENGINE)


def check_mutate_authorization(context, image_ref):
    if not context.is_image_mutable(image_ref):
        logger.info(_("Attempted to modify image user did not own."))
        msg = _("You do not own this image")
        raise exception.NotAuthorized(msg)


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session"""
    global _MAKER, _ENGINE
    if not _MAKER:
        assert _ENGINE
        _MAKER = sessionmaker(bind=_ENGINE,
                              autocommit=autocommit,
                              expire_on_commit=expire_on_commit)
    return _MAKER()


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


def image_get(context, image_id, session=None):
    """Get an image or raise if it does not exist."""
    session = session or get_session()
    try:
        #NOTE(bcwaldon): this is to prevent false matches when mysql compares
        # an integer to a string that begins with that integer
        image_id = int(image_id)
    except (TypeError, ValueError):
        raise exception.NotFound("No image found")

    try:
        query = session.query(models.Image).\
                        options(joinedload(models.Image.properties)).\
                        options(joinedload(models.Image.members)).\
                        filter_by(id=image_id)

        if not can_show_deleted(context):
            query = query.filter_by(deleted=False)

        image = query.one()
    except exc.NoResultFound:
        raise exception.NotFound("No image found with ID %s" % image_id)

    # Make sure they can look at it
    if not context.is_image_visible(image):
        raise exception.NotAuthorized("Image not visible to you")

    return image


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
                   options(joinedload(models.Image.members)).\
                   filter(models.Image.status != 'killed')

    if not can_show_deleted(context) or 'deleted' not in filters:
        query = query.filter_by(deleted=False)
    else:
        query = query.filter_by(deleted=filters['deleted'])

    if 'deleted' in filters:
        del filters['deleted']

    sort_dir_func = {
        'asc': asc,
        'desc': desc,
    }[sort_dir]

    sort_key_attr = getattr(models.Image, sort_key)

    query = query.order_by(sort_dir_func(sort_key_attr)).\
                  order_by(sort_dir_func(models.Image.id))

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

    for (k, v) in filters.pop('properties', {}).items():
        query = query.filter(models.Image.properties.any(name=k, value=v))

    for (k, v) in filters.items():
        if v is not None:
            query = query.filter(getattr(models.Image, k) == v)

    if marker != None:
        # images returned should be created before the image defined by marker
        marker_image = image_get(context, marker)
        marker_value = getattr(marker_image, sort_key)
        if sort_dir == 'desc':
            query = query.filter(
                or_(sort_key_attr < marker_value,
                    and_(sort_key_attr == marker_value,
                         models.Image.id < marker)))
        else:
            query = query.filter(
                or_(sort_key_attr > marker_value,
                    and_(sort_key_attr == marker_value,
                         models.Image.id > marker)))

    if limit != None:
        query = query.limit(limit)

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

    if disk_format and disk_format not in DISK_FORMATS:
        msg = "Invalid disk format '%s' for image." % disk_format
        raise exception.Invalid(msg)

    if container_format and container_format not in CONTAINER_FORMATS:
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

            values['is_public'] = bool(values.get('is_public', False))
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
        raise exception.NotAuthorized("Image not visible to you")

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

    sort_dir_func = {
        'asc': asc,
        'desc': desc,
    }[sort_dir]

    sort_key_attr = getattr(models.ImageMember, sort_key)

    query = query.order_by(sort_dir_func(sort_key_attr)).\
                  order_by(sort_dir_func(models.ImageMember.id))

    if marker != None:
        # memberships returned should be created before the membership
        # defined by marker
        marker_membership = image_member_get(context, marker)
        marker_value = getattr(marker_membership, sort_key)
        if sort_dir == 'desc':
            query = query.filter(
                or_(sort_key_attr < marker_value,
                    and_(sort_key_attr == marker_value,
                         models.ImageMember.id < marker)))
        else:
            query = query.filter(
                or_(sort_key_attr > marker_value,
                    and_(sort_key_attr == marker_value,
                         models.ImageMember.id > marker)))

    if limit != None:
        query = query.limit(limit)

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
