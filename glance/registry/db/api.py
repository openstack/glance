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
Defines interface for DB access
"""

from glance.common import exception
from glance.common import flags
from glance.common import utils


FLAGS = flags.FLAGS
flags.DEFINE_string('db_backend', 'sqlalchemy',
                    'The backend to use for db')


IMPL = utils.LazyPluggable(FLAGS['db_backend'],
                           sqlalchemy='glance.registry.db.sqlalchemy.api')


# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'type', 'status', 'size',
                                      'is_public', 'location'])

###################


def image_create(context, values):
    """Create an image from the values dictionary."""
    return IMPL.image_create(context, values)


def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    return IMPL.image_destroy(context, image_id)


def image_get(context, image_id):
    """Get an image or raise if it does not exist."""
    return IMPL.image_get(context, image_id)


def image_get_all(context):
    """Get all images."""
    return IMPL.image_get_all(context)


def image_get_all_public(context, public=True):
    """Get all public images."""
    return IMPL.image_get_all_public(context, public=public)


def image_get_by_str(context, str_id):
    """Get an image by string id."""
    return IMPL.image_get_by_str(context, str_id)


def image_update(context, image_id, values):
    """Set the given properties on an image and update it.

    Raises NotFound if image does not exist.

    """
    return IMPL.image_update(context, image_id, values)


###################


def image_file_create(context, values):
    """Create an image file from the values dictionary."""
    return IMPL.image_file_create(context, values)


###################


def image_property_create(context, values):
    """Create an image property from the values dictionary."""
    return IMPL.image_property_create(context, values)
