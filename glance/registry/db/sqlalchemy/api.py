# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Implementation of SQLAlchemy backend
"""

import sys
from glance.common import db
from glance.common import exception
from glance.common import flags
from glance.common.db.sqlalchemy.session import get_session
from glance.registry.db.sqlalchemy import models
from sqlalchemy.orm import exc

#from sqlalchemy.orm import joinedload_all
# TODO(sirp): add back eager loading
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func

FLAGS = flags.FLAGS


# NOTE(vish): disabling docstring pylint because the docstrings are
#             in the interface definition
# pylint: disable-msg=C0111
def _deleted(context):
    """Calculates whether to include deleted objects based on context.

    Currently just looks for a flag called deleted in the context dict.
    """
    if not hasattr(context, 'get'):
        return False
    return context.get('deleted', False)


###################


def image_create(_context, values):
    values['size'] = int(values['size'])
    values['is_public'] = bool(values.get('is_public', False))
    properties = values.pop('properties', {})

    image_ref = models.Image()
    image_ref.update(values)
    image_ref.save()
 
    for key, value in properties.iteritems():
        prop_values = {'image_id': image_ref.id, 'key': key, 'value': value}
        image_property_create(_context, prop_values)
 
    return image_get(_context, image_ref.id)


def image_destroy(_context, image_id):
    session = get_session()
    with session.begin():
        image_ref = models.Image.find(image_id, session=session)
        image_ref.delete(session=session)


def image_get(context, image_id):
    session = get_session()
    try:
        return session.query(models.Image
                     ).options(joinedload(models.Image.properties)
                     ).filter_by(deleted=_deleted(context)
                     ).filter_by(id=image_id
                     ).one()
    except exc.NoResultFound:
        new_exc = exception.NotFound("No model for id %s" % image_id)
        raise new_exc.__class__, new_exc, sys.exc_info()[2]


def image_get_all(context):
    session = get_session()
    return session.query(models.Image
                 ).options(joinedload(models.Image.properties)
                 ).filter_by(deleted=_deleted(context)
                 ).all()


def image_get_all_public(context, public):
    session = get_session()
    return session.query(models.Image
                 ).options(joinedload(models.Image.properties)
                 ).filter_by(deleted=_deleted(context)
                 ).filter_by(is_public=public
                 ).all()


def image_get_by_str(context, str_id):
    return models.Image.find_by_str(str_id, deleted=_deleted(context))


def image_update(_context, image_id, values):
    session = get_session()
    with session.begin():
        values['size'] = int(values['size'])
        values['is_public'] = bool(values.get('is_public', False))
        properties = values.pop('properties', {})

        image_ref = models.Image.find(image_id, session=session)
        image_ref.update(values)
        image_ref.save(session=session)

        for key, value in properties.iteritems():
            prop_values = {'image_id': image_ref.id, 'key': key, 'value': value}
            image_property_create(_context, prop_values)


###################


def image_file_create(_context, values):
    image_file_ref = models.ImageFile()
    image_file_ref.update(values)
    image_file_ref.save()
    return image_file_ref


###################


def image_property_create(_context, values):
    image_property_ref = models.ImageProperty()
    image_property_ref.update(values)
    image_property_ref.save()
    return image_property_ref
