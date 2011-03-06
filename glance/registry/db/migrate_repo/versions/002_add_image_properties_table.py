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

from sqlalchemy.schema import (
    Column, ForeignKey, Index, MetaData, Table, UniqueConstraint)

from glance.registry.db.migrate_repo.schema import (
    Boolean, DateTime, Integer, String, Text, create_tables, drop_tables,
    from_migration_import)


def define_image_properties_table(meta):
    (define_images_table,) = from_migration_import(
        '001_add_images_table', ['define_images_table'])

    images = define_images_table(meta)

    image_properties = Table('image_properties', meta,
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('image_id', Integer(), ForeignKey('images.id'), nullable=False,
               index=True),
        Column('key', String(255), nullable=False),
        Column('value', Text()),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        Column('deleted_at', DateTime()),
        Column('deleted', Boolean(), nullable=False, default=False,
               index=True),
        UniqueConstraint('image_id', 'key'),
        mysql_engine='InnoDB',
        useexisting=True)

    Index('ix_image_properties_image_id_key', image_properties.c.image_id,
          image_properties.c.key)

    return image_properties


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_image_properties_table(meta)]
    create_tables(tables)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_image_properties_table(meta)]
    drop_tables(tables)
