# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2012 OpenStack LLC.
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

from glance.common import exception
import glance.domain
from glance.openstack.common import cfg
from glance.openstack.common import importutils

sql_connection_opt = cfg.StrOpt('sql_connection',
                                default='sqlite:///glance.sqlite',
                                secret=True,
                                metavar='CONNECTION',
                                help='A valid SQLAlchemy connection '
                                     'string for the registry database. '
                                     'Default: %(default)s')

CONF = cfg.CONF
CONF.register_opt(sql_connection_opt)


def add_cli_options():
    """
    Adds any configuration options that the db layer might have.

    :retval None
    """
    CONF.unregister_opt(sql_connection_opt)
    CONF.register_cli_opt(sql_connection_opt)


def get_api():
    return importutils.import_module(CONF.data_api)


# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])


IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size',
                                      'disk_format', 'container_format',
                                      'min_disk', 'min_ram', 'is_public',
                                      'location', 'checksum', 'owner',
                                      'protected'])


class ImageRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def get(self, image_id):
        try:
            db_api_image = dict(self.db_api.image_get(self.context, image_id))
            assert not db_api_image['deleted']
        except (exception.NotFound, exception.Forbidden, AssertionError):
            raise exception.NotFound(image_id=image_id)
        tags = self.db_api.image_tag_get_all(self.context, image_id)
        image = self._format_image_from_db(db_api_image, tags)
        return image

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        db_filters = self._translate_filters(filters)
        db_api_images = self.db_api.image_get_all(
                self.context, filters=db_filters, marker=marker, limit=limit,
                sort_key=sort_key, sort_dir=sort_dir)
        images = []
        for db_api_image in db_api_images:
            tags = self.db_api.image_tag_get_all(self.context,
                                                 db_api_image['id'])
            image = self._format_image_from_db(dict(db_api_image), tags)
            images.append(image)
        return images

    def _translate_filters(self, filters):
        db_filters = {}
        if filters is None:
            return None
        for key, value in filters.iteritems():
            if key == 'visibility':
                db_filters['is_public'] = value == 'public'
            else:
                db_filters[key] = value
        return db_filters

    def _format_image_from_db(self, db_image, db_tags):
        visibility = 'public' if db_image['is_public'] else 'private'
        properties = {}
        for prop in db_image.pop('properties'):
            # NOTE(markwash) db api requires us to filter deleted
            if not prop['deleted']:
                properties[prop['name']] = prop['value']
        return glance.domain.Image(
            image_id=db_image['id'],
            name=db_image['name'],
            status=db_image['status'],
            created_at=db_image['created_at'],
            updated_at=db_image['updated_at'],
            visibility=visibility,
            min_disk=db_image['min_disk'],
            min_ram=db_image['min_ram'],
            protected=db_image['protected'],
            location=db_image['location'],
            checksum=db_image['checksum'],
            owner=db_image['owner'],
            disk_format=db_image['disk_format'],
            container_format=db_image['container_format'],
            size=db_image['size'],
            extra_properties=properties,
            tags=db_tags
        )

    def _format_image_to_db(self, image):
        return {
            'id': image.image_id,
            'name': image.name,
            'status': image.status,
            'created_at': image.created_at,
            'min_disk': image.min_disk,
            'min_ram': image.min_ram,
            'protected': image.protected,
            'location': image.location,
            'checksum': image.checksum,
            'owner': image.owner,
            'disk_format': image.disk_format,
            'container_format': image.container_format,
            'size': image.size,
            'is_public': image.visibility == 'public',
            'properties': dict(image.extra_properties),
        }

    def add(self, image):
        image_values = self._format_image_to_db(image)
        new_values = self.db_api.image_create(self.context, image_values)
        self.db_api.image_tag_set_all(self.context,
                                      image.image_id, image.tags)
        image.created_at = new_values['created_at']
        image.updated_at = new_values['updated_at']

    def save(self, image):
        image_values = self._format_image_to_db(image)
        try:
            new_values = self.db_api.image_update(self.context,
                                                  image.image_id,
                                                  image_values,
                                                  purge_props=True)
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound(image_id=image.image_id)
        self.db_api.image_tag_set_all(self.context, image.image_id,
                                      image.tags)
        image.updated_at = new_values['updated_at']

    def remove(self, image):
        image_values = self._format_image_to_db(image)
        try:
            self.db_api.image_update(self.context, image.image_id,
                                     image_values, purge_props=True)
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound(image_id=image.image_id)
        # NOTE(markwash): don't update tags?
        new_values = self.db_api.image_destroy(self.context, image.image_id)
        image.updated_at = new_values['updated_at']
