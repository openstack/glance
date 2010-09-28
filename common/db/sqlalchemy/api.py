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

from common import db
from common import exception
from common import flags
from common.db.sqlalchemy import models
from common.db.sqlalchemy.session import get_session
from sqlalchemy import or_
#from sqlalchemy.orm import joinedload_all
# TODO(sirp): add back eager loading
#from sqlalchemy.orm import joinedload
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
    image_ref = models.Image()
    for (key, value) in values.iteritems():
        image_ref[key] = value
    image_ref.save()
    return image_ref


def image_destroy(_context, image_id):
    session = get_session()
    with session.begin():
        image_ref = models.Image.find(image_id, session=session)
        image_ref.delete(session=session)


def image_get(context, image_id):
    return models.Image.find(image_id, deleted=_deleted(context))


def image_get_all(context):
    session = get_session()
    # TODO(sirp): add back eager loading
    return session.query(models.Image
                 #).options(joinedload(models.Image.image_chunks)
                 #).options(joinedload(models.Image.image_metadata)
                 ).filter_by(deleted=_deleted(context)
                 ).all()


def image_get_by_str(context, str_id):
    return models.Image.find_by_str(str_id, deleted=_deleted(context))


def image_update(_context, image_id, values):
    session = get_session()
    with session.begin():
        image_ref = models.Image.find(image_id, session=session)
        for (key, value) in values.iteritems():
            image_ref[key] = value
        image_ref.save(session=session)


