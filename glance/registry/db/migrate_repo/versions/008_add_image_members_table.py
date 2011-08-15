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

from glance.registry.db.migrate_repo.schema import (
    Boolean, DateTime, BigInteger, Integer, String, Text,
    create_tables, drop_tables, from_migration_import)


def get_images_table(meta):
    """
    No changes to the images table from 007...
    """
    (get_images_table,) = from_migration_import(
        '007_add_owner', ['get_images_table'])

    images = get_images_table(meta)
    return images


def get_image_properties_table(meta):
    """
    No changes to the image properties table from 007...
    """
    (get_image_properties_table,) = from_migration_import(
        '007_add_owner', ['get_image_properties_table'])

    image_properties = get_image_properties_table(meta)
    return image_properties


def get_image_members_table(meta):
    images = get_images_table(meta)

    image_members = Table('image_members', meta,
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('image_id', Integer(), ForeignKey('images.id'), nullable=False,
               index=True),
        Column('member', String(255), nullable=False),
        Column('can_share', Boolean(), nullable=False, default=False),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        Column('deleted_at', DateTime()),
        Column('deleted', Boolean(), nullable=False, default=False,
               index=True),
        UniqueConstraint('image_id', 'member'),
        mysql_engine='InnoDB',
        useexisting=True)

    Index('ix_image_members_image_id_member', image_members.c.image_id,
          image_members.c.member)

    return image_members


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [get_image_members_table(meta)]
    create_tables(tables)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [get_image_members_table(meta)]
    drop_tables(tables)
