# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

from migrate.changeset import *
from sqlalchemy import *
from sqlalchemy.sql import and_, not_

from glance.registry.db.migrate_repo.schema import (
    Boolean, DateTime, Integer, String, Text, from_migration_import)


def get_images_table(meta):
    """
    No changes to the image properties table from 002...
    """
    (get_images_table,) = from_migration_import(
        '004_add_checksum', ['get_images_table'])

    images = get_images_table(meta)
    return images


def get_image_properties_table(meta):
    """
    Returns the Table object for the image_properties table that
    corresponds to the image_properties table definition of this version.
    """
    (get_images_table,) = from_migration_import(
        '004_add_checksum', ['get_images_table'])

    images = get_images_table(meta)

    image_properties = Table('image_properties', meta,
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('image_id', Integer(), ForeignKey('images.id'), nullable=False,
               index=True),
        Column('name', String(255), nullable=False),
        Column('value', Text()),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        Column('deleted_at', DateTime()),
        Column('deleted', Boolean(), nullable=False, default=False,
               index=True),
        UniqueConstraint('image_id', 'name'),
        mysql_engine='InnoDB',
        useexisting=True)

    return image_properties


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    (get_image_properties_table,) = from_migration_import(
        '004_add_checksum', ['get_image_properties_table'])
    image_properties = get_image_properties_table(meta)

    index = Index('ix_image_properties_image_id_get',
                  image_properties.c.image_id,
          image_properties.c.key)
    index.rename('ix_image_properties_image_id_name')

    image_properties = get_image_properties_table(meta)
    image_properties.columns['key'].alter(name="name")


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    image_properties = get_image_properties_table(meta)

    index = Index('ix_image_properties_image_id_name',
                  image_properties.c.image_id,
          image_properties.c.name)
    index.rename('ix_image_properties_image_id_key')

    image_properties.columns['name'].alter(name="key")
