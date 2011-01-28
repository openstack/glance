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

from sqlalchemy.orm import joinedload

from glance.common import exception
from glance.common import utils
from glance.common.db.sqlalchemy.session import get_session
from glance.registry.db import models


# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'type', 'status', 'size',
                                      'is_public', 'location'])

###################


def image_create(context, values):
    """Create an image from the values dictionary."""
    return _image_update(context, values, None)


def image_update(context, image_id, values):
    """Set the given properties on an image and update it.

    Raises NotFound if image does not exist.

    """
    return _image_update(context, values, image_id)


def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    session = get_session()
    with session.begin():
        image_ref = image_get(context, image_id, session=session)
        image_ref.delete(session=session)


def image_get(context, image_id, session=None):
    """Get an image or raise if it does not exist."""
    session = session or get_session()
    try:
        return session.query(models.Image).\
                       options(joinedload(models.Image.properties)).\
                       filter_by(deleted=_deleted(context)).\
                       filter_by(id=image_id).\
                       one()
    except exc.NoResultFound:
        new_exc = exception.NotFound("No model for id %s" % image_id)
        raise new_exc.__class__, new_exc, sys.exc_info()[2]


def image_get_all_public(context, public=True):
    """Get all public images."""
    session = get_session()
    return session.query(models.Image).\
                   options(joinedload(models.Image.properties)).\
                   filter_by(deleted=_deleted(context)).\
                   filter_by(is_public=public).\
                   all()


def _drop_protected_attrs(model_class, values):
    """Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


def _image_update(context, values, image_id):
    """Used internally by image_create and image_update

    :param context: Request context
    :param values: A dict of attributes to set
    :param image_id: If None, create the image, otherwise, find and update it
    """
    session = get_session()
    with session.begin():
        _drop_protected_attrs(models.Image, values)

        if 'size' in values:
            values['size'] = int(values['size'])

        values['is_public'] = bool(values.get('is_public', False))
        properties = values.pop('properties', {})

        if image_id:
            image_ref = image_get(context, image_id, session=session)
        else:
            image_ref = models.Image()

        image_ref.update(values)
        image_ref.save(session=session)

        _set_properties_for_image(context, image_ref, properties, session)

    return image_get(context, image_ref.id)


def _set_properties_for_image(context, image_ref, properties, session=None):
    """
    Create or update a set of image_properties for a given image

    :param context: Request context
    :param image_ref: An Image object
    :param properties: A dict of properties to set
    :param session: A SQLAlchemy session to use (if present)
    """
    orig_properties = {}
    for prop_ref in image_ref.properties:
        orig_properties[prop_ref.key] = prop_ref

    for key, value in properties.iteritems():
        prop_values = {'image_id': image_ref.id,
                       'key': key,
                       'value': value}
        if key in orig_properties:
            prop_ref = orig_properties[key]
            image_property_update(context, prop_ref, prop_values,
                                  session=session)
        else:
            image_property_create(context, prop_values, session=session)


def image_property_create(context, values, session=None):
    """Create an ImageProperty object"""
    prop_ref = models.ImageProperty()
    return _image_property_update(context, prop_ref, values, session=session)


def image_property_update(context, prop_ref, values, session=None):
    """Update an ImageProperty object"""
    return _image_property_update(context, prop_ref, values, session=session)


def _image_property_update(context, prop_ref, values, session=None):
    """Used internally by image_property_create and image_property_update
    """
    _drop_protected_attrs(models.ImageProperty, values)
    prop_ref.update(values)
    prop_ref.save(session=session)
    return prop_ref


# pylint: disable-msg=C0111
def _deleted(context):
    """Calculates whether to include deleted objects based on context.

    Currently just looks for a flag called deleted in the context dict.
    """
    if not hasattr(context, 'get'):
        return False
    return context.get('deleted', False)
